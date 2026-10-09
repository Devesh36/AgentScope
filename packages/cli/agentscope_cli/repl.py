"""Interactive client; all telemetry and decisions come from the selected server."""

import argparse
import cmd
import getpass
import json
import os
import sys
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__

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
    prompt = "agentscope> "
    intro = (
        "AgentScope REPL · type help for commands, demo for synthetic telemetry, exit to leave.\n"
        "Connects to your existing API. Approval and execution are separate actions."
    )

    def __init__(
        self, client, dashboard="http://127.0.0.1:3000", stdout=None, wait_seconds=60
    ):
        super().__init__(stdout=stdout)
        self.client = client
        self.dashboard = server_url(dashboard)
        self.wait_seconds = wait_seconds
        self.last_investigation = None

    def write(self, value):
        print(value, file=self.stdout)

    def onecmd(self, line):
        try:
            return super().onecmd(line)
        except ClientError as exc:
            self.write(f"Error: {exc}")
        except KeyboardInterrupt:
            self.write(
                "Interrupted. Submitted server actions may still complete; check investigation status."
            )
        return False

    def emptyline(self):
        # cmd.Cmd otherwise repeats the last command, including mutations.
        return None

    def default(self, line):
        self.write("Unknown command. Type help.")

    def do_status(self, arg):
        """status: check authenticated API connectivity and selected project metrics."""
        projects = self.client.request("/api/v1/projects", scoped=False)
        self.write(f"Connected to {self.client.endpoint}; {len(projects)} projects.")
        if self.client.project:
            self.write(
                json.dumps(self.client.request("/api/v1/metrics/overview"), indent=2)
            )

    def do_projects(self, arg):
        """projects: list projects on the selected server."""
        for project in self.client.request("/api/v1/projects", scoped=False):
            self.write(f"{project['id']}  {project['name']}")

    def do_use(self, arg):
        """use PROJECT_ID: select an existing project."""
        projects = self.client.request("/api/v1/projects", scoped=False)
        if not any(p["id"] == arg.strip() for p in projects):
            raise ClientError("Project ID not found on this server.")
        self.client.project = arg.strip()
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
        """incidents: list persisted incidents in the selected project."""
        for incident in self.client.request("/api/v1/incidents")["items"]:
            self.write(f"{incident['id']}  {incident['status']}  {incident['title']}")

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
        self.write(f"Investigation {value['id']}: {value['status']}")
        report = value.get("report", {})
        for field in ("summary", "decision_summary", "recommendation"):
            if report.get(field):
                self.write(f"{field.replace('_', ' ').capitalize()}: {report[field]}")
        self.write(f"Evidence references: {len(report.get('evidence', []))}")
        for remediation in self.proposals(value):
            self.write(
                f"Proposal {remediation['id']}: {remediation['status']} · verification {remediation.get('verification', {}).get('result', 'not started')}"
            )
            self.write(
                f"Explicit controls: approve {remediation['id']} ; execute {remediation['id']}"
            )
        self.write(
            "Demo control is opt-in: policy demo on. Real agents remain recommendation-only."
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
        url = f"{self.dashboard}/dashboard"
        self.write(
            f"Dashboard: {url} · project {self.client.project or 'not selected'}"
        )
        webbrowser.open(url)

    def do_exit(self, arg):
        """exit: close the client; server data and background work are preserved."""
        return True

    do_quit = do_exit

    def do_EOF(self, arg):
        self.write("")
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="AgentScope interactive client for an existing server."
    )
    parser.add_argument(
        "--version", action="version", version=f"AgentScope {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)
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
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0].lower() == "repl":
        args_list[0] = "repl"
    args = parser.parse_args(args_list)
    try:
        Repl(Client(args.url, args.token_file), dashboard=args.dashboard).cmdloop()
    except ClientError as exc:
        parser.exit(2, f"Error: {exc}\n")
    except KeyboardInterrupt:
        print("\nClient closed; server state preserved.")
    return 0
