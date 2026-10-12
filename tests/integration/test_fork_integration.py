"""Integration tests for fork functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import Trace, record, trace_tool
from stepfork.fork import ForkPoint, fork_trace


@trace_tool(name="search")
def search(query: str) -> dict[str, list[str]]:
    """Search tool."""
    return {"results": ["result1", "result2"]}


@trace_tool(name="book")
def book(item_id: str) -> dict[str, str]:
    """Booking tool."""
    return {"status": "booked", "id": item_id}


def run_agent() -> dict[str, str]:
    """Agent that uses multiple tools."""
    results = search("flights")
    booking = book("FL123")
    return {"search_count": len(results["results"]), "booking": booking["status"]}


@pytest.mark.integration
def test_fork_recorded_trace(tmp_path: Path) -> None:
    """Fork a real recorded trace."""
    # Record a trace
    trace_path = tmp_path / "original.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        agent_result = run_agent()
        session.set_output(agent_result)

    # Load and inspect trace
    original_trace = Trace.load(trace_path)
    original_event_count = len(original_trace.events)

    # Fork at step 2 (after first tool call)
    forked_path = tmp_path / "forked.sftrace"
    fork_point = ForkPoint(event_id=None, step=2)

    result = fork_trace(
        trace_path,
        fork_point,
        output_path=forked_path,
    )

    # Verify fork succeeded
    assert result.success
    assert result.forked_event_count < original_event_count

    # Load and verify forked trace
    forked_trace = Trace.load(forked_path)
    assert forked_trace.agent_name == original_trace.agent_name
    assert len(forked_trace.events) == result.forked_event_count

    # Verify all events have the same agent name
    assert all(
        event.run_id == forked_trace.run_id
        for event in forked_trace.events
    )


@pytest.mark.integration
def test_fork_preserves_trace_validity(tmp_path: Path) -> None:
    """Forked trace passes validation."""
    # Record a trace
    trace_path = tmp_path / "original.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        agent_result = run_agent()
        session.set_output(agent_result)

    # Fork it
    forked_path = tmp_path / "forked.sftrace"
    fork_point = ForkPoint(event_id=None, step=1)

    fork_trace(
        trace_path,
        fork_point,
        output_path=forked_path,
    )

    # Validate forked trace
    from stepfork.trace.validation import validate_bundle

    result = validate_bundle(forked_path, strict=False)
    assert result.valid


@pytest.mark.integration
def test_fork_at_different_steps(tmp_path: Path) -> None:
    """Can fork at multiple different steps."""
    # Record a trace
    trace_path = tmp_path / "original.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        agent_result = run_agent()
        session.set_output(agent_result)

    # Fork at different steps
    for step in [0, 1, 2]:
        forked_path = tmp_path / f"forked-step{step}.sftrace"
        fork_point = ForkPoint(event_id=None, step=step)

        result = fork_trace(
            trace_path,
            fork_point,
            output_path=forked_path,
        )

        assert result.success
        assert result.fork_point_step == step

        forked_trace = Trace.load(forked_path)
        assert len(forked_trace.events) == step + 1


@pytest.mark.integration
def test_fork_by_event_id(tmp_path: Path) -> None:
    """Can fork by event ID."""
    # Record a trace
    trace_path = tmp_path / "original.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        agent_result = run_agent()
        session.set_output(agent_result)

    # Get an event ID
    original_trace = Trace.load(trace_path)
    target_event = original_trace.events[1]

    # Fork at that event ID
    forked_path = tmp_path / "forked.sftrace"
    fork_point = ForkPoint(event_id=target_event.id, step=None)

    result = fork_trace(
        trace_path,
        fork_point,
        output_path=forked_path,
    )

    assert result.success
    assert result.fork_point_event_id == target_event.id
    assert result.fork_point_step == target_event.step


@pytest.mark.integration
def test_fork_error_handling(tmp_path: Path) -> None:
    """Fork handles errors gracefully."""
    # Record a trace
    trace_path = tmp_path / "original.sftrace"
    with record("test-agent", output=str(trace_path)) as session:
        agent_result = run_agent()
        session.set_output(agent_result)

    # Try to fork at invalid step
    fork_point = ForkPoint(event_id=None, step=999)

    result = fork_trace(
        trace_path,
        fork_point,
        output_path=tmp_path / "forked.sftrace",
    )

    assert not result.success
    assert result.error_message is not None
    assert "not found" in result.error_message.lower()
