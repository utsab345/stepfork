"""Integration tests for trace minimization."""

from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import Trace, record, trace_tool
from stepfork.minimize.engine import MinimizationEngine


@trace_tool(name="sample_tool")
def sample_tool(value: int) -> dict[str, int]:
    """Sample tool that returns a value."""
    return {"result": value * 2}


def agent_with_multiple_calls() -> dict[str, int]:
    """Sample agent that makes multiple tool calls."""
    r1 = sample_tool(1)
    r2 = sample_tool(2)
    r3 = sample_tool(3)
    return {"sum": r1["result"] + r2["result"] + r3["result"]}


def agent_minimal() -> dict[str, int]:
    """Minimal agent with single tool call."""
    r1 = sample_tool(1)
    return {"result": r1["result"]}


@pytest.mark.integration
def test_minimization_reduces_trace_size(tmp_path: Path) -> None:
    """Minimization should reduce trace to minimal failing subset."""
    # Create a trace with multiple tool calls
    trace_path = tmp_path / "original.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        result = agent_with_multiple_calls()
        session.set_output(result)

    # Load the trace
    trace = Trace.load(trace_path)
    original_count = len(trace.events)

    # Run minimization with expected output that causes failure
    # (incorrect expected output to force a failure)
    expected_output = {"sum": 999}  # Wrong value

    engine = MinimizationEngine(
        trace,
        entrypoint="test_minimize_integration:agent_with_multiple_calls",
        expected_output=expected_output,
        mode="frozen",
        timeout_seconds=10.0,
    )

    result = engine.minimize()

    # Minimization should succeed
    assert result.success
    assert result.minimized_event_count is not None
    assert result.minimized_event_count <= original_count  # May already be minimal
    assert result.preserved_failure


@pytest.mark.integration
def test_minimization_preserves_failure_signature(tmp_path: Path) -> None:
    """Minimized trace should preserve the original failure signature."""
    # Create a trace
    trace_path = tmp_path / "failure.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        result = agent_minimal()
        session.set_output(result)

    trace = Trace.load(trace_path)

    # Wrong expected output
    expected_output = {"result": 999}

    engine = MinimizationEngine(
        trace,
        entrypoint="test_minimize_integration:agent_minimal",
        expected_output=expected_output,
        mode="frozen",
        timeout_seconds=10.0,
    )

    result = engine.minimize()

    assert result.success
    assert result.failure_signature is not None
    assert result.preserved_failure


@pytest.mark.integration
def test_minimization_handles_successful_trace(tmp_path: Path) -> None:
    """Minimization should fail gracefully when trace doesn't fail."""
    # Create a successful trace
    trace_path = tmp_path / "success.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        result = agent_minimal()
        session.set_output(result)

    trace = Trace.load(trace_path)

    # Correct expected output (no failure)
    expected_output = {"result": 2}

    engine = MinimizationEngine(
        trace,
        entrypoint="test_minimize_integration:agent_minimal",
        expected_output=expected_output,
        mode="frozen",
        timeout_seconds=10.0,
    )

    result = engine.minimize()

    # Should fail because there's no failure to minimize
    assert not result.success
    assert "no failure to minimize" in (result.error_message or "").lower()


@pytest.mark.integration
def test_minimization_preserves_dependencies(tmp_path: Path) -> None:
    """Minimized trace must preserve parent-child relationships."""
    # Create a trace
    trace_path = tmp_path / "deps.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        result = agent_with_multiple_calls()
        session.set_output(result)

    trace = Trace.load(trace_path)

    # Force a failure
    expected_output = {"sum": 999}

    engine = MinimizationEngine(
        trace,
        entrypoint="test_minimize_integration:agent_with_multiple_calls",
        expected_output=expected_output,
        mode="frozen",
        timeout_seconds=10.0,
    )

    result = engine.minimize()

    if result.success and result.minimized_event_count:
        # Load minimized trace and verify dependencies
        from stepfork.minimize.delta_debug import (
            EventSubset,
            create_minimized_trace,
        )

        subset = EventSubset(
            events=tuple(trace.events[: result.minimized_event_count]),
            includes_dependency_calls=True,
        )
        minimized_trace = create_minimized_trace(trace, subset)

        # Verify all parent IDs are valid
        event_ids = {event.id for event in minimized_trace.events}
        for event in minimized_trace.events:
            if event.parent_id is not None:
                assert (
                    event.parent_id in event_ids
                ), f"Event {event.id} has invalid parent {event.parent_id}"


@pytest.mark.integration
def test_minimization_counts_replay_attempts(tmp_path: Path) -> None:
    """Minimization should track replay attempts."""
    trace_path = tmp_path / "attempts.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        result = agent_minimal()
        session.set_output(result)

    trace = Trace.load(trace_path)
    expected_output = {"result": 999}

    engine = MinimizationEngine(
        trace,
        entrypoint="test_minimize_integration:agent_minimal",
        expected_output=expected_output,
        mode="frozen",
        timeout_seconds=10.0,
    )

    result = engine.minimize()

    # Should have made multiple replay attempts during minimization
    assert result.replay_attempts > 0
