"""Exercise watch/run, real provider clients, persistence and REPL locally."""

import argparse
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/cli"))
from agentscope_cli.repl import Client, Repl


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, value, status=200, streaming=False):
        data = value.encode() if streaming else json.dumps(value).encode()
        self.send_response(status)
        self.send_header(
            "Content-Type", "text/event-stream" if streaming else "application/json"
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            if streaming:
                # Break SSE lines and UTF-8 packets across transport chunks.
                for offset in range(0, len(data), 17):
                    self.wfile.write(data[offset : offset + 17])
                    self.wfile.flush()
            else:
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.send({"status": "ok"})

    def do_POST(self):
        value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if value.get("model") == "fail":
            self.send(
                {
                    "error": {
                        "message": "private-error-sentinel",
                        "type": "server_error",
                    }
                },
                500,
            )
            return
        if self.path.endswith("/messages"):
            message = {
                "id": "msg_mock",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "private-answer-sentinel"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 5, "output_tokens": 3},
            }
            parts = [
                {
                    "type": "message_start",
                    "message": {
                        **message,
                        "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": 5, "output_tokens": 0},
                    },
                },
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "private-answer-sentinel"},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 3},
                },
                {"type": "message_stop"},
            ]
        elif self.path.endswith("/responses"):
            message = {
                "id": "resp_mock",
                "object": "response",
                "created_at": 1,
                "model": "gpt-4o-mini",
                "status": "completed",
                "output": [],
                "usage": {"input_tokens": 13, "output_tokens": 5, "total_tokens": 18},
            }
            parts = [
                {
                    "type": "response.created",
                    "response": {**message, "status": "in_progress", "usage": None},
                },
                {"type": "response.completed", "response": message},
            ]
        else:
            message = {
                "id": "chat_mock",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "private-answer-sentinel",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            }
            parts = [
                {
                    **message,
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "private-answer-sentinel"},
                            "finish_reason": None,
                        }
                    ],
                    "usage": None,
                },
                {**message, "object": "chat.completion.chunk", "choices": []},
            ]
        if value.get("stream"):
            data = "".join(
                f"event: {part.get('type', 'message')}\ndata: {json.dumps(part)}\n\n"
                for part in parts
            )
            self.send(data, streaming=True)
        else:
            self.send(message)


def wait(predicate, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.25)
    raise AssertionError("Watch acceptance timed out")


