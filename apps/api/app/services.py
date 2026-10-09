"""Deterministic detection, evidence-grounded LangGraph investigations, and demo control."""

import hashlib
import random
from datetime import timedelta
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from .db import (
    Agent,
    Anomaly,
    Audit,
    Incident,
    Investigation,
    Remediation,
    Run,
    Session,
    Settings,
    Span,
    TelemetryEvent,
    now,
    uid,
)
from .schemas import ProjectSettings, SpanEvent
from .telemetry import aware, ingest

TITLES = {
    "tool_loop": "Repeated tool calls without progress",
    "token_budget": "Run exceeded its token or cost budget",
    "tool_failure": "Elevated tool failure rate",
    "stalled": "Agent execution has stalled",
    "unexpected_workflow": "Unexpected tool sequence detected",
}


def settings_for(db, project_id):
    row = db.scalar(select(Settings).where(Settings.project_id == project_id))
    return ProjectSettings.model_validate(row.value if row else {}).model_dump()


def audit(db, project_id, action, target_id, details=None):
    db.add(
        Audit(
            project_id=project_id,
            action=action,
            target_id=target_id,
            details=details or {},
        )
    )


def detect(db, run):
    config = settings_for(db, run.project_id)["detection"]
    agent = db.get(Agent, run.agent_id)
    spans = list(
        db.scalars(select(Span).where(Span.run_id == run.id).order_by(Span.started_at))
    )
    tools = [s for s in spans if s.kind == "tool"]
    candidates = []
    groups = {}
    for span in tools:
        if span.status != "completed" or span.attributes.get("legitimate_polling"):
            continue
        fp = span.attributes.get("argument_fingerprint")
        result = span.attributes.get("result_fingerprint")
        if fp and result:
            groups.setdefault((span.name, fp, result), []).append(span)
    progress = [s for s in spans if s.kind == "progress"]
    for group in groups.values():
        if len(group) >= config["loop_threshold"] and not any(
            s.started_at >= group[0].started_at for s in progress
        ):
            candidates.append(
                (
                    "tool_loop",
                    "high",
                    {
                        "repeated_calls": len(group),
                        "threshold": config["loop_threshold"],
                        "tool": group[0].name,
                        "progress_events": 0,
                    },
                    [s.id for s in group],
                )
            )
            break
    total_tokens = run.input_tokens + run.output_tokens
    if total_tokens > config["token_budget"] or (
        run.cost is not None and run.cost > config["cost_budget"]
    ):
        candidates.append(
            (
                "token_budget",
                "high",
                {
                    "tokens": total_tokens,
                    "budget": config["token_budget"],
                    "cost": run.cost,
                    "cost_budget": config["cost_budget"],
                },
                [s.id for s in spans if s.kind == "llm"],
            )
        )
    failures = [s for s in tools if s.status == "failed"]
    if len(failures) >= config["failure_threshold"]:
        candidates.append(
            (
                "tool_failure",
                "critical",
                {
                    "failed_calls": len(failures),
                    "total_calls": len(tools),
                    "threshold": config["failure_threshold"],
                },
                [s.id for s in failures],
            )
        )
    last = max(
        [aware(s.ended_at or s.started_at) for s in spans] or [aware(run.started_at)]
    )
    idle = (now() - last).total_seconds()
    expected = agent.configuration.get("expected_duration_seconds", 0)
    if run.status == "running" and idle > max(config["stall_seconds"], expected):
        candidates.append(
            (
                "stalled",
                "medium",
                {
                    "idle_seconds": round(idle),
                    "threshold_seconds": max(config["stall_seconds"], expected),
                },
                [s.id for s in spans[-3:]],
            )
        )
    allowed = agent.configuration.get("allowed_tools")
    unexpected = [s for s in tools if allowed and s.name not in allowed]
    if unexpected:
        candidates.append(
            (
                "unexpected_workflow",
                "medium",
                {
                    "unexpected_tools": sorted({s.name for s in unexpected}),
                    "allowed_tools": allowed,
                },
                [s.id for s in unexpected],
            )
        )
    for kind, severity, measurements, refs in candidates:
        anomaly = db.scalar(
            select(Anomaly).where(Anomaly.run_id == run.id, Anomaly.kind == kind)
        )
        if anomaly:
            anomaly.measurements = measurements
            anomaly.evidence_ids = refs
            continue
        anomaly = Anomaly(
            id=uid(),
            project_id=run.project_id,
            run_id=run.id,
            agent_id=run.agent_id,
            kind=kind,
            severity=severity,
            measurements=measurements,
            evidence_ids=refs,
        )
        db.add(anomaly)
        db.flush()
        incident = Incident(
            id=uid(),
            project_id=run.project_id,
            anomaly_id=anomaly.id,
            run_id=run.id,
            agent_id=run.agent_id,
            title=TITLES[kind],
            severity=severity,
        )
        db.add(incident)
        audit(
            db,
            run.project_id,
            "incident.detected",
            incident.id,
            {"rule": kind, "version": "1.0"},
        )
    db.flush()


