from __future__ import annotations

from stepfork import FailureInfo, ToolCall, Trace
from stepfork.trace import ErrorEvent, RunEnd, RunStart, RunStatus, ToolResult
from stepfork.trace.validation import validate_trace


def complete_trace(*, status: RunStatus = RunStatus.COMPLETED) -> Trace:
    trace = Trace(agent_name="demo-agent", status=status)
    start = trace.add(RunStart(input={"prompt": "book"}))
    call = trace.add(
        ToolCall(
            name="search",
            input={"query": "Kathmandu flights"},
            parent_id=start.id,
        )
    )
    result = trace.add(
        ToolResult(name="search", output={"flights": []}, parent_id=call.id)
    )
    trace.add(RunEnd(run_status=status, parent_id=result.id))
    return trace


def issue_codes(trace: Trace, *, strict: bool = True) -> set[str]:
    return {issue.code for issue in validate_trace(trace, strict=strict).issues}


def test_valid_complete_trace_passes() -> None:
    assert validate_trace(complete_trace()).valid


def test_valid_partial_trace_passes_in_partial_mode() -> None:
    trace = Trace(agent_name="demo-agent")
    trace.add(ToolCall(name="search", input={"query": "Kathmandu flights"}))

    assert validate_trace(trace, strict=False).valid


def test_partial_trace_fails_strict_mode() -> None:
    trace = Trace(agent_name="demo-agent")
    trace.add(ToolCall(name="search", input={"query": "Kathmandu flights"}))

    assert issue_codes(trace) == {"run_start_count"}


def test_duplicate_id_rejected() -> None:
    trace = complete_trace()
    duplicate = trace.events[1].model_copy(update={"id": trace.events[0].id})
    trace.events[1] = duplicate

    assert "duplicate_event_id" in issue_codes(trace)


def test_invalid_parent_rejected() -> None:
    trace = complete_trace()
    trace.events[1] = trace.events[1].model_copy(update={"parent_id": "evt_missing"})

    assert "invalid_parent" in issue_codes(trace)


def test_future_parent_rejected() -> None:
    trace = complete_trace()
    trace.events[1] = trace.events[1].model_copy(
        update={"parent_id": trace.events[2].id}
    )

    assert "parent_not_earlier" in issue_codes(trace)


def test_self_parent_rejected() -> None:
    trace = complete_trace()
    trace.events[1] = trace.events[1].model_copy(
        update={"parent_id": trace.events[1].id}
    )

    assert "parent_not_earlier" in issue_codes(trace)


def test_wrong_run_id_rejected() -> None:
    trace = complete_trace()
    trace.events[1] = trace.events[1].model_copy(update={"run_id": "run_other"})

    assert "run_id_mismatch" in issue_codes(trace)


def test_decreasing_step_rejected() -> None:
    trace = complete_trace()
    trace.events[2] = trace.events[2].model_copy(update={"step": 0})

    assert "step_order" in issue_codes(trace)


def test_noncontiguous_non_decreasing_steps_accepted() -> None:
    trace = complete_trace()
    trace.events[2] = trace.events[2].model_copy(update={"step": 10})
    trace.events[3] = trace.events[3].model_copy(update={"step": 11})

    assert validate_trace(trace).valid


def test_incorrect_manifest_count_rejected() -> None:
    trace = complete_trace()
    trace.totals = trace.totals.model_copy(update={"events": 999})

    assert "event_count_mismatch" in issue_codes(trace)


def test_multiple_run_start_events_rejected() -> None:
    trace = complete_trace()
    trace.events.append(
        RunStart(
            id="evt_extra",
            run_id=trace.run_id,
            step=4,
            parent_id=trace.events[0].id,
        )
    )
    trace.totals = trace.totals.model_copy(update={"events": len(trace.events)})

    assert "run_start_count" in issue_codes(trace)


def test_missing_run_start_rejected_in_strict_mode() -> None:
    trace = Trace(agent_name="demo-agent")

    assert "run_start_count" in issue_codes(trace)


def test_failed_trace_without_error_rejected_in_strict_mode() -> None:
    trace = complete_trace(status=RunStatus.FAILED)
    trace.failure = FailureInfo(type="ToolError", message="boom", step=2)

    assert "missing_error_event" in issue_codes(trace)


def test_failed_trace_with_error_accepted() -> None:
    trace = Trace(
        agent_name="demo-agent",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolError", message="boom", step=1),
    )
    start = trace.add(RunStart(input={"prompt": "book"}))
    error = trace.add(
        ErrorEvent(error_type="ToolError", message="boom", parent_id=start.id)
    )
    trace.add(RunEnd(run_status=RunStatus.FAILED, parent_id=error.id))

    assert validate_trace(trace).valid


def test_multiple_independent_issues_returned_together() -> None:
    trace = Trace(agent_name="demo-agent")
    trace.events = [
        ToolCall(
            id="evt_same",
            run_id="run_other",
            step=2,
            name="search",
            input={},
        ),
        ToolCall(
            id="evt_same",
            run_id=trace.run_id,
            step=1,
            parent_id="evt_missing",
            name="fetch",
            input={},
        ),
    ]
    trace.totals = trace.totals.model_copy(update={"events": len(trace.events)})

    assert {
        "duplicate_event_id",
        "run_id_mismatch",
        "step_order",
        "invalid_parent",
        "run_start_count",
    }.issubset(issue_codes(trace))


def test_payload_hash_mismatch_rejected_when_requested() -> None:
    trace = complete_trace()
    trace.events[1] = trace.events[1].model_copy(update={"input_hash": "0" * 64})

    result = validate_trace(trace, verify_payload_hashes=True)

    assert "payload_hash_mismatch" in {issue.code for issue in result.issues}


def test_missing_payload_hash_unverified_when_requested() -> None:
    trace = complete_trace()

    result = validate_trace(trace, verify_payload_hashes=True)

    assert "integrity_unverified" in {issue.code for issue in result.issues}
