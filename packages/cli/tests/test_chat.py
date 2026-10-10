"""Exercise actual provider wire formats, conversational routing, and setup boundaries."""

import argparse
import io
import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from agentscope_cli.chat import (
    PROVIDERS,
    ChatError,
    Conversation,
    Models,
    Parser,
    arguments,
)
from agentscope_cli.repl import Client, Repl, main


@pytest.fixture(autouse=True)
def private_chat_home(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTSCOPE_HOME", str(tmp_path / "home"))
    for _, _, _, variable in PROVIDERS.values():
        if variable:
            monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def provider_server():
    calls = []
    state = {"status": 200, "reply": None, "redirect": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, dict(self.headers), value))
            self.send_response(state["status"])
            if state["redirect"]:
                self.send_header("Location", state["redirect"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            answer = "I am AgentScope. I help you monitor and understand AI agents."
            response = state["reply"]
            if response is None:
                if self.path.endswith("/responses"):
                    response = {
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": answer}],
                            }
                        ]
                    }
                elif self.path.endswith("/messages"):
                    response = {"content": [{"type": "text", "text": answer}]}
                elif self.path.endswith(":generateContent"):
                    response = {
                        "candidates": [{"content": {"parts": [{"text": answer}]}}]
                    }
                else:
                    response = {"choices": [{"message": {"content": answer}}]}
            self.wfile.write(json.dumps(response).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def configure(provider, origin=None, name=None, secret=None):
    models = Models()
    options = argparse.Namespace(
        provider=provider,
        name=name,
        model="fixture-model",
        base_url=(origin + "/v1") if origin else None,
        key_env=None,
        key_file=None,
    )
    models.save(options, secret=secret)
    return models


@pytest.mark.parametrize(
    "provider", [p for p in PROVIDERS if p not in ("codex", "claude-cli")]
)
def test_real_http_protocols_identity_and_follow_up(provider, provider_server):
    origin, calls, _ = provider_server
    models = configure(
        provider,
        origin,
        secret="test-only-provider-key"
        if provider not in ("compatible", "ollama")
        else None,
    )
    chat = Conversation(models)
    assert "AgentScope" in chat.ask("Who are you?")[2]
    chat.ask("How do I start monitoring?")
    path, headers, body = calls[-1]
    headers = {name.lower(): value for name, value in headers.items()}
    protocol = PROVIDERS[provider][0]
    if protocol == "responses":
        assert path == "/v1/responses" and body["store"] is False
        assert "You are AgentScope" in body["instructions"]
        history = body["input"]
        assert headers["authorization"] == "Bearer test-only-provider-key"
    elif protocol == "anthropic":
        assert path == "/v1/messages"
        assert "You are AgentScope" in body["system"]
        assert headers["x-api-key"] == "test-only-provider-key"
        assert headers["anthropic-version"] == "2023-06-01"
        history = body["messages"]
    elif protocol == "gemini":
        assert path == "/v1/models/fixture-model:generateContent"
        assert headers["x-goog-api-key"] == "test-only-provider-key"
        assert "You are AgentScope" in body["systemInstruction"]["parts"][0]["text"]
        assert [m["role"] for m in body["contents"]] == ["user", "model", "user"]
        assert body["contents"][0]["parts"][0]["text"] == "Who are you?"
        return
    else:
        assert path == "/v1/chat/completions"
        assert "You are AgentScope" in body["messages"][0]["content"]
        history = body["messages"][1:]
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert history[0]["content"] == "Who are you?"
    assert "test-only-provider-key" not in json.dumps(body)


def test_ordinary_questions_do_not_execute_commands_or_connect_to_dashboard(
    provider_server, monkeypatch
):
    origin, calls, _ = provider_server
    configure("compatible", origin)
    output = io.StringIO()
    shell = Repl(Client("http://127.0.0.1:1"), stdout=output)
    monkeypatch.setattr(
        shell.client,
        "request",
        lambda *a, **k: pytest.fail("Chat unexpectedly queried telemetry"),
    )
    monkeypatch.setattr(
        shell, "do_watch", lambda arg: pytest.fail("Chat executed watch")
    )
    for question in (
        "Who are you?",
        "What are you?",
        "hello",
        "chat Tell me how watch works",
        "ask How can I monitor my app?",
    ):
        shell.onecmd(question)
    assert len(calls) == 5 and output.getvalue().count("I am AgentScope") == 5
    shell.onecmd("watc")
    shell.onecmd("/unknown-command please")
    assert len(calls) == 5
    assert "Did you mean watch?" in output.getvalue()
    shell.onecmd("chat reset")
    assert shell.conversation.history == []


def test_configuration_required_and_credentials_are_private(monkeypatch):
    output = io.StringIO()
    shell = Repl(Client("http://localhost:1"), stdout=output)
    shell.onecmd("Who are you?")
    assert "Configure AgentScope" in output.getvalue()
    models = configure("openai", secret="hidden-test-key")
    value = json.loads(models.path.read_text())
    assert "hidden-test-key" not in models.path.read_text()
    key = Path(value["profiles"]["openai"]["key_file"])
    assert key.read_text() == "hidden-test-key"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(models.path.stat().st_mode) == 0o600
    shell.onecmd("model")
    assert "hidden-test-key" not in output.getvalue()
    assert "connection not tested" in output.getvalue()


def test_interactive_first_run_wizard_and_hidden_key(monkeypatch):
    output = io.StringIO()
    output.isatty = lambda: True
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    answers = iter(["claude", "", "work", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    hidden = []
    monkeypatch.setattr(
        "getpass.getpass", lambda prompt: hidden.append(prompt) or "hidden-test-key"
    )
    shell = Repl(Client("http://localhost:1"), stdout=output)
    shell.preloop()
    name, profile = shell.models.active()
    assert name == "work" and profile["provider"] == "anthropic"
    assert len(hidden) == 1 and "hidden-test-key" not in output.getvalue()


def test_first_run_can_explicitly_select_monitoring_only(monkeypatch):
    output = io.StringIO()
    output.isatty = lambda: True
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "0")
    shell = Repl(Client("http://localhost:1"), stdout=output)
    shell.preloop()
    assert "Monitoring-only mode" in output.getvalue()
    assert not shell.models.path.exists()


def test_project_context_is_opt_in_filtered_and_history_isolated(
    provider_server, monkeypatch
):
    origin, calls, _ = provider_server
    configure("compatible", origin)
    shell = Repl(Client("http://localhost:1"), stdout=io.StringIO())
    shell.client.project = "first"
    fetches = []

    def metrics(path):
        fetches.append(path)
        return {
            "llm_calls": 4,
            "unsupported_claims": None,
            "tokens": 60,
            "agents": [{"secret": "private trace content"}],
        }

    monkeypatch.setattr(shell.client, "request", metrics)
    shell.onecmd("Who are you?")
    assert fetches == []
    shell.onecmd("context on")
    shell.onecmd("What happened in my project?")
    body = calls[-1][2]
    assert len(body["messages"]) == 2
    assert '"llm_calls": 4' in body["messages"][0]["content"]
    assert "private trace content" not in json.dumps(body)
    shell.client.project = "second"
    shell.onecmd("How is this project doing?")
    assert len(calls[-1][2]["messages"]) == 2
    shell.onecmd("context off")
    shell.onecmd("Who are you?")
    assert "Current project summary" not in calls[-1][2]["messages"][0]["content"]
    assert len(fetches) == 2


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_provider_errors_are_safe_and_do_not_append_failed_turns(
    status, provider_server
):
    origin, _calls, state = provider_server
    models = configure("openai", origin, secret="private-test-key")
    chat = Conversation(models)
    chat.ask("Who are you?")
    before = chat.history.copy()
    state.update(
        status=status, reply={"error": "private-test-key secret upstream diagnostic"}
    )
    with pytest.raises(ChatError, match=f"HTTP {status}") as caught:
        chat.ask("Failed question")
    assert "private-test-key" not in str(caught.value) and "diagnostic" not in str(
        caught.value
    )
    assert chat.history == before
    state["status"] = 200
    state["reply"] = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "private-test-key"}],
            }
        ]
    }
    assert chat.ask("Retry question")[2] == "[credential redacted]"