def process_outbox():
    with Session() as db:
        pending = list(
            db.scalars(
                select(TelemetryEvent)
                .where(TelemetryEvent.processed.is_(False))
                .limit(1000)
            )
        )
        run_ids = {e.run_id for e in pending}
        run_ids.update(db.scalars(select(Run.id).where(Run.status == "running")))
        for run_id in run_ids:
            detect(db, db.get(Run, run_id))
        for event in pending:
            event.processed = True
        # Detection and outbox acknowledgement are committed atomically. A crash retries safely.
        db.commit()
    verify_pending()
    enforce_retention()


class InvestigationState(TypedDict):
    investigation_id: str


def investigation_step(phase, progress):
    def step(state):
        with Session() as db:
            inv = db.get(Investigation, state["investigation_id"])
            if not inv or inv.status == "cancelled":
                return state
            incident = db.get(Incident, inv.incident_id)
            anomaly = db.get(Anomaly, incident.anomaly_id)
            run = db.get(Run, incident.run_id)
            agent = db.get(Agent, incident.agent_id)
            spans = list(
                db.scalars(
                    select(Span).where(Span.run_id == run.id).order_by(Span.started_at)
                )
            )
            inv.status, inv.phase, inv.progress = "running", phase, progress
            inv.timeline = [*inv.timeline, {"phase": phase, "at": now().isoformat()}]
            if phase == "Collect evidence":
                evidence = [
                    {
                        "id": s.id,
                        "span_id": s.span_id,
                        "name": s.name,
                        "kind": s.kind,
                        "status": s.status,
                        "at": aware(s.started_at).isoformat(),
                        "error": s.error,
                        "tokens": s.input_tokens + s.output_tokens,
                        "argument_fingerprint": s.attributes.get(
                            "argument_fingerprint"
                        ),
                        "result_fingerprint": s.attributes.get("result_fingerprint"),
                    }
                    for s in spans
                    if s.id in anomaly.evidence_ids
                ]
                inv.report = {
                    "evidence": evidence,
                    "measurements": anomaly.measurements,
                    "agent": agent.name,
                    "run_id": run.id,
                    "synthetic": run.synthetic,
                    "rule": anomaly.kind,
                    "rule_version": anomaly.rule_version,
                }
            elif phase == "Build execution timeline":
                inv.report = {
                    **inv.report,
                    "execution_timeline": [
                        {
                            "name": s.name,
                            "kind": s.kind,
                            "status": s.status,
                            "at": aware(s.started_at).isoformat(),
                            "id": s.id,
                        }
                        for s in spans
                    ],
                }
            elif phase == "Validate hypotheses":
                hypotheses = {
                    "tool_loop": (
                        "The retry path is reprocessing unchanged results without a recorded progress event.",
                        "The calls could represent deliberate polling; inspect the agent retry policy.",
                        "Introduce deduplication, a bounded retry budget, and progress checkpoints.",
                    ),
                    "token_budget": (
                        "Recorded model usage exceeded the configured per-run budget.",
                        "Large legitimate tasks may need a higher explicitly approved budget.",
                        "Add a token budget guard and bound the context window and LLM retries.",
                    ),
                    "tool_failure": (
                        "Repeated tool failures interrupted the execution.",
                        "An upstream dependency may be transiently unavailable.",
                        "Use bounded exponential backoff, inspect tool credentials and upstream availability.",
                    ),
                    "stalled": (
                        "No telemetry or heartbeat arrived within the configured progress window.",
                        "The exporter may be disconnected or the operation may be legitimately long running.",
                        "Check agent liveness and exporter connectivity; configure heartbeats and operation timeouts.",
                    ),
                    "unexpected_workflow": (
                        "Recorded tool invocations violated the agent allowlist.",
                        "The declared allowlist may be incomplete for this task.",
                        "Review the declared workflow and require an approved allowlist update.",
                    ),
                }
                hypothesis, alternative, recommendation = hypotheses[anomaly.kind]
                ids = [e["id"] for e in inv.report["evidence"]]
                inv.report = {
                    **inv.report,
                    "summary": f"{TITLES[anomaly.kind]} for {agent.name}. Measurements were evaluated against rule {anomaly.kind} v{anomaly.rule_version}.",
                    "hypotheses": [
                        {
                            "explanation": hypothesis,
                            "epistemic_status": "supported",
                            "supporting_evidence": ids,
                            "contradictory_evidence": [],
                            "validation_steps": [
                                "Compare the observed measurements with the configured threshold.",
                                "Review the referenced execution spans and agent configuration.",
                            ],
                        },
                        {
                            "explanation": alternative,
                            "epistemic_status": "unverified",
                            "supporting_evidence": [],
                            "contradictory_evidence": [],
                            "validation_steps": [
                                "Confirm intended behavior with the agent owner before intervention."
                            ],
                        },
                    ],
                    "recommendation": recommendation,
                    "limitations": [
                        "Deterministic report; no external model was used.",
                        "Telemetry establishes observations, not agent intent.",
                        "No raw prompts or tool outputs are needed for this report.",
                    ],
                    "decision_summary": hypothesis,
                }
                provider_settings = settings_for(db, incident.project_id)
                from .provider import suggest

                suggestion, note = suggest(provider_settings, inv.report)
                inv.report = {**inv.report, "provider_note": note}
                if suggestion:
                    inv.report = {
                        **inv.report,
                        "hypotheses": [
                            *inv.report["hypotheses"],
                            {
                                "explanation": suggestion.explanation,
                                "epistemic_status": "unverified",
                                "supporting_evidence": suggestion.evidence_ids,
                                "contradictory_evidence": [],
                                "validation_steps": suggestion.validation_steps,
                            },
                        ],
                    }
            elif phase == "Propose remediation":
                if not db.scalar(
                    select(Remediation).where(Remediation.incident_id == incident.id)
                ):
                    db.add(
                        Remediation(
                            project_id=incident.project_id, incident_id=incident.id
                        )
                    )
            elif phase == "Complete":
                inv.status = "complete"
                incident.status = "ACTION_REQUIRED"
                audit(db, incident.project_id, "investigation.completed", inv.id)
            db.commit()
        return state

    return step


