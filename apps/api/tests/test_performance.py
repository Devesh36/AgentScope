"""Guard read bounds, exact metrics, atomic batches, and watch SDK reuse."""

import threading
from datetime import timedelta
from uuid import uuid4

from agentscope_sdk import AgentScope
from app.db import Agent, Run, Session, engine, now
from app.main import agents, overview, runs
from sqlalchemy import event as sql_event
from test_workflows import agent, event


def test_history_reads_have_bounded_queries_and_previews(client, headers):
    project = headers["X-Project-ID"]
    with Session() as db:
        for i in range(12):
            item = Agent(id=str(uuid4()), project_id=project, name=f"App {i}")
            db.add(item)
            db.flush()
            for j in range(12):
                run = Run(
                    id=str(uuid4()),
                    project_id=project,
                    agent_id=item.id,
                    external_id=str(uuid4()),
                    started_at=now() - timedelta(minutes=j),
                    ended_at=now(),
                    status="completed",
                    input_tokens=2,
                    output_tokens=1,
                )
                db.add(run)
        db.commit()
    owner = threading.get_ident()
    queries = []

    def count(conn, cursor, statement, params, context, many):
        if threading.get_ident() == owner and statement.lstrip().startswith("SELECT"):
            queries.append(statement)

    sql_event.listen(engine, "before_cursor_execute", count)
    try:
        with Session() as db:
            result = overview(db, project, hours=24, synthetic=None)
            assert result["total_runs"] == 144 and result["tokens"] == 432
            assert all(len(a["recent_runs"]) == 5 for a in result["agents"])
            assert all(a["run_count"] == 12 for a in result["agents"])
            assert len(queries) <= 16
        queries.clear()
        with Session() as db:
            assert len(agents(db, project)) == 12
            assert len(queries) <= 6
        queries.clear()
        with Session() as db:
            page = runs(
                db,
                project,
                search="",
                status=None,
                synthetic=None,
                hours=24,
                limit=50,
                offset=0,
            )
            assert len(page["items"]) == 50 and page["total"] == 144
            assert len(queries) <= 4
    finally:
        sql_event.remove(engine, "before_cursor_execute", count)


def test_time_buckets_preserve_future_records_and_zero_grounding(client, headers):
    a = agent(client, headers)
    events = []
    for index, minutes in enumerate((0, 1, 2)):
        start = now() + timedelta(minutes=minutes)
        root = event(
            a["id"],
            run_id=f"future-{index}",
            trace_id=f"{index + 1:032x}",
            started_at=start.isoformat(),
            ended_at=(start + timedelta(seconds=1)).isoformat(),
        )
        llm = {
            **root,
            "event_id": str(uuid4()),
            "span_id": "2" * 16,
            "parent_span_id": root["span_id"],
            "kind": "llm",
            "input_tokens": 3,
            "attributes": {
                "grounding": {"unsupported_claims": 0, "evaluator": "reference"}
            },
        }
        events.extend([root, llm])
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": events}
        ).status_code
        == 202
    )
    value = client.get("/api/v1/metrics/overview", headers=headers).json()
    assert value["total_runs"] == 3 and value["tokens"] == 9
    assert value["grounding_evaluations"] == 3 and value["unsupported_claims"] == 0
    assert sum(bucket["runs"] for bucket in value["series"]) == 3
    assert sum(bucket["input_tokens"] for bucket in value["series"]) == 9
    assert value["series"][-1]["runs"] == 3


def test_latency_keeps_microseconds_and_rounding_ties(client, headers):
    a = agent(client, headers)
    start = now().replace(microsecond=0) - timedelta(seconds=10)
    events = [
        event(
            a["id"],
            run_id=f"precise-{index}",
            trace_id=f"{index + 1:032x}",
            started_at=start.isoformat(),
            ended_at=(start + timedelta(microseconds=micros)).isoformat(),
        )
        for index, micros in enumerate((500, 10_500, 250_500, 1_000_500))
    ]
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": events}
        ).status_code
        == 202
    )
    value = client.get("/api/v1/metrics/overview", headers=headers).json()
    assert value["latency_p50"] == 250
    assert value["latency_p95"] == 1000 and value["latency_p99"] == 1000
    assert value["average_latency_ms"] == 316
    assert value["agents"][0]["average_latency_ms"] == 316


def test_batch_duplicates_conflicts_and_terminal_order_are_atomic(client, headers):
    first = agent(client, headers)
    second = agent(client, headers, name="Second app")
    completed = event(first["id"])
    assert (
        client.post(
            "/api/v1/telemetry/events",
            headers=headers,
            json={"events": [completed, completed]},
        ).json()["duplicates"]
        == 1
    )
    older = {
        **completed,
        "event_id": str(uuid4()),
        "status": "running",
        "ended_at": None,
    }
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": [older]}
        ).status_code
        == 202
    )
    assert (
        client.get("/api/v1/runs", headers=headers).json()["items"][0]["status"]
        == "completed"
    )
    new = event(first["id"], run_id="conflicting-run", trace_id="a" * 32)
    conflict = {**new, "event_id": str(uuid4()), "agent_id": second["id"]}
    assert (
        client.post(
            "/api/v1/telemetry/events",
            headers=headers,
            json={"events": [new, conflict]},
        ).status_code
        == 409
    )
    assert client.get("/api/v1/runs", headers=headers).json()["total"] == 1


def test_watch_sdk_exports_without_registering_again(monkeypatch, tmp_path):
    key = tmp_path / "key"
    key.write_text("test-ingestion-key")
    identifier = str(uuid4())
    for name, value in {
        "AGENTSCOPE_WATCH_URL": "http://127.0.0.1:8000",
        "AGENTSCOPE_WATCH_KEY_FILE": str(key),
        "AGENTSCOPE_WATCH_AGENT_NAME": "App",
        "AGENTSCOPE_WATCH_AGENT_ID": identifier,
    }.items():
        monkeypatch.setenv(name, value)
    calls = []

    def request(self, path, body):
        calls.append((path, body))
        return {"accepted": len(body["events"])}

    monkeypatch.setattr(AgentScope, "_request", request)
    with AgentScope.from_watch() as scope, scope.span("Observed app", "agent"):
        pass
    assert scope.stats["exported_events"] == 2
    assert all(path == "telemetry/events" for path, _ in calls)
    assert all(e["agent_id"] == identifier for _, body in calls for e in body["events"])
