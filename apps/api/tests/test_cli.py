"""Drive the shipped urllib client against the real API without network credentials."""

import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages/cli"))

from agentscope_cli.repl import Client, Repl


def test_repl_demo_requires_separate_policy_approval_and_execution(client, monkeypatch):
    monkeypatch.setenv(
        "AGENTSCOPE_ADMIN_TOKEN", "test-dashboard-token-not-a-real-credential"
    )
    api = Client("http://localhost:8000")
    methods = []

    def open_request(request, timeout):
        methods.append((request.method, urlsplit(request.full_url).path))
        response = client.request(
            request.method,
            urlsplit(request.full_url).path,
            headers=dict(request.header_items()),
            content=request.data,
        )
        if response.status_code >= 400:
            raise HTTPError(
                request.full_url,
                response.status_code,
                "API error",
                {},
                io.BytesIO(response.content),
            )
        return io.BytesIO(response.content)

    monkeypatch.setattr(api.opener, "open", open_request)
    output = io.StringIO()
    shell = Repl(api, stdout=output, wait_seconds=15)
    shell.onecmd("demo")
    assert "Error:" not in output.getvalue()
    assert "SYNTHETIC DEMO" in output.getvalue()
    assert "Evidence references: 8" in output.getvalue()
    investigation = shell.investigation(shell.last_investigation)
    proposal = investigation["incident"]["remediation"]
    proposal_id = proposal["id"]
    assert proposal["status"] == "proposed"
    assert not any(path.endswith(("/approve", "/execute")) for _, path in methods)
    assert api.request("/api/v1/settings")["allow_demo_control"] is False
    shell.onecmd(f"execute {proposal_id}")
    assert "Operation rejected" in output.getvalue()
    shell.onecmd(f"approve {proposal_id}")
    proposal = shell.investigation(shell.last_investigation)["incident"]["remediation"]
    assert proposal["status"] == "approved"
    assert "executed_at" not in proposal
    shell.onecmd(f"execute {proposal_id}")
    assert (
        shell.investigation(shell.last_investigation)["incident"]["remediation"][
            "status"
        ]
        == "approved"
    )
    shell.onecmd("policy demo on")
    shell.onecmd(f"execute {proposal_id}")
    first = shell.investigation(shell.last_investigation)
    assert first["incident"]["remediation"]["verification"]["result"] == "PENDING"
    shell.onecmd(f"execute {proposal_id}")
    shell.onecmd(f"approve {proposal_id}")
    second = shell.investigation(shell.last_investigation)
    assert (
        first["incident"]["remediation"]["executed_at"]
        == second["incident"]["remediation"]["executed_at"]
    )
    audits = second["incident"]["audit"]
    assert sum(a["action"] == "remediation.approved" for a in audits) == 1
    assert sum(a["action"] == "remediation.executed" for a in audits) == 1
    assert "test-dashboard-token-not-a-real-credential" not in output.getvalue()
    assert (
        json.dumps(api.request("/api/v1/runs")["items"]).count(
            "Verify synthetic recovery"
        )
        == 1
    )
