"""Own a loopback-only local stack and launch a project with runtime hooks."""

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from . import __version__
from .repl import Client, ClientError


@contextmanager
def exclusive(path):
    # macOS and Linux are the supported local-service hosts (Homebrew/uv).
    if os.name != "posix":
        raise ClientError("Local watch currently requires macOS or Linux.")
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ClientError(
                "Another watch session is using this workspace; stop it first."
            ) from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def private_json(path, value):
    temporary = path.with_suffix(".tmp")
    with open(
        temporary, "w", opener=lambda name, flags: os.open(name, flags, 0o600)
    ) as output:
        json.dump(value, output)
    temporary.replace(path)


def runtime_source():
    configured = os.environ.get("AGENTSCOPE_RUNTIME_SOURCE")
    if configured:
        return Path(configured).expanduser().resolve()
    bundled = Path(__file__).parent / "_runtime"
    if bundled.is_dir():
        return bundled
    checkout = Path(__file__).resolve().parents[3]
    if (checkout / "apps/api/app/main.py").is_file():
        return checkout
    raise ClientError(
        "The installed runtime is missing. Reinstall AgentScope from main."
    )


def prepare_runtime(home, write, source=None):
    source = Path(source).resolve() if source else runtime_source()
    for program in ("node", "npm", "uv"):
        if not shutil.which(program):
            raise ClientError(
                f"watch needs {program}. Install Node.js 24 with npm and uv, then retry."
            )
    version = subprocess.check_output(["node", "--version"], text=True).strip()
    if not version.startswith("v24."):
        raise ClientError("watch requires Node.js 24.x; activate Node 24 and retry.")
    if not (source / "apps/api/requirements.txt").is_file():
        raise ClientError("Local runtime sources are incomplete. Reinstall AgentScope.")
    # Explicit --runtime is useful to developers and controlled offline installs.
    if (source / ".venv/bin/uvicorn").is_file() and (
        source / "apps/web/.next/standalone/server.js"
    ).is_file():
        return source
    destination = home / f"runtime-{__version__}"
    with exclusive(home / "runtime.lock"):
        ready = destination / ".prepared"
        if ready.is_file():
            return destination
        write("Preparing the local API and dashboard (first run only)…")
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(mode=0o700)
        for name in ("apps/api", "apps/web", "packages/python-sdk"):
            shutil.copytree(
                source / name,
                destination / name,
                ignore=shutil.ignore_patterns(
                    "node_modules",
                    ".next",
                    ".next-*",
                    "__pycache__",
                    ".env*",
                    "test-results",
                    "tests",
                    "out",
                ),
            )
        environment = os.environ.copy()
        environment.update(
            NEXT_TELEMETRY_DISABLED="1",
            UV_CACHE_DIR=str(home / "cache/uv"),
            npm_config_cache=str(home / "cache/npm"),
        )
        commands = [
            ["uv", "venv", str(destination / ".venv"), "--python", sys.executable],
            [
                "uv",
                "pip",
                "sync",
                str(destination / "apps/api/requirements.txt"),
                "--python",
                str(destination / ".venv/bin/python"),
            ],
            [
                "npm",
                "--prefix",
                str(destination / "apps/web"),
                "ci",
                "--no-audit",
                "--no-fund",
            ],
            ["npm", "--prefix", str(destination / "apps/web"), "run", "build"],
        ]
        with (destination / "setup.log").open("w") as log:
            os.chmod(destination / "setup.log", 0o600)
            for command in commands:
                process = None
                try:
                    runner = Path(__file__).parent / "hooks/service-runner.py"
                    process = subprocess.Popen(
                        [sys.executable, str(runner), str(os.getpid()), *command],
                        cwd=destination,
                        env=environment,
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )
                    if process.wait(timeout=1200):
                        raise subprocess.CalledProcessError(process.returncode, command)
                except (OSError, subprocess.SubprocessError):
                    raise ClientError(
                        f"Runtime setup failed. Inspect the private setup log at {destination / 'setup.log'} and retry."
                    ) from None
                finally:
                    stop_process(process)
        ready.touch(mode=0o600)
    return destination


def free_port(preferred):
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", preferred))
        except OSError:
            listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    except ProcessLookupError:
        pass


