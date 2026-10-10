"""Batched read models: summarize history in SQL and load only visible records."""

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import Integer, case, cast, extract, func, select

from .db import Agent, Incident, Run, Span, now
from .telemetry import aware


def serialize(row):
    return {
        c.name: (aware(value).isoformat() if hasattr(value, "isoformat") else value)
        for c in row.__table__.columns
        if (value := getattr(row, c.name)) is not None
    }


def sqlite_microseconds(column):
    # SQLAlchemy stores SQLite datetimes with six fractional digits. Parse the
    # integer parts separately: julianday rounds fractions to milliseconds and
    # subtracting large floating-point epochs loses precision at rounding ties.
    return cast(
        func.strftime("%s", func.substr(column, 1, 19)), Integer
    ) * 1_000_000 + cast(func.substr(column, 21, 6), Integer)


def epoch(db, column):
    if db.bind.dialect.name == "sqlite":
        return sqlite_microseconds(column) / 1_000_000.0
    return extract("epoch", column)


def latency(db):
    if db.bind.dialect.name == "sqlite":
        return (
            sqlite_microseconds(Run.ended_at) - sqlite_microseconds(Run.started_at)
        ) / 1000.0
    return (epoch(db, Run.ended_at) - epoch(db, Run.started_at)) * 1000