workflow = StateGraph(InvestigationState)
phases = [
    "Collect evidence",
    "Build execution timeline",
    "Validate hypotheses",
    "Propose remediation",
    "Complete",
]
for i, phase in enumerate(phases):
    workflow.add_node(phase, investigation_step(phase, (i + 1) * 20))
    workflow.add_edge(START if i == 0 else phases[i - 1], phase)
workflow.add_edge(phases[-1], END)
investigation_graph = workflow.compile()


def investigate(investigation_id):
    try:
        investigation_graph.invoke(
            {"investigation_id": investigation_id}, {"recursion_limit": 8}
        )
    except Exception:
        with Session() as db:
            inv = db.get(Investigation, investigation_id)
            if inv:
                inv.status, inv.phase = (
                    "failed",
                    "Investigation failed; retry is available",
                )
                audit(db, inv.project_id, "investigation.failed", inv.id)
                db.commit()
        raise


def simulate(db, project_id, scenario, seed, include_baseline=True):
    rng = random.Random(seed)
    names = [
        ("research-agent", "LangGraph"),
        ("support-assistant", "Custom"),
        ("coding-agent", "LangGraph"),
        ("data-pipeline", "Custom"),
    ]
    agents = []
    for name, framework in names:
        name = f"demo/{name}"
        agent = db.scalar(
            select(Agent).where(
                Agent.project_id == project_id,
                Agent.name == name,
                Agent.environment == "simulation",
            )
        )
        if not agent:
            agent = Agent(
                id=uid(),
                project_id=project_id,
                name=name,
                framework=framework,
                environment="simulation",
                synthetic=True,
                configuration={
                    "allowed_tools": [
                        "web_search",
                        "read_document",
                        "github_search",
                        "vector_search",
                    ],
                    "control_adapter": "demo",
                },
            )
            db.add(agent)
            db.flush()
        agents.append(agent)
    runs = []
    batch_nonce = uid()

    def generate(agent, index, kind, start):
        external_id = f"demo:{batch_nonce}:{index}"
        trace_id = hashlib.sha256(external_id.encode()).hexdigest()[:32]
        root = hashlib.sha256(f"{external_id}:root".encode()).hexdigest()[:16]
        events = []

        def emit(n, name, span_kind, offset, duration, **kwargs):
            span_id = (
                root
                if n == 0
                else hashlib.sha256(f"{external_id}:{n}".encode()).hexdigest()[:16]
            )
            events.append(
                SpanEvent(
                    event_id=f"{external_id}:{n}",
                    agent_id=agent.id,
                    run_id=external_id,
                    run_name={
                        "healthy": "Research and summarize documents",
                        "tool_loop": "Search repository context",
                        "tool_failure": "Retrieve external evidence",
                        "token_budget": "Analyze a large context",
                        "stalled": "Process agent task",
                        "unexpected_workflow": "Execute restricted workflow",
                    }[kind],
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=None if n == 0 else root,
                    name=name,
                    kind=span_kind,
                    started_at=start + timedelta(seconds=offset),
                    ended_at=None
                    if duration is None
                    else start + timedelta(seconds=offset + duration),
                    **kwargs,
                )
            )

        calls = 8 if kind == "tool_loop" else 5 if kind == "tool_failure" else 2
        for n in range(calls):
            failed = kind == "tool_failure"
            emit(
                n + 1,
                "delete_repository"
                if kind == "unexpected_workflow" and n == 0
                else "github_search"
                if kind == "tool_loop"
                else "web_search",
                "tool",
                n * 1.1 + 0.5,
                0.4 + rng.random() * 0.4,
                status="failed" if failed else "completed",
                error="HTTP 429: upstream rate limit exceeded" if failed else None,
                attributes={
                    "argument_fingerprint": "sha256:query-4f91",
                    "result_fingerprint": "sha256:result-c28b",
                    "http_status": 429 if failed else 200,
                },
            )
        tokens = 22000 if kind == "token_budget" else rng.randint(1000, 3500)
        emit(
            calls + 1,
            "Generate response",
            "llm",
            calls * 1.1 + 1,
            1.8,
            model="gpt-4.1-mini",
            input_tokens=tokens,
            output_tokens=rng.randint(200, 900),
            attributes={"temperature": 0.2, "provider": "synthetic-local"},
        )
        terminal = (
            "running"
            if kind in ("tool_loop", "stalled", "token_budget")
            else "failed"
            if kind in ("tool_failure", "unexpected_workflow")
            else "completed"
        )
        emit(
            0,
            agent.name,
            "agent",
            0,
            None if terminal == "running" else calls * 1.1 + 3.2,
            status=terminal,
        )
        result = ingest(db, project_id, events, synthetic=True)
        runs.extend(result["run_ids"])
        for run_id in result["run_ids"]:
            detect(db, db.get(Run, run_id))

    if include_baseline:
        for i in range(24):
            generate(
                agents[i % len(agents)],
                i,
                "healthy",
                now() - timedelta(minutes=240 - i * 9),
            )
    age = 12 if scenario == "stalled" else 0.5
    generate(
        agents[
            0
            if scenario in ("tool_loop", "stalled")
            else 1
            if scenario == "tool_failure"
            else 2
        ],
        100,
        scenario,
        now() - timedelta(minutes=age),
    )
    audit(
        db,
        project_id,
        "simulation.triggered",
        batch_nonce,
        {"scenario": scenario, "seed": seed, "synthetic": True},
    )
    return {"run_ids": runs, "scenario": scenario, "seed": seed, "synthetic": True}