class WatchSession:
    def __init__(self, args, stdout=None):
        self.args = args
        self.stdout = stdout or sys.stdout
        self.repo = Path(args.repo).expanduser().resolve()
        if not self.repo.is_dir():
            raise ClientError("The project directory does not exist.")
        self.home = (
            Path(os.environ.get("AGENTSCOPE_HOME", str(Path.home() / ".agentscope")))
            .expanduser()
            .resolve()
        )
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        identifier = hashlib.sha256(str(self.repo).encode()).hexdigest()[:20]
        self.data = self.home / "projects" / identifier
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.children = []
        self.logs = []
        self.client = None
        self.agent = None
        self.target = None

    def write(self, message):
        print(message, file=self.stdout, flush=True)

    def spawn(self, command, cwd, environment, log_name):
        output = (self.data / log_name).open("a")
        os.chmod(self.data / log_name, 0o600)
        self.logs.append(output)
        runner = Path(__file__).parent / "hooks/service-runner.py"
        process = subprocess.Popen(
            [sys.executable, str(runner), str(os.getpid()), *command],
            cwd=cwd,
            env=environment,
            stdout=output,
            stderr=output,
            start_new_session=True,
        )
        self.children.append(process)
        return process

    def ready(self, url, process):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ClientError(
                    f"A local service stopped during startup. Inspect private logs in {self.data}."
                )
            try:
                with urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (URLError, OSError):
                pass
            time.sleep(0.25)
        raise ClientError(
            f"Local service startup timed out. Inspect private logs in {self.data}."
        )

    def heartbeat(self, status):
        self.client.request(
            f"/api/v1/agents/{self.agent}/watch",
            "PUT",
            {
                "repository": self.repo.name[:120] or "project",
                "session_id": self.session_id,
                "status": status,
            },
        )

    def start(self):
        from uuid import uuid4

        self.session_id = str(uuid4())
        self.runtime = prepare_runtime(self.home, self.write, self.args.runtime)
        self.api_port = free_port(self.args.api_port)
        self.web_port = free_port(self.args.port)
        if self.api_port == self.web_port:
            self.web_port = free_port(0)
        self.endpoint = f"http://127.0.0.1:{self.api_port}"
        self.dashboard = f"http://127.0.0.1:{self.web_port}"
        environment = os.environ.copy()
        # Dedicated local storage and credentials; do not reuse ambient server configuration.
        for name in (
            "DATABASE_URL",
            "AGENTSCOPE_CONTAINER",
            "AGENTSCOPE_ADMIN_TOKEN",
            "AGENTSCOPE_ADMIN_TOKEN_FILE",
            "DASHBOARD_PASSWORD",
            "DASHBOARD_PASSWORD_FILE",
            "PROVIDER_API_KEY",
            "PYTHONPATH",
            "NODE_OPTIONS",
        ):
            environment.pop(name, None)
        environment.update(
            AGENTSCOPE_DATA_DIR=str(self.data), NEXT_TELEMETRY_DISABLED="1"
        )
        python = str(self.runtime / ".venv/bin/python")
        with (self.data / "api.log").open("a") as log:
            os.chmod(self.data / "api.log", 0o600)
            try:
                subprocess.run(
                    [python, "-m", "alembic", "upgrade", "head"],
                    cwd=self.runtime / "apps/api",
                    env=environment,
                    stdout=log,
                    stderr=log,
                    check=True,
                    timeout=60,
                )
            except subprocess.SubprocessError:
                raise ClientError(
                    f"Database migration failed. Inspect {self.data / 'api.log'}."
                ) from None
        api = self.spawn(
            [
                python,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.api_port),
            ],
            self.runtime / "apps/api",
            environment,
            "api.log",
        )
        self.ready(f"{self.endpoint}/health/ready", api)
        self.client = Client(self.endpoint, self.data / "admin-token")
        state_path = self.data / "workspace.json"
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            state = {}
        projects = self.client.request("/api/v1/projects", scoped=False)
        if any(project["id"] == state.get("project_id") for project in projects):
            self.client.project = state["project_id"]
        else:
            project = self.client.request(
                "/api/v1/projects",
                "POST",
                {
                    "name": self.repo.name[:120] or "project",
                    "description": "Local repository watch workspace",
                },
                scoped=False,
            )
            self.client.project = project["id"]
        key_path = self.data / "ingestion-key"
        active_keys = self.client.request("/api/v1/api-keys")
        if not key_path.is_file() or not any(
            key["id"] == state.get("key_id") and not key["revoked"]
            for key in active_keys
        ):
            key = self.client.request(
                "/api/v1/api-keys", "POST", {"name": "Local watch ingestion"}
            )
            with open(
                key_path, "w", opener=lambda name, flags: os.open(name, flags, 0o600)
            ) as output:
                output.write(key["key"])
            os.chmod(key_path, 0o600)
            state["key_id"] = key["id"]
        state.update(project_id=self.client.project, repository=str(self.repo))
        private_json(state_path, state)
        name = self.repo.name[:120] or "project"
        agent = self.client.request(
            "/api/v1/agents",
            "POST",
            {
                "name": name,
                "framework": "Automatic LLM instrumentation",
                "environment": "development",
            },
        )
        self.agent = agent["id"]
        previous = agent.get("configuration", {}).get("watch")
        if (
            isinstance(previous, dict)
            and previous.get("session_id")
            and previous.get("status") != "stopped"
        ):
            # We hold the project's exclusive lock; this is a lease left behind
            # by an interrupted owner, not another live watcher.
            self.client.request(
                f"/api/v1/agents/{self.agent}/watch",
                "PUT",
                {
                    "repository": self.repo.name[:120] or "project",
                    "session_id": previous["session_id"],
                    "status": "stopped",
                },
            )
        self.heartbeat("waiting")
        web = self.runtime / "apps/web"
        standalone = web / ".next/standalone"
        # Next's standalone output omits static files and public assets by design.
        shutil.copytree(
            web / ".next/static", standalone / ".next/static", dirs_exist_ok=True
        )
        shutil.copytree(web / "public", standalone / "public", dirs_exist_ok=True)
        environment.update(
            API_URL=self.endpoint,
            AGENTSCOPE_TOKEN_FILE=str(self.data / "admin-token"),
            HOSTNAME="127.0.0.1",
            PORT=str(self.web_port),
        )
        dashboard = self.spawn(
            ["node", "server.js"], standalone, environment, "dashboard.log"
        )
        self.ready(f"{self.dashboard}/", dashboard)
        self.dashboard_url = f"{self.dashboard}/dashboard?project={self.client.project}"
        self.write(f"Watching project: {self.repo.name}")
        self.write(f"Dashboard: {self.dashboard_url}")
        self.write(
            "Automatic capture: Python OpenAI/Anthropic; Node.js fetch-based OpenAI/Anthropic-compatible calls."
        )
        self.write(
            "Prompt and response content is excluded. Hallucinations require explicit grounding evaluations."
        )
        self.write(
            "Use stop or exit to stop monitoring."
            if getattr(self.args, "interactive", False)
            else "Press Ctrl+C to stop local services. Recorded telemetry is kept for the next session."
        )
        if not self.args.no_open:
            try:
                webbrowser.open(self.dashboard_url)
            except webbrowser.Error:
                self.write("Open the dashboard URL above in your browser.")

    def launch(self):
        command = self.args.application
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            self.write(
                "Waiting for instrumented activity. Launch your app with: agentscope run -- YOUR_COMMAND"
            )
            return
        self.target = launch_application(
            command, self.repo, self.runtime, self.data, self.endpoint, self.agent
        )
        self.children.append(self.target)
        self.heartbeat("monitoring")

    def poll(self):
        for child in self.children:
            if child is not self.target and child.poll() is not None:
                raise ClientError(
                    f"A local service stopped. Inspect private logs in {self.data}."
                )
        active = self.target and self.target.poll() is None
        if not active:
            active = self.client.request("/api/v1/metrics/overview")["active_runs"] > 0
        self.heartbeat("monitoring" if active else "waiting")

    def close(self):
        if self.client and self.agent:
            try:
                self.heartbeat("stopped")
            except ClientError:
                pass
        for child in reversed(self.children):
            stop_process(child)
        for output in self.logs:
            output.close()

    def run(self):
        with exclusive(self.data / "watch.lock"):
            try:
                self.start()
                private_json(
                    self.data / "session.json",
                    {
                        "pid": os.getpid(),
                        "url": self.endpoint,
                        "runtime": str(self.runtime),
                        "agent_id": self.agent,
                    },
                )
                self.launch()
                last = 0
                announced = False
                while True:
                    if self.target and self.target.poll() is not None:
                        if self.args.once:
                            return self.target.returncode
                        if not announced:
                            self.write(
                                "Application finished. Dashboard remains available; start another run or press Ctrl+C."
                            )
                            announced = True
                    if time.monotonic() - last >= 10:
                        self.poll()
                        last = time.monotonic()
                    time.sleep(0.25)
            finally:
                (self.data / "session.json").unlink(missing_ok=True)
                self.close()


