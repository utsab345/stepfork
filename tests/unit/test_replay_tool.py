"""Replay engine tests, including proof that frozen replay never executes tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import ReplaySession, record, trace_tool
from stepfork.replay import (
    RecordedDependencyError,
    ReplayError,
    ReplayExhaustedError,
    ReplayMismatchError,
    ReplayPolicyError,
)
from stepfork.trace import (
    ReplayPolicy,
    RunEnd,
    RunStart,
    RunStatus,
    ToolCall,
    Trace,
)

EXTERNAL_CALLS: list[str] = []


@trace_tool(name="dangerous_external")
def dangerous_external_tool() -> dict[str, bool]:
    EXTERNAL_CALLS.append("executed")
    raise AssertionError("External tool must not execute during frozen replay")


@trace_tool(name="safe_tool")
def safe_tool(value: str) -> dict[str, str]:
    EXTERNAL_CALLS.append(value)
    return {"value": value}


@trace_tool(name="failing_tool")
def failing_tool() -> dict[str, bool]:
    raise ValueError("dependency exploded")


@trace_tool(name="forbidden_tool", replay_policy=ReplayPolicy.FORBIDDEN)
def forbidden_tool() -> dict[str, bool]:
    return {"ok": True}


@trace_tool(name="manual_tool", replay_policy=ReplayPolicy.MANUAL)
def manual_tool() -> dict[str, bool]:
    return {"ok": True}


def _record(destination: Path, action: object) -> None:
    with record("demo-agent", output=destination):
        action()  # type: ignore[operator]


def test_frozen_replay_returns_captured_result_without_execution(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "run.sftrace"
    EXTERNAL_CALLS.clear()
    with pytest.raises(AssertionError):
        _record(destination, dangerous_external_tool)
    assert EXTERNAL_CALLS == ["executed"]
    assert len(EXTERNAL_CALLS) == 1

    EXTERNAL_CALLS.clear()
    with ReplaySession.from_trace(destination, mode="frozen") as replay:
        with pytest.raises(RecordedDependencyError):
            dangerous_external_tool()
        replay.verify_complete()

    # The tool body never ran during replay: the counter stayed empty and no
    # AssertionError from the body was raised.
    assert EXTERNAL_CALLS == []


def test_frozen_replay_substitutes_successful_tool(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    EXTERNAL_CALLS.clear()
    _record(destination, lambda: safe_tool("a"))

    EXTERNAL_CALLS.clear()
    with ReplaySession.from_trace(destination, mode="frozen") as replay:
        assert safe_tool("a") == {"value": "a"}
        replay.verify_complete()

    assert EXTERNAL_CALLS == []


def test_replay_input_mismatch_is_detected(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, lambda: safe_tool("a"))

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="input diverged"),
    ):
        safe_tool("b")


def test_replay_wrong_tool_name_is_detected(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, lambda: safe_tool("a"))

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="expected tool"),
    ):
        failing_tool()


def test_replay_exhausted_trace(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, lambda: safe_tool("a"))

    with ReplaySession.from_trace(destination, mode="frozen"):
        safe_tool("a")
        with pytest.raises(ReplayExhaustedError, match="already consumed"):
            safe_tool("a")


def test_repeated_calls_are_matched_in_order(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"

    def action() -> None:
        safe_tool("first")
        safe_tool("second")

    _record(destination, action)

    EXTERNAL_CALLS.clear()
    with ReplaySession.from_trace(destination, mode="frozen") as replay:
        assert safe_tool("first") == {"value": "first"}
        assert safe_tool("second") == {"value": "second"}
        replay.verify_complete()

    assert EXTERNAL_CALLS == []


def test_multiple_tools_in_order(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"

    def action() -> None:
        safe_tool("a")
        failing_tool()

    with pytest.raises(ValueError, match="dependency exploded"):
        _record(destination, action)

    with ReplaySession.from_trace(destination, mode="frozen") as replay:
        assert safe_tool("a") == {"value": "a"}
        with pytest.raises(RecordedDependencyError, match="dependency exploded"):
            failing_tool()
        assert replay.pending == 0


def test_recorded_tool_failure_is_reproduced(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    with pytest.raises(ValueError, match="dependency exploded"):
        _record(destination, failing_tool)

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(RecordedDependencyError) as excinfo,
    ):
        failing_tool()
    assert excinfo.value.error_type == "ValueError"
    assert excinfo.value.kind == "tool"


def test_missing_result_is_rejected() -> None:
    trace = Trace(agent_name="demo-agent")
    trace.add(RunStart())
    trace.add(ToolCall(name="safe_tool", input={"value": "a"}))
    trace.add(RunEnd(run_status=RunStatus.COMPLETED))

    with (
        ReplaySession.from_trace(trace, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="no captured result"),
    ):
        safe_tool("a")


def test_forbidden_recorded_policy_is_enforced(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, forbidden_tool)

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(ReplayPolicyError, match="forbids"),
    ):
        forbidden_tool()


def test_manual_recorded_policy_is_enforced(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, manual_tool)

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(ReplayPolicyError, match="manual"),
    ):
        manual_tool()


def test_forbidden_mode_rejects_every_call(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, lambda: safe_tool("a"))

    with (
        ReplaySession.from_trace(destination, mode="forbidden"),
        pytest.raises(ReplayPolicyError, match="forbidden"),
    ):
        safe_tool("a")


def test_manual_mode_requires_approval(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, lambda: safe_tool("a"))

    with (
        ReplaySession.from_trace(destination, mode="manual"),
        pytest.raises(ReplayPolicyError, match="approval"),
    ):
        safe_tool("a")


def test_derived_mode_unsupported(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, lambda: safe_tool("a"))

    with (
        ReplaySession.from_trace(destination, mode="derived"),
        pytest.raises(ReplayPolicyError, match="derived"),
    ):
        safe_tool("a")


def test_replay_requires_active_session(tmp_path: Path) -> None:
    # A tool called with no replay/recording context is a plain passthrough.
    EXTERNAL_CALLS.clear()
    assert safe_tool("plain") == {"value": "plain"}
    assert EXTERNAL_CALLS == ["plain"]


def test_dispatch_without_enter_raises(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, lambda: safe_tool("a"))

    replay = ReplaySession.from_trace(destination, mode="frozen")
    with pytest.raises(ReplayError, match="not active"):
        replay.before_tool(name="safe_tool", input={"value": "a"})


def test_replay_session_cannot_be_reentered(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"
    _record(destination, lambda: safe_tool("a"))

    with ReplaySession.from_trace(destination, mode="frozen"):
        pass

    session = ReplaySession.from_trace(destination, mode="frozen")
    with session, pytest.raises(ReplayError, match="re-entered"):
        session.__enter__()