def execute_demo(db, remediation):
    incident = db.get(Incident, remediation.incident_id)
    run = db.get(Run, incident.run_id)
    # This adapter controls ONLY the in-process simulation, never a monitored real agent.
    run.status, run.ended_at = "cancelled", now()
    remediation.status, remediation.executed_at = "verifying", now()
    remediation.verification = {
        "result": "PENDING",
        "window_seconds": 15,
        "started_at": now().isoformat(),
        "measurements": {"target_run_terminated": True},
        "synthetic": True,
    }
    incident.status = "VERIFYING"
    recovery_id, trace_id, parent = (
        uid(),
        uid().replace("-", ""),
        uid().replace("-", "")[:16],
    )
    started = now()
    events = [
        SpanEvent(
            event_id=f"{recovery_id}:{i}",
            agent_id=run.agent_id,
            run_id=recovery_id,
            trace_id=trace_id,
            span_id=parent if i == 0 else uid().replace("-", "")[:16],
            parent_span_id=None if i == 0 else parent,
            name="Demo recovery execution" if i == 0 else "web_search",
            kind="agent" if i == 0 else "tool",
            status="completed",
            started_at=started,
            ended_at=now(),
            run_name="Verify synthetic recovery",
            attributes={"recovery_for": incident.id},
        )
        for i in range(2)
    ]
    ingest(db, incident.project_id, events, synthetic=True)
    audit(
        db,
        incident.project_id,
        "remediation.executed",
        remediation.id,
        {"adapter": "demo", "action": remediation.action},
    )


