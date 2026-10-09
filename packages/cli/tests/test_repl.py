import io
from urllib.error import HTTPError, URLError

import pytest
from agentscope_cli.repl import Client, ClientError, NoRedirect, Repl, main


def test_empty_line_never_repeats_mutation():
    shell = Repl(Client("http://127.0.0.1:8000"), stdout=io.StringIO())
    shell.lastcmd = "demo"
    calls = []
    shell.do_demo = calls.append
    shell.onecmd("")
    assert calls == []


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:secret@example.com",
        "https://example.com/api",
        "https://example.com?token=secret",
        "file:///tmp/api",
    ],
)
def test_rejects_unsafe_server_origins(url):
    with pytest.raises(ClientError):
        Client(url)


def test_redirects_never_forward_admin_credentials():
    assert (
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example")
        is None
    )


def test_server_failure_does_not_print_response_or_credentials(monkeypatch):
    client = Client("http://127.0.0.1:8000")
    monkeypatch.setenv("AGENTSCOPE_ADMIN_TOKEN", "test-private-token")
    for failure in [
        HTTPError(
            "https://private", 500, "secret response", {}, io.BytesIO(b"secret body")
        ),
        URLError("private diagnostic"),
    ]:

        def fail(*args, failure=failure, **kwargs):
            raise failure

        monkeypatch.setattr(client.opener, "open", fail)
        with pytest.raises(ClientError) as caught:
            client.request("/api/v1/projects", scoped=False)
        assert "secret" not in str(caught.value)
        assert "private" not in str(caught.value)
        assert "substituted" in str(caught.value)


def test_help_and_requested_alias_work_offline(monkeypatch, capsys):
    monkeypatch.setattr(Repl, "cmdloop", lambda self: self.onecmd("help"))
    assert main(["Repl"]) == 0
    output = capsys.readouterr().out
    assert "demo" in output and "approve" in output and "execute" in output


def test_missing_or_empty_token_files_fail_clearly(tmp_path):
    path = tmp_path / "token"
    client = Client("http://localhost:8000", token_file=path)
    with pytest.raises(ClientError, match="Cannot read"):
        client.token()
    path.write_text("\n")
    with pytest.raises(ClientError, match="nonempty"):
        client.token()


def test_invalid_scenario_makes_no_server_requests():
    output = io.StringIO()
    shell = Repl(Client("http://localhost:8000"), stdout=output)
    shell.onecmd("demo unknown")
    assert shell.client.project is None
    assert "Scenarios:" in output.getvalue()
