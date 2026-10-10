import argparse
import io
import json
import os

import pytest
from agentscope_cli.repl import Client, ClientError, Repl, main
from agentscope_cli.watch import (
    add_watch_arguments,
    exclusive,
    private_json,
    run_existing,
    validate_arguments,
)


def arguments(*values):
    parser = argparse.ArgumentParser()
    add_watch_arguments(parser)
    return parser.parse_args(values)


def test_watch_paths_and_explicit_commands():
    args = arguments("/tmp/project with spaces", "--", "python", "app.py")
    validate_arguments(args)
    assert args.repo == "/tmp/project with spaces"
    assert args.application == ["--", "python", "app.py"]
    with pytest.raises(ClientError, match="after --"):
        validate_arguments(arguments("python", "app.py"))
    with pytest.raises(ClientError, match="requires"):
        validate_arguments(arguments("--once", "--"))
    with pytest.raises(ClientError, match="Ports"):
        validate_arguments(arguments("--port", "99999"))


def test_a_second_watcher_cannot_acquire_the_same_project(tmp_path):
    path = tmp_path / "watch.lock"
    with (
        exclusive(path),
        pytest.raises(ClientError, match="Another watch"),
        exclusive(path),
    ):
        pass
    with exclusive(path):
        pass


def test_connection_files_are_private_and_contain_no_ingestion_secret(tmp_path):
    path = tmp_path / "workspace.json"
    private_json(path, {"project_id": "a-project", "repository": "local-app"})
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())["project_id"] == "a-project"


def test_run_without_a_session_is_actionable(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_HOME", str(tmp_path / "state"))
    with pytest.raises(ClientError, match="Start agentscope watch"):
        run_existing(tmp_path, ["--", "python", "app.py"])


def test_repl_monitor_help_is_offline_and_invalid_input_does_not_exit(
    monkeypatch, capsys
):
    monkeypatch.setattr(Repl, "cmdloop", lambda self: self.onecmd("help watch"))
    assert main(["repl"]) == 0
    assert "background" in capsys.readouterr().out
    output = io.StringIO()
    shell = Repl(Client("http://127.0.0.1:8000"), stdout=output)
    shell.onecmd("watch 'unterminated")
    assert "Unbalanced quoting" in output.getvalue()
    shell.onecmd("stop")
    assert "No local watch" in output.getvalue()
