import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from google.protobuf.json_format import ParseDict, ParseError
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession
from starlette.responses import StreamingResponse

from .config import secret_file
from .db import (
    LOCAL,
    Agent,
    Anomaly,
    APIKey,
    Audit,
    Incident,
    Investigation,
    Project,
    Remediation,
    Run,
    Session,
    Settings,
    Span,
    engine,
    now,
    uid,
)
from .schemas import (
    AgentCreate,
    AgentUpdate,
    EventBatch,
    KeyCreate,
    ProjectCreate,
    ProjectSettings,
    SimulationRequest,
)
from .services import (
    audit,
    execute_demo,
    investigate,
    process_outbox,
    settings_for,
    simulate,
)
from .telemetry import PRICING_VERSION, aware, ingest, otlp_events

logger = logging.getLogger("agentscope")
TOKEN_FILE = LOCAL / "admin-token"
if os.getenv("AGENTSCOPE_CONTAINER") == "1" or os.getenv("AGENTSCOPE_ADMIN_TOKEN_FILE"):
    ADMIN_TOKEN = secret_file("AGENTSCOPE_ADMIN_TOKEN_FILE")
elif os.getenv("AGENTSCOPE_ADMIN_TOKEN"):
    ADMIN_TOKEN = os.environ["AGENTSCOPE_ADMIN_TOKEN"]
else:
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_urlsafe(48))
        TOKEN_FILE.chmod(0o600)
    ADMIN_TOKEN = TOKEN_FILE.read_text().strip()


