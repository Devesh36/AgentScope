"""Persistent application storage; SQLite local mode or PostgreSQL via DATABASE_URL."""

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import database_url

ROOT = Path(__file__).resolve().parents[3]
LOCAL = Path(os.getenv("AGENTSCOPE_DATA_DIR", str(ROOT / ".local")))
LOCAL.mkdir(parents=True, exist_ok=True)
DATABASE_URL = database_url(LOCAL)
IS_SQLITE = str(DATABASE_URL).startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {"connect_timeout": 5},
    pool_pre_ping=True,
)
if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def sqlite_settings(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


Session = sessionmaker(engine, expire_on_commit=False)


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class Project(Record, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000), default="")


class Scoped(Record):
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)


class APIKey(Scoped, Base):
    __tablename__ = "api_keys"
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(16))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Agent(Scoped, Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("project_id", "name", "environment"),)
    name: Mapped[str] = mapped_column(String(120))
    framework: Mapped[str] = mapped_column(String(80), default="Custom")
    environment: Mapped[str] = mapped_column(String(80), default="development")
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class Run(Scoped, Base):
    __tablename__ = "runs"
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    __table_args__ = (UniqueConstraint("project_id", "external_id"),)
    name: Mapped[str] = mapped_column(String(200), default="Agent execution")
    status: Mapped[str] = mapped_column(String(24), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Span(Scoped, Base):
    __tablename__ = "spans"
    __table_args__ = (
        UniqueConstraint("project_id", "trace_id", "span_id"),
        Index("ix_spans_run_start", "run_id", "started_at"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    trace_id: Mapped[str] = mapped_column(String(32))
    span_id: Mapped[str] = mapped_column(String(16))
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class TelemetryEvent(Scoped, Base):
    __tablename__ = "telemetry_events"
    __table_args__ = (UniqueConstraint("project_id", "event_id"),)
    event_id: Mapped[str] = mapped_column(String(128))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Anomaly(Scoped, Base):
    __tablename__ = "anomalies"
    __table_args__ = (UniqueConstraint("run_id", "kind"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    kind: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active")
    rule_version: Mapped[str] = mapped_column(String(20), default="1.0")
    measurements: Mapped[dict] = mapped_column(JSON)
    evidence_ids: Mapped[list] = mapped_column(JSON)


class Incident(Scoped, Base):
    __tablename__ = "incidents"
    anomaly_id: Mapped[str] = mapped_column(ForeignKey("anomalies.id"), unique=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="OPEN")


class Investigation(Scoped, Base):
    __tablename__ = "investigations"
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    phase: Mapped[str] = mapped_column(String(80), default="Collect evidence")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    timeline: Mapped[list] = mapped_column(JSON, default=list)


class Remediation(Scoped, Base):
    __tablename__ = "remediations"
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), unique=True)
    action: Mapped[str] = mapped_column(String(40), default="cancel_run")
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification: Mapped[dict] = mapped_column(JSON, default=dict)


class Settings(Scoped, Base):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("project_id"),)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Audit(Scoped, Base):
    __tablename__ = "audit_log"
    action: Mapped[str] = mapped_column(String(100))
    target_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
