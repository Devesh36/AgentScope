import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentscope_cli.repl import Client, Repl
from agentscope_cli.terminal import Terminal


def test_guidance_slash_aliases_and_comments_are_offline(monkeypatch):
    output = io.StringIO()
    shell = Repl(Client("http://127.0.0.1:8000"), stdout=output)

    def fail(*args, **kwargs):
        pytest.fail("Offline help requested a server connection")

    monkeypatch.setattr(shell.client, "request", fail)
    shell.preloop()
    for command in ("/help", "/guide", "help run", "watc", "clear"):
        shell.onecmd(command)
    value = output.getvalue()
    assert "connectivity has not been checked" in value
    assert "Did you mean watch?" in value
    assert "agentscope run -- python app.py" in value
    assert "\033" not in value
    assert "/status" in shell.completenames("/sta")


def test_rendering_wraps_and_neutralizes_terminal_control_sequences(monkeypatch):
    monkeypatch.setenv("COLUMNS", "32")
    output = io.StringIO()
    terminal = Terminal(output)
    terminal.banner("test", "/long/path/" * 10 + "\033[2J", "http://127.0.0.1:8000")
    terminal.record("Unsafe\033]0;title\007", "Description" * 12, "a" * 36)
    assert "\033" not in output.getvalue()
    assert "\007" not in output.getvalue()
    assert all(len(line) <= 32 for line in output.getvalue().splitlines())


def test_no_color_overrides_interactive_terminal(monkeypatch):
    output = io.StringIO()
    output.isatty = lambda: True
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    terminal = Terminal(output)
    assert "\033[33m" in terminal.style("Amber")
    assert terminal.style("Prompt", prompt=True).startswith("\001\033")
    monkeypatch.setenv("NO_COLOR", "")
    assert Terminal(output).style("Plain") == "Plain"


def test_status_distinguishes_unassessed_from_zero_and_json_is_parseable(monkeypatch):
    output = io.StringIO()
    shell = Repl(Client("http://localhost:8000"), stdout=output)
    shell.client.project = "project-123"
    metrics = {"llm_calls": 2, "unsupported_claims": None, "cost": None}

    def request(path, **kwargs):
        return (
            [{"id": "project-123", "name": "Banking app"}]
            if path.endswith("projects")
            else metrics
        )

    monkeypatch.setattr(shell.client, "request", request)
    shell.onecmd("/status")
    assert "Not evaluated" in output.getvalue()
    assert "Unavailable" in output.getvalue()
    assert "Banking app" in shell.prompt
    metrics.update(unsupported_claims=0, cost=0)
    output.seek(0)
    output.truncate(0)
    shell.onecmd("status --json")
    value = json.loads(output.getvalue())
    assert value["metrics"]["unsupported_claims"] == 0
    assert value["metrics"]["cost"] == 0


def test_foreground_run_requires_watch_and_preserves_quoted_arguments(monkeypatch):
    output = io.StringIO()
    shell = Repl(Client("http://localhost:8000"), stdout=output)
    shell.onecmd("run -- python app.py")
    assert "Start watch" in output.getvalue()
    calls = []
    monkeypatch.setattr(
        "agentscope_cli.watch.run_existing",
        lambda repo, args: calls.append((repo, args)) or 7,
    )
    shell.watch_session = SimpleNamespace(repo=Path("/tmp/project with spaces"))
    shell.onecmd('run -- python "app with spaces.py"')
    assert calls == [
        (Path("/tmp/project with spaces"), ["--", "python", "app with spaces.py"])
    ]
    assert "exited with code 7" in output.getvalue()
    shell.onecmd('run -- python "unterminated')
    assert "Unbalanced quoting" in output.getvalue()
    assert len(calls) == 1
