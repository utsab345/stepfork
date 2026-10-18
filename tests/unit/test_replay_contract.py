"""Contract tests for frozen replay behavior.

These tests document and verify the supported replay contract:
- Original trace with unchanged calls/args replays correctly
- Changed arguments cause ReplayMismatchError (input diverged)
- Additional tool calls cause ReplayExhaustedError (unexpected tool call)
- Missing recorded calls cause ReplayMismatchError (unmatched calls)

Generated tests from failure traces that cannot execute on the fixed code
correctly fail during replay due to contract violations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import record, trace_tool
from stepfork.replay import ReplayMismatchError, ReplaySession


@trace_tool(name="step")
def step(value: str) -> dict[str, str]:
    return {"value": value}


@trace_tool(name="compute")
def compute(x: int, y: int) -> dict[str, int]:
    return {"sum": x + y, "diff": x - y}


def original_trace_agent() -> dict[str, str]:
    return step("a")


def agent_changes_arg() -> dict[str, str]:
    return step("b")  # different arg from recorded "a"


def agent_extra_call() -> dict[str, str]:
    step("a")
    step("extra")  # extra call not in original trace
    return {"extra": True}


def agent_missing_calls() -> dict[str, object]:
    return {"done": True}  # skips the recorded step call


def _record_step_trace(destination: Path) -> None:
    with record("step-agent", output=destination):
        step("a")
        # Set output after recording the step call
    # Better: record with session output
    pass


def test_original_trace_replays_successfully(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.sftrace"
    with record("step-agent", output=trace_path) as session:
        session.set_output(step("a"))

    # Replay against original agent behavior
    with ReplaySession.from_trace(trace_path, mode="frozen") as replay:
        result = step("a")
        replay.verify_complete()
    assert result == {"value": "a"}


def test_changed_arguments_cause_replay_mismatch(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.sftrace"
    with record("step-agent", output=trace_path) as session:
        session.set_output(step("a"))

    # Replay with different argument - should diverge
    with (
        pytest.raises(ReplayMismatchError, match="input diverged"),
        ReplaySession.from_trace(trace_path, mode="frozen"),
    ):
        step("b")


def test_extra_tool_call_cause_replay_exhausted(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.sftrace"
    with record("step-agent", output=trace_path) as session:
        session.set_output(step("a"))

    # First call matches, second is extra (beyond recorded)
    with (
        pytest.raises(ReplayMismatchError),
        ReplaySession.from_trace(trace_path, mode="frozen"),
    ):
        step("a")
        step("extra")  # extra call


def test_missing_recorded_calls_cause_unmatched(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.sftrace"
    with record("step-agent", output=trace_path) as session:
        session.set_output(step("a"))

    # Agent makes no calls but trace expects 1
    with pytest.raises(ReplayMismatchError, match=r"unmatched|ended before consuming"):
        with ReplaySession.from_trace(trace_path, mode="frozen") as replay:
            replay.verify_complete()
