from datetime import timedelta
from uuid import uuid4

from app.db import APIKey, Remediation, Session, TelemetryEvent, now
from app.services import investigate, process_outbox, verify_pending
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from sqlalchemy import select


def agent(client, headers, **kwargs):
    response = client.post(
        "/api/v1/agents", headers=headers, json={"name": "test-agent", **kwargs}
    )
    assert response.status_code == 201
    return response.json()


def event(agent_id, **kwargs):
    started = now() - timedelta(seconds=10)
    return {
        "event_id": str(uuid4()),
        "agent_id": agent_id,
        "run_id": "run-1",
        "trace_id": "1" * 32,
        "span_id": "1" * 16,
        "kind": "agent",
        "name": "test execution",
        "status": "completed",
        "started_at": started.isoformat(),
        "ended_at": (started + timedelta(seconds=2)).isoformat(),
        **kwargs,
    }


def test_empty_database_is_honest(client, headers):
    metrics = client.get("/api/v1/metrics/overview", headers=headers).json()
    assert metrics["registered_agents"] == 0
    assert metrics["total_runs"] == 0
    assert metrics["success_rate"] is None
    assert metrics["cost"] is None
    assert len(metrics["series"]) == 24
    assert client.get("/health/ready").json()["status"] == "ready"


def test_ingestion_deduplicates_and_preserves_unknown_pricing(client, headers):
    a = agent(client, headers)
    root = event(a["id"])
    llm = event(
        a["id"],
        event_id="llm",
        span_id="2" * 16,
        parent_span_id="1" * 16,
        kind="llm",
        model="unknown-model",
        input_tokens=100,
        output_tokens=50,
    )
    response = client.post(
        "/api/v1/telemetry/events", headers=headers, json={"events": [llm, root]}
    )
    assert response.status_code == 202
    assert response.json()["accepted"] == 2
    duplicate = client.post(
        "/api/v1/telemetry/events", headers=headers, json={"events": [llm, root]}
    ).json()
    assert duplicate["duplicates"] == 2 and duplicate["accepted"] == 0
    runs = client.get("/api/v1/runs", headers=headers).json()["items"]
    assert len(runs) == 1 and runs[0]["tokens"] == 150 and runs[0]["cost"] is None
    trace = client.get(f"/api/v1/runs/{runs[0]['id']}/trace", headers=headers).json()
    assert len(trace["spans"]) == 2
    assert (
        next(s for s in trace["spans"] if s["kind"] == "llm")["parent_span_id"]
        == root["span_id"]
    )


def test_key_hash_revocation_and_project_isolation(client, headers):
    a = agent(client, headers)
    created = client.post(
        "/api/v1/api-keys", headers=headers, json={"name": "sdk"}
    ).json()
    sdk_headers = {"Authorization": f"Bearer {created['key']}"}
    assert client.get("/api/v1/agents", headers=sdk_headers).status_code == 200
    other = client.post(
        "/api/v1/projects", headers=headers, json={"name": "Other"}
    ).json()
    assert (
        client.get(
            "/api/v1/agents", headers={**sdk_headers, "X-Project-ID": other["id"]}
        ).status_code
        == 403
    )
    other_headers = {**headers, "X-Project-ID": other["id"]}
    assert (
        client.get(f"/api/v1/agents/{a['id']}", headers=other_headers).status_code
        == 404
    )
    assert client.get("/api/v1/agents", headers=other_headers).json() == []
    assert (
        client.post(
            "/api/v1/projects", headers=sdk_headers, json={"name": "Forbidden"}
        ).status_code
        == 401
    )
    with Session() as db:
        saved = db.get(APIKey, created["id"])
        assert saved.digest != created["key"] and len(saved.digest) == 64
    listing = client.get("/api/v1/api-keys", headers=headers).json()
    assert all("digest" not in k and "key" not in k for k in listing)
    assert (
        client.delete(f"/api/v1/api-keys/{created['id']}", headers=headers).status_code
        == 204
    )
    assert client.get("/api/v1/agents", headers=sdk_headers).status_code == 401


