#!/usr/bin/env python3
"""Measure API reads and 500-event updates against an isolated disposable SQLite fixture.

Times include JSON encoding for reads and the commit for ingestion. Five samples
produce each median; ingestion first warms 500 existing spans. No user data is read.
"""

import argparse
import json
import os
import statistics
import sys
import time
import tracemalloc
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid5

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--report", type=Path)
options = parser.parse_args()
root = Path(__file__).resolve().parents[1]
fixture = TemporaryDirectory(prefix="agentscope-performance-")
fixture_path = Path(fixture.name)
os.environ["DATABASE_URL"] = "sqlite:///" + str(fixture_path / "benchmark.sqlite")
os.environ["AGENTSCOPE_DATA_DIR"] = str(fixture_path / "state")
sys.path.insert(0, str(root / "apps/api"))
from app.db import Agent, Base, Project, Run, Session, Span, engine, now
from app.main import agents, overview, runs
from sqlalchemy import event


def ident(value):
    return str(uuid5(NAMESPACE_URL, value))


project = ident("optimization-project")
Base.metadata.create_all(engine)
with Session() as db:
    if not db.get(Project, project):
        db.add(Project(id=project, name="Performance fixture"))
        db.flush()
        start = now() - timedelta(hours=1)
        agent_records = []
        run_records = []
        span_records = []
        for i in range(20):
            agent = ident("perf-agent-" + str(i))
            agent_records.append(
                {"id": agent, "project_id": project, "name": "Agent " + str(i)}
            )
            for j in range(250):
                run = ident("perf-run-" + str(i) + "-" + str(j))
                at = start - timedelta(seconds=j * 20)
                failed = j % 10 == 0
                run_records.append(
                    {
                        "id": run,
                        "project_id": project,
                        "agent_id": agent,
                        "external_id": run,
                        "name": "Measured call",
                        "started_at": at,
                        "ended_at": at + timedelta(milliseconds=50 + j),
                        "status": "failed" if failed else "completed",
                        "input_tokens": 5,
                        "output_tokens": 3,
                        "cost": 0.00001,
                    }
                )
                span_records.append(
                    {
                        "id": ident("perf-span-" + run),
                        "project_id": project,
                        "run_id": run,
                        "trace_id": run.replace("-", ""),
                        "span_id": "1" * 16,
                        "name": "LLM call",
                        "kind": "llm",
                        "status": "failed" if failed else "completed",
                        "started_at": at,
                        "ended_at": at + timedelta(milliseconds=50 + j),
                        "input_tokens": 5,
                        "output_tokens": 3,
                        "model": "gpt-4o-mini",
                        "cost": 0.00001,
                        "attributes": {
                            "grounding": {
                                "unsupported_claims": j,
                                "evaluator": "fixture",
                            }
                        }
                        if i == 0 and j < 2
                        else {},
                    }
                )
        db.execute(Agent.__table__.insert(), agent_records)
        db.execute(Run.__table__.insert(), run_records)
        db.execute(Span.__table__.insert(), span_records)
        db.commit()
count = 0


@event.listens_for(engine, "before_cursor_execute")
def query(*args):
    global count
    if args[2].lstrip().upper().startswith("SELECT"):
        count += 1


out = {"fixture": {"agents": 20, "runs": 5000, "llm_spans": 5000}, "measurements": {}}
for name, fetch in [
    ("overview", lambda db: overview(db, project, hours=24, synthetic=None)),
    ("agents", lambda db: agents(db, project)),
    (
        "run_page",
        lambda db: runs(
            db,
            project,
            hours=24,
            limit=50,
            offset=0,
            search="",
            status=None,
            synthetic=None,
        ),
    ),
]:
    times = []
    counts = []
    for _ in range(5):
        count = 0
        with Session() as db:
            started = time.perf_counter()
            value = fetch(db)
            json.dumps(value)
            times.append((time.perf_counter() - started) * 1000)
            counts.append(count)
    tracemalloc.start()
    with Session() as db:
        fetch(db)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    out["measurements"][name] = {
        "median_ms": round(statistics.median(times), 2),
        "select_queries": counts[-1],
        "peak_python_mib": round(peak / 1024 / 1024, 2),
    }
    if name == "overview":
        out["metrics"] = {
            k: value[k]
            for k in (
                "total_runs",
                "tokens",
                "llm_calls",
                "llm_errors",
                "cost",
                "grounding_evaluations",
                "unsupported_claims",
                "latency_p50",
                "latency_p95",
                "latency_p99",
            )
        }
from app.schemas import SpanEvent
from app.telemetry import ingest

project = ident("ingestion-project")
with Session() as db:
    if not db.get(Project, project):
        db.add(Project(id=project, name="Ingestion benchmark"))
        db.flush()
        db.add(Agent(id=ident("ingestion-agent"), project_id=project, name="Batch app"))
        db.commit()
start = now() - timedelta(seconds=1)
samples = []
counts = []
for iteration in range(6):
    batch = [
        SpanEvent(
            event_id=ident("batch-" + str(iteration) + "-" + str(i)),
            agent_id=ident("ingestion-agent"),
            run_id=ident("ingestion-run" + str(i)),
            trace_id=ident("ingestion-run" + str(i)).replace("-", ""),
            span_id="a" * 16,
            name="Batched execution",
            kind="agent",
            status="completed",
            started_at=start,
            ended_at=start + timedelta(milliseconds=10),
        )
        for i in range(500)
    ]
    count = 0
    with Session() as db:
        began = time.perf_counter()
        result = ingest(db, project, batch)
        db.commit()
        samples.append((time.perf_counter() - began) * 1000)
        counts.append(count)
    assert result["accepted"] == 500
out["measurements"]["ingestion"] = {
    "events_per_batch": 500,
    "median_ms": round(statistics.median(samples[1:]), 2),
    "select_queries": counts[-1],
}
print(json.dumps(out, indent=2))
if options.report:
    options.report.parent.mkdir(parents=True, exist_ok=True)
    options.report.write_text(json.dumps(out, indent=2) + "\n")
engine.dispose()
fixture.cleanup()