def verify_pending():
    with Session() as db:
        for remediation in db.scalars(
            select(Remediation).where(Remediation.status == "verifying")
        ):
            if (now() - aware(remediation.executed_at)).total_seconds() < 15:
                continue
            incident = db.get(Incident, remediation.incident_id)
            run = db.get(Run, incident.run_id)
            recent_runs = list(
                db.scalars(
                    select(Run).where(
                        Run.agent_id == run.agent_id,
                        Run.started_at >= remediation.executed_at,
                    )
                )
            )
            healthy = [r for r in recent_runs if r.status == "completed"]
            failures = [r for r in recent_runs if r.status == "failed"]
            recovered = run.status == "cancelled" and bool(healthy) and not failures
            result = "VERIFIED_RECOVERED" if recovered else "INCONCLUSIVE"
            remediation.status = "executed"
            remediation.verification = {
                **remediation.verification,
                "result": result,
                "checked_at": now().isoformat(),
                "measurements": {
                    "target_run_terminated": run.status == "cancelled",
                    "successful_followup_runs": len(healthy),
                    "failed_followup_runs": len(failures),
                },
                "evidence_ids": [r.id for r in healthy],
            }
            incident.status = "RESOLVED" if recovered else "ACTION_REQUIRED"
            if recovered:
                db.get(Anomaly, incident.anomaly_id).status = "resolved"
            audit(
                db,
                incident.project_id,
                "recovery.verified",
                remediation.id,
                {"result": result},
            )
        db.commit()


_last_retention = None


def enforce_retention():
    """Delete expired telemetry only when no open incident depends on its evidence."""
    global _last_retention
    if _last_retention and (now() - _last_retention).total_seconds() < 3600:
        return
    with Session() as db:
        from .db import Project

        for project in db.scalars(select(Project)):
            cutoff = now() - timedelta(
                days=settings_for(db, project.id)["retention_days"]
            )
            for run in db.scalars(
                select(Run).where(Run.project_id == project.id, Run.started_at < cutoff)
            ):
                if db.scalar(select(Incident.id).where(Incident.run_id == run.id)):
                    continue  # Evidence remains pinned for incident history.
                for model in (Span, TelemetryEvent):
                    from sqlalchemy import delete

                    db.execute(delete(model).where(model.run_id == run.id))
                db.delete(run)
        db.commit()
    _last_retention = now()