def launch_application(command, repo, runtime, data, endpoint, agent):
    if not command:
        raise ClientError("Supply an application command after --.")
    environment = os.environ.copy()
    for name in (
        "AGENTSCOPE_ADMIN_TOKEN",
        "AGENTSCOPE_ADMIN_TOKEN_FILE",
        "AGENTSCOPE_TOKEN_FILE",
    ):
        environment.pop(name, None)
    hooks = Path(__file__).parent / "hooks"
    environment.update(
        AGENTSCOPE_WATCH_URL=endpoint,
        AGENTSCOPE_WATCH_KEY_FILE=str(data / "ingestion-key"),
        AGENTSCOPE_WATCH_AGENT_ID=agent,
        AGENTSCOPE_WATCH_AGENT_NAME=repo.name[:120] or "project",
    )
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(hooks),
                str(runtime / "packages/python-sdk"),
                environment.get("PYTHONPATH"),
            ],
        )
    )
    environment["NODE_OPTIONS"] = (
        f"{environment.get('NODE_OPTIONS', '')} --require={json.dumps(str(hooks / 'watch-hook.cjs'))}".strip()
    )
    try:
        return subprocess.Popen(
            [
                sys.executable,
                str(hooks / "service-runner.py"),
                str(os.getpid()),
                *command,
            ],
            cwd=repo,
            env=environment,
            start_new_session=True,
        )
    except OSError:
        raise ClientError(
            "Cannot launch the application command. Check its executable and arguments."
        ) from None


