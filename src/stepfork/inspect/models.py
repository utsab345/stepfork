"""Structured models for trace inspection output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class EventSummary(BaseModel):
    """Concise event data for timeline display."""

    model_config = ConfigDict(extra="forbid")

    id: str
    step: int
    type: str
    label: str
    status: str
    parent_id: str | None = None
    duration_ms: int | None = None
    details: dict[str, Any]


class TraceInspection(BaseModel):
    """Sanitized trace inspection result."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    agent_name: str
    run_id: str
    schema_version: str
    status: str
    created_at: str
    events: int
    llm_calls: int
    tool_calls: int
    duration_ms: int | None = None
    failure: dict[str, Any] | None = None
    integrity: str
    timeline: list[EventSummary]
