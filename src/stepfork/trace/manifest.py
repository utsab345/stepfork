"""Manifest models for the Stepfork `.sftrace` v0.1 contract."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RunStatus(StrEnum):
    """Lifecycle status for an agent run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FailureInfo(BaseModel):
    """Failure summary stored in a trace manifest."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    step: int = Field(ge=0)


class EnvironmentInfo(BaseModel):
    """Optional environment metadata captured by future recorders."""

    model_config = ConfigDict(extra="forbid")

    python: str | None = None
    os: str | None = None
    stepfork_version: str | None = None


class TraceTotals(BaseModel):
    """Aggregate counters for a trace."""

    model_config = ConfigDict(extra="forbid")

    events: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)


class TraceManifest(BaseModel):
    """Top-level manifest for a portable `.sftrace` directory."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["stepfork"] = "stepfork"
    schema_version: Literal["0.1"] = "0.1"

    run_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    created_at: datetime

    status: RunStatus

    failure: FailureInfo | None = None
    environment: EnvironmentInfo = Field(default_factory=EnvironmentInfo)
    totals: TraceTotals = Field(default_factory=TraceTotals)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        """Reject naive datetimes instead of assuming UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def failure_must_match_status(self) -> Self:
        """Keep manifest failure details aligned with run status."""
        if self.status is RunStatus.FAILED and self.failure is None:
            raise ValueError("failure is required when status is failed")
        if self.status is not RunStatus.FAILED and self.failure is not None:
            raise ValueError("failure must be omitted unless status is failed")
        return self
