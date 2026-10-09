from __future__ import annotations

from stepfork.replay.plan import extract_recorded_calls
from stepfork.trace import ErrorEvent, EventStatus, ToolCall, ToolResult, Trace


def test_legacy_forward_matching_pairs_results_without_parent_links() -> None:
    trace = Trace(agent_name="legacy")
    trace.add(ToolCall(name="step", input={"v": 1}))
    trace.add(ToolResult(name="step", output={"r": 1}))
    trace.add(ToolCall(name="step", input={"v": 2}))
    trace.add(ToolResult(name="step", output={"r": 2}))

    calls = extract_recorded_calls(trace)

    assert [call.status for call in calls] == [EventStatus.OK, EventStatus.OK]
    assert [call.output for call in calls] == [{"r": 1}, {"r": 2}]


def test_legacy_forward_matching_stops_at_next_call_of_same_name() -> None:
    trace = Trace(agent_name="legacy")
    trace.add(ToolCall(name="step", input={"v": 1}))
    trace.add(ToolCall(name="step", input={"v": 2}))
    trace.add(ToolResult(name="step", output={"r": 1}))
    trace.add(ToolResult(name="step", output={"r": 2}))

    calls = extract_recorded_calls(trace)

    assert calls[0].missing is True
    assert calls[1].missing is False
    assert calls[1].output == {"r": 1}


def test_tool_error_result_uses_child_error_event() -> None:
    trace = Trace(agent_name="plan-agent")
    call = trace.add(ToolCall(name="step", input={"value": "a"}))
    result = trace.add(
        ToolResult(
            name="step",
            output={},
            status=EventStatus.ERROR,
            parent_id=call.id,
        )
    )
    trace.add(ErrorEvent(error_type="ToolError", message="boom", parent_id=result.id))

    calls = extract_recorded_calls(trace)

    assert calls[0].status is EventStatus.ERROR
    assert calls[0].error_type == "ToolError"
    assert calls[0].error_message == "boom"


def test_tool_error_result_falls_back_to_payload() -> None:
    trace = Trace(agent_name="plan-agent")
    call = trace.add(ToolCall(name="step", input={"value": "a"}))
    trace.add(
        ToolResult(
            name="step",
            output={"error_type": "PayloadError", "message": "bad call"},
            status=EventStatus.ERROR,
            parent_id=call.id,
        )
    )

    calls = extract_recorded_calls(trace)

    assert calls[0].error_type == "PayloadError"
    assert calls[0].error_message == "bad call"


def test_tool_error_result_with_non_dict_payload() -> None:
    trace = Trace(agent_name="plan-agent")
    call = trace.add(ToolCall(name="step", input={"value": "a"}))
    trace.add(
        ToolResult(
            name="step",
            output=[1, 2],
            status=EventStatus.ERROR,
            parent_id=call.id,
        )
    )

    calls = extract_recorded_calls(trace)

    assert calls[0].error_type is None
    assert calls[0].error_message is None


def test_llm_error_call_is_recorded_as_error() -> None:
    from stepfork.trace.models import LLMRequest

    trace = Trace(agent_name="plan-agent")
    request = trace.add(LLMRequest(provider="fake", model="demo", input={"q": 1}))
    trace.add(
        ErrorEvent(error_type="ProviderError", message="down", parent_id=request.id)
    )

    calls = extract_recorded_calls(trace)

    assert calls[0].kind == "llm"
    assert calls[0].status is EventStatus.ERROR
    assert calls[0].error_type == "ProviderError"
    assert calls[0].missing is False


def test_llm_call_without_response_or_error_is_missing() -> None:
    from stepfork.trace.models import LLMRequest

    trace = Trace(agent_name="plan-agent")
    trace.add(LLMRequest(provider="fake", model="demo", input={"q": 1}))

    calls = extract_recorded_calls(trace)

    assert calls[0].kind == "llm"
    assert calls[0].status is EventStatus.SKIPPED
    assert calls[0].missing is True