async def worker(stop):
    while not stop.is_set():
        try:
            await asyncio.to_thread(process_outbox)
            with Session() as db:
                unfinished = list(
                    db.scalars(
                        select(Investigation.id).where(
                            Investigation.status.in_(["queued", "running"])
                        )
                    )
                )
            for inv_id in unfinished:
                if stop.is_set():
                    break
                await asyncio.to_thread(investigate, inv_id)
        except Exception as exc:  # noqa: BLE001 — retry persisted work without logging secrets
            # Database/HTTP exceptions can include credentials or telemetry payloads.
            logger.error(
                "Background worker failed (%s); persisted work will be retried",
                type(exc).__name__,
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(_app):
    with Session() as db:
        db.execute(text("SELECT 1 FROM projects LIMIT 1"))
        if not db.scalar(select(Project.id)):
            db.add(
                Project(
                    name="My workspace",
                    description="Your agent observability workspace",
                )
            )
            db.commit()
    stop = asyncio.Event()
    task = asyncio.create_task(worker(stop))
    _app.state.stop = stop
    _app.state.draining = False
    _app.state.worker = task
    try:
        yield
    finally:
        # Finish the current synchronous transaction before disposing connections.
        stop.set()
        await task
        engine.dispose()


app = FastAPI(title="AgentScope API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def payload_limit(request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 2 * 1024 * 1024):
            return Response("Payload exceeds 2 MiB", status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2 * 1024 * 1024:
                return Response("Payload exceeds 2 MiB", status_code=413)
        request._body = bytes(body)
    return await call_next(request)


def get_db():
    with Session() as db:
        yield db


DB = Annotated[DBSession, Depends(get_db)]


def credential(request):
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.startswith("Bearer ") else ""


def admin(request: Request):
    if not hmac.compare_digest(credential(request), ADMIN_TOKEN):
        raise HTTPException(401, "Dashboard authentication required")


Admin = Annotated[None, Depends(admin)]


def project_scope(request: Request, db: DB):
    token = credential(request)
    if hmac.compare_digest(token, ADMIN_TOKEN):
        project_id = request.headers.get("x-project-id") or request.query_params.get(
            "project_id"
        )
        if not project_id:
            raise HTTPException(400, "X-Project-ID is required")
    else:
        key = db.scalar(
            select(APIKey).where(
                APIKey.digest == hashlib.sha256(token.encode()).hexdigest(),
                APIKey.revoked.is_(False),
            )
        )
        if not key:
            raise HTTPException(401, "A valid project API key is required")
        project_id = key.project_id
        requested = request.headers.get("x-project-id") or request.query_params.get(
            "project_id"
        )
        if requested and requested != project_id:
            raise HTTPException(403, "API key cannot access another project")
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return project_id


Scope = Annotated[str, Depends(project_scope)]


def record(db, model, object_id, project_id):
    row = db.get(model, object_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "Record not found in this project")
    return row


def serialize(row):
    return {
        c.name: (aware(value).isoformat() if hasattr(value, "isoformat") else value)
        for c in row.__table__.columns
        if (value := getattr(row, c.name)) is not None
    }


def run_view(db, run):
    agent = db.get(Agent, run.agent_id)
    end = aware(run.ended_at) if run.ended_at else now()
    return {
        **serialize(run),
        "cost": run.cost,
        "tokens": run.input_tokens + run.output_tokens,
        "duration_ms": max(
            0, round((end - aware(run.started_at)).total_seconds() * 1000)
        ),
        "agent_name": agent.name,
        "framework": agent.framework,
        "environment": agent.environment,
        "incidents": [
            serialize(i)
            for i in db.scalars(select(Incident).where(Incident.run_id == run.id))
        ],
    }


def agent_view(db, agent):
    runs = list(
        db.scalars(
            select(Run).where(Run.agent_id == agent.id).order_by(Run.started_at.desc())
        )
    )
    terminal = [r for r in runs if r.status in ("completed", "failed")]
    incidents = list(
        db.scalars(
            select(Incident)
            .where(Incident.agent_id == agent.id)
            .order_by(Incident.created_at.desc())
        )
    )
    return {
        **serialize(agent),
        "status": "degraded"
        if any(i.status not in ("RESOLVED", "DISMISSED") for i in incidents)
        else "active"
        if any(r.status == "running" for r in runs)
        else "healthy"
        if runs
        else "idle",
        "success_rate": round(
            sum(r.status == "completed" for r in terminal) / len(terminal) * 100, 1
        )
        if terminal
        else None,
        "average_latency_ms": round(
            sum(
                (aware(r.ended_at) - aware(r.started_at)).total_seconds() * 1000
                for r in terminal
                if r.ended_at
            )
            / len(terminal)
        )
        if terminal
        else None,
        "tokens": sum(r.input_tokens + r.output_tokens for r in runs),
        "run_count": len(runs),
        "recent_runs": [run_view(db, r) for r in runs[:5]],
        "recent_incidents": [serialize(i) for i in incidents[:5]],
    }


def incident_view(db, incident, full=False):
    anomaly = db.get(Anomaly, incident.anomaly_id)
    investigation = db.scalar(
        select(Investigation).where(Investigation.incident_id == incident.id)
    )
    remediation = db.scalar(
        select(Remediation).where(Remediation.incident_id == incident.id)
    )
    run = db.get(Run, incident.run_id)
    result = {
        **serialize(incident),
        "agent_name": db.get(Agent, incident.agent_id).name,
        "synthetic": run.synthetic,
        "anomaly": serialize(anomaly),
        "investigation_id": investigation.id if investigation else None,
        "investigation_status": investigation.status if investigation else None,
        "remediation": serialize(remediation) if remediation else None,
    }
    if full:
        result["investigation"] = serialize(investigation) if investigation else None
        result["run"] = run_view(db, run)
        result["audit"] = [
            serialize(a)
            for a in db.scalars(
                select(Audit)
                .where(
                    Audit.project_id == incident.project_id,
                    Audit.target_id.in_(
                        [
                            incident.id,
                            investigation.id if investigation else "",
                            remediation.id if remediation else "",
                        ]
                    ),
                )
                .order_by(Audit.created_at)
            )
        ]
    return result


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(request: Request, db: DB):
    try:
        db.execute(text("SELECT 1 FROM projects LIMIT 1"))
        if (
            os.getenv("AGENTSCOPE_CONTAINER") == "1"
            and db.scalar(text("SELECT version_num FROM alembic_version")) != "001"
        ):
            raise RuntimeError("Migrations not current")
        if request.app.state.worker.done():
            raise RuntimeError("Worker stopped")
    except (SQLAlchemyError, RuntimeError):
        raise HTTPException(
            503, "Database, migrations, or background worker unavailable"
        ) from None
    return {
        "status": "ready",
        "storage": db.get_bind().dialect.name,
        "processing": "durable-local-outbox",
        "investigator": "deterministic-langgraph",
    }


@app.get("/api/v1/projects")
def projects(db: DB, _: Admin):
    return [
        serialize(p) for p in db.scalars(select(Project).order_by(Project.created_at))
    ]


@app.post("/api/v1/projects", status_code=201)
def create_project(body: ProjectCreate, db: DB, _: Admin):
    project = Project(**body.model_dump())
    db.add(project)
    db.commit()
    return serialize(project)


@app.get("/api/v1/agents")
def agents(db: DB, project_id: Scope):
    return [
        agent_view(db, a)
        for a in db.scalars(
            select(Agent).where(Agent.project_id == project_id).order_by(Agent.name)
        )
    ]


@app.post("/api/v1/agents", status_code=201)
def create_agent(body: AgentCreate, db: DB, project_id: Scope):
    existing = db.scalar(
        select(Agent).where(
            Agent.project_id == project_id,
            Agent.name == body.name,
            Agent.environment == body.environment,
        )
    )
    if existing:
        return agent_view(db, existing)
    agent = Agent(project_id=project_id, **body.model_dump())
    db.add(agent)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Agent already registered")
    return agent_view(db, agent)


@app.get("/api/v1/agents/{agent_id}")
def agent_detail(agent_id: str, db: DB, project_id: Scope):
    return agent_view(db, record(db, Agent, agent_id, project_id))


@app.patch("/api/v1/agents/{agent_id}")
def update_agent(agent_id: str, body: AgentUpdate, db: DB, project_id: Scope, _: Admin):
    agent = record(db, Agent, agent_id, project_id)
    if "control_adapter" in body.configuration:
        raise HTTPException(
            422, "Control adapters cannot be enabled through telemetry configuration"
        )
    agent.configuration = {
        **body.configuration,
        **({"control_adapter": "demo"} if agent.synthetic else {}),
    }
    audit(db, project_id, "agent.configuration.updated", agent.id)
    db.commit()
    return agent_view(db, agent)


@app.post("/api/v1/telemetry/events", status_code=202)
def events(body: EventBatch, db: DB, project_id: Scope):
    try:
        result = ingest(db, project_id, body.events)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Concurrent duplicate ingestion; retry the identical batch"
        )
    return result


@app.post("/v1/traces")
async def traces(request: Request, db: DB, project_id: Scope):
    agent_id = request.headers.get("x-agent-id")
    if not agent_id:
        raise HTTPException(400, "X-Agent-ID is required for OTLP")
    record(db, Agent, agent_id, project_id)
    message = ExportTraceServiceRequest()
    content_type = request.headers.get("content-type", "").split(";")[0]
    try:
        if content_type == "application/x-protobuf":
            message.ParseFromString(await request.body())
        elif content_type == "application/json":
            ParseDict(await request.json(), message)
        else:
            raise HTTPException(415, "Use application/x-protobuf or application/json")
        batch = otlp_events(message, agent_id)
        if len(batch) > 1000:
            raise HTTPException(413, "Maximum 1000 spans per batch")
        if batch:
            ingest(db, project_id, batch)
            db.commit()
    except HTTPException:
        raise
    except DecodeError as exc:
        raise HTTPException(400, "Malformed OTLP protobuf") from exc
    except (ValidationError, ValueError, TypeError, ParseError) as exc:
        raise HTTPException(422, "Invalid OTLP span data") from exc
    return (
        Response(
            ExportTraceServiceResponse().SerializeToString(),
            media_type="application/x-protobuf",
        )
        if content_type == "application/x-protobuf"
        else {}
    )


@app.get("/api/v1/runs")
def runs(
    db: DB,
    project_id: Scope,
    search: str = "",
    status: str | None = None,
    synthetic: bool | None = None,
    hours: int = Query(24, ge=1, le=8760),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(Run).where(
        Run.project_id == project_id, Run.started_at >= now() - timedelta(hours=hours)
    )
    if status:
        stmt = stmt.where(Run.status == status)
    if synthetic is not None:
        stmt = stmt.where(Run.synthetic == synthetic)
    if search:
        stmt = stmt.join(Agent).where(
            Run.name.ilike(f"%{search}%")
            | Agent.name.ilike(f"%{search}%")
            | Run.id.ilike(f"%{search}%")
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {
        "items": [
            run_view(db, r)
            for r in db.scalars(
                stmt.order_by(Run.started_at.desc()).offset(offset).limit(limit)
            )
        ],
        "total": total,
    }


@app.get("/api/v1/runs/{run_id}")
def run_detail(run_id: str, db: DB, project_id: Scope):
    return run_view(db, record(db, Run, run_id, project_id))


@app.get("/api/v1/runs/{run_id}/trace")
def trace_detail(run_id: str, db: DB, project_id: Scope):
    run = record(db, Run, run_id, project_id)
    items = []
    for span in db.scalars(
        select(Span).where(Span.run_id == run_id).order_by(Span.started_at)
    ):
        start, end = (
            aware(span.started_at),
            aware(span.ended_at) if span.ended_at else now(),
        )
        items.append(
            {
                **serialize(span),
                "cost": span.cost,
                "duration_ms": max(0, round((end - start).total_seconds() * 1000)),
                "offset_ms": max(
                    0, round((start - aware(run.started_at)).total_seconds() * 1000)
                ),
            }
        )
    return {"run": run_view(db, run), "spans": items}


@app.get("/api/v1/anomalies")
def anomalies(db: DB, project_id: Scope):
    return [
        serialize(a)
        for a in db.scalars(
            select(Anomaly)
            .where(Anomaly.project_id == project_id)
            .order_by(Anomaly.created_at.desc())
            .limit(200)
        )
    ]


@app.get("/api/v1/incidents")
def incidents(
    db: DB,
    project_id: Scope,
    search: str = "",
    status: str | None = None,
    severity: str | None = None,
    sort: str = "newest",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(Incident).where(Incident.project_id == project_id)
    if status == "active":
        stmt = stmt.where(Incident.status.notin_(["RESOLVED", "DISMISSED"]))
    elif status:
        stmt = stmt.where(Incident.status == status)
    if severity:
        stmt = stmt.where(Incident.severity == severity)
    if search:
        stmt = stmt.join(Agent).where(
            Incident.title.ilike(f"%{search}%") | Agent.name.ilike(f"%{search}%")
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = (
        Incident.created_at.asc() if sort == "oldest" else Incident.created_at.desc()
    )
    return {
        "items": [
            incident_view(db, i)
            for i in db.scalars(stmt.order_by(order).offset(offset).limit(limit))
        ],
        "total": total,
    }


@app.get("/api/v1/incidents/{incident_id}")
def incident_detail(incident_id: str, db: DB, project_id: Scope):
    return incident_view(db, record(db, Incident, incident_id, project_id), full=True)


@app.post("/api/v1/incidents/{incident_id}/investigate", status_code=202)
def start_investigation(incident_id: str, db: DB, project_id: Scope, _: Admin):
    incident = record(db, Incident, incident_id, project_id)
    if incident.status in ("RESOLVED", "DISMISSED", "VERIFYING", "MITIGATING"):
        raise HTTPException(409, "Incident cannot be investigated in its current state")
    inv = db.scalar(
        select(Investigation).where(Investigation.incident_id == incident_id)
    )
    if inv and inv.status != "failed":
        return serialize(inv)
    if inv:
        inv.status, inv.timeline, inv.progress, inv.report = "queued", [], 0, {}
    else:
        inv = Investigation(id=uid(), project_id=project_id, incident_id=incident_id)
        db.add(inv)
    incident.status = "INVESTIGATING"
    audit(db, project_id, "investigation.started", inv.id)
    db.commit()
    return serialize(inv)


@app.get("/api/v1/investigations")
def investigations(db: DB, project_id: Scope):
    return [
        {
            **serialize(i),
            "incident_title": record(db, Incident, i.incident_id, project_id).title,
            "agent_name": record(
                db,
                Agent,
                record(db, Incident, i.incident_id, project_id).agent_id,
                project_id,
            ).name,
        }
        for i in db.scalars(
            select(Investigation)
            .where(Investigation.project_id == project_id)
            .order_by(Investigation.created_at.desc())
            .limit(100)
        )
    ]


@app.get("/api/v1/investigations/{investigation_id}")
def investigation_detail(investigation_id: str, db: DB, project_id: Scope):
    inv = record(db, Investigation, investigation_id, project_id)
    return {
        **serialize(inv),
        "incident": incident_view(db, db.get(Incident, inv.incident_id), full=True),
    }


@app.post("/api/v1/remediations/{remediation_id}/approve")
def approve(remediation_id: str, db: DB, project_id: Scope, _: Admin):
    remediation = record(db, Remediation, remediation_id, project_id)
    if remediation.status != "proposed":
        if remediation.approved_at:
            return serialize(remediation)
        raise HTTPException(409, "Proposal cannot be approved in its current state")
    remediation.status, remediation.approved_at = "approved", now()
    audit(db, project_id, "remediation.approved", remediation.id)
    db.commit()
    return serialize(remediation)


@app.post("/api/v1/remediations/{remediation_id}/execute")
def execute(remediation_id: str, db: DB, project_id: Scope, _: Admin):
    remediation = record(db, Remediation, remediation_id, project_id)
    if remediation.executed_at:
        return serialize(remediation)
    if remediation.status != "approved" or not remediation.approved_at:
        raise HTTPException(409, "Explicit approval is required")
    incident = record(db, Incident, remediation.incident_id, project_id)
    run, agent = (
        record(db, Run, incident.run_id, project_id),
        record(db, Agent, incident.agent_id, project_id),
    )
    if (
        not run.synthetic
        or not agent.synthetic
        or agent.configuration.get("control_adapter") != "demo"
    ):
        raise HTTPException(
            409, "Recommendation only: this agent has no compatible control adapter"
        )
    if not settings_for(db, project_id)["allow_demo_control"]:
        raise HTTPException(
            409,
            "Enable demo control in Settings → Remediation policies before execution",
        )
    claimed = db.execute(
        update(Remediation)
        .where(
            Remediation.id == remediation.id,
            Remediation.status == "approved",
            Remediation.executed_at.is_(None),
        )
        .values(status="executing")
        .returning(Remediation.id)
    ).scalar_one_or_none()
    if not claimed:
        db.rollback()
        return serialize(record(db, Remediation, remediation_id, project_id))
    execute_demo(db, remediation)
    db.commit()
    return serialize(remediation)


@app.get("/api/v1/settings")
def get_settings(db: DB, project_id: Scope):
    return settings_for(db, project_id)


@app.get("/api/v1/settings/provider-status")
def provider_readiness(project_id: Scope, _: Admin):
    from .provider import provider_status

    return provider_status()


@app.put("/api/v1/settings")
def put_settings(body: ProjectSettings, db: DB, project_id: Scope, _: Admin):
    row = db.scalar(select(Settings).where(Settings.project_id == project_id))
    if not row:
        row = Settings(project_id=project_id)
        db.add(row)
    row.value = body.model_dump()
    audit(db, project_id, "settings.updated", project_id)
    db.commit()
    return row.value


@app.get("/api/v1/api-keys")
def api_keys(db: DB, project_id: Scope, _: Admin):
    return [
        {k: v for k, v in serialize(key).items() if k != "digest"}
        for key in db.scalars(
            select(APIKey)
            .where(APIKey.project_id == project_id)
            .order_by(APIKey.created_at.desc())
        )
    ]


@app.post("/api/v1/api-keys", status_code=201)
def create_key(body: KeyCreate, db: DB, project_id: Scope, _: Admin):
    value = "as_" + secrets.token_urlsafe(32)
    key = APIKey(
        project_id=project_id,
        name=body.name,
        prefix=value[:10],
        digest=hashlib.sha256(value.encode()).hexdigest(),
    )
    db.add(key)
    db.flush()
    audit(db, project_id, "api_key.created", key.id)
    db.commit()
    return {"id": key.id, "name": key.name, "key": value, "prefix": key.prefix}


@app.delete("/api/v1/api-keys/{key_id}", status_code=204)
def revoke_key(key_id: str, db: DB, project_id: Scope, _: Admin):
    key = record(db, APIKey, key_id, project_id)
    key.revoked = True
    audit(db, project_id, "api_key.revoked", key.id)
    db.commit()


@app.post("/api/v1/simulations", status_code=201)
def simulation(body: SimulationRequest, db: DB, project_id: Scope, _: Admin):
    result = simulate(db, project_id, body.scenario, body.seed, body.include_baseline)
    db.commit()
    return result


@app.get("/api/v1/metrics/overview")
def overview(
    db: DB,
    project_id: Scope,
    hours: int = Query(24, ge=1, le=8760),
    synthetic: bool | None = None,
):
    since = now() - timedelta(hours=hours)
    stmt = select(Run).where(Run.project_id == project_id, Run.started_at >= since)
    if synthetic is not None:
        stmt = stmt.where(Run.synthetic == synthetic)
    rows = list(db.scalars(stmt))
    spans = (
        list(db.scalars(select(Span).where(Span.run_id.in_([r.id for r in rows]))))
        if rows
        else []
    )
    terminal = [r for r in rows if r.status in ("completed", "failed")]
    durations = sorted(
        (aware(r.ended_at) - aware(r.started_at)).total_seconds() * 1000
        for r in terminal
        if r.ended_at
    )

    def percentile(q):
        return (
            round(durations[min(len(durations) - 1, round((len(durations) - 1) * q))])
            if durations
            else None
        )

    active = list(
        db.scalars(
            select(Incident).where(
                Incident.project_id == project_id,
                Incident.status.notin_(["RESOLVED", "DISMISSED"]),
            )
        )
    )
    if synthetic is not None:
        active = [
            i
            for i in active
            if record(db, Run, i.run_id, project_id).synthetic == synthetic
        ]
    llms = [s for s in spans if s.kind == "llm"]
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

    def pos(value):
        return min(
            23,
            max(0, int((aware(value) - since).total_seconds() / (hours * 3600 / 24))),
        )

    for run in rows:
        bins[pos(run.started_at)]["runs"] += 1
        bins[pos(run.started_at)]["input_tokens"] += run.input_tokens
        bins[pos(run.started_at)]["output_tokens"] += run.output_tokens
    for span in spans:
        if span.kind == "tool":
            bins[pos(span.started_at)]["tool_calls"] += 1
            bins[pos(span.started_at)]["tool_errors"] += int(span.status == "failed")
    all_agents = list(db.scalars(select(Agent).where(Agent.project_id == project_id)))
    if synthetic is not None:
        all_agents = [a for a in all_agents if a.synthetic == synthetic]
    invs = list(
        db.scalars(
            select(Investigation)
            .where(Investigation.project_id == project_id)
            .order_by(Investigation.created_at.desc())
            .limit(5)
        )
    )
    return {
        "registered_agents": len(all_agents),
        "active_runs": sum(r.status == "running" for r in rows),
        "completed_runs": sum(r.status == "completed" for r in rows),
        "failed_runs": sum(r.status == "failed" for r in rows),
        "success_rate": round(
            sum(r.status == "completed" for r in terminal) / len(terminal) * 100, 1
        )
        if terminal
        else None,
        "tokens": sum(r.input_tokens + r.output_tokens for r in rows),
        "input_tokens": sum(r.input_tokens for r in rows),
        "output_tokens": sum(r.output_tokens for r in rows),
        "cost": round(sum(s.cost or 0 for s in llms), 6)
        if llms and all(s.cost is not None for s in llms)
        else None,
        "pricing_version": PRICING_VERSION,
        "active_incidents": len(active),
        "total_runs": len(rows),
        "average_latency_ms": round(sum(durations) / len(durations))
        if durations
        else None,
        "latency_p50": percentile(0.5),
        "latency_p95": percentile(0.95),
        "latency_p99": percentile(0.99),
        "tool_calls": sum(s.kind == "tool" for s in spans),
        "tool_errors": sum(s.kind == "tool" and s.status == "failed" for s in spans),
        "synthetic_runs": sum(r.synthetic for r in rows),
        "series": bins,
        "agents": [agent_view(db, a) for a in all_agents],
        "incidents": [incident_view(db, i) for i in active[:5]],
        "investigations": [
            {
                **serialize(i),
                "incident_title": record(db, Incident, i.incident_id, project_id).title,
            }
            for i in invs
        ],
        "recent_runs": [
            run_view(db, r)
            for r in sorted(rows, key=lambda r: r.started_at, reverse=True)[:5]
        ],
        "updated_at": now().isoformat(),
    }


@app.get("/api/v1/events")
async def event_stream(request: Request, project_id: Scope):
    async def stream():
        # A bounded stream also lets an ASGI server drain clients on shutdown.
        # EventSource reconnects automatically and immediately refreshes data.
        deadline = asyncio.get_running_loop().time() + 60
        while not await request.is_disconnected() and not request.app.state.draining:
            yield f"event: refresh\ndata: {json.dumps({'project_id': project_id, 'at': now().isoformat()})}\n\n"
            await asyncio.sleep(3)
            if asyncio.get_running_loop().time() >= deadline:
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/metrics")
def prometheus(db: DB, _: Admin):
    return Response(
        f"# TYPE agentscope_runs_total gauge\nagentscope_runs_total {db.scalar(select(func.count(Run.id)))}\n# TYPE agentscope_spans_total gauge\nagentscope_spans_total {db.scalar(select(func.count(Span.id)))}\n",
        media_type="text/plain; version=0.0.4",
    )