def test_failed_batch_is_atomic_and_timestamp_validation(client, headers):
    a = agent(client, headers)
    valid = event(a["id"])
    invalid = event("nonexistent", event_id="invalid")
    assert (
        client.post(
            "/api/v1/telemetry/events",
            headers=headers,
            json={"events": [valid, invalid]},
        ).status_code
        == 404
    )
    assert client.get("/api/v1/runs", headers=headers).json()["total"] == 0
    invalid_time = event(a["id"], started_at=(now() + timedelta(hours=1)).isoformat())
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": [invalid_time]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/telemetry/events",
            headers=headers,
            content=b"x" * (2 * 1024 * 1024 + 1),
        ).status_code
        == 413
    )


def test_otlp_protobuf_and_malformed_payload(client, headers):
    a = agent(client, headers)
    message = ExportTraceServiceRequest()
    span = message.resource_spans.add().scope_spans.add().spans.add()
    span.trace_id, span.span_id, span.name = (
        bytes.fromhex("3" * 32),
        bytes.fromhex("4" * 16),
        "OTLP root",
    )
    span.start_time_unix_nano = int((now() - timedelta(seconds=3)).timestamp() * 1e9)
    span.end_time_unix_nano = int(now().timestamp() * 1e9)
    otlp_headers = {
        **headers,
        "X-Agent-ID": a["id"],
        "Content-Type": "application/x-protobuf",
    }
    response = client.post(
        "/v1/traces", headers=otlp_headers, content=message.SerializeToString()
    )
    assert (
        response.status_code == 200
        and response.headers["content-type"] == "application/x-protobuf"
    )
    trace = client.get("/api/v1/runs", headers=headers).json()["items"][0]
    assert trace["status"] == "completed"
    assert (
        client.post(
            "/v1/traces", headers=otlp_headers, content=b"bad protobuf"
        ).status_code
        == 400
    )


def test_all_five_detectors_and_evidence_grounded_investigation(client, headers):
    expected = [
        "tool_loop",
        "token_budget",
        "tool_failure",
        "stalled",
        "unexpected_workflow",
    ]
    for scenario in expected:
        response = client.post(
            "/api/v1/simulations",
            headers=headers,
            json={"scenario": scenario, "include_baseline": False, "seed": 42},
        )
        assert response.status_code == 201
    process_outbox()
    incidents = client.get("/api/v1/incidents", headers=headers).json()["items"]
    assert set(expected).issubset({i["anomaly"]["kind"] for i in incidents})
    incident = next(i for i in incidents if i["anomaly"]["kind"] == "tool_loop")
    inv = client.post(
        f"/api/v1/incidents/{incident['id']}/investigate", headers=headers
    ).json()
    investigate(inv["id"])
    result = client.get(f"/api/v1/investigations/{inv['id']}", headers=headers).json()
    assert result["status"] == "complete" and result["progress"] == 100
    assert len(result["report"]["evidence"]) == 8
    assert result["report"]["hypotheses"][0]["epistemic_status"] == "supported"
    assert set(result["report"]["hypotheses"][0]["supporting_evidence"]) <= set(
        incident["anomaly"]["evidence_ids"]
    )
    assert "confidence" not in str(result["report"])
    with Session() as db:
        stored = list(
            db.scalars(
                select(TelemetryEvent).where(
                    TelemetryEvent.run_id == incident["run_id"]
                )
            )
        )
        assert all(e.processed for e in stored)
    process_outbox()
    assert client.get("/api/v1/incidents", headers=headers).json()["total"] == len(
        incidents
    )


