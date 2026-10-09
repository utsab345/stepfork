"""Structured, machine-readable behavioral diff models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stepfork.trace.models import JsonValue

ChangeKind = Literal["added", "removed", "changed", "unchanged"]
LeafChangeKind = Literal["added", "removed", "changed"]


class FieldChange(BaseModel):
    """One changed field difference between baseline and candidate."""

    model_config = ConfigDict(extra="forbid")

    path: str
    kind: LeafChangeKind
    expected: JsonValue | None = None
    actual: JsonValue | None = None


class StepDiff(BaseModel):
    """Comparison result for one aligned behavior step."""

    model_config = ConfigDict(extra="forbid")

    index: int
    kind: ChangeKind
    step_type: str
    label: str
    fields: list[str] = Field(default_factory=list)
    changes: list[FieldChange] = Field(default_factory=list)


class TraceSummary(BaseModel):
    """Identity metadata for one side of the comparison."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    agent_name: str
    run_id: str
    status: str
    events: int


class DiffResult(BaseModel):
    """Structured behavioral comparison between two traces."""

    model_config = ConfigDict(extra="forbid")

    equivalent: bool
    baseline: TraceSummary
    candidate: TraceSummary
    steps: list[StepDiff] = Field(default_factory=list)
    added: int = 0
    removed: int = 0
    changed: int = 0
    unchanged: int = 0
