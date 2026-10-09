import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from agentscope_sdk import AgentScope
from app.config import database_url, secret_file
from app.db import Audit, Investigation, Session
from app.services import investigate, investigation_step
from sqlalchemy import func, select


def test_container_configuration_never_falls_back_or_prints_secrets(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AGENTSCOPE_CONTAINER", "1")
    monkeypatch.delenv("DATABASE_HOST", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_HOST"):
        database_url(tmp_path)
    secret = tmp_path / "password"
    secret.write_text("special:@/password")
    for name, value in {
        "DATABASE_HOST": "postgres",
        "DATABASE_NAME": "agentscope",
        "DATABASE_USER": "agentscope",
        "DATABASE_PASSWORD_FILE": str(secret),
    }.items():
        monkeypatch.setenv(name, value)
    url = database_url(tmp_path)
    assert url.password == "special:@/password"
    assert "special" not in str(url)
    secret.unlink()
    with pytest.raises(RuntimeError, match="DATABASE_PASSWORD_FILE"):
        secret_file("DATABASE_PASSWORD_FILE")


def test_frozen_migrations_first_start_and_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'fresh.db'}")
    monkeypatch.setenv("AGENTSCOPE_DATA_DIR", str(tmp_path / "state"))
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    import sqlite3

    with sqlite3.connect(tmp_path / "fresh.db") as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "001",
        )
        assert db.execute("SELECT count(*) FROM telemetry_events").fetchone() == (0,)


def test_investigation_resumes_without_repeating_checkpoint_or_audit(client, headers):
    client.post(
        "/api/v1/simulations",
        headers=headers,
        json={"scenario": "tool_loop", "seed": 14, "include_baseline": False},
    ).json()
    incident = client.get("/api/v1/incidents", headers=headers).json()["items"][0]
    inv = client.post(
        f"/api/v1/incidents/{incident['id']}/investigate", headers=headers
    ).json()
    # Worker may run concurrently; persisted phase retries must be harmless either way.
    investigation_step("Collect evidence", 20)({"investigation_id": inv["id"]})
    investigate(inv["id"])
    investigate(inv["id"])
    with Session() as db:
        row = db.get(Investigation, inv["id"])
        assert row.status == "complete" and len(row.timeline) == 5
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(
                    Audit.target_id == row.id, Audit.action == "investigation.completed"
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"queue_size": 0},
        {"queue_size": -1},
        {"batch_size": 0},
        {"batch_size": 1001},
        {"timeout": float("inf")},
    ],
)
def test_sdk_rejects_unbounded_configuration(kwargs):
    with pytest.raises(ValueError):
        AgentScope("http://127.0.0.1:1", "test", "test", **kwargs)


def test_sdk_close_stops_producers_and_accounts_for_pending_queue(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def blocked(self, path, body):
        entered.set()
        release.wait(1)
        raise OSError("offline")

    monkeypatch.setattr(AgentScope, "_request", blocked)
    scope = AgentScope("http://127.0.0.1:1", "test", "test", queue_size=4, batch_size=1)
    scope._enqueue({"n": 0})
    assert entered.wait(1)
    for i in range(10):
        scope._enqueue({"n": i + 1})
    start = time.monotonic()
    assert scope.close(timeout=0.02) is False
    assert time.monotonic() - start < 0.5 and scope._queue.qsize() == 0
    scope._enqueue({"n": 12})
    release.set()
    assert scope.close(1) is True
    assert scope.stats["dropped_events"] == 12
    assert scope._queue.unfinished_tasks == 0
