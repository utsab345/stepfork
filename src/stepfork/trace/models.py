"""Typed event models for the Stepfork `.sftrace` v0.1 contract."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypeAlias, TypeVar, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import TypeAliasType

from stepfork.trace.manifest import (
    EnvironmentInfo,
    FailureInfo,
    RunStatus,
    TraceTotals,
)
from stepfork.trace.replay_policy import ReplayPolicy

JsonPrimitive: TypeAlias = str | int | float | bool | None
if TYPE_CHECKING:
    JsonValue: TypeAlias = JsonPrimitive | list[Any] | dict[str, Any]
else:
    JsonValue = TypeAliasType(
        "JsonValue",
        JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"],
    )
E = TypeVar("E", bound="EventBase")


def _new_event_id() -> str:
    """Return an opaque local event ID."""
    return f"evt_{uuid4().hex}"


def _new_run_id() -> str:
    """Return an opaque local run ID."""
    return f"run_{uuid4().hex}"


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class EventStatus(StrEnum):
    """Status for a recorded event."""

    OK = "ok"
    ERROR = "error"
    SKIPPED = "skipped"


class EventType(StrEnum):
    """The deliberately small v0.1 event taxonomy."""

    RUN_START = "run_start"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATE_CHANGE = "state_change"
    ERROR = "error"
    RUN_END = "run_end"


class EventBase(BaseModel):
    """Common fields shared by all persisted trace events."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_event_id, min_length=1)
    run_id: str = Field(default_factory=_new_run_id, min_length=1)
    parent_id: str | None = Field(default=None, min_length=1)

    step: int = Field(default=0, ge=0)

    type: EventType
    timestamp: datetime = Field(default_factory=_utc_now)
    duration_ms: int | None = Field(default=None, ge=0)

    status: EventStatus = EventStatus.OK
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN

    input_hash: str | None = None
    output_hash: str | None = None

    redactions: list[str] = Field(default_factory=list)

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        """Reject naive datetimes instead of assuming UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class RunStart(EventBase):
    """Event marking the start of a run."""

    type: Literal[EventType.RUN_START] = EventType.RUN_START

    input: JsonValue | None = None


class LLMRequest(EventBase):
    """Request sent to an LLM provider."""

    type: Literal[EventType.LLM_REQUEST] = EventType.LLM_REQUEST

    provider: str | None = Field(default=None, min_length=1)
    model: str = Field(min_length=1)
    input: JsonValue


class LLMResponse(EventBase):
    """Response received from an LLM provider."""

    type: Literal[EventType.LLM_RESPONSE] = EventType.LLM_RESPONSE

    model: str | None = Field(default=None, min_length=1)
    output: JsonValue

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class ToolCall(EventBase):
    """Call made to a tool.

    Tool calls can be constructed directly with only `name` and JSON `input`.
    Runtime defaults fill in event identity, run identity, 0-based step, and a
    timezone-aware timestamp; `Trace.add()` normalizes run ID and step.
    """

    type: Literal[EventType.TOOL_CALL] = EventType.TOOL_CALL

    name: str = Field(min_length=1)
    input: JsonValue


class ToolResult(EventBase):
    """Result returned by a tool."""

    type: Literal[EventType.TOOL_RESULT] = EventType.TOOL_RESULT

    name: str = Field(min_length=1)
    output: JsonValue


class StateChange(EventBase):
    """Change to agent state represented as JSON-compatible values."""

    type: Literal[EventType.STATE_CHANGE] = EventType.STATE_CHANGE

    key: str | None = Field(default=None, min_length=1)
    before: JsonValue | None = None
    after: JsonValue | None = None


class ErrorEvent(EventBase):
    """Error observed during a run."""

    type: Literal[EventType.ERROR] = EventType.ERROR

    status: EventStatus = EventStatus.ERROR
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: JsonValue | None = None


class RunEnd(EventBase):
    """Event marking the end of a run."""

    type: Literal[EventType.RUN_END] = EventType.RUN_END

    run_status: RunStatus
    output: JsonValue | None = None


Event: TypeAlias = Annotated[
    RunStart
    | LLMRequest
    | LLMResponse
    | ToolCall
    | ToolResult
    | StateChange
    | ErrorEvent
    | RunEnd,
    Field(discriminator="type"),
]


class Trace(BaseModel):
    """Minimal in-memory trace container.

    `Trace.add()` uses 0-based logical steps: the first added event receives
    step `0`, the second receives step `1`, and so on. Partial traces can be
    saved for development and later validated in partial or strict mode.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=_new_run_id, min_length=1)
    agent_name: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=_utc_now)
    status: RunStatus = RunStatus.RUNNING
    failure: FailureInfo | None = None
    environment: EnvironmentInfo = Field(default_factory=EnvironmentInfo)
    totals: TraceTotals = Field(default_factory=TraceTotals)
    events: list[Event] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        """Reject naive datetimes instead of assuming UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    def add(self, event: E) -> E:
        """Append an event after normalizing run ID and 0-based logical step."""
        normalized = event.model_copy(
            update={"run_id": self.run_id, "step": len(self.events)}
        )
        self.events.append(cast(Event, normalized))
        self.totals = self._computed_totals()
        return normalized

    def _computed_totals(self) -> TraceTotals:
        """Return manifest counters derived from the current event sequence."""
        return TraceTotals(
            events=len(self.events),
            llm_calls=sum(event.type is EventType.LLM_REQUEST for event in self.events),
            tool_calls=sum(event.type is EventType.TOOL_CALL for event in self.events),
            cost_usd=self.totals.cost_usd,
            duration_ms=self.totals.duration_ms,
        )

    def save(
        self,
        path: str | Path,
        *,
        status: RunStatus | str | None = None,
        failure: FailureInfo | None = None,
        environment: EnvironmentInfo | None = None,
        overwrite: bool = False,
    ) -> Path:
        """Persist this trace as a `.sftrace` directory bundle."""
        from stepfork.trace.storage import save_trace

        return save_trace(
            self,
            Path(path),
            status=status,
            failure=failure,
            environment=environment,
            overwrite=overwrite,
        )

    @classmethod
    def load(cls, path: str | Path) -> Trace:
        """Load a trace from a `.sftrace` directory bundle."""
        from stepfork.trace.storage import load_trace

        return load_trace(Path(path))
