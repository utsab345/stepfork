"""Edge case tests for fork operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import ToolCall, Trace
from stepfork.fork import ForkEngine, ForkError, ForkPoint, OverrideSpec, fork_trace
from stepfork.trace import RunEnd, RunStart, RunStatus, ToolResult


def test_fork_with_override_by_event_id(tmp_path: Path) -> None:
    """Can override using event ID instead of step."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    start = trace.add(RunStart())
    call = trace.add(ToolCall(name="test", input={}, parent_id=start.id))
    result = trace.add(ToolResult(name="test", output={"old": 1}, parent_id=call.id))
    trace.add(RunEnd(run_status=RunStatus.COMPLETED, parent_id=result.id))

    # Save trace
    trace_path = tmp_path / "test.sftrace"
    trace.save(trace_path)

    # Fork with override by event_id
    result_event_id = result.id
    fork_result = fork_trace(
        trace_path,
        ForkPoint(event_id=None, step=2),
        overrides=[OverrideSpec(event_id=result_event_id, output={"new": 2})],
        output_path=tmp_path / "forked.sftrace",
    )

    assert fork_result.success
    assert fork_result.overrides_applied == 1

    # Verify override was applied
    forked = Trace.load(tmp_path / "forked.sftrace")
    forked_result = forked.events[2]
    assert isinstance(forked_result, ToolResult)
    assert forked_result.output == {"new": 2}


def test_fork_at_step_zero(tmp_path: Path) -> None:
    """Can fork at step 0 (just the RunStart)."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    start = trace.add(RunStart())
    call = trace.add(ToolCall(name="test", input={}, parent_id=start.id))
    result = trace.add(ToolResult(name="test", output={}, parent_id=call.id))

    trace_path = tmp_path / "test.sftrace"
    trace.save(trace_path)

    # Fork at step 0
    fork_result = fork_trace(
        trace_path,
        ForkPoint(event_id=None, step=0),
        output_path=tmp_path / "forked.sftrace",
    )

    assert fork_result.success
    forked = Trace.load(tmp_path / "forked.sftrace")
    assert len(forked.events) == 1
    assert forked.events[0].type.value == "run_start"


def test_forked_trace_passes_validation(tmp_path: Path) -> None:
    """Forked traces pass strict validation."""
    from stepfork.trace.validation import validate_bundle

    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    start = trace.add(RunStart())
    call = trace.add(ToolCall(name="test", input={}, parent_id=start.id))
    result = trace.add(ToolResult(name="test", output={"x": 1}, parent_id=call.id))

    trace_path = tmp_path / "test.sftrace"
    trace.save(trace_path)

    # Fork with override
    forked_path = tmp_path / "forked.sftrace"
    fork_trace(
        trace_path,
        ForkPoint(event_id=None, step=2),
        overrides=[OverrideSpec(step=2, output={"x": 999})],
        output_path=forked_path,
    )

    # Validate in strict mode
    validation = validate_bundle(forked_path, strict=True)
    assert validation.valid, f"Validation failed: {validation.errors}"


def test_override_priority_event_id_over_step() -> None:
    """Event ID override takes priority over step override."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    start = trace.add(RunStart())
    call = trace.add(ToolCall(name="test", input={}, parent_id=start.id))
    result = trace.add(ToolResult(name="test", output={"orig": 1}, parent_id=call.id))

    # Both step and event_id target the same event
    event_id = result.id
    overrides = [
        OverrideSpec(step=2, output={"from": "step"}),
        OverrideSpec(event_id=event_id, output={"from": "event_id"}),
    ]

    engine = ForkEngine(trace, ForkPoint(event_id=None, step=2), overrides=overrides)
    forked, info = engine.fork()

    # Event ID should take priority
    forked_result = forked.events[2]
    assert isinstance(forked_result, ToolResult)
    assert forked_result.output == {"from": "event_id"}


def test_fork_preserves_created_at_timestamp() -> None:
    """Forked trace preserves original created_at timestamp."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    start = trace.add(RunStart())
    original_created_at = trace.created_at

    engine = ForkEngine(trace, ForkPoint(event_id=None, step=0))
    forked, _ = engine.fork()

    assert forked.created_at == original_created_at


def test_fork_with_no_events_excluded() -> None:
    """Can fork at the last event (includes all events)."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    start = trace.add(RunStart())
    call = trace.add(ToolCall(name="test", input={}, parent_id=start.id))

    engine = ForkEngine(trace, ForkPoint(event_id=None, step=1))
    forked, info = engine.fork()

    # Should include all events
    assert len(forked.events) == len(trace.events)
    assert info.fork_point_step == 1


def test_override_validation_rejects_future_steps() -> None:
    """Override validation rejects steps beyond trace length."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    trace.add(RunStart())

    engine = ForkEngine(
        trace,
        ForkPoint(event_id=None, step=0),
        overrides=[OverrideSpec(step=999, output={})],
    )

    with pytest.raises(ForkError, match="targets step 999"):
        engine.fork()


def test_override_validation_rejects_nonexistent_event_id() -> None:
    """Override validation rejects nonexistent event IDs."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    trace.add(RunStart())

    engine = ForkEngine(
        trace,
        ForkPoint(event_id=None, step=0),
        overrides=[OverrideSpec(event_id="evt_fake", output={})],
    )

    with pytest.raises(ForkError, match="non-existent event"):
        engine.fork()


def test_fork_result_counts_are_accurate(tmp_path: Path) -> None:
    """ForkResult event counts match actual trace."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    start = trace.add(RunStart())
    call = trace.add(ToolCall(name="test", input={}, parent_id=start.id))
    result = trace.add(ToolResult(name="test", output={}, parent_id=call.id))

    trace_path = tmp_path / "test.sftrace"
    trace.save(trace_path)

    fork_result = fork_trace(
        trace_path,
        ForkPoint(event_id=None, step=1),
        output_path=tmp_path / "forked.sftrace",
    )

    assert fork_result.original_event_count == 3
    assert fork_result.forked_event_count == 2
    assert fork_result.original_event_count - fork_result.forked_event_count == 1


def test_fork_with_empty_overrides_list() -> None:
    """Fork with empty overrides list works like no overrides."""
    trace = Trace(agent_name="test", status=RunStatus.COMPLETED)
    start = trace.add(RunStart())
    call = trace.add(ToolCall(name="test", input={}, parent_id=start.id))
    result = trace.add(ToolResult(name="test", output={"x": 1}, parent_id=call.id))

    engine1 = ForkEngine(trace, ForkPoint(event_id=None, step=2), overrides=[])
    engine2 = ForkEngine(trace, ForkPoint(event_id=None, step=2), overrides=None)

    forked1, info1 = engine1.fork()
    forked2, info2 = engine2.fork()

    assert info1.overrides_applied == 0
    assert info2.overrides_applied == 0
    assert len(forked1.events) == len(forked2.events)