def test_redirects_never_forward_provider_credentials(provider_server):
    origin, calls, state = provider_server
    state.update(status=302, redirect=origin + "/credential-theft")
    models = configure("openai", origin, secret="private-test-key")
    with pytest.raises(ChatError, match="HTTP 302"):
        Conversation(models).ask("Who are you?")
    assert len(calls) == 1 and calls[0][0] == "/v1/responses"


@pytest.mark.parametrize(
    "value",
    [
        "http://remote.example/v1",
        "https://key@remote.example/v1",
        "https://example.com/v1?api_key=secret",
        "https://example.com:bad/v1",
    ],
)
def test_rejects_unsafe_provider_urls(value):
    with pytest.raises(ChatError):
        Models().save(
            argparse.Namespace(
                provider="openai",
                name=None,
                model=None,
                base_url=value,
                key_env=None,
                key_file=None,
            )
        )


def test_parser_does_not_echo_pasted_credentials():
    parser = Parser(add_help=False)
    arguments(parser)
    with pytest.raises(ChatError) as caught:
        parser.parse_args(["openai", "--api-key", "private-test-key"])
    assert "private-test-key" not in str(caught.value)


def test_missing_keys_and_malformed_provider_response_fail_clearly(provider_server):
    origin, calls, state = provider_server
    models = configure("openai", origin)
    with pytest.raises(ChatError, match="credential is missing"):
        Conversation(models).ask("Who are you?")
    assert calls == []
    models = configure("compatible", origin)
    state["reply"] = []
    with pytest.raises(ChatError, match="unsupported response"):
        Conversation(models).ask("Who are you?")


