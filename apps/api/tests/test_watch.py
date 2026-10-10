from datetime import timedelta
from uuid import uuid4

from app.db import Agent, Session, now
from test_workflows import agent, event


def test_watch_is_admin_scoped_and_expires_without_heartbeat(client, headers):
    a = agent(client, headers)
    body = {
        "repository": "banking-app",
        "session_id": str(uuid4()),
        "status": "waiting",
    }
    path = f"/api/v1/agents/{a['id']}/watch"
    key = client.post(
        "/api/v1/api-keys", headers=headers, json={"name": "ingest"}
    ).json()["key"]
    assert (
        client.put(
            path, headers={"Authorization": f"Bearer {key}"}, json=body
        ).status_code
        == 401
    )
    assert client.put(path, headers=headers, json=body).status_code == 200
    conflict = {**body, "session_id": str(uuid4())}
    assert client.put(path, headers=headers, json=conflict).status_code == 409
    value = client.get("/api/v1/metrics/overview", headers=headers).json()
    assert value["watch_sessions"][0]["status"] == "waiting"
    with Session() as db:
        row = db.get(Agent, a["id"])
        row.configuration = {
            "watch": {
                **row.configuration["watch"],
                "expires_at": (now() - timedelta(seconds=1)).isoformat(),
            }
        }
        db.commit()
    assert (
        client.get("/api/v1/metrics/overview", headers=headers).json()[
            "watch_sessions"
        ][0]["status"]
        == "disconnected"
    )
    assert client.put(path, headers=headers, json=conflict).status_code == 200
    assert (
        client.put(
            path, headers=headers, json={**conflict, "status": "stopped"}
        ).status_code
        == 200
    )
    assert (
        client.get("/api/v1/metrics/overview", headers=headers).json()[
            "watch_sessions"
        ][0]["status"]
        == "stopped"
    )


def test_grounding_is_unassessed_until_an_explicit_valid_evaluation(client, headers):
    a = agent(client, headers)
    root = event(a["id"])
    llm = event(
        a["id"],
        span_id="2" * 16,
        kind="llm",
        parent_span_id=root["span_id"],
        model="gpt-4o-mini",
        attributes={"usage_observed": False},
    )
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": [root, llm]}
        ).status_code
        == 202
    )
    metrics = client.get("/api/v1/metrics/overview", headers=headers).json()
    assert metrics["llm_calls"] == 1
    assert (
        metrics["grounding_evaluations"] == 0 and metrics["unsupported_claims"] is None
    )
    assert metrics["cost"] is None
    evaluated = {
        **llm,
        "event_id": str(uuid4()),
        "attributes": {
            "grounding": {"unsupported_claims": 2, "evaluator": "reference-check"}
        },
    }
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": [evaluated]}
        ).status_code
        == 202
    )
    metrics = client.get("/api/v1/metrics/overview", headers=headers).json()
    assert metrics["grounding_evaluations"] == 1 and metrics["unsupported_claims"] == 2
    invalid = {
        **evaluated,
        "event_id": str(uuid4()),
        "attributes": {
            "grounding": {"unsupported_claims": True, "evaluator": "reference-check"}
        },
    }
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": [invalid]}
        ).status_code
        == 422
    )


def test_watch_cannot_modify_another_project(client, headers):
    a = agent(client, headers)
    other = client.post(
        "/api/v1/projects", headers=headers, json={"name": "Other"}
    ).json()["id"]
    response = client.put(
        f"/api/v1/agents/{a['id']}/watch",
        headers={**headers, "X-Project-ID": other},
        json={
            "session_id": str(uuid4()),
            "repository": "Other",
            "status": "monitoring",
        },
    )
    assert response.status_code == 404


def test_stopping_watch_closes_unfinished_observations_without_claiming_failure(
    client, headers
):
    a = agent(client, headers)
    body = {
        "session_id": str(uuid4()),
        "repository": "sample-app",
        "status": "monitoring",
    }
    path = f"/api/v1/agents/{a['id']}/watch"
    assert client.put(path, headers=headers, json=body).status_code == 200
    root = event(a["id"], status="running", ended_at=None)
    llm = event(
        a["id"],
        span_id="2" * 16,
        kind="llm",
        parent_span_id=root["span_id"],
        status="running",
        ended_at=None,
    )
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": [root, llm]}
        ).status_code
        == 202
    )
    assert (
        client.get("/api/v1/metrics/overview", headers=headers).json()["active_runs"]
        == 1
    )
    assert (
        client.put(
            path, headers=headers, json={**body, "status": "stopped"}
        ).status_code
        == 200
    )
    metrics = client.get("/api/v1/metrics/overview", headers=headers).json()
    assert metrics["active_runs"] == 0 and metrics["failed_runs"] == 0
    run = client.get("/api/v1/runs", headers=headers).json()["items"][0]
    assert run["status"] == "interrupted" and run["meta"]["observation_interrupted"]
    trace = client.get(f"/api/v1/runs/{run['id']}/trace", headers=headers).json()
    assert all(span["status"] == "interrupted" for span in trace["spans"])
    # A final event arriving after the observation window remains authoritative.
    final = {
        **root,
        "event_id": str(uuid4()),
        "status": "completed",
        "ended_at": now().isoformat(),
    }
    assert (
        client.post(
            "/api/v1/telemetry/events", headers=headers, json={"events": [final]}
        ).status_code
        == 202
    )
    assert (
        client.get("/api/v1/runs", headers=headers).json()["items"][0]["status"]
        == "completed"
    )
