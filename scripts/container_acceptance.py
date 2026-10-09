#!/usr/bin/env python3
"""Isolated local acceptance. Never prunes Docker or deletes a database volume."""

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/python-sdk"))
from agentscope_sdk import AgentScope


def require(condition, description):
    if not condition:
        raise RuntimeError(description)


class Stack:
    def __init__(self, state):
        self.state = Path(state).resolve()
        require(
            self.state.is_relative_to(ROOT / ".local/container-acceptance"),
            "State must be inside .local/container-acceptance",
        )
        self.config = json.loads((self.state / "state.json").read_text())
        self.project = self.config["project"]
        require(
            self.project.startswith("agentscope-accept-"),
            "Refusing an unrelated Compose project",
        )
        self.env = os.environ.copy()
        # Keep the host's Docker credentials/configuration, but store writable builder state locally.
        self.env["BUILDX_CONFIG"] = str(ROOT / ".local/cache/buildx")
        for name in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        ):
            self.env.pop(name, None)
        self.docker = ["docker", "--host=unix:///var/run/docker.sock"]
        self.compose = self.docker + [
            "compose",
            "--env-file",
            str(self.state / "stack.env"),
            "-p",
            self.project,
            "-f",
            str(ROOT / "docker-compose.yml"),
        ]
        self.report = {
            "execution": "local",
            "project": self.project,
            "checks": [],
            "status": "running",
        }
        self.secret_values = [
            p.read_text().strip() for p in (self.state / "secrets").iterdir()
        ]

    def command(self, args, *, cwd=ROOT, env=None, expected=0, capture=True):
        result = subprocess.run(
            args,
            cwd=cwd,
            env=env or self.env,
            text=True,
            capture_output=capture,
            timeout=900,
            check=False,
        )
        # Do not attach environment, credential-bearing HTTP errors, or unsanitized command output.
        require(
            result.returncode == expected,
            f"Command failed ({result.returncode}): {Path(args[0]).name}; see the named check",
        )
        return (
            (result.stdout + (result.stderr if expected != 0 else ""))
            if capture
            else ""
        )

    def check(self, name, function):
        print(f"Checking {name}...", flush=True)
        started = time.monotonic()
        try:
            value = function()
        except Exception:
            self.report["checks"].append(
                {
                    "name": name,
                    "status": "failed",
                    "seconds": round(time.monotonic() - started, 2),
                }
            )
            self.save("failed")
            raise
        self.report["checks"].append(
            {
                "name": name,
                "status": "passed",
                "seconds": round(time.monotonic() - started, 2),
                "measurements": value,
            }
        )
        self.save("running")
        print(f"Passed {name}", flush=True)
        return value

    def save(self, status):
        self.report["status"] = status
        (self.state / "report.json").write_text(
            json.dumps(self.report, indent=2) + "\n"
        )

    def api(
        self,
        path,
        body=None,
        method=None,
        project=None,
        key=None,
        web=False,
        expected=200,
    ):
        token = key or (self.state / "secrets/admin-token").read_text().strip()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if project:
            headers["X-Project-ID"] = project
        port = self.config["api_port"]
        if web:
            password = (self.state / "secrets/dashboard-password").read_text().strip()
            headers["Authorization"] = (
                "Basic " + base64.b64encode(f"admin:{password}".encode()).decode()
            )
            port = self.config["web_port"]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status, payload = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, payload = exc.code, exc.read()
        require(
            status == expected,
            f"HTTP status mismatch at {path}: {status}, expected {expected}",
        )
        return json.loads(payload) if payload else None

    def sql(self, query):
        return self.command(
            self.compose
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "agentscope",
                "-d",
                "agentscope",
                "-tA",
                "-c",
                query,
            ]
        ).strip()

    def guard(self):
        ids = self.command(self.compose + ["ps", "-aq"]).split()
        for container_id in ids:
            value = json.loads(self.command(self.docker + ["inspect", container_id]))[0]
            require(
                value["Config"]["Labels"].get("com.docker.compose.project")
                == self.project,
                "Container ownership mismatch",
            )

    def up(self):
        self.guard()
        self.command(
            self.compose
            + ["up", "-d", "--wait", "--wait-timeout", "120", "--no-build"],
            capture=False,
        )

    def stop(self):
        self.guard()
        started = time.monotonic()
        ids = self.command(self.compose + ["ps", "-aq"]).split()
        self.command(self.compose + ["stop", "--timeout", "30"], capture=False)
        exits = {}
        for cid in ids:
            value = json.loads(self.command(self.docker + ["inspect", cid]))[0]
            service = value["Config"]["Labels"]["com.docker.compose.service"]
            exits[service] = value["State"]["ExitCode"]
            clean = exits[service] == 0
            if service == "api" and exits[service] == 143:
                # Uvicorn re-raises SIGTERM after its complete ASGI teardown.
                logs = self.command(
                    self.compose
                    + [
                        "logs",
                        "--no-color",
                        "--since",
                        value["State"]["StartedAt"],
                        "api",
                    ]
                )
                clean = (
                    "Application shutdown complete." in logs
                    and "Finished server process" in logs
                    and "timeout graceful shutdown" not in logs
                    and "ERROR" not in logs
                )
            if service == "web" and exits[service] == 143:
                logs = self.command(
                    self.compose
                    + [
                        "logs",
                        "--no-color",
                        "--since",
                        value["State"]["StartedAt"],
                        "web",
                    ]
                )
                clean = "AgentScope dashboard graceful shutdown complete" in logs
            require(
                clean and not value["State"]["OOMKilled"],
                f"{service} did not shut down cleanly",
            )
        return {"seconds": round(time.monotonic() - started, 2), "exit_codes": exits}

    def snapshot(self):
        tables = [
            "projects",
            "agents",
            "runs",
            "spans",
            "telemetry_events",
            "anomalies",
            "incidents",
            "investigations",
            "remediations",
            "settings",
            "audit_log",
            "api_keys",
        ]
        # Hash the entire persistent records, including approvals/audits/settings, without exporting secrets.
        checksums = {}
        counts = {}
        for table in tables:
            rows = self.sql(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY id")
            checksums[table] = hashlib.sha256(rows.encode()).hexdigest()
            counts[table] = int(self.sql(f"SELECT count(*) FROM {table}"))
        return {"checksums": checksums, "counts": counts}

    def restart(self):
        before = self.snapshot()
        volume = self.volume()
        shutdown = self.stop()
        self.up()
        after = self.snapshot()
        require(
            before == after and volume == self.volume(),
            "Persistent records or database volume changed on restart",
        )
        result = {
            "shutdown": shutdown,
            "volume": volume,
            "records": after["counts"],
            "all_record_checksums_match": True,
        }
        (self.state / "restart.json").write_text(json.dumps(result, indent=2) + "\n")
        return result

    def volume(self):
        cid = self.command(self.compose + ["ps", "-q", "postgres"]).strip()
        value = json.loads(self.command(self.docker + ["inspect", cid]))[0]
        return next(m["Name"] for m in value["Mounts"] if m["Type"] == "volume")

    def native(self):
        python = ROOT / ".venv/bin/python"
        require(
            python.exists() and (ROOT / "apps/web/node_modules").exists(),
            "Run npm run setup first (Python, Node, uv required)",
        )
        env = self.env.copy()
        env.pop("TEST_DATABASE_URL", None)
        env["AGENTSCOPE_DATA_DIR"] = str(self.state / "native-api-state")
        for name, args, cwd in [
            ("api_sdk_tests", [str(python), "-m", "pytest", "-q"], ROOT / "apps/api"),
            (
                "ruff",
                [
                    str(ROOT / ".venv/bin/ruff"),
                    "check",
                    "apps/api",
                    "packages/python-sdk",
                    "examples",
                    "infrastructure/docker",
                    "scripts/container_acceptance.py",
                ],
                ROOT,
            ),
            (
                "mypy",
                [
                    str(ROOT / ".venv/bin/mypy"),
                    "apps/api/app",
                    "--ignore-missing-imports",
                    "--follow-untyped-imports",
                ],
                ROOT,
            ),
            ("web_typecheck", ["npm", "run", "typecheck"], ROOT / "apps/web"),
            ("web_unit_tests", ["npm", "test"], ROOT / "apps/web"),
        ]:
            self.check(
                name,
                lambda a=args, c=cwd: self.command(a, cwd=c, env=env, capture=False),
            )
        # A separate source copy prevents next build from replacing a running dev server's .next.
        dest = self.state / "native-web"
        shutil.copytree(
            ROOT / "apps/web",
            dest,
            ignore=shutil.ignore_patterns(
                "node_modules",
                ".next*",
                "test-results",
                "playwright-report",
                "*.tsbuildinfo",
            ),
        )
        shutil.copy2(ROOT / "package.json", dest.parent / "package.json")
        env["npm_config_cache"] = str(ROOT / ".local/cache/npm")
        env["NEXT_TELEMETRY_DISABLED"] = "1"
        self.check(
            "native_web_locked_install",
            lambda: self.command(
                ["npm", "ci", "--no-audit", "--no-fund"],
                cwd=dest,
                env=env,
                capture=False,
            ),
        )
        self.check(
            "native_production_build",
            lambda: self.command(
                ["npm", "run", "build"], cwd=dest, env=env, capture=False
            ),
        )
        # Remove only this generated source/dependency copy after its checks pass.
        # Native .next, node_modules, SQLite state and every database volume stay intact.
        shutil.rmtree(dest)

    def constraints(self):
        measurements = {}
        for service in ("api", "web", "postgres"):
            cid = self.command(self.compose + ["ps", "-q", service]).strip()
            value = json.loads(self.command(self.docker + ["inspect", cid]))[0]
            config = value["HostConfig"]
            require(
                value["State"]["Health"]["Status"] == "healthy",
                f"{service} is unhealthy",
            )
            require(
                config["Memory"] > 0
                and config["NanoCpus"] > 0
                and config["PidsLimit"] > 0,
                f"{service} lacks resource bounds",
            )
            require(
                value["Config"]["User"] not in ("", "0", "root", "0:0"),
                f"{service} runs as root",
            )
            require(
                all(
                    binding["HostIp"] == "127.0.0.1"
                    for bindings in (config["PortBindings"] or {}).values()
                    for binding in bindings
                ),
                "Non-loopback port found",
            )
            if service != "postgres":
                require(
                    config["ReadonlyRootfs"] and "ALL" in config["CapDrop"],
                    "Application hardening missing",
                )
            measurements[service] = {
                "user": value["Config"]["User"],
                "memory_bytes": config["Memory"],
                "cpu": config["NanoCpus"] / 1e9,
                "pids": config["PidsLimit"],
                "image": value["Image"],
            }
        require(
            self.sql("SELECT version_num FROM alembic_version") == "001",
            "Migration did not reach head",
        )
        require(
            self.sql("SELECT count(*) FROM runs") == "0",
            "First start must have no demo or live runs",
        )
        self.api("/api/health/ready", web=True)
        return measurements

    def failure_checks(self):
        for service, expected_name in (
            ("api", "DATABASE_HOST"),
            ("web", "AGENTSCOPE_TOKEN_FILE"),
        ):
            args = self.docker + [
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--memory",
                "256m",
                "--pids-limit",
                "64",
                "--tmpfs",
                "/tmp:rw,size=16m,uid=10001,gid=10001",
                "-e",
                "AGENTSCOPE_CONTAINER=1",
                "-e",
                "AGENTSCOPE_DATA_DIR=/tmp/agentscope",
                f"{self.project}-{service}:local",
            ]
            output = self.command(args, expected=1)
            # Startup diagnostics are deliberately short and contain variable names only.
            require(
                expected_name in output and "startup failed" in output,
                f"Missing actionable {service} startup diagnostic",
            )
        return {"missing_configuration_exits": {"api": 1, "web": 1}}

    def dependency_failure(self):
        self.guard()
        self.command(
            self.compose + ["stop", "--timeout", "30", "postgres"], capture=False
        )
        api = self.api("/health/ready", expected=503)
        web = self.api("/api/health/ready", web=True, expected=503)
        require(
            "unavailable" in api["detail"] and web == api,
            "Dependency failure was hidden",
        )
        self.command(self.compose + ["stop", "--timeout", "30", "api"], capture=False)
        # Exercise the actual exporter against the offline API, with a small finite queue.
        scope = AgentScope(
            f"http://127.0.0.1:{self.config['api_port']}",
            "offline-test-no-credential",
            "offline-agent",
            timeout=0.5,
            queue_size=4,
            batch_size=2,
        )
        for index in range(20):
            scope._enqueue({"event_id": f"offline:{index}"})
        scope.close(2)
        require(
            scope.close(2)
            and scope._queue.qsize() == 0
            and scope.stats["exported_events"] == 0
            and scope.stats["dropped_events"] == 20,
            "Offline SDK did not bound/finish/drop its queue",
        )
        self.up()
        require(
            self.sql("SELECT count(*) FROM runs") == "0",
            "Failure substituted demo data",
        )
        return {
            "api_status": 503,
            "dashboard_status": 503,
            "silent_demo_runs": 0,
            "offline_sdk": scope.stats,
        }

    def sdk(self):
        project = self.api(
            "/api/v1/projects", {"name": "Real SDK container acceptance"}, expected=201
        )["id"]
        key = self.api(
            "/api/v1/api-keys",
            {"name": "Acceptance SDK"},
            project=project,
            expected=201,
        )
        self.secret_values.append(key["key"])
        scope = AgentScope(
            f"http://127.0.0.1:{self.config['api_port']}",
            key["key"],
            "container-calculator",
            framework="Custom",
            queue_size=16,
            batch_size=16,
        )
        captured = []
        lost_ack = False
        original = scope._request

        def request(path, body):
            nonlocal lost_ack
            result = original(path, body)
            if path == "telemetry/events":
                captured.extend(body["events"] if not lost_ack else [])
                if not lost_ack:
                    lost_ack = True
                    # The server committed the batch; simulate loss of its acknowledgement.
                    raise OSError("Injected lost acknowledgement")
            return result

        scope._request = request

        @scope.trace_tool
        def add(a, b):
            return a + b

        @scope.trace_agent
        def calculator():
            result = add(13, 16)
            scope.heartbeat("calculation complete")
            return result

        require(calculator() == 29 and scope.close(), "SDK did not finish exporting")
        require(
            scope.stats["exported_events"] == 4
            and scope.stats["dropped_events"] == 0
            and scope.stats["export_failures"] == 1,
            "SDK retry counters disagree",
        )
        runs = self.api("/api/v1/runs", project=project)
        require(runs["total"] == 1, "Duplicate or missing SDK runs")
        run = runs["items"][0]
        trace = self.api(f"/api/v1/runs/{run['id']}/trace", project=project)
        overview = self.api("/api/v1/metrics/overview?synthetic=false", project=project)
        dashboard = self.api(
            "/api/v1/metrics/overview?synthetic=false", project=project, web=True
        )
        for data in (overview, dashboard):
            require(
                sum(bin["runs"] for bin in data["series"]) == 1
                and sum(bin["tool_calls"] for bin in data["series"]) == 1
                and sum(bin["tool_errors"] for bin in data["series"]) == 0
                and sum(
                    bin["input_tokens"] + bin["output_tokens"] for bin in data["series"]
                )
                == 0,
                "Dashboard chart series disagrees with persisted telemetry",
            )
        require(
            run["status"] == "completed"
            and not run["synthetic"]
            and run["tokens"] == 0
            and run["cost"] is None,
            "Real telemetry was mislabeled or fabricated",
        )
        require(
            len(trace["spans"]) == 3
            and sum(s["kind"] == "tool" for s in trace["spans"]) == 1,
            "Nested trace disagrees",
        )
        require(
            overview["registered_agents"] == 1
            and overview["total_runs"] == 1
            and overview["success_rate"] == 100
            and overview["tokens"] == 0
            and overview["cost"] is None
            and overview["tool_calls"] == 1,
            "Metrics disagree with real SDK",
        )
        require(
            {k: v for k, v in overview.items() if k not in ("updated_at", "series")}
            == {
                k: v for k, v in dashboard.items() if k not in ("updated_at", "series")
            },
            "Dashboard proxy data disagrees",
        )
        duplicate = self.api(
            "/api/v1/telemetry/events",
            {"events": captured},
            project=project,
            key=key["key"],
            expected=202,
        )
        require(duplicate["accepted"] == 0, "Replay was not deduplicated")
        (self.state / "sdk.json").write_text(
            json.dumps(
                {
                    "project": project,
                    "run": run["id"],
                    "key_id": key["id"],
                    "events": captured,
                },
                indent=2,
            )
        )
        return {
            "result": 29,
            "runs": 1,
            "spans": 3,
            "tokens": 0,
            "cost": None,
            "synthetic": False,
            "sdk": scope.stats,
            "replayed_events_accepted": duplicate["accepted"],
        }

    def browser(self):
        env = self.env.copy()
        env.update(
            {
                "API_URL": f"http://127.0.0.1:{self.config['api_port']}",
                "PLAYWRIGHT_BASE_URL": f"http://127.0.0.1:{self.config['web_port']}",
                "AGENTSCOPE_ADMIN_TOKEN_FILE": str(self.state / "secrets/admin-token"),
                "DASHBOARD_PASSWORD_FILE": str(
                    self.state / "secrets/dashboard-password"
                ),
                "AGENTSCOPE_ACCEPTANCE_STATE": str(self.state),
                "PLAYWRIGHT_OUTPUT_DIR": str(self.state / "browser-results"),
                "PLAYWRIGHT_SCREENSHOT_DIR": str(self.state / "screenshots"),
            }
        )
        env.pop("AGENTSCOPE_ADMIN_TOKEN", None)
        self.command(
            ["npm", "run", "test:e2e"], cwd=ROOT / "apps/web", env=env, capture=False
        )
        last = json.loads((self.state / "browser-results/.last-run.json").read_text())
        require(last["status"] == "passed", "Browser runner did not pass")
        return {
            "status": last["status"],
            "restart": json.loads((self.state / "restart.json").read_text()),
        }

    def audit(self):
        require(
            int(
                self.sql(
                    "SELECT count(*) FROM audit_log WHERE action = 'remediation.approved'"
                )
            )
            == 1,
            "Approval audit duplicated",
        )
        require(
            int(
                self.sql(
                    "SELECT count(*) FROM audit_log WHERE action = 'remediation.executed'"
                )
            )
            == 1,
            "Execution audit duplicated",
        )
        require(
            int(
                self.sql(
                    "SELECT count(*) FROM audit_log WHERE action = 'recovery.verified'"
                )
            )
            == 1,
            "Recovery audit missing or duplicated",
        )
        sdk = json.loads((self.state / "sdk.json").read_text())
        self.api(
            f"/api/v1/api-keys/{sdk['key_id']}",
            method="DELETE",
            project=sdk["project"],
            expected=204,
        )
        return self.snapshot()["counts"]

    def secret_audit(self):
        output = self.command(self.compose + ["logs", "--no-color"])
        forbidden = self.secret_values + [
            base64.b64encode(f"admin:{value}".encode()).decode()
            for value in self.secret_values
        ]
        for service in ("api", "web"):
            image = f"{self.project}-{service}:local"
            output += self.command(self.docker + ["image", "inspect", image])
            output += self.command(self.docker + ["history", "--no-trunc", image])
            args = (
                [
                    "python",
                    "-c",
                    "from pathlib import Path; assert not Path('/run/secrets/proxy_ca').exists(); assert not Path('/app/.local').exists()",
                ]
                if service == "api"
                else [
                    "node",
                    "-e",
                    "const fs=require('fs'); if(fs.existsSync('/run/secrets/proxy_ca')||fs.existsSync('/app/.local'))process.exit(1)",
                ]
            )
            self.command(
                self.docker
                + ["run", "--rm", "--network", "none", "--entrypoint", args[0], image]
                + args[1:]
            )
        require(
            all(value not in output for value in forbidden),
            "Credential found in own container logs or image metadata",
        )
        return {
            "credential_values_found": 0,
            "native_state_in_images": False,
            "build_ca_in_images": False,
        }


def initialize(api_port, web_port):
    for port in (api_port, web_port):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    require(api_port != web_port, "API and web ports must differ")
    name = "agentscope-accept-" + uuid4().hex[:12]
    state = ROOT / ".local/container-acceptance" / name
    state.mkdir(parents=True, mode=0o700)
    directory = state / "secrets"
    directory.mkdir(mode=0o700)
    for name in ("database-password", "admin-token", "dashboard-password"):
        path = directory / name
        path.write_text(secrets.token_urlsafe(48))
        # Docker Compose bind-mounted secrets ignore uid/gid overrides. The parent
        # directory is private on the host; container mounts are read-only.
        path.chmod(0o444)
    bundle = state / "build-ca.pem"
    bundle.write_bytes(
        Path("/etc/ssl/certs/ca-certificates.crt").read_bytes()
        + (
            b"\n" + Path(os.environ["CODEX_PROXY_CERT"]).read_bytes()
            if os.getenv("CODEX_PROXY_CERT")
            else b""
        )
    )
    bundle.chmod(0o600)
    project = state.name
    (state / "state.json").write_text(
        json.dumps({"project": project, "api_port": api_port, "web_port": web_port})
    )
    (state / "stack.env").write_text(
        f"COMPOSE_PROJECT_NAME={project}\nAGENTSCOPE_API_PORT={api_port}\nAGENTSCOPE_WEB_PORT={web_port}\nAGENTSCOPE_SECRET_DIR={directory}\nAGENTSCOPE_BUILD_CA={bundle}\n"
    )
    (state / "stack.env").chmod(0o600)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["init", "run", "restart", "stop", "up"],
        nargs="?",
        default="run",
    )
    parser.add_argument("--state")
    parser.add_argument("--api-port", type=int, default=18000)
    parser.add_argument("--web-port", type=int, default=13000)
    args = parser.parse_args()
    if args.action == "init":
        print(initialize(args.api_port, args.web_port))
        return
    if args.action != "run":
        require(args.state is not None, "--state is required")
        stack = Stack(args.state)
        result = getattr(stack, args.action)()
        if result:
            print(json.dumps(result, indent=2))
        return
    require(
        args.state is None,
        "Acceptance always creates a fresh disposable project; use up/restart/stop for an existing stack",
    )
    state = initialize(args.api_port, args.web_port)
    print(f"Acceptance state: {state}", flush=True)
    stack = Stack(state)
    try:
        stack.native()
        stack.check(
            "compose_validation",
            lambda: stack.command(stack.compose + ["config", "--quiet"]),
        )
        stack.check(
            "container_builds",
            lambda: stack.command(stack.compose + ["build"], capture=False),
        )
        stack.check("missing_configuration", stack.failure_checks)
        stack.check("first_start", stack.up)
        stack.check("security_readiness_migrations_empty_database", stack.constraints)
        stack.check(
            "dependency_failure_no_fallback_and_bounded_sdk", stack.dependency_failure
        )
        stack.check("real_sdk_ingestion_retry_dedup_metrics", stack.sdk)
        stack.check("browser_workflow_and_restart_persistence", stack.browser)
        stack.check("secrets_absent_from_logs_and_image_metadata", stack.secret_audit)
        stack.check("final_audit_and_key_revocation", stack.audit)
        stack.check("final_graceful_shutdown", stack.stop)
        stack.report["volume_retained"] = f"{stack.project}_postgres-data"
        stack.report["branch"] = stack.command(
            ["git", "branch", "--show-current"]
        ).strip()
        stack.report["commit_at_start"] = stack.command(
            ["git", "rev-parse", "HEAD"]
        ).strip()
        stack.save("passed")
        print(f"Local acceptance passed. Report: {state / 'report.json'}", flush=True)
    except Exception as exc:  # noqa: BLE001 — preserve evidence and report failure without a traceback
        stack.save("failed")
        print(
            f"Acceptance failed ({type(exc).__name__}): {exc}. State and database retained: {state}",
            file=sys.stderr,
        )
        # Leave failed services available for diagnosis; no prune/down -v/delete.
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
