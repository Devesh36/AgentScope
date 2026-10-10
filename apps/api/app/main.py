import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
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
from .read_models import agent_views, overview_metrics, run_views, serialize
from .schemas import (
    AgentCreate,
    AgentUpdate,
    EventBatch,
    KeyCreate,
    ProjectCreate,
    ProjectSettings,
    SimulationRequest,
    WatchUpdate,
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


# Streaming responses do not use this session after authentication. Release it
# before streaming so open dashboard tabs do not occupy the database pool.
DB = Annotated[DBSession, Depends(get_db, scope="function")]


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


def run_view(db, run):
    return run_views(db, [run])[0]


def watch_view(agent):
    value = agent.configuration["watch"]
    if not isinstance(value, dict):
        value = {}
    try:
        live = aware(datetime.fromisoformat(value["expires_at"])) > now()
    except (KeyError, ValueError, TypeError):
        live = False
    status = value.get("status", "disconnected")
    if status != "stopped" and not live:
        status = "disconnected"
    return {
        "agent_id": agent.id,
        "repository": value.get("repository", agent.name),
        "status": status,
        "heartbeat_at": value.get("heartbeat_at"),
    }


def agent_view(db, agent):
    return agent_views(db, [agent])[0]


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
    items = list(
        db.scalars(
            select(Agent).where(Agent.project_id == project_id).order_by(Agent.name)
        )
    )
    return agent_views(db, items)


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


@app.put("/api/v1/agents/{agent_id}/watch")
def watch_heartbeat(
    agent_id: str, body: WatchUpdate, db: DB, project_id: Scope, _: Admin
):
    agent = record(db, Agent, agent_id, project_id)
    if agent.synthetic:
        raise HTTPException(422, "Watch sessions require a real telemetry agent")
    previous = agent.configuration.get("watch", {})
    if not isinstance(previous, dict):
        previous = {}
    session_id = str(body.session_id)
    if previous.get("session_id") != session_id and previous.get("status") != "stopped":
        try:
            live = aware(datetime.fromisoformat(previous["expires_at"])) > now()
        except (KeyError, TypeError, ValueError):
            live = False
        if live:
            raise HTTPException(409, "This agent already has a live watch session")
    value = {
        **body.model_dump(mode="json"),
        "heartbeat_at": now().isoformat(),
        "expires_at": (now() + timedelta(seconds=35)).isoformat(),
    }
    agent.configuration = {**agent.configuration, "watch": value}
    if body.status == "stopped":
        # This closes the observation window, not the application's execution.
        # Later terminal telemetry can still supply the actual outcome.
        observed = list(
            db.scalars(
                select(Run).where(
                    Run.project_id == project_id,
                    Run.agent_id == agent_id,
                    Run.status == "running",
                )
            )
        )
        for run in observed:
            if run.status == "running":
                run.status = "interrupted"
                run.ended_at = now()
                run.meta = {**run.meta, "observation_interrupted": True}
        for span in db.scalars(
            select(Span)
            .join(Run)
            .where(
                Run.project_id == project_id,
                Run.agent_id == agent_id,
                Span.status == "running",
            )
        ):
            span.status = "interrupted"
            span.ended_at = now()
            span.attributes = {**span.attributes, "observation_interrupted": True}
    if previous.get("session_id") != session_id or (
        body.status == "stopped" and previous.get("status") != "stopped"
    ):
        audit(
            db,
            project_id,
            "watch.stopped" if body.status == "stopped" else "watch.started",
            agent_id,
        )
    db.commit()
    return value


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
        "items": run_views(
            db,
            list(
                db.scalars(
                    stmt.order_by(Run.started_at.desc(), Run.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ),
        ),
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
    metrics = overview_metrics(db, project_id, hours, synthetic)
    agent_query = select(Agent).where(Agent.project_id == project_id)
    if synthetic is not None:
        agent_query = agent_query.where(Agent.synthetic == synthetic)
    all_agents = list(db.scalars(agent_query.order_by(Agent.name)))
    active_query = (
        select(Incident)
        .join(Run, Run.id == Incident.run_id)
        .where(
            Incident.project_id == project_id,
            Incident.status.notin_(["RESOLVED", "DISMISSED"]),
        )
    )
    if synthetic is not None:
        active_query = active_query.where(Run.synthetic == synthetic)
    active_count = db.scalar(select(func.count()).select_from(active_query.subquery()))
    active = list(
        db.scalars(
            active_query.order_by(Incident.created_at.desc(), Incident.id.desc()).limit(
                5
            )
        )
    )
    investigations = db.execute(
        select(Investigation, Incident.title)
        .join(
            Incident,
            Incident.id == Investigation.incident_id,
        )
        .where(Investigation.project_id == project_id)
        .order_by(Investigation.created_at.desc())
        .limit(5)
    ).all()
    recent_query = select(Run).where(
        Run.project_id == project_id,
        Run.started_at >= now() - timedelta(hours=hours),
    )
    if synthetic is not None:
        recent_query = recent_query.where(Run.synthetic == synthetic)
    recent = list(
        db.scalars(recent_query.order_by(Run.started_at.desc(), Run.id.desc()).limit(5))
    )
    return {
        **metrics,
        "registered_agents": len(all_agents),
        "active_incidents": active_count,
        "pricing_version": PRICING_VERSION,
        "watch_sessions": [
            watch_view(a) for a in all_agents if a.configuration.get("watch")
        ],
        "agents": agent_views(db, all_agents),
        "incidents": [incident_view(db, i) for i in active],
        "investigations": [
            {**serialize(i), "incident_title": title} for i, title in investigations
        ],
        "recent_runs": run_views(db, recent, {a.id: a for a in all_agents}),
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
