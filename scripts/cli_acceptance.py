#!/usr/bin/env python3
"""Repeatable CLI acceptance against an existing server; creates one labeled demo project."""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/cli"))
from agentscope_cli.repl import Client, ClientError, Repl


def require(condition, message):
    if not condition:
        raise ClientError(message)


def acceptance(client, dashboard):
    started = time.monotonic()
    shell = Repl(client, dashboard=dashboard)
    shell.do_demo("")
    investigation = shell.investigation(shell.last_investigation)
    proposal = investigation["incident"]["remediation"]
    proposal_id = proposal["id"]
    require(proposal["status"] == "proposed", "Demo unexpectedly approved or executed.")
    require(
        not client.request("/api/v1/settings")["allow_demo_control"],
        "Demo unexpectedly enabled intervention.",
    )
    try:
        client.request(f"/api/v1/remediations/{proposal_id}/execute", "POST")
    except ClientError as exc:
        require("Operation rejected" in str(exc), "Unexpected pre-approval failure.")
    else:
        raise ClientError("Execution succeeded without approval.")
    shell.do_policy("demo on")
    shell.do_approve(proposal_id)
    approved = shell.investigation(shell.last_investigation)["incident"]["remediation"]
    require(
        approved["status"] == "approved" and not approved.get("executed_at"),
        "Approval executed an action.",
    )
    shell.do_execute(proposal_id)
    pending = shell.investigation(shell.last_investigation)["incident"]["remediation"]
    require(
        pending["verification"]["result"] == "PENDING",
        "Recovery was declared before observation.",
    )
    shell.do_verify(shell.last_investigation)
    recovered = shell.investigation(shell.last_investigation)
    remediation = recovered["incident"]["remediation"]
    require(
        remediation["verification"]["result"] == "VERIFIED_RECOVERED",
        "Recovery not verified by persisted evidence.",
    )
    follow_up_id = remediation["verification"]["evidence_ids"][0]
    follow_up = client.request(f"/api/v1/runs/{follow_up_id}")
    executed = datetime.fromisoformat(remediation["executed_at"])
    checked = datetime.fromisoformat(remediation["verification"]["checked_at"])
    require(
        datetime.fromisoformat(follow_up["started_at"]) >= executed,
        "Follow-up predates intervention.",
    )
    observation_seconds = (checked - executed).total_seconds()
    require(observation_seconds >= 15, "Recovery observation window was bypassed.")
    for action in ("approve", "execute", "execute"):
        client.request(f"/api/v1/remediations/{proposal_id}/{action}", "POST")
    unchanged = shell.investigation(shell.last_investigation)
    require(
        unchanged["incident"]["audit"] == recovered["incident"]["audit"],
        "Repeated actions duplicated audit records.",
    )
    runs = client.request("/api/v1/runs")["items"]
    require(
        sum(run["name"] == "Verify synthetic recovery" for run in runs) == 1,
        "Duplicate follow-up execution.",
    )
    require(all(run["synthetic"] for run in runs), "Demo contains unlabeled telemetry.")
    return {
        "execution": "local",
        "status": "passed",
        "project": client.project,
        "investigation": shell.last_investigation,
        "synthetic_runs": len(runs),
        "evidence_references": len(recovered["report"]["evidence"]),
        "verification": remediation["verification"]["result"],
        "observation_seconds": round(observation_seconds, 2),
        "duplicate_actions": 0,
        "seconds": round(time.monotonic() - started, 2),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--dashboard", default="http://127.0.0.1:3000")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--report", help="Optional path for sanitized measurements.")
    args = parser.parse_args()
    try:
        result = acceptance(Client(args.url, args.token_file), args.dashboard)
    except ClientError as exc:
        parser.exit(1, f"Acceptance failed: {exc}. Server records retained.\n")
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
