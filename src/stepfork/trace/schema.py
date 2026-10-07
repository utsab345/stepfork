"""JSON Schema helpers for the Stepfork trace contract."""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from stepfork.trace.manifest import TraceManifest
from stepfork.trace.models import Event, Trace


def event_json_schema() -> dict[str, Any]:
    """Return the generated JSON Schema for the discriminated Event union."""
    return TypeAdapter(Event).json_schema()


def manifest_json_schema() -> dict[str, Any]:
    """Return the generated JSON Schema for trace manifests."""
    return TraceManifest.model_json_schema()


def trace_json_schema() -> dict[str, Any]:
    """Return the generated JSON Schema for the in-memory Trace model."""
    return Trace.model_json_schema()
