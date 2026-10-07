from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from stepfork import ToolCall, Trace
from stepfork.trace import (
    ErrorEvent,
    Event,
    EventBase,
    EventStatus,
    EventType,
    LLMRequest,
    LLMResponse,
    ReplayPolicy,
    RunEnd,
    RunStatus,
)


def aware_now() -> datetime:
    return datetime(2026, 10, 7, 14, 30, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "policy",
    [
        "frozen",
        "live",
        "manual",
        "forbidden",
        "derived",
    ],
)
def test_replay_policy_accepts_known_values(policy: str) -> None:
    assert ReplayPolicy(policy).value == policy


def test_replay_policy_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        ReplayPolicy("surprise")


def test_event_type_contains_exact_v01_values() -> None:
    assert {event_type.value for event_type in EventType} == {
        "run_start",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "state_change",
        "error",
        "run_end",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": ""},
        {"run_id": ""},
        {"step": -1},
        {"timestamp": datetime(2026, 10, 7, 14, 30, 1)},
        {"duration_ms": -1},
        {"parent_id": ""},
    ],
)
def test_event_base_rejects_invalid_common_fields(kwargs: dict[str, Any]) -> None:
    base_kwargs: dict[str, Any] = {
        "id": "evt_001",
        "run_id": "run_123",
        "step": 0,
        "type": EventType.TOOL_CALL,
        "timestamp": aware_now(),
    }
    base_kwargs.update(kwargs)

    with pytest.raises(ValidationError):
        EventBase(**base_kwargs)


def test_event_base_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ToolCall.model_validate(
            {"name": "search", "input": {"query": "Kathmandu flights"}, "extra": True}
        )


def test_tool_call_intended_api_generates_runtime_defaults() -> None:
    event = ToolCall(name="search", input={"query": "Kathmandu flights"})

    assert event.type is EventType.TOOL_CALL
    assert event.name == "search"
    assert event.input == {"query": "Kathmandu flights"}
    assert event.id.startswith("evt_")
    assert event.run_id.startswith("run_")
    assert event.step == 0
    assert event.timestamp.tzinfo is not None
    assert event.timestamp.utcoffset() is not None


def test_tool_call_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ToolCall(name="", input={"query": "Kathmandu flights"})


def test_error_event_defaults_to_error_status() -> None:
    event = ErrorEvent(error_type="RuntimeError", message="boom")

    assert event.status is EventStatus.ERROR


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prompt_tokens": -1},
        {"completion_tokens": -1},
        {"total_tokens": -1},
        {"cost_usd": -0.01},
    ],
)
def test_llm_response_rejects_negative_token_and_cost_values(
    kwargs: dict[str, int | float],
) -> None:
    with pytest.raises(ValidationError):
        LLMResponse.model_validate({"output": {"text": "hello"}, **kwargs})


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "hello",
        1,
        1.5,
        True,
        ["hello", 1, False],
        [["nested"], [1, 2]],
        {"query": "Kathmandu flights"},
        {"nested": {"list": [1, None, {"ok": True}]}},
    ],
)
def test_json_payload_accepts_json_values(payload: Any) -> None:
    event = ToolCall(name="search", input=payload)

    assert event.input == payload


@pytest.mark.parametrize("payload", [object(), {"bad": object()}])
def test_json_payload_rejects_arbitrary_python_objects(payload: object) -> None:
    with pytest.raises(ValidationError):
        ToolCall.model_validate({"name": "search", "input": payload})


def test_discriminated_union_parses_tool_call() -> None:
    adapter: TypeAdapter[Event] = TypeAdapter(Event)

    event = adapter.validate_python(
        {
            "id": "evt_004",
            "run_id": "run_7f2a",
            "parent_id": "evt_003",
            "step": 4,
            "type": "tool_call",
            "name": "search",
            "input": {"query": "Kathmandu flights"},
            "timestamp": "2026-10-07T14:30:01Z",
            "status": "ok",
            "replay_policy": "frozen",
        }
    )

    assert isinstance(event, ToolCall)
    assert event.name == "search"


@pytest.mark.parametrize(
    ("event_type", "expected_type", "extra"),
    [
        ("llm_request", LLMRequest, {"model": "gpt-test", "input": {"messages": []}}),
        ("llm_response", LLMResponse, {"output": {"text": "hello"}}),
        ("error", ErrorEvent, {"error_type": "RuntimeError", "message": "boom"}),
    ],
)
def test_discriminated_union_parses_event_variants(
    event_type: str,
    expected_type: type[object],
    extra: dict[str, Any],
) -> None:
    adapter: TypeAdapter[Event] = TypeAdapter(Event)
    payload = {
        "id": "evt_001",
        "run_id": "run_123",
        "step": 0,
        "type": event_type,
        "timestamp": "2026-10-07T14:30:01Z",
        **extra,
    }

    assert isinstance(adapter.validate_python(payload), expected_type)


def test_discriminated_union_rejects_unknown_event_type() -> None:
    adapter: TypeAdapter[Event] = TypeAdapter(Event)

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "id": "evt_001",
                "run_id": "run_123",
                "step": 0,
                "type": "framework_magic",
                "timestamp": "2026-10-07T14:30:01Z",
            }
        )


def test_trace_add_normalizes_run_id_and_step() -> None:
    trace = Trace(agent_name="demo-agent")

    event = trace.add(ToolCall(name="search", input={"query": "Kathmandu flights"}))

    assert trace.agent_name == "demo-agent"
    assert event.run_id == trace.run_id
    assert event.step == 0
    assert len(trace.events) == 1
    assert trace.events[0] == event

    second = trace.add(ToolCall(name="fetch", input={"url": "https://example.com"}))

    assert second.run_id == trace.run_id
    assert second.step == 1


def test_trace_add_preserves_parent_id() -> None:
    trace = Trace(agent_name="demo-agent")

    event = trace.add(
        ToolCall(
            name="search",
            input={"query": "Kathmandu flights"},
            parent_id="evt_parent",
        )
    )

    assert event.parent_id == "evt_parent"


def test_trace_add_normalizes_temporary_run_id() -> None:
    trace = Trace(agent_name="demo-agent")
    event = ToolCall(
        name="search",
        input={"query": "Kathmandu flights"},
        run_id="run_temporary",
    )

    normalized = trace.add(event)

    assert normalized.run_id == trace.run_id
    assert event.run_id == "run_temporary"


def test_trace_rejects_empty_agent_name() -> None:
    with pytest.raises(ValidationError):
        Trace(agent_name="")


def test_trace_rejects_naive_created_at() -> None:
    with pytest.raises(ValidationError):
        Trace(agent_name="demo-agent", created_at=datetime(2026, 10, 7, 14, 30))


def test_trace_created_at_is_timezone_aware() -> None:
    trace = Trace(agent_name="demo-agent")

    assert trace.created_at.tzinfo is not None
    assert trace.created_at.utcoffset() is not None


def test_public_api() -> None:
    trace = Trace(agent_name="demo-agent")

    event = trace.add(
        ToolCall(
            name="search",
            input={"query": "Kathmandu flights"},
        )
    )

    assert event.name == "search"
    assert event.step == 0
    assert event.run_id == trace.run_id


def test_run_end_accepts_run_status() -> None:
    adapter: TypeAdapter[Event] = TypeAdapter(Event)
    event = adapter.validate_python(
        {
            "id": "evt_002",
            "run_id": "run_123",
            "step": 1,
            "type": "run_end",
            "timestamp": "2026-10-07T14:30:01Z",
            "run_status": "completed",
        }
    )

    assert isinstance(event, RunEnd)
    assert event.run_status is RunStatus.COMPLETED
