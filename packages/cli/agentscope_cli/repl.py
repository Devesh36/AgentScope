"""Interactive client; all telemetry and decisions come from the selected server."""

import argparse
import cmd
import difflib
import getpass
import json
import os
import shlex
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__
from .chat import PROVIDERS, ChatError, Conversation, Models, Parser, arguments, wizard
from .terminal import Terminal, plain

SCENARIOS = (
    "tool_loop",
    "token_budget",
    "tool_failure",
    "stalled",
    "unexpected_workflow",
    "healthy",
)


class ClientError(Exception):
    """Safe client-facing failure; never includes credentials or response bodies."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward privileged credentials to another endpoint.
        return None


def server_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ClientError(
            "Use an http(s) server origin without credentials, path, query or fragment."
        )
    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise ClientError("Use HTTPS for servers outside loopback.")
    return value.rstrip("/")


class Client:
    def __init__(self, endpoint, token_file=None, timeout=10):
        self.endpoint = server_url(endpoint)
        self.token_file = token_file
        self.timeout = timeout
        self.project = None
        self._token = None
        self.opener = build_opener(NoRedirect())

    def token(self):
        if self._token is None:
            if self.token_file:
                try:
                    self._token = Path(self.token_file).read_text().strip()
                except OSError as exc:
                    raise ClientError("Cannot read admin token file.") from exc
            else:
                self._token = os.environ.get("AGENTSCOPE_ADMIN_TOKEN", "").strip()
                if not self._token:
                    if not sys.stdin.isatty():
                        raise ClientError(
                            "Set AGENTSCOPE_ADMIN_TOKEN_FILE or AGENTSCOPE_ADMIN_TOKEN before connecting."
                        )
                    self._token = getpass.getpass(
                        "Server admin token (hidden): "
                    ).strip()
            if not self._token or "\n" in self._token or "\r" in self._token:
                self._token = None
                raise ClientError("A nonempty single-line admin token is required.")
        return self._token

    def request(self, path, method="GET", body=None, scoped=True):
        if scoped and not self.project:
            raise ClientError(
                "Select a project with 'use ID', or create an isolated demo with 'demo'."
            )
        headers = {
            "Authorization": f"Bearer {self.token()}",
            "Accept": "application/json",
        }
        if scoped:
            headers["X-Project-ID"] = self.project
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        try:
            with self.opener.open(
                Request(
                    self.endpoint + path, data=data, headers=headers, method=method
                ),
                timeout=self.timeout,
            ) as response:
                return json.load(response)
        except HTTPError as exc:
            messages = {
                401: "Authentication failed. Check the server admin token.",
                403: "This operation is not authorized.",
                404: "The record or API endpoint was not found.",
                409: "Operation rejected. Check proposal approval, demo control policy and record state.",
                422: "The server rejected the request parameters.",
            }
            raise ClientError(
                messages.get(
                    exc.code,
                    f"Server returned HTTP {exc.code}. No demo data was substituted.",
                )
            ) from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise ClientError(
                "Server request failed. Check connectivity and API readiness; no demo data was substituted."
            ) from exc


class Repl(cmd.Cmd):
    intro = None

    def __init__(
        self, client, dashboard="http://127.0.0.1:3000", stdout=None, wait_seconds=60
    ):
        super().__init__(stdout=stdout)
        self.client = client
        self.dashboard = server_url(dashboard)
        self.wait_seconds = wait_seconds
        self.last_investigation = None
        self.watch_session = None
        self.watch_stop = None
        self.watch_thread = None
        self.watch_lock = None
        self.project_name = None
        self.terminal = Terminal(self.stdout)
        self.models = Models()
        self.conversation = Conversation(self.models)
        self.chat_context = False
        self.command_only = False

    @property
    def prompt(self):
        context = self.project_name or (
            self.client.project[:8] if self.client.project else "ready"
        )
        if self.watch_session:
            context += " | watch"
        context = plain(context)[:40]
        return self.terminal.style(f"agentscope [{context}] > ", prompt=True)

    def preloop(self):
        self.terminal.banner(__version__, str(Path.cwd()), self.client.endpoint)
        self.terminal.text("Local monitoring: type watch to start your local dashboard.")
        self.terminal.text(
            "No chat model or provider key is required to launch monitoring.", "muted"
        )
        try:
            name, profile = self.models.active()
            self.terminal.text(
                f"Chat model: {name} · {profile['model']}. Type a question, or model check to test the connection."
            )
        except ChatError as exc:
            # Chat setup is explicit so provider prompts never block local commands.
            self.terminal.text(f"Optional assistant chat: {exc}", "muted")

    def write(self, value):
        for line in str(value).split("\n"):
            print(plain(line), file=self.stdout)

    def onecmd(self, line):
        # Slash commands are aliases for the same handlers, including safeguards.
        self.command_only = line.lstrip().startswith("/")
        line = line.lstrip().removeprefix("/")
        try:
            return super().onecmd(line)
        except (ClientError, ChatError) as exc:
            self.terminal.text(f"Error: {exc}", "error")
        except EOFError:
            self.terminal.text("Setup cancelled. Run configure when ready.", "muted")
        except OSError:
            self.terminal.text(
                "Error: A local file or process could not be accessed. Check permissions and retry.",
                "error",
            )
        except KeyboardInterrupt:
            monitoring = (
                " Local monitoring remains active." if self.watch_session else ""
            )
            self.terminal.text(
                f"Interrupted.{monitoring} Submitted server actions may still complete. Use status or investigation to inspect them.",
                "muted",
            )
        finally:
            self.command_only = False
        return False

    def emptyline(self):
        # cmd.Cmd otherwise repeats the last command, including mutations.
        return None

    def default(self, line):
        command = line.split()[0] if line.split() else ""
        candidates = self.completenames(command)
        if not candidates:
            candidates = difflib.get_close_matches(command, self.completenames(""), n=1)
        if not self.command_only and not (
            len(line.split()) == 1
            and candidates
            and command.lower() not in ("hi", "hello", "hey")
        ):
            self.do_chat(line)
            return
        hint = f" Did you mean {candidates[0]}?" if candidates else ""
        self.terminal.text(
            f"Unknown command: {command}.{hint} Type help to browse commands.", "error"
        )

    def completenames(self, text, *ignored):
        prefix = "/" if text.startswith("/") else ""
        return [prefix + name for name in super().completenames(text.removeprefix("/"))]

    def do_help(self, arg):
        """help [COMMAND]: browse grouped commands or show detailed usage."""
        name = arg.strip().removeprefix("/")
        if name:
            handler = getattr(self, f"do_{name}", None)
            if not handler or not handler.__doc__:
                self.terminal.text(f"No help for {name}. Type help to browse commands.")
                return
            self.terminal.heading(name)
            self.terminal.text(handler.__doc__)
            if name in ("watch", "monitor"):
                self.terminal.text(
                    "Examples: watch . --no-open | watch -- python app.py | watch -- npm start"
                )
            elif name == "run":
                self.terminal.text("Examples: run -- python app.py | run -- npm start")
            return
        # Help is deliberately local: browsing commands never requests credentials.
        groups = [
            (
                "Chat with AgentScope",
                [
                    (
                        "configure [PROVIDER]",
                        "Set up your assistant model and credentials",
                    ),
                    (
                        "model [list|providers|check]",
                        "Inspect profiles and test the selected model",
                    ),
                    ("model use PROFILE", "Switch your assistant provider/model"),
                    (
                        "chat MESSAGE / ask MESSAGE",
                        "Ask a question; ordinary sentences work too",
                    ),
                    ("chat reset", "Clear the in-memory conversation"),
                    (
                        "context on|off",
                        "Choose whether chat receives project summary metrics",
                    ),
                ],
            ),
            (
                "Monitor",
                [
                    ("watch [PATH]", "Start local monitoring in the background"),
                    (
                        "run -- COMMAND",
                        "Launch an app with capture; waits until it exits",
                    ),
                    ("status [--json]", "View activity, usage, and watch health"),
                    ("stop", "Stop local services and keep your records"),
                    ("open", "Open the selected project's dashboard"),
                ],
            ),
            (
                "Explore",
                [
                    ("projects [--json]", "List workspaces"),
                    ("use PROJECT_ID", "Switch the selected workspace"),
                    ("agents [--json]", "List registered agents"),
                    ("runs [--json]", "Inspect recent executions"),
                    ("incidents [--json]", "List incidents and their IDs"),
                ],
            ),
            (
                "Investigate",
                [
                    ("investigate INCIDENT_ID", "Collect evidence and recommendations"),
                    ("investigation [ID]", "Read the latest investigation"),
                    ("demo [SCENARIO]", "Practice with labeled synthetic telemetry"),
                ],
            ),
            (
                "Demo controls",
                [
                    ("policy demo on|off", "Configure isolated synthetic control"),
                    ("approve PROPOSAL_ID", "Approve a proposal separately"),
                    ("execute PROPOSAL_ID", "Execute an approved synthetic proposal"),
                    ("verify [ID]", "Wait for observed recovery evidence"),
                ],
            ),
            (
                "Session",
                [
                    ("guide / tips", "Step-by-step monitoring workflow"),
                    ("clear", "Clear the visible terminal"),
                    ("help COMMAND", "Read command usage"),
                    ("exit / quit", "Close the REPL and its local services"),
                ],
            ),
        ]
        for title, items in groups:
            self.terminal.heading(title)
            self.terminal.pairs(items)
        self.terminal.text(
            "Slash aliases work too: /watch, /status, /help. Use --json for complete API data.",
            "muted",
        )

    do_commands = do_help

    def do_configure(self, arg):
        """configure [PROVIDER] [--name PROFILE] [--model MODEL] [--base-url URL] [--key-env VARIABLE | --key-file PATH]: configure AgentScope's chat model. With no arguments, opens hidden-key setup in an interactive terminal. API keys are never command arguments. Use model providers to see integrations."""
        if not arg.strip():
            if not sys.stdin.isatty():
                raise ChatError(
                    "Interactive setup requires a terminal. Use configure PROVIDER --model MODEL --key-env VARIABLE or --key-file PATH."
                )
            wizard(self.models, self.terminal, read=input, hidden=getpass.getpass)
        elif arg.strip() in ("--help", "-h"):
            self.do_help("configure")
            return
        else:
            parser = Parser(add_help=False)
            arguments(parser)
            try:
                options = parser.parse_args(shlex.split(arg))
            except ValueError:
                raise ChatError("Unbalanced quoting. Use help configure.") from None
            name, profile = self.models.save(options)
            self.terminal.text(
                f"Chat model configured: {name} · {profile['model']}. Use model check to verify access."
            )
        self.conversation.reset()

    def do_model(self, arg):
        """model [status|list|providers|check|use PROFILE]: view chat configuration, select a saved profile, or test the provider with a short real model call. CLI profiles use their CLI login. Configuration never prints credential values."""
        parts = arg.split()
        action = parts[0] if parts else "status"
        if action == "providers" and len(parts) == 1:
            self.terminal.heading("Chat providers")
            self.terminal.pairs(
                [
                    (
                        name,
                        f"{value[1] or 'choose a model'} · {'existing CLI login' if value[0] in ('codex', 'claude-cli') else value[3] or 'local, no key'}",
                    )
                    for name, value in PROVIDERS.items()
                ]
            )
            self.terminal.text(
                "Claude aliases Anthropic; codex uses the Codex CLI; openai-codex uses the OpenAI API. Models depend on your account or local installation."
            )
        elif action == "list" and len(parts) == 1:
            value = self.models.load()
            self.terminal.heading("Saved chat models")
            self.terminal.pairs(
                [
                    (
                        name + (" *" if value["active"] == name else ""),
                        f"{profile['provider']} · {profile['model']}",
                    )
                    for name, profile in value["profiles"].items()
                ]
            )
            if not value["profiles"]:
                self.terminal.text("No profiles yet. Run configure.")
        elif action == "use" and len(parts) == 2:
            self.models.use(parts[1])
            self.conversation.reset()
            self.terminal.text(
                f"Chat profile selected: {parts[1]}. Conversation cleared."
            )
        elif action == "status" and len(parts) <= 1:
            name, profile = self.models.active()
            try:
                self.models.credential(profile)
                readiness = "Credential or CLI available; connection not tested"
            except ChatError as exc:
                readiness = str(exc)
            self.terminal.heading("AgentScope's chat model")
            self.terminal.pairs(
                [
                    ("Profile", name),
                    ("Provider", profile["provider"]),
                    ("Model", profile["model"]),
                    ("Readiness", readiness),
                    (
                        "Project context",
                        "on: summary metrics" if self.chat_context else "off",
                    ),
                ]
            )
        elif action == "check" and len(parts) == 1:
            self.terminal.text("Testing the configured model…", "muted")
            name, model, answer = Conversation(self.models).ask(
                "Introduce yourself as AgentScope in one sentence."
            )
            self.render_answer(name, model, answer)
        else:
            raise ChatError("Use model status, list, providers, check, or use PROFILE.")

    def do_context(self, arg):
        """context on|off: opt in to sending the selected project's summary metrics to your chat provider. No prompts, trace bodies, credentials, or source files are included. Changing this clears the conversation."""
        if arg.strip() not in ("on", "off"):
            raise ChatError(
                "Use context on or context off. Project summaries are off by default."
            )
        self.chat_context = arg.strip() == "on"
        self.conversation.reset()
        self.terminal.text(
            "Project summary context enabled; it will be sent to your selected chat provider."
            if self.chat_context
            else "Project context disabled. Conversation cleared."
        )

    def render_answer(self, name, model, answer):
        self.terminal.heading("AgentScope", f"{name} · {model}")
        for line in answer.splitlines():
            self.terminal.text(line)

    def do_chat(self, arg):
        """chat MESSAGE: ask AgentScope through your configured model. Ordinary questions and ask MESSAGE also work. chat reset clears the in-memory history; chat never runs commands or modifies your project."""
        if arg.strip() == "reset":
            self.conversation.reset()
            self.terminal.text("Conversation cleared; telemetry is preserved.")
            return
        self.models.active()
        context = None
        if self.chat_context:
            if not self.client.project:
                raise ChatError(
                    "Select a project with watch or use before chatting with context; context off asks without project data."
                )
            metrics = self.client.request("/api/v1/metrics/overview")
            fields = (
                "total_runs",
                "active_runs",
                "completed_runs",
                "failed_runs",
                "llm_calls",
                "llm_errors",
                "tool_calls",
                "tool_errors",
                "input_tokens",
                "output_tokens",
                "tokens",
                "cost",
                "active_incidents",
                "grounding_evaluations",
                "unsupported_claims",
                "latency_p50",
                "latency_p95",
                "latency_p99",
                "updated_at",
            )
            context = {"window_hours": 24, **{key: metrics.get(key) for key in fields}}
        self.terminal.text("AgentScope is thinking…", "muted")
        name, model, answer = self.conversation.ask(
            arg, context=context, project=self.client.project
        )
        self.render_answer(name, model, answer)

    do_ask = do_chat

    def do_guide(self, arg):
        """guide: show a practical monitoring workflow; no server connection required."""
        self.terminal.heading("Your first session")
        self.terminal.pairs(
            [
                (
                    "1. Configure",
                    "configure, then model check; ask Who are you? to meet AgentScope",
                ),
                (
                    "2. Start",
                    "watch . --no-open (leave off --no-open to launch the browser)",
                ),
                (
                    "3. Launch",
                    "In another terminal: agentscope run -- python app.py or agentscope run -- npm start",
                ),
                ("4. Inspect", "status -> agents -> runs -> incidents -> open"),
                (
                    "5. Investigate",
                    "investigate INCIDENT_ID, then investigation to read the evidence",
                ),
                ("6. Finish", "stop keeps telemetry; exit closes this session"),
            ]
        )
        self.terminal.heading("Useful notes")
        self.terminal.text(
            "You can also start an app with watch -- python app.py, or use run -- COMMAND here for a foreground run. Ctrl+C interrupts that run and returns to the REPL."
        )
        self.terminal.text(
            "Start existing apps through watch/run to enable capture. Python OpenAI/Anthropic create calls and Node fetch-based compatible endpoints are supported. Tool boundaries need SDK instrumentation."
        )
        self.terminal.text(
            "Prompts and response bodies are excluded from automatic capture. Unsupported claims show Not evaluated until your application supplies a grounding assessment."
        )
        self.terminal.text(
            "Already have a server? projects, then use PROJECT_ID. To practice incident handling, demo creates an isolated synthetic project."
        )

    do_tips = do_guide

    def do_clear(self, arg):
        """clear: clear the visible terminal without changing the workspace or records."""
        if self.terminal.interactive and os.environ.get("TERM") != "dumb":
            self.terminal.write("\033[2J\033[H")
        else:
            self.write("Screen clearing is available in an interactive terminal.")

    def json_requested(self, arg):
        if arg.strip() not in ("", "--json"):
            raise ClientError(
                "Use --json for complete API data, or omit it for a readable summary."
            )
        return arg.strip() == "--json"

    def render_records(self, title, records, describe, empty):
        self.terminal.heading(title, f"{len(records)} records returned")
        if not records:
            self.terminal.text(empty, "muted")
        for value in records:
            name, detail = describe(value)
            self.terminal.record(name, detail, value["id"])

    def do_status(self, arg):
        """status [--json]: check connectivity and project metrics over the last 24 hours."""
        raw = self.json_requested(arg)
        projects = self.client.request("/api/v1/projects", scoped=False)
        metrics = (
            self.client.request("/api/v1/metrics/overview")
            if self.client.project
            else None
        )
        if raw:
            self.write(
                json.dumps(
                    {
                        "endpoint": self.client.endpoint,
                        "project_id": self.client.project,
                        "projects": projects,
                        "metrics": metrics,
                    },
                    indent=2,
                )
            )
            return
        self.terminal.heading("Workspace")
        self.terminal.text(
            f"Connected to {self.client.endpoint}; {len(projects)} projects."
        )
        if self.client.project:
            self.project_name = next(
                (p["name"] for p in projects if p["id"] == self.client.project), None
            )
            self.terminal.pairs(
                [
                    ("Project", self.project_name or self.client.project),
                    ("Project ID", self.client.project),
                ]
            )
            self.terminal.heading(
                "Activity", "Last 24 hours; status refreshes when you run it."
            )
            cost = metrics.get("cost")
            claims = metrics.get("unsupported_claims")
            self.terminal.pairs(
                [
                    ("Agents", metrics.get("registered_agents", 0)),
                    (
                        "Runs / active / failed",
                        f"{metrics.get('total_runs', 0)} / {metrics.get('active_runs', 0)} / {metrics.get('failed_runs', 0)}",
                    ),
                    (
                        "LLM calls / errors",
                        f"{metrics.get('llm_calls', 0)} / {metrics.get('llm_errors', 0)}",
                    ),
                    (
                        "Tokens / in / out",
                        f"{metrics.get('tokens', 0)} / {metrics.get('input_tokens', 0)} / {metrics.get('output_tokens', 0)}",
                    ),
                    (
                        "Estimated cost",
                        f"${cost:.6f}"
                        if cost is not None
                        else "Unavailable (pricing or usage incomplete)",
                    ),
                    ("Active incidents", metrics.get("active_incidents", 0)),
                    (
                        "Unsupported claims",
                        claims if claims is not None else "Not evaluated",
                    ),
                ]
            )
            for session in metrics.get("watch_sessions", []):
                self.terminal.pairs(
                    [("Watch", f"{session['repository']} / {session['status']}")]
                )
            self.terminal.text(
                "Next: runs to inspect executions; incidents to find issues; open for the dashboard.",
                "muted",
            )
        else:
            self.terminal.text(
                "Next: watch to monitor this repo, or projects then use PROJECT_ID to select a workspace.",
                "muted",
            )

    def do_projects(self, arg):
        """projects [--json]: list projects; select one with use PROJECT_ID."""
        raw = self.json_requested(arg)
        projects = self.client.request("/api/v1/projects", scoped=False)
        if raw:
            self.write(json.dumps(projects, indent=2))
            return
        self.render_records(
            "Projects",
            projects,
            lambda p: (
                p["name"],
                "Selected workspace"
                if p["id"] == self.client.project
                else "Select with use " + p["id"],
            ),
            "No projects yet. Type watch to create a local workspace, or demo for synthetic telemetry.",
        )

    def do_agents(self, arg):
        """agents [--json]: list registered agents in the selected project."""
        raw = self.json_requested(arg)
        agents = self.client.request("/api/v1/agents")
        if raw:
            self.write(json.dumps(agents, indent=2))
            return
        self.render_records(
            "Agents",
            agents,
            lambda a: (
                a["name"],
                f"{a.get('framework', 'Unknown framework')} / {'synthetic' if a.get('synthetic') else 'observed telemetry'}",
            ),
            "No registered agents. Launch your application through watch/run to begin capture.",
        )

    def do_runs(self, arg):
        """runs [--json]: list recent executions in the selected project."""
        raw = self.json_requested(arg)
        result = self.client.request("/api/v1/runs")
        if raw:
            self.write(json.dumps(result, indent=2))
            return
        self.render_records(
            "Recent runs",
            result["items"],
            lambda r: (
                r["name"],
                f"{r['status']} / {r.get('tokens', 0)} tokens / {r.get('duration_ms', 0)} ms / {'synthetic' if r.get('synthetic') else 'observed telemetry'}",
            ),
            "No executions recorded. Relaunch your app through watch/run, then use status to check capture.",
        )

    def do_use(self, arg):
        """use PROJECT_ID: select an existing project."""
        projects = self.client.request("/api/v1/projects", scoped=False)
        if not any(p["id"] == arg.strip() for p in projects):
            raise ClientError("Project ID not found on this server.")
        self.client.project = arg.strip()
        self.project_name = next(
            p["name"] for p in projects if p["id"] == self.client.project
        )
        self.last_investigation = None
        self.write(f"Selected project {self.client.project}.")

    def wait_for(self, fetch, predicate):
        deadline = time.monotonic() + self.wait_seconds
        while True:
            value = fetch()
            if predicate(value):
                return value
            if time.monotonic() >= deadline:
                raise ClientError(
                    "Timed out waiting for the server. Work remains persisted; inspect it again later."
                )
            time.sleep(0.5)

    def do_demo(self, arg):
        """demo [SCENARIO]: create a dedicated synthetic project, simulate and investigate. Never approves or executes."""
        scenario = arg.strip() or "tool_loop"
        if scenario not in SCENARIOS:
            raise ClientError("Scenarios: " + ", ".join(SCENARIOS))
        project = self.client.request(
            "/api/v1/projects",
            "POST",
            {"name": f"REPL synthetic demo {uuid.uuid4().hex[:8]}"},
            scoped=False,
        )
        self.client.project = project["id"]
        self.project_name = project["name"]
        self.last_investigation = None
        self.write(
            f"SYNTHETIC DEMO · project {project['id']} · scenario {scenario} · seed 42"
        )
        result = self.client.request(
            "/api/v1/simulations",
            "POST",
            {"scenario": scenario, "seed": 42, "include_baseline": True},
        )
        self.write(
            f"Persisted {len(result['run_ids'])} runs. Open {self.dashboard}/dashboard and select this project."
        )
        if scenario == "healthy":
            self.write(
                "Healthy scenario: no incident is expected. Use status to inspect actual metrics."
            )
            return
        run_ids = set(result["run_ids"])
        incidents = self.wait_for(
            lambda: self.client.request("/api/v1/incidents")["items"],
            lambda items: any(i["run_id"] in run_ids for i in items),
        )
        incident = next(i for i in incidents if i["run_id"] in run_ids)
        self.write(f"Incident {incident['id']}: {incident['title']}")
        self.do_investigate(incident["id"])

    def do_incidents(self, arg):
        """incidents [--json]: list incidents; investigate one with investigate INCIDENT_ID."""
        raw = self.json_requested(arg)
        result = self.client.request("/api/v1/incidents")
        if raw:
            self.write(json.dumps(result, indent=2))
            return
        self.render_records(
            "Incidents",
            result["items"],
            lambda i: (i["title"], f"{i['status']} / investigate {i['id']}"),
            "No incidents recorded in this project. Use status to check whether activity is being captured.",
        )

    def identifier(self, arg):
        value = arg.strip()
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise ClientError(
                "Supply a valid record UUID; see help for usage."
            ) from exc

    def do_investigate(self, arg):
        """investigate INCIDENT_ID: start or resume a persisted investigation."""
        incident_id = self.identifier(arg)
        inv = self.client.request(
            f"/api/v1/incidents/{incident_id}/investigate", "POST"
        )
        self.last_investigation = inv["id"]
        self.write(f"Investigation {inv['id']}; waiting for evidence collection.")
        value = self.wait_for(
            lambda: self.investigation(inv["id"]),
            lambda i: i["status"] in ("complete", "failed"),
        )
        self.show_investigation(value)

    def investigation(self, inv_id):
        return self.client.request(f"/api/v1/investigations/{self.identifier(inv_id)}")

    def show_investigation(self, value):
        self.terminal.heading("Investigation", f"{value['id']} / {value['status']}")
        report = value.get("report", {})
        for field in ("summary", "decision_summary", "recommendation"):
            if report.get(field):
                self.terminal.heading(field.replace("_", " "))
                self.terminal.text(report[field])
        self.write(f"Evidence references: {len(report.get('evidence', []))}")
        for remediation in self.proposals(value):
            self.terminal.heading("Proposal")
            self.terminal.pairs(
                [
                    ("ID", remediation["id"]),
                    ("Status", remediation["status"]),
                    (
                        "Verification",
                        remediation.get("verification", {}).get(
                            "result", "not started"
                        ),
                    ),
                ]
            )
            self.terminal.text(
                f"Explicit controls: approve {remediation['id']} ; execute {remediation['id']}"
            )
        self.terminal.text(
            "Demo control is opt-in: policy demo on. Real agents remain recommendation-only.",
            "muted",
        )

    def proposals(self, value):
        proposal = value["incident"].get("remediation")
        return [proposal] if proposal else []

    def do_investigation(self, arg):
        """investigation [INVESTIGATION_ID]: show evidence-grounded results and proposal state."""
        inv_id = arg.strip() or self.last_investigation
        if not inv_id:
            raise ClientError("Supply an investigation ID or run demo first.")
        self.show_investigation(self.investigation(inv_id))

    def do_policy(self, arg):
        """policy demo on|off: explicitly enable/disable isolated synthetic control for the selected project."""
        if arg.strip() not in ("demo on", "demo off"):
            raise ClientError("Usage: policy demo on|off")
        settings = self.client.request("/api/v1/settings")
        settings["allow_demo_control"] = arg.strip() == "demo on"
        self.client.request("/api/v1/settings", "PUT", settings)
        self.write(
            f"Isolated demo control {'enabled' if settings['allow_demo_control'] else 'disabled'}. Approval is still required."
        )

    def do_approve(self, arg):
        """approve REMEDIATION_ID: explicitly approve a proposal. Does not execute it."""
        value = self.client.request(
            f"/api/v1/remediations/{self.identifier(arg)}/approve", "POST"
        )
        self.write(
            f"Proposal {value['id']}: {value['status']}. Execution requires the separate execute command."
        )

    def do_execute(self, arg):
        """execute REMEDIATION_ID: execute an approved isolated demo proposal; recovery remains pending."""
        value = self.client.request(
            f"/api/v1/remediations/{self.identifier(arg)}/execute", "POST"
        )
        self.write(
            f"Proposal {value['id']}: {value['status']}. Recovery requires the server's observation window; use verify INVESTIGATION_ID."
        )

    def do_verify(self, arg):
        """verify [INVESTIGATION_ID]: wait for delayed persisted recovery measurements (up to 60 seconds)."""
        inv_id = arg.strip() or self.last_investigation
        if not inv_id:
            raise ClientError("Supply an investigation ID.")
        value = self.investigation(inv_id)
        proposals = self.proposals(value)
        if not proposals or not any(p.get("executed_at") for p in proposals):
            raise ClientError(
                "No executed proposal to verify. Approve and execute explicitly first."
            )
        self.write(
            "Waiting for persisted recovery measurements after the observation window…"
        )
        value = self.wait_for(
            lambda: self.investigation(inv_id),
            lambda i: (
                bool(self.proposals(i))
                and all(
                    p["status"] not in ("executing", "verifying")
                    for p in self.proposals(i)
                )
            ),
        )
        self.show_investigation(value)

    def do_open(self, arg):
        """open: open the dashboard in your browser; select the printed project ID."""
        url = f"{self.dashboard}/dashboard" + (
            f"?project={self.client.project}" if self.client.project else ""
        )
        self.write(
            f"Dashboard: {url} · project {self.client.project or 'not selected'}"
        )
        webbrowser.open(url)

    def do_watch(self, arg):
        """watch [DIRECTORY] [-- APPLICATION]: monitor a local project in the background. Use stop to finish."""
        from .watch import (
            WatchSession,
            add_watch_arguments,
            exclusive,
            validate_arguments,
        )

        if self.watch_session:
            raise ClientError(
                "A project is already being watched. Use stop before starting another session."
            )

        parser = argparse.ArgumentParser(prog="watch")
        add_watch_arguments(parser)
        try:
            arguments = shlex.split(arg)
        except ValueError:
            raise ClientError("Unbalanced quoting in watch command.") from None
        try:
            options = parser.parse_args(arguments)
        except SystemExit:
            return
        validate_arguments(options)
        if options.once:
            raise ClientError(
                "Use --once with the CLI watch command; REPL watch continues until stop."
            )
        options.interactive = True
        session = WatchSession(options, self.stdout)
        lock = exclusive(session.data / "watch.lock")
        lock.__enter__()
        self.watch_session, self.watch_lock = session, lock
        try:
            session.start()
            from .watch import private_json

            private_json(
                session.data / "session.json",
                {
                    "pid": os.getpid(),
                    "url": session.endpoint,
                    "runtime": str(session.runtime),
                    "agent_id": session.agent,
                },
            )
            session.launch()
            self.client = Client(session.endpoint, session.data / "admin-token")
            self.client.project = session.client.project
            self.project_name = session.repo.name or "project"
            self.dashboard = session.dashboard
            self.last_investigation = None
            self.watch_stop = threading.Event()
            # Capture this session's event; stop may clear the REPL attributes.
            stopped = self.watch_stop

            def keep_alive():
                while not stopped.wait(10):
                    try:
                        session.poll()
                    except ClientError as exc:
                        self.write(f"Watch: {exc}. Use stop, then watch to restart.")
                        return

            self.watch_thread = threading.Thread(
                target=keep_alive, daemon=True, name="agentscope-watch"
            )
            self.watch_thread.start()
            self.write(
                "Monitoring continues in the background. Use status, incidents, or open to inspect this project."
            )
        except BaseException:
            self.close_watch()
            raise

    do_monitor = do_watch

    def do_run(self, arg):
        """run -- COMMAND: launch an app in this REPL's watched repository, with capture enabled. Waits for exit; Ctrl+C returns to the REPL."""
        from .watch import run_existing

        if not self.watch_session:
            raise ClientError(
                "Start watch in this REPL before using run. Type guide for the workflow."
            )
        try:
            command = shlex.split(arg)
        except ValueError:
            raise ClientError("Unbalanced quoting in run command.") from None
        if len(command) < 2 or command[0] != "--":
            raise ClientError(
                "Usage: run -- COMMAND (for example, run -- python app.py)"
            )
        self.terminal.heading("Application", f"Repository: {self.watch_session.repo}")
        self.terminal.text(
            "Running in the foreground. Ctrl+C returns here; monitoring continues.",
            "muted",
        )
        result = run_existing(self.watch_session.repo, command)
        self.terminal.text(
            f"Application exited with code {result}. Next: status, runs, or open."
        )

    def close_watch(self):
        if not self.watch_session:
            return
        if self.watch_stop:
            self.watch_stop.set()
        if self.watch_thread:
            self.watch_thread.join(timeout=12)
        try:
            (self.watch_session.data / "session.json").unlink(missing_ok=True)
            self.watch_session.close()
        finally:
            self.watch_lock.__exit__(None, None, None)
            self.watch_session = self.watch_stop = self.watch_thread = (
                self.watch_lock
            ) = None

    def do_stop(self, arg):
        """stop: stop this REPL's watch services, preserving recorded telemetry."""
        if not self.watch_session:
            self.write("No local watch session is running in this REPL.")
            return
        self.close_watch()
        self.write("Watch stopped; recorded telemetry is preserved.")
        self.terminal.text(
            "Next: watch to resume this repository, or exit to finish.", "muted"
        )

    def do_exit(self, arg):
        """exit: close the REPL and its watch services; persisted telemetry is preserved."""
        self.close_watch()
        self.terminal.text("Session closed. Recorded telemetry is preserved.", "muted")
        return True

    do_quit = do_exit

    def do_EOF(self, arg):
        self.write("")
        return self.do_exit(arg)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Monitor a local project or investigate agent telemetry interactively."
    )
    parser.add_argument(
        "--version", action="version", version=f"AgentScope {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser(
        "configure", help="Configure AgentScope's conversational model before chatting."
    )
    arguments(setup)
    repl = sub.add_parser(
        "repl", help="Open the interactive client (help works offline)."
    )
    repl.add_argument(
        "--url", default=os.environ.get("AGENTSCOPE_URL", "http://127.0.0.1:8000")
    )
    repl.add_argument(
        "--dashboard",
        default=os.environ.get("AGENTSCOPE_DASHBOARD_URL", "http://127.0.0.1:3000"),
    )
    repl.add_argument(
        "--token-file", default=os.environ.get("AGENTSCOPE_ADMIN_TOKEN_FILE")
    )
    from .watch import add_watch_arguments, run_existing, watch_main

    watch = sub.add_parser(
        "watch", help="Start a local dashboard and monitor supported LLM calls."
    )
    add_watch_arguments(watch)
    run = sub.add_parser(
        "run", help="Launch an application in an existing local watch session."
    )
    run.add_argument("--repo", default=".")
    run.add_argument("application", nargs=argparse.REMAINDER)
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0].lower() == "repl":
        args_list[0] = "repl"
    args = parser.parse_args(args_list)
    try:
        if args.command == "configure":
            models = Models()
            if args.provider:
                name, profile = models.save(args)
                print(
                    f"Chat model configured: {name} · {profile['model']}. Start agentscope repl, then model check."
                )
            elif sys.stdin.isatty():
                wizard(models, Terminal(sys.stdout), read=input, hidden=getpass.getpass)
            else:
                raise ChatError(
                    "Choose a provider with agentscope configure PROVIDER --model MODEL --key-env VARIABLE."
                )
            return 0
        if args.command == "watch":
            return watch_main(args)
        if args.command == "run":
            return run_existing(args.repo, args.application)
        shell = Repl(Client(args.url, args.token_file), dashboard=args.dashboard)
        try:
            shell.cmdloop()
        finally:
            shell.close_watch()
    except (ClientError, ChatError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    except EOFError:
        parser.exit(2, "Setup cancelled. Run agentscope configure when ready.\n")
    except KeyboardInterrupt:
        print("\nClient closed; server state preserved.")
        return 130
    except OSError:
        parser.exit(
            2,
            "Error: A local process or file could not be accessed. Check permissions and prerequisites.\n",
        )
    return 0
