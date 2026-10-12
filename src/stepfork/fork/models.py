"""Data models for fork-at-step operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stepfork.trace.models import JsonValue


class ForkInfo(BaseModel):
    """Provenance metadata for a forked trace."""

    model_config = ConfigDict(extra="forbid")

    parent_trace_path: str | None = Field(default=None, min_length=1)
    parent_run_id: str = Field(min_length=1)
    fork_point_event_id: str = Field(min_length=1)
    fork_point_step: int = Field(ge=0)
    fork_timestamp: datetime
    overrides_applied: int = Field(default=0, ge=0)


class OverrideSpec(BaseModel):
    """Specification for overriding an event's output."""

    model_config = ConfigDict(extra="forbid")

    target_type: Literal["tool", "llm", "event"]
    target_identifier: str = Field(min_length=1)  # tool name, model name, or event ID
    override_value: JsonValue
    override_field: str = Field(default="output")  # output, input, etc.


@dataclass(frozen=True)
class ForkPoint:
    """Identifies where to fork a trace."""

    event_id: str | None
    step: int | None

    def __post_init__(self) -> None:
        """Validate that at least one identifier is provided."""
        if self.event_id is None and self.step is None:
            raise ValueError("fork point requires either event_id or step")


@dataclass(frozen=True)
class ForkResult:
    """Result of a fork operation."""

    success: bool
    forked_trace_path: str | None
    original_event_count: int
    forked_event_count: int
    fork_point_step: int
    fork_point_event_id: str
    overrides_applied: int
    error_message: str | None = None


class ForkError(Exception):
    """Raised when a fork operation fails."""