def run(args):
    state = Path(args.state).resolve() / f"run-{uuid4().hex[:8]}"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    repo = state / "sample project"
    repo.mkdir(exist_ok=True)
    pydeps = ROOT / ".local/watch-check/provider-deps"
    nodedeps = ROOT / ".local/watch-check/node-providers"
    environment = os.environ.copy()
    environment.update(
        AGENTSCOPE_HOME=str(state / "home"),
        NEXT_TELEMETRY_DISABLED="1",
        PYTHONPATH=str(pydeps),
        WATCH_NODE_PACKAGE=str(nodedeps / "package.json"),
    )
    if not args.skip_install:
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--target",
                str(pydeps),
                "-r",
                str(ROOT / "packages/cli/tests/requirements-watch.txt"),
            ],
            check=True,
        )
        subprocess.run(
            [
                "npm",
                "install",
                "--prefix",
                str(nodedeps),
                "--save-exact",
                "--no-audit",
                "--no-fund",
                "openai@7.32.0",
                "@anthropic-ai/sdk@0.133.0",
            ],
            check=True,
        )
    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    environment["WATCH_MOCK_ORIGIN"] = f"http://127.0.0.1:{provider.server_port}"
    cli = str(ROOT / ".venv/bin/agentscope")
    project_data = (
        Path(environment["AGENTSCOPE_HOME"])
        / "projects"
        / hashlib.sha256(str(repo).encode()).hexdigest()[:20]
    )
    base = [
        cli,
        "watch",
        "--runtime",
        str(ROOT),
        "--no-open",
        "--repo",
        str(repo),
        "--port",
        "0",
        "--api-port",
        "0",
    ]
    log_path = state / "watch.log"
    log = log_path.open("w")
    os.chmod(log_path, 0o600)
    watcher = None
    report = {
        "provider_calls": "Local mock HTTP only",
        "python_sdks": {"openai": "2.54.0", "anthropic": "0.125.0"},
        "node_sdks": {"openai": "7.32.0", "anthropic": "0.133.0"},
        "checks": [],
    }

    def start():
        process = subprocess.Popen(
            base, cwd=repo, env=environment, stdout=log, stderr=log
        )
        wait(
            lambda: (
                (
                    (project_data / "session.json").is_file()
                    and json.loads((project_data / "session.json").read_text())["pid"]
                    == process.pid
                )
                or process.poll() is not None
            )
        )
        assert process.poll() is None, "Watch startup failed; inspect its private log"
        session = json.loads((project_data / "session.json").read_text())
        client = Client(session["url"], project_data / "admin-token")
        workspace = json.loads((project_data / "workspace.json").read_text())
        client.project = workspace["project_id"]
        return process, client

    try:
        watcher, client = start()
        project_id = client.project
        report["checks"].append("Automatic startup and stable project provisioning")
        second = subprocess.run(
            base,
            cwd=repo,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert second.returncode == 2 and "Another watch" in second.stderr
        report["checks"].append(
            "Duplicate watcher rejected without affecting the live session"
        )
        for command in (
            [
                str(ROOT / ".venv/bin/python"),
                str(ROOT / "packages/cli/tests/fixtures/watch_python.py"),
            ],
            ["node", str(ROOT / "packages/cli/tests/fixtures/watch_node.cjs")],
        ):
            launched = subprocess.run(
                [cli, "run", "--repo", str(repo), "--", *command],
                cwd=repo,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if launched.returncode:
                # The fixtures contain mock values only; failure detail stays local.
                (state / "fixture-failure.txt").write_text(
                    launched.stdout + launched.stderr
                )
            assert launched.returncode == 0, (
                "Provider fixture failed; inspect local fixture-failure.txt"
            )
        metrics = wait(
            lambda: (
                m
                if (m := client.request("/api/v1/metrics/overview"))["llm_calls"] == 21
                else None
            )
        )
        assert metrics["llm_errors"] == 2 and metrics["active_runs"] == 0
        assert (
            metrics["unsupported_claims"] is None
            and metrics["grounding_evaluations"] == 0
        )
        assert len(client.request("/api/v1/agents")) == 1
        runs = client.request("/api/v1/runs")["items"]
        traces = [client.request(f"/api/v1/runs/{r['id']}/trace") for r in runs]
        serialized = json.dumps(traces)
        for sentinel in (
            "private-prompt-sentinel",
            "private-answer-sentinel",
            "private-error-sentinel",
            "mock-provider-key",
            "private-tool-result-sentinel",
        ):
            assert sentinel not in serialized
        llms = [s for trace in traces for s in trace["spans"] if s["kind"] == "llm"]
        successful = [span for span in llms if span["status"] == "completed"]
        assert all(span["attributes"]["usage_observed"] for span in successful)
        assert all(
            (s["input_tokens"], s["output_tokens"]) in ((11, 7), (13, 5), (5, 3))
            for s in successful
        )
        grouped = next(
            trace for trace in traces if trace["run"]["name"] == "grouped_agent"
        )
        assert (
            len(grouped["spans"]) == 7
            and sum(s["kind"] == "llm" for s in grouped["spans"]) == 1
        )
        report["checks"].extend(
            [
                "Python/Node real provider SDKs, sync/async calls, SSE streams and exceptions",
                "Usage/timing persisted with metadata-only telemetry",
                "Whole-agent/tool grouping without duplicate LLM spans",
                "Grounding remains unassessed without an evaluator",
            ]
        )
        incident = wait(
            lambda: next(iter(client.request("/api/v1/incidents")["items"]), None)
        )
        shell = Repl(client, stdout=io.StringIO(), wait_seconds=30)
        shell.onecmd(f"investigate {incident['id']}")
        assert (
            "Error:" not in shell.stdout.getvalue()
            and shell.investigation(shell.last_investigation)["status"] == "complete"
        )
        report["checks"].append(
            "Captured tool-loop telemetry produces an evidence-grounded investigation"
        )
        grounded = subprocess.run(
            [
                cli,
                "run",
                "--repo",
                str(repo),
                "--",
                str(ROOT / ".venv/bin/python"),
                str(ROOT / "packages/cli/tests/fixtures/watch_python.py"),
            ],
            env={**environment, "WATCH_FIXTURE_MODE": "grounding"},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert grounded.returncode == 0
        metrics = wait(
            lambda: (
                m
                if (m := client.request("/api/v1/metrics/overview"))[
                    "grounding_evaluations"
                ]
                == 1
                else None
            )
        )
        assert metrics["llm_calls"] == 22 and metrics["unsupported_claims"] == 2
        report["checks"].append(
            "Explicit grounding assessment displayed without duplicate capture"
        )
        for filename in (
            "admin-token",
            "ingestion-key",
            "workspace.json",
            "session.json",
        ):
            assert (project_data / filename).stat().st_mode & 0o777 == 0o600
        assert list(repo.iterdir()) == []
        report["checks"].append("Project files unchanged and credential files private")
        if args.browser:
            url = next(
                line.split("Dashboard: ", 1)[1]
                for line in log_path.read_text().splitlines()
                if "Dashboard: " in line
            )
            subprocess.run(
                [
                    "npm",
                    "--prefix",
                    str(ROOT / "apps/web"),
                    "run",
                    "test:e2e",
                    "--",
                    "--project=workflow",
                    "tests/e2e/landing.spec.ts",
                    "tests/e2e/explorers.spec.ts",
                    "tests/e2e/watch.spec.ts",
                ],
                cwd=ROOT,
                env={
                    **environment,
                    "PLAYWRIGHT_BASE_URL": url.split("/dashboard", 1)[0],
                },
                check=True,
                timeout=180,
            )
            report["checks"].append(
                "Production browser checks: project selection, live metrics, grounding, public docs, shareable filters, history, pagination, and responsive layouts"
            )
        if args.hold_for_browser:
            report["dashboard_url"] = next(
                line.split("Dashboard: ", 1)[1]
                for line in log_path.read_text().splitlines()
                if "Dashboard: " in line
            )
            (state / "browser-ready.json").write_text(json.dumps(report))
            print(
                f"Watch browser check ready: {state / 'browser-ready.json'}", flush=True
            )
            wait(lambda: (state / "browser-done").is_file(), seconds=180)
        watcher.send_signal(signal.SIGTERM)
        watcher.wait(timeout=30)
        assert not (project_data / "session.json").exists()
        watcher, restarted = start()
        assert (
            restarted.project == project_id
            and restarted.request("/api/v1/metrics/overview")["llm_calls"] == 22
        )
        report["checks"].append("Graceful shutdown and restart persistence")
        watcher.kill()
        watcher.wait(timeout=5)
        # Service supervisors detect parent death; the next start clears the old lease.
        time.sleep(3)
        watcher, restarted = start()
        assert restarted.project == project_id
        watcher.send_signal(signal.SIGTERM)
        watcher.wait(timeout=30)
        watcher = None
        report["checks"].append(
            "Unexpected parent death releases owned services and allows restart"
        )
        commands = f"watch --runtime {ROOT} --no-open --repo '{repo}' --port 0 --api-port 0\nstatus\nincidents\nstop\nexit\n"
        repl = subprocess.run(
            [cli, "repl"],
            input=commands,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert (
            repl.returncode == 0
            and "Monitoring continues in the background" in repl.stdout
            and "Connected to" in repl.stdout
            and "Watch stopped" in repl.stdout
        )
        assert "Error:" not in repl.stdout
        report["checks"].append(
            "REPL watch remains interactive and stop/exit preserve records"
        )
        once = subprocess.run(
            [*base, "--once", "--", sys.executable, "-c", "raise SystemExit(7)"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert once.returncode == 7 and not (project_data / "session.json").exists()
        report["checks"].append(
            "Finite watch preserves application exit code and stops services"
        )
        report["llm_calls"] = 22
        report["llm_errors"] = 2
        report["unsupported_claims"] = 2
        (state / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(
            f"Watch acceptance passed: {len(report['checks'])} checks; report {state / 'report.json'}",
            flush=True,
        )
    finally:
        if watcher and watcher.poll() is None:
            watcher.send_signal(signal.SIGTERM)
            watcher.wait(timeout=30)
        log.close()
        provider.shutdown()
        provider.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=str(ROOT / ".local/watch-acceptance"))
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--hold-for-browser", action="store_true")
    parser.add_argument("--browser", action="store_true")
    run(parser.parse_args())