def count_if(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def run_views(db, runs, agents=None):
    if not runs:
        return []
    agents = dict(agents or {})
    missing = {r.agent_id for r in runs} - agents.keys()
    if missing:
        agents.update(
            (a.id, a) for a in db.scalars(select(Agent).where(Agent.id.in_(missing)))
        )
    incidents = defaultdict(list)
    for item in db.scalars(
        select(Incident).where(Incident.run_id.in_([r.id for r in runs]))
    ):
        incidents[item.run_id].append(serialize(item))
    current = now()
    result = []
    for run in runs:
        agent = agents[run.agent_id]
        end = aware(run.ended_at) if run.ended_at else current
        result.append(
            {
                **serialize(run),
                "cost": run.cost,
                "tokens": run.input_tokens + run.output_tokens,
                "duration_ms": max(
                    0, round((end - aware(run.started_at)).total_seconds() * 1000)
                ),
                "agent_name": agent.name,
                "framework": agent.framework,
                "environment": agent.environment,
                "incidents": incidents[run.id],
            }
        )
    return result


def agent_views(db, agents):
    if not agents:
        return []
    ids = [a.id for a in agents]
    terminal = Run.status.in_(["completed", "failed"])
    stats = {
        row.agent_id: row
        for row in db.execute(
            select(
                Run.agent_id,
                func.count().label("total"),
                count_if(Run.status == "running").label("active"),
                count_if(Run.status == "completed").label("completed"),
                count_if(terminal).label("terminal"),
                func.sum(Run.input_tokens + Run.output_tokens).label("tokens"),
                func.sum(case((terminal, latency(db)), else_=0)).label("latency"),
            )
            .where(Run.agent_id.in_(ids))
            .group_by(Run.agent_id)
        )
    }
    active = dict(
        db.execute(
            select(Incident.agent_id, func.count())
            .where(
                Incident.agent_id.in_(ids),
                Incident.status.notin_(["RESOLVED", "DISMISSED"]),
            )
            .group_by(Incident.agent_id)
        ).all()
    )
    # Window functions bound previews to five records per agent on both databases.
    ranked_runs = (
        select(
            Run.id,
            func.row_number()
            .over(
                partition_by=Run.agent_id,
                order_by=(Run.started_at.desc(), Run.id.desc()),
            )
            .label("position"),
        )
        .where(Run.agent_id.in_(ids))
        .subquery()
    )
    recent = list(
        db.scalars(
            select(Run)
            .join(ranked_runs, Run.id == ranked_runs.c.id)
            .where(ranked_runs.c.position <= 5)
            .order_by(Run.started_at.desc(), Run.id.desc())
        )
    )
    run_items = defaultdict(list)
    for run, view in zip(
        recent, run_views(db, recent, {a.id: a for a in agents}), strict=True
    ):
        run_items[run.agent_id].append(view)
    ranked_incidents = (
        select(
            Incident.id,
            func.row_number()
            .over(
                partition_by=Incident.agent_id,
                order_by=(Incident.created_at.desc(), Incident.id.desc()),
            )
            .label("position"),
        )
        .where(Incident.agent_id.in_(ids))
        .subquery()
    )
    incident_items = defaultdict(list)
    for incident in db.scalars(
        select(Incident)
        .join(ranked_incidents, Incident.id == ranked_incidents.c.id)
        .where(ranked_incidents.c.position <= 5)
        .order_by(Incident.created_at.desc(), Incident.id.desc())
    ):
        incident_items[incident.agent_id].append(serialize(incident))
    result = []
    for agent in agents:
        summary = stats.get(agent.id)
        result.append(
            {
                **serialize(agent),
                "status": "degraded"
                if active.get(agent.id)
                else "active"
                if summary and summary.active
                else "healthy"
                if summary
                else "idle",
                "success_rate": round(summary.completed / summary.terminal * 100, 1)
                if summary and summary.terminal
                else None,
                "average_latency_ms": round((summary.latency or 0) / summary.terminal)
                if summary and summary.terminal
                else None,
                "tokens": summary.tokens if summary else 0,
                "run_count": summary.total if summary else 0,
                "recent_runs": run_items[agent.id],
                "recent_incidents": incident_items[agent.id],
            }
        )
    return result


def overview_metrics(db, project_id, hours, synthetic):
    since = now() - timedelta(hours=hours)
    conditions = [Run.project_id == project_id, Run.started_at >= since]
    if synthetic is not None:
        conditions.append(Run.synthetic == synthetic)
    selected_runs = select(Run.id).where(*conditions)
    values = (
        db.execute(
            select(
                func.count().label("total_runs"),
                count_if(Run.status == "running").label("active_runs"),
                count_if(Run.status == "completed").label("completed_runs"),
                count_if(Run.status == "failed").label("failed_runs"),
                func.coalesce(func.sum(Run.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(Run.output_tokens), 0).label("output_tokens"),
                count_if(Run.synthetic.is_(True)).label("synthetic_runs"),
            ).where(*conditions)
        )
        .mappings()
        .one()
    )
    result = dict(values)
    result["tokens"] = result["input_tokens"] + result["output_tokens"]
    terminal_count = result["completed_runs"] + result["failed_runs"]
    result["success_rate"] = (
        round(result["completed_runs"] / terminal_count * 100, 1)
        if terminal_count
        else None
    )
    durations = sorted(
        db.scalars(
            select(latency(db)).where(
                *conditions,
                Run.status.in_(["completed", "failed"]),
                Run.ended_at.is_not(None),
            )
        )
    )
    result["average_latency_ms"] = (
        round(sum(durations) / len(durations)) if durations else None
    )
    for name, quantile in (
        ("latency_p50", 0.5),
        ("latency_p95", 0.95),
        ("latency_p99", 0.99),
    ):
        result[name] = (
            round(
                durations[
                    min(len(durations) - 1, round((len(durations) - 1) * quantile))
                ]
            )
            if durations
            else None
        )
    spans = [Span.project_id == project_id, Span.run_id.in_(selected_runs)]
    llm = Span.kind == "llm"
    grounding = Span.attributes["grounding"]["unsupported_claims"].as_integer()
    totals = (
        db.execute(
            select(
                count_if(llm).label("llm_calls"),
                count_if(llm & (Span.status == "failed")).label("llm_errors"),
                count_if(Span.kind == "tool").label("tool_calls"),
                count_if((Span.kind == "tool") & (Span.status == "failed")).label(
                    "tool_errors"
                ),
                count_if(llm & grounding.is_not(None)).label("grounding_evaluations"),
                func.sum(case((llm, grounding), else_=None)).label(
                    "unsupported_claims"
                ),
                count_if(llm & Span.cost.is_(None)).label("unpriced"),
                func.sum(case((llm, Span.cost), else_=None)).label("cost"),
            ).where(*spans)
        )
        .mappings()
        .one()
    )
    result.update({k: v for k, v in totals.items() if k != "unpriced"})
    result["cost"] = (
        round(totals["cost"], 6)
        if totals["llm_calls"] and not totals["unpriced"]
        else None
    )
    bins = [
        {
            "at": (since + timedelta(hours=hours * i / 24)).isoformat(),
            "input_tokens": 0,
            "output_tokens": 0,
            "tool_calls": 0,
            "tool_errors": 0,
            "runs": 0,
        }
        for i in range(24)
    ]

    def bucket(column):
        position = (epoch(db, column) - since.timestamp()) / (hours * 3600 / 24)
        # PostgreSQL rounds float-to-integer casts; SQLite truncates them.
        if db.bind.dialect.name != "sqlite":
            position = func.floor(position)
        return cast(position, Integer)

    for row in db.execute(
        select(
            bucket(Run.started_at).label("position"),
            func.count().label("runs"),
            func.sum(Run.input_tokens).label("input_tokens"),
            func.sum(Run.output_tokens).label("output_tokens"),
        )
        .where(*conditions)
        .group_by("position")
    ):
        index = min(23, max(0, row.position))
        for key in ("runs", "input_tokens", "output_tokens"):
            bins[index][key] += getattr(row, key)
    for row in db.execute(
        select(
            bucket(Span.started_at).label("position"),
            func.count().label("tool_calls"),
            count_if(Span.status == "failed").label("tool_errors"),
        )
        .where(*spans, Span.kind == "tool")
        .group_by("position")
    ):
        index = min(23, max(0, row.position))
        bins[index]["tool_calls"] += row.tool_calls
        bins[index]["tool_errors"] += row.tool_errors
    result["series"] = bins
    return result
