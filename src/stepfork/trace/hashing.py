"""SHA-256 helpers for sanitized JSON payloads."""

from __future__ import annotations

import hashlib

from stepfork.trace.canonical import canonical_json_bytes
from stepfork.trace.models import (
    ErrorEvent,
    Event,
    JsonValue,
    LLMRequest,
    LLMResponse,
    RunEnd,
    RunStart,
    StateChange,
    ToolCall,
    ToolResult,
)


def hash_json(value: JsonValue) -> str:
    """Return the SHA-256 hex digest for a canonical JSON value."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def hash_event_payloads(event: Event) -> Event:
    """Return an event copy with payload hashes populated where applicable."""
    updates: dict[str, str | None] = {"input_hash": None, "output_hash": None}

    if isinstance(event, RunStart):
        if "input" in event.model_fields_set:
            updates["input_hash"] = hash_json(event.input)
    elif isinstance(event, LLMRequest | ToolCall):
        updates["input_hash"] = hash_json(event.input)
    elif isinstance(event, LLMResponse | ToolResult):
        updates["output_hash"] = hash_json(event.output)
    elif isinstance(event, StateChange):
        if "before" in event.model_fields_set:
            updates["input_hash"] = hash_json(event.before)
        if "after" in event.model_fields_set:
            updates["output_hash"] = hash_json(event.after)
    elif isinstance(event, ErrorEvent):
        if event.details is not None or "details" in event.model_fields_set:
            updates["output_hash"] = hash_json(event.details)
    elif isinstance(event, RunEnd) and (
        event.output is not None or "output" in event.model_fields_set
    ):
        updates["output_hash"] = hash_json(event.output)

    return event.model_copy(update=updates)


def verify_event_payload_hashes(event: Event) -> list[str]:
    """Return payload hash mismatch issue fields for an event."""
    expected = hash_event_payloads(event)
    mismatches: list[str] = []

    if event.input_hash is not None and event.input_hash != expected.input_hash:
        mismatches.append("input_hash")
    if event.output_hash is not None and event.output_hash != expected.output_hash:
        mismatches.append("output_hash")

    return mismatches


def event_payload_hash_fields(event: Event) -> set[str]:
    """Return hash fields that are expected for the event's payload shape."""
    expected = hash_event_payloads(event)
    fields: set[str] = set()
    if expected.input_hash is not None:
        fields.add("input_hash")
    if expected.output_hash is not None:
        fields.add("output_hash")
    return fields
