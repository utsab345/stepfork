"""Build sanitized inspection summaries from loaded traces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stepfork.inspect.models import EventSummary, TraceInspection
from stepfork.trace import (
    ErrorEvent,
    Event,
    LLMRequest,
    LLMResponse,
    RunEnd,
    RunStart,
    StateChange,
    ToolCall,
    ToolResult,
    Trace,
    TraceStorageError,
)
from stepfork.trace.integrity import verify_bundle_integrity
from stepfork.trace.redaction import redact_json


def inspect_bundle(path: str | Path) -> TraceInspection:
    """Load and inspect a `.sftrace` bundle."""
    bundle_path = Path(path)
    trace = Trace.load(bundle_path)
    integrity = verify_bundle_integrity(bundle_path).status.value
    return inspect_trace(trace, path=str(bundle_path), integrity=integrity)


def inspect_trace(
    trace: Trace,
    *,
    path: str | None = None,
    integrity: str = "not_checked",
) -> TraceInspection:
    """Return a sanitized inspection summary for a trace."""
    return TraceInspection(
        path=path,
        agent_name=_sanitize_text(trace.agent_name),
        run_id=trace.run_id,
        schema_version="0.1",
        status=trace.status.value,
        created_at=trace.created_at.isoformat(),
        events=len(trace.events),
        llm_calls=trace.totals.llm_calls,
        tool_calls=trace.totals.tool_calls,
        duration_ms=trace.totals.duration_ms,
        failure=_sanitize_failure(trace.failure.model_dump(mode="json"))
        if trace.failure
        else None,
        integrity=integrity,
        timeline=[_event_summary(event) for event in trace.events],
    )


def filter_timeline(
    inspection: TraceInspection,
    *,
    errors_only: bool = False,
    step: int | None = None,
) -> TraceInspection:
    """Return an inspection copy with filtered timeline events."""
    timeline = inspection.timeline
    if errors_only:
        timeline = [
            event
            for event in timeline
            if event.status == "error" or event.type == "error"
        ]
    if step is not None:
        timeline = [event for event in timeline if event.step == step]
    return inspection.model_copy(update={"timeline": timeline})


def _event_summary(event: Event) -> EventSummary:
    payload = _sanitize_json(event.model_dump(mode="json"))
    return EventSummary(
        id=event.id,
        step=event.step,
        type=event.type.value,
        label=_event_label(event),
        status=event.status.value,
        parent_id=event.parent_id,
        duration_ms=event.duration_ms,
        details=_event_details(payload),
    )


def _event_label(event: Event) -> str:
    if isinstance(event, RunStart):
        return "run_start"
    if isinstance(event, LLMRequest):
        return event.model
    if isinstance(event, LLMResponse):
        return event.model or "llm_response"
    if isinstance(event, ToolCall | ToolResult):
        return event.name
    if isinstance(event, StateChange):
        return event.key or "state_change"
    if isinstance(event, ErrorEvent):
        return _sanitize_text(event.error_type)
    if isinstance(event, RunEnd):
        return event.run_status.value
    return event.type.value


def _event_details(payload: dict[str, Any]) -> dict[str, Any]:
    hidden = {
        "id",
        "run_id",
        "parent_id",
        "step",
        "type",
        "timestamp",
        "status",
        "replay_policy",
        "input_hash",
        "output_hash",
        "redactions",
    }
    return {key: value for key, value in payload.items() if key not in hidden}


def _sanitize_failure(value: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_json(value)
    if not isinstance(sanitized, dict):
        raise TraceStorageError("inspection failure sanitizer returned non-object")
    return sanitized


def _sanitize_json(value: Any) -> Any:
    return redact_json(value).value


def _sanitize_text(value: str) -> str:
    sanitized = redact_json(value).value
    if not isinstance(sanitized, str):
        raise TraceStorageError("inspection text sanitizer returned non-string")
    return sanitized