def test_model_switch_and_bounded_history(provider_server):
    origin, calls, _ = provider_server
    models = configure("compatible", origin, name="local")
    chat = Conversation(models)
    for i in range(14):
        chat.ask(f"Question {i}")
    assert len(calls[-1][2]["messages"]) <= 22
    configure("openai", origin, name="cloud", secret="test-only-key")
    chat.ask("New provider")
    assert calls[-1][2]["input"] == [{"role": "user", "content": "New provider"}]
    models.use("local")
    chat.ask("Back to local")
    assert len(calls[-1][2]["messages"]) == 2


@pytest.mark.parametrize(
    "provider,program", [("codex", "codex"), ("claude-cli", "claude")]
)
def test_cli_adapters_use_stdin_isolation_and_existing_login(
    provider, program, tmp_path, monkeypatch
):
    directory = tmp_path / "bin"
    directory.mkdir()
    capture = tmp_path / "capture.json"
    executable = directory / program
    executable.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ["CHAT_TEST_CAPTURE"]).write_text(json.dumps({"argv":sys.argv,"cwd":os.getcwd(),"input":sys.stdin.read()}))
if Path(sys.argv[0]).name == "codex":
 print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"I am AgentScope."}}))
else:
 print(json.dumps({"result":"I am AgentScope.","is_error":False}))
""")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("CHAT_TEST_CAPTURE", str(capture))
    models = configure(provider)
    assert Conversation(models).ask("Who are you?")[2] == "I am AgentScope."
    value = json.loads(capture.read_text())
    assert "Who are you?" in value["input"] and "You are AgentScope" in value["input"]
    assert "Who are you?" not in " ".join(value["argv"])
    assert value["cwd"] != str(Path.cwd()) and not Path(value["cwd"]).exists()
    if provider == "codex":
        assert "--ephemeral" in value["argv"] and "read-only" in value["argv"]
        assert "shell_tool" in value["argv"] and "mcp_servers={}" in value["argv"]
        assert "unified_exec" in value["argv"]
    else:
        assert (
            "--no-session-persistence" in value["argv"]
            and "--strict-mcp-config" in value["argv"]
        )
        assert value["argv"][value["argv"].index("--tools") + 1] == ""


def test_top_level_setup_reuses_environment_without_exposing_key(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    assert main(["configure", "openai"]) == 0
    _, profile = Models().active()
    assert profile["key_env"] == "OPENAI_API_KEY"
    assert "private-test-key" not in capsys.readouterr().out
