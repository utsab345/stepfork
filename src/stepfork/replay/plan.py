"""Extraction of replayable dependency calls from a recorded trace.

The recorded dependency sequence is the ordered list of ``tool_call`` and
``llm_request`` events. Each call is paired with its captured outcome:

- ``tool_call`` → the ``tool_result`` whose ``parent_id`` points at it.
- ``llm_request`` → the ``llm_response`` whose ``parent_id`` points at it, or
  the ``error`` event whose ``parent_id`` points at it when the call failed.

Pairing falls back to forward name matching when a legacy bundle does not use
parent links.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from stepfork.trace.models import (
    ErrorEvent,
    EventStatus,
    EventType,
    JsonValue,
    LLMRequest,
    LLMResponse,
    ToolCall,
    ToolResult,
    Trace,
)
from stepfork.trace.replay_policy import ReplayPolicy

ERROR_PAYLOAD_KEYS = ("error_type", "message")


@dataclass(frozen=True)
class RecordedCall:
    """One dependency call captured in a trace."""

    index: int
    kind: Literal["tool", "llm"]
    label: str
    name: str | None
    model: str | None
    provider: str | None
    input: JsonValue
    policy: ReplayPolicy
    status: EventStatus
    output: JsonValue | None
    error_type: str | None
    error_message: str | None
    missing: bool
    call_event_id: str


def extract_recorded_calls(trace: Trace) -> list[RecordedCall]:
    """Return the ordered dependency calls recorded in ``trace``."""
    children: dict[str, list[int]] = {}
    for index, event in enumerate(trace.events):
        if event.parent_id is not None:
            children.setdefault(event.parent_id, []).append(index)

    paired_results: set[str] = set()
    calls: list[RecordedCall] = []

    for index, event in enumerate(trace.events):
        if isinstance(event, ToolCall):
            result_index = _find_child_index(
                trace,
                children.get(event.id, []),
                wanted=EventType.TOOL_RESULT,
            )
            if result_index is None:
                result_index = _find_forward_result(
                    trace,
                    start=index + 1,
                    name=event.name,
                    paired_results=paired_results,
                )
            result = trace.events[result_index] if result_index is not None else None
            if isinstance(result, ToolResult):
                paired_results.add(result.id)
            calls.append(
                _build_tool_call(
                    index=len(calls),
                    call=event,
                    result=result if isinstance(result, ToolResult) else None,
                    trace=trace,
                    children=children,
                )
            )
        elif isinstance(event, LLMRequest):
            response_index = _find_child_index(
                trace,
                children.get(event.id, []),
                wanted=EventType.LLM_RESPONSE,
            )
            error_index = _find_child_index(
                trace,
                children.get(event.id, []),
                wanted=EventType.ERROR,
            )
            response = (
                trace.events[response_index] if response_index is not None else None
            )
            error = trace.events[error_index] if error_index is not None else None
            calls.append(
                _build_llm_call(
                    index=len(calls),
                    request=event,
                    response=response if isinstance(response, LLMResponse) else None,
                    error=error if isinstance(error, ErrorEvent) else None,
                )
            )

    return calls


def _find_child_index(
    trace: Trace,
    child_indexes: list[int],
    *,
    wanted: EventType,
) -> int | None:
    for child_index in child_indexes:
        if trace.events[child_index].type is wanted:
            return child_index
    return None


def _find_forward_result(
    trace: Trace,
    *,
    start: int,
    name: str,
    paired_results: set[str],
) -> int | None:
    for index in range(start, len(trace.events)):
        event = trace.events[index]
        if isinstance(event, ToolCall) and event.name == name:
            return None
        if (
            isinstance(event, ToolResult)
            and event.name == name
            and event.id not in paired_results
        ):
            return index
    return None


def _build_tool_call(
    *,
    index: int,
    call: ToolCall,
    result: ToolResult | None,
    trace: Trace,
    children: dict[str, list[int]],
) -> RecordedCall:
    error_type: str | None = None
    error_message: str | None = None

    if result is None:
        return RecordedCall(
            index=index,
            kind="tool",
            label=call.name,
            name=call.name,
            model=None,
            provider=None,
            input=call.input,
            policy=call.replay_policy,
            status=EventStatus.SKIPPED,
            output=None,
            error_type=None,
            error_message=None,
            missing=True,
            call_event_id=call.id,
        )

    if result.status is EventStatus.ERROR:
        error_index = _find_child_index(
            trace,
            children.get(result.id, []),
            wanted=EventType.ERROR,
        )
        if error_index is not None:
            error = trace.events[error_index]
            if isinstance(error, ErrorEvent):
                error_type = error.error_type
                error_message = error.message
        if error_type is None:
            error_type, error_message = _error_from_payload(result.output)

    return RecordedCall(
        index=index,
        kind="tool",
        label=call.name,
        name=call.name,
        model=None,
        provider=None,
        input=call.input,
        policy=call.replay_policy,
        status=result.status,
        output=result.output,
        error_type=error_type,
        error_message=error_message,
        missing=False,
        call_event_id=call.id,
    )


def _build_llm_call(
    *,
    index: int,
    request: LLMRequest,
    response: LLMResponse | None,
    error: ErrorEvent | None,
) -> RecordedCall:
    label = f"{request.provider}/{request.model}" if request.provider else request.model

    if response is not None:
        return RecordedCall(
            index=index,
            kind="llm",
            label=label,
            name=None,
            model=request.model,
            provider=request.provider,
            input=request.input,
            policy=request.replay_policy,
            status=response.status,
            output=response.output,
            error_type=None,
            error_message=None,
            missing=False,
            call_event_id=request.id,
        )

    if error is not None:
        return RecordedCall(
            index=index,
            kind="llm",
            label=label,
            name=None,
            model=request.model,
            provider=request.provider,
            input=request.input,
            policy=request.replay_policy,
            status=EventStatus.ERROR,
            output=None,
            error_type=error.error_type,
            error_message=error.message,
            missing=False,
            call_event_id=request.id,
        )

    return RecordedCall(
        index=index,
        kind="llm",
        label=label,
        name=None,
        model=request.model,
        provider=request.provider,
        input=request.input,
        policy=request.replay_policy,
        status=EventStatus.SKIPPED,
        output=None,
        error_type=None,
        error_message=None,
        missing=True,
        call_event_id=request.id,
    )


def _error_from_payload(output: JsonValue) -> tuple[str | None, str | None]:
    if not isinstance(output, dict):
        return None, None
    error_type = output.get("error_type")
    message = output.get("message")
    return (
        error_type if isinstance(error_type, str) else None,
        message if isinstance(message, str) else None,
    )
