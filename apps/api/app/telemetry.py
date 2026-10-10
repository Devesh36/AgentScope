"""Normalized ingestion, durable local outbox, model pricing, and OTLP translation."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from .db import Agent, Run, Span, TelemetryEvent, uid
from .schemas import SpanEvent

# USD / million tokens. Estimated list pricing, versioned and persisted on each LLM span.
PRICING_VERSION = "2025-04-14"
PRICING = {
    "gpt-4.1": (2, 8),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4o": (2.5, 10),
    "gpt-4o-mini": (0.15, 0.6),
}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def ingest(db, project_id, events, synthetic=False):
    accepted, duplicate = 0, 0
    affected = set()
    # Validate the whole batch before persisting any records.
    for event in events:
        agent = db.get(Agent, event.agent_id)
        if not agent or agent.project_id != project_id:
            raise HTTPException(404, "Agent not found in this project")
        if event.ended_at and event.ended_at < event.started_at:
            raise HTTPException(422, "Span end must follow span start")
    for event in events:
        if db.scalar(
            select(TelemetryEvent).where(
                TelemetryEvent.project_id == project_id,
                TelemetryEvent.event_id == event.event_id,
            )
        ):
            duplicate += 1
            continue
        run = db.scalar(
            select(Run).where(
                Run.project_id == project_id, Run.external_id == event.run_id
            )
        )
        if run and run.agent_id != event.agent_id:
            raise HTTPException(
                409, "Run identifier already belongs to a different agent"
            )
        if not run:
            run = Run(
                id=uid(),
                project_id=project_id,
                agent_id=event.agent_id,
                external_id=event.run_id,
                name=event.run_name,
                status="running",
                started_at=event.started_at,
                synthetic=synthetic,
                meta={"source": "simulation" if synthetic else "telemetry"},
            )
            db.add(run)
            db.flush()
        elif event.started_at < aware(run.started_at):
            run.started_at = event.started_at
        span = db.scalar(
            select(Span).where(
                Span.project_id == project_id,
                Span.trace_id == event.trace_id,
                Span.span_id == event.span_id,
            )
        )
        if span and span.run_id != run.id:
            raise HTTPException(409, "Trace span already belongs to another run")
        if not span:
            span = Span(id=uid(), project_id=project_id, run_id=run.id)
            db.add(span)
        # An older start update must not reopen a terminal span.
        if not span.ended_at or (
            event.ended_at and event.ended_at >= aware(span.ended_at)
        ):
            for field in (
                "trace_id",
                "span_id",
                "parent_span_id",
                "name",
                "kind",
                "status",
                "started_at",
                "ended_at",
                "input_tokens",
                "output_tokens",
                "model",
                "error",
            ):
                setattr(span, field, getattr(event, field))
            span.attributes = {**event.attributes, "synthetic": synthetic}
            if event.kind == "llm" and event.model in PRICING and event.attributes.get("usage_observed") is not False:
                ip, op = PRICING[event.model]
                span.cost = (
                    event.input_tokens * ip + event.output_tokens * op
                ) / 1_000_000
                span.attributes = {
                    **span.attributes,
                    "pricing_version": PRICING_VERSION,
                }
            else:
                span.cost = None
            if event.kind == "agent" and event.parent_span_id is None:
                run.status = event.status
                run.name = event.run_name
                run.ended_at = event.ended_at
        db.add(
            TelemetryEvent(
                id=uid(),
                project_id=project_id,
                event_id=event.event_id,
                run_id=run.id,
                payload=event.model_dump(mode="json"),
                processed=False,
            )
        )
        db.flush()
        affected.add(run.id)
        accepted += 1
    for run_id in affected:
        run = db.get(Run, run_id)
        spans = list(db.scalars(select(Span).where(Span.run_id == run_id)))
        llms = [s for s in spans if s.kind == "llm"]
        run.input_tokens = sum(s.input_tokens for s in spans)
        run.output_tokens = sum(s.output_tokens for s in spans)
        run.cost = (
            sum(s.cost or 0 for s in llms)
            if llms and all(s.cost is not None for s in llms)
            else None
        )
    db.flush()
    return {"accepted": accepted, "duplicates": duplicate, "run_ids": sorted(affected)}


def otlp_events(message, agent_id):
    def unpack(value):
        selected = value.WhichOneof("value")
        if selected == "array_value":
            return [unpack(v) for v in value.array_value.values]
        if selected == "kvlist_value":
            return {v.key: unpack(v.value) for v in value.kvlist_value.values}
        return getattr(value, selected) if selected else None

    events = []
    for resource in message.resource_spans:
        resource_attrs = {a.key: unpack(a.value) for a in resource.resource.attributes}
        for scope in resource.scope_spans:
            for span in scope.spans:
                attrs = {
                    **resource_attrs,
                    **{a.key: unpack(a.value) for a in span.attributes},
                }
                trace_id = span.trace_id.hex()
                started = datetime.fromtimestamp(
                    span.start_time_unix_nano / 1e9, timezone.utc
                )
                ended = (
                    datetime.fromtimestamp(span.end_time_unix_nano / 1e9, timezone.utc)
                    if span.end_time_unix_nano
                    else None
                )
                error = span.status.message if span.status.code == 2 else None
                span_id = span.span_id.hex()
                events.append(
                    SpanEvent(
                        event_id=f"{trace_id}:{span_id}:{span.end_time_unix_nano}",
                        agent_id=agent_id,
                        run_id=str(attrs.get("agentscope.run_id", trace_id)),
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=span.parent_span_id.hex() or None,
                        name=span.name,
                        kind=attrs.get(
                            "agentscope.kind",
                            "agent"
                            if not span.parent_span_id
                            else "llm"
                            if "gen_ai.request.model" in attrs
                            else "tool",
                        ),
                        status="failed"
                        if span.status.code == 2
                        else "completed"
                        if ended
                        else "running",
                        started_at=started,
                        ended_at=ended,
                        input_tokens=attrs.get("gen_ai.usage.input_tokens", 0),
                        output_tokens=attrs.get("gen_ai.usage.output_tokens", 0),
                        model=attrs.get("gen_ai.request.model"),
                        attributes=attrs,
                        error=error,
                    )
                )
    return events
