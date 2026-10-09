from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


def validate_configuration(value):
    if "control_adapter" in value:
        raise ValueError(
            "Control adapters are registered by the server, not agent configuration"
        )
    tools = value.get("allowed_tools")
    if tools is not None and (
        not isinstance(tools, list)
        or len(tools) > 1000
        or not all(isinstance(t, str) and len(t) <= 200 for t in tools)
    ):
        raise ValueError("allowed_tools must be a string array with at most 1000 items")
    seconds = value.get("expected_duration_seconds", 0)
    if not isinstance(seconds, (int, float)) or not 0 <= seconds <= 86400:
        raise ValueError(
            "expected_duration_seconds must be a number between 0 and 86400"
        )
    return value


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    framework: str = Field(default="Custom", max_length=80)
    environment: str = Field(default="development", max_length=80)
    configuration: dict = Field(default_factory=dict)

    @field_validator("configuration")
    @classmethod
    def configuration_types(cls, value):
        return validate_configuration(value)


class AgentUpdate(BaseModel):
    configuration: dict

    @field_validator("configuration")
    @classmethod
    def configuration_types(cls, value):
        return validate_configuration(value)


class SpanEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    agent_id: str
    run_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(pattern=r"^[a-fA-F0-9]{32}$")
    span_id: str = Field(pattern=r"^[a-fA-F0-9]{16}$")
    parent_span_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{16}$")
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["agent", "tool", "llm", "progress"] = "agent"
    status: Literal["running", "completed", "failed", "paused", "cancelled"] = (
        "completed"
    )
    started_at: datetime
    ended_at: datetime | None = None
    input_tokens: int = Field(default=0, ge=0, le=1_000_000_000)
    output_tokens: int = Field(default=0, ge=0, le=1_000_000_000)
    model: str | None = Field(default=None, max_length=100)
    attributes: dict = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=2000)
    run_name: str = Field(default="Agent execution", max_length=200)

    @field_validator("started_at", "ended_at")
    @classmethod
    def timestamp(cls, value):
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("Use timezone-aware timestamps")
        if value.timestamp() > datetime.now(timezone.utc).timestamp() + 300:
            raise ValueError("Timestamp is more than five minutes in the future")
        return value.astimezone(timezone.utc)


class EventBatch(BaseModel):
    events: list[SpanEvent] = Field(min_length=1, max_length=1000)


class DetectionSettings(BaseModel):
    loop_threshold: int = Field(default=5, ge=3, le=1000)
    token_budget: int = Field(default=16000, ge=100, le=100_000_000)
    failure_threshold: int = Field(default=3, ge=2, le=1000)
    stall_seconds: int = Field(default=300, ge=30, le=86400)
    cost_budget: float = Field(default=1.0, gt=0, le=100000)


class ProjectSettings(BaseModel):
    detection: DetectionSettings = Field(default_factory=DetectionSettings)
    allow_demo_control: bool = False
    retention_days: int = Field(default=30, ge=1, le=3650)
    provider: Literal["deterministic", "openai_compatible"] = "deterministic"
    provider_base_url: str = Field(
        default="https://api.openai.com/v1", max_length=500, pattern=r"^https://[^\s]+$"
    )
    provider_model: str = Field(default="gpt-4.1-mini", min_length=1, max_length=100)


class SimulationRequest(BaseModel):
    scenario: Literal[
        "tool_loop",
        "token_budget",
        "tool_failure",
        "stalled",
        "unexpected_workflow",
        "healthy",
    ]
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    include_baseline: bool = True


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