def test_remediation_requires_approval_and_policy_then_verifies(client, headers):
    client.post(
        "/api/v1/simulations",
        headers=headers,
        json={"scenario": "tool_loop", "include_baseline": False},
    )
    incident = next(
        i
        for i in client.get("/api/v1/incidents", headers=headers).json()["items"]
        if i["anomaly"]["kind"] == "tool_loop"
    )
    inv = client.post(
        f"/api/v1/incidents/{incident['id']}/investigate", headers=headers
    ).json()
    investigate(inv["id"])
    details = client.get(f"/api/v1/incidents/{incident['id']}", headers=headers).json()
    remediation_id = details["remediation"]["id"]
    endpoint = f"/api/v1/remediations/{remediation_id}"
    assert client.post(endpoint + "/execute", headers=headers).status_code == 409
    assert client.post(endpoint + "/approve", headers=headers).status_code == 200
    assert client.post(endpoint + "/execute", headers=headers).status_code == 409
    settings = client.get("/api/v1/settings", headers=headers).json()
    settings["allow_demo_control"] = True
    assert (
        client.put("/api/v1/settings", headers=headers, json=settings).status_code
        == 200
    )
    result = client.post(endpoint + "/execute", headers=headers).json()
    assert result["verification"]["result"] == "PENDING"
    followup = next(
        r
        for r in client.get("/api/v1/runs", headers=headers).json()["items"]
        if r["name"] == "Verify synthetic recovery"
    )
    assert followup["started_at"] >= result["executed_at"]
    verify_pending()
    assert (
        client.get(f"/api/v1/incidents/{incident['id']}", headers=headers).json()[
            "status"
        ]
        == "VERIFYING"
    )
    with Session() as db:
        r = db.get(Remediation, remediation_id)
        r.executed_at = now() - timedelta(seconds=16)
        db.commit()
    verify_pending()
    result = client.get(f"/api/v1/incidents/{incident['id']}", headers=headers).json()
    assert result["status"] == "RESOLVED"
    assert result["remediation"]["verification"]["result"] == "VERIFIED_RECOVERED"
    before = client.get("/api/v1/runs", headers=headers).json()["total"]
    assert client.post(endpoint + "/execute", headers=headers).status_code == 200
    assert client.get("/api/v1/runs", headers=headers).json()["total"] == before


def test_metrics_filters_and_known_pricing(client, headers):
    a = agent(client, headers)
    events = [
        event(a["id"]),
        event(
            a["id"],
            event_id="llm",
            span_id="2" * 16,
            parent_span_id="1" * 16,
            kind="llm",
            model="gpt-4.1-mini",
            input_tokens=1000,
            output_tokens=500,
        ),
    ]
    client.post("/api/v1/telemetry/events", headers=headers, json={"events": events})
    metrics = client.get("/api/v1/metrics/overview", headers=headers).json()
    assert (
        metrics["tokens"] == 1500
        and metrics["cost"] == 0.0012
        and metrics["success_rate"] == 100
    )
    assert sum(b["input_tokens"] for b in metrics["series"]) == 1000
    assert (
        client.get("/api/v1/metrics/overview?synthetic=true", headers=headers).json()[
            "total_runs"
        ]
        == 0
    )
    assert (
        client.get("/api/v1/runs?status=failed", headers=headers).json()["total"] == 0
    )
    assert client.get("/api/v1/runs?search=test", headers=headers).json()["total"] == 1


def test_timezone_normalization_and_malformed_otlp_json(client, headers):
    a = agent(client, headers)
    from datetime import timezone

    started = (now() - timedelta(seconds=5)).astimezone(
        timezone(timedelta(hours=5, minutes=30))
    )
    payload = event(
        a["id"],
        started_at=started.isoformat(),
        ended_at=(started + timedelta(seconds=1)).isoformat(),
    )
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": [payload]}
        ).status_code
        == 202
    )
    run = client.get("/api/v1/runs", headers=headers).json()["items"][0]
    assert run["duration_ms"] == 1000
    assert run["started_at"].endswith("+00:00")
    invalid = client.post(
        "/v1/traces",
        headers={**headers, "X-Agent-ID": a["id"], "Content-Type": "application/json"},
        json={"nonexistentField": 42},
    )
    assert invalid.status_code == 422


def test_concurrent_execution_is_idempotent(client, headers):
    from concurrent.futures import ThreadPoolExecutor

    client.post(
        "/api/v1/simulations",
        headers=headers,
        json={"scenario": "tool_loop", "include_baseline": False},
    )
    incident = client.get("/api/v1/incidents", headers=headers).json()["items"][0]
    inv = client.post(
        f"/api/v1/incidents/{incident['id']}/investigate", headers=headers
    ).json()
    investigate(inv["id"])
    remediation = client.get(
        f"/api/v1/incidents/{incident['id']}", headers=headers
    ).json()["remediation"]
    endpoint = f"/api/v1/remediations/{remediation['id']}"
    client.post(endpoint + "/approve", headers=headers)
    settings = client.get("/api/v1/settings", headers=headers).json()
    settings["allow_demo_control"] = True
    client.put("/api/v1/settings", headers=headers, json=settings)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(endpoint + "/execute", headers=headers), range(2)
            )
        )
    assert all(r.status_code == 200 for r in responses)
    followups = [
        r
        for r in client.get("/api/v1/runs", headers=headers).json()["items"]
        if r["name"] == "Verify synthetic recovery"
    ]
    assert len(followups) == 1