def run_existing(repo, command):
    root = Path(repo).expanduser().resolve()
    home = (
        Path(os.environ.get("AGENTSCOPE_HOME", str(Path.home() / ".agentscope")))
        .expanduser()
        .resolve()
    )
    identifier = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    data = home / "projects" / identifier
    try:
        state = json.loads((data / "session.json").read_text())
        os.kill(state["pid"], 0)
        client = Client(state["url"], data / "admin-token")
        client.request("/api/v1/projects", scoped=False)
    except (OSError, ValueError, KeyError, ClientError):
        raise ClientError(
            "No running watch session for this directory. Start agentscope watch here first."
        ) from None
    if command and command[0] == "--":
        command = command[1:]
    child = launch_application(
        command, root, Path(state["runtime"]), data, state["url"], state["agent_id"]
    )
    try:
        return child.wait()
    finally:
        stop_process(child)


def add_watch_arguments(parser):
    parser.add_argument(
        "--repo", default=".", help="Project directory (default: current directory)."
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Print the dashboard URL without opening a browser.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="Preferred dashboard port; occupied ports are skipped.",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="Preferred API port; occupied ports are skipped.",
    )
    parser.add_argument("--runtime", help=argparse.SUPPRESS)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Stop services when the application exits (requires a command).",
    )
    parser.add_argument(
        "application",
        nargs=argparse.REMAINDER,
        help="Application command following --.",
    )


def validate_arguments(args):
    if args.application and args.application[0] != "--":
        args.repo = args.application[0]
        args.application = args.application[1:]
        if args.application and args.application[0] != "--":
            raise ClientError(
                "Put application commands after --; use --repo for a project directory."
            )
    if not 0 <= args.port <= 65535 or not 0 <= args.api_port <= 65535:
        raise ClientError("Ports must be between 0 and 65535 (0 selects a free port).")
    if args.once and not [part for part in args.application if part != "--"]:
        raise ClientError("--once requires an application command following --.")


def watch_main(args, stdout=None):
    validate_arguments(args)
    previous = signal.getsignal(signal.SIGTERM)

    def interrupted(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        return WatchSession(args, stdout).run()
    except KeyboardInterrupt:
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous)
