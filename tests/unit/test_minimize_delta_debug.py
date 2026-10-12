"""Unit tests for delta debugging engine."""

from __future__ import annotations

from stepfork import ToolCall, Trace
from stepfork.minimize.delta_debug import (
    DeltaDebugger,
    EventSubset,
    create_minimized_trace,
)
from stepfork.trace import RunEnd, RunStart, RunStatus, ToolResult


def build_test_trace() -> Trace:
    """Build a test trace with multiple tool calls."""
    trace = Trace(agent_name="test-agent", status=RunStatus.COMPLETED)
    start = trace.add(RunStart(input={"query": "test"}))

    # Add three tool calls
    call1 = trace.add(
        ToolCall(name="search", input={"q": "flights"}, parent_id=start.id)
    )
    result1 = trace.add(
        ToolResult(name="search", output={"count": 5}, parent_id=call1.id)
    )

    call2 = trace.add(
        ToolCall(name="book", input={"id": "FL123"}, parent_id=result1.id)
    )
    result2 = trace.add(
        ToolResult(name="book", output={"status": "confirmed"}, parent_id=call2.id)
    )

    call3 = trace.add(
        ToolCall(
            name="notify", input={"email": "test@example.com"}, parent_id=result2.id
        )
    )
    result3 = trace.add(
        ToolResult(name="notify", output={"sent": True}, parent_id=call3.id)
    )

    trace.add(RunEnd(run_status=RunStatus.COMPLETED, parent_id=result3.id))
    return trace


def test_build_subset_preserves_dependencies() -> None:
    """_build_subset must preserve parent-child dependencies."""
    trace = build_test_trace()
    debugger = DeltaDebugger(
        trace,
        predicate=lambda _: False,  # Predicate not used in this test
    )

    # Try to build a subset with just one middle event
    # The builder should automatically include all its ancestors
    middle_event_idx = 3  # A tool result with parents
    subset = debugger._build_subset({middle_event_idx})

    # Verify all parent events were included
    event_ids = {event.id for event in subset.events}
    for event in subset.events:
        if event.parent_id is not None:
            assert event.parent_id in event_ids


def test_build_subset_preserves_run_markers() -> None:
    """_build_subset preserves run_start and run_end by default."""
    trace = build_test_trace()
    debugger = DeltaDebugger(
        trace,
        predicate=lambda _: False,
        preserve_run_markers=True,
    )

    # Build a subset with just one middle event
    subset = debugger._build_subset({3})

    # Should have run_start and run_end
    event_types = [event.type for event in subset.events]
    assert "run_start" in event_types
    assert "run_end" in event_types


def test_create_minimized_trace() -> None:
    """Creating a minimized trace preserves agent metadata."""
    trace = build_test_trace()

    # Create a subset with just the first two events
    subset = EventSubset(
        events=tuple(trace.events[:2]),
        includes_dependency_calls=False,
    )

    minimized = create_minimized_trace(trace, subset)

    assert minimized.agent_name == trace.agent_name
    assert minimized.run_id == trace.run_id
    assert len(minimized.events) == 2


def test_delta_debugger_identifies_minimizable_events() -> None:
    """Delta debugger correctly identifies which events can be removed."""
    trace = build_test_trace()
    debugger = DeltaDebugger(
        trace,
        predicate=lambda _: False,
    )

    # Tool calls and results should be minimizable
    assert any(
        idx in debugger.minimizable
        for idx, event in enumerate(trace.events)
        if event.type == "tool_call"
    )

    # Run markers should not be minimizable when preserve_run_markers=True
    run_marker_indices = [
        idx
        for idx, event in enumerate(trace.events)
        if event.type in ("run_start", "run_end")
    ]
    if debugger.preserve_run_markers:
        for idx in run_marker_indices:
            assert idx not in debugger.minimizable


def test_delta_debugger_handles_empty_trace() -> None:
    """Delta debugger handles trace with no minimizable events."""
    trace = Trace(agent_name="empty-agent", status=RunStatus.COMPLETED)
    trace.add(RunStart())
    trace.add(RunEnd(run_status=RunStatus.COMPLETED))

    debugger = DeltaDebugger(
        trace,
        predicate=lambda _: True,
    )
    result = debugger.minimize()

    # Should return at least run markers
    assert len(result.events) >= 2


def test_event_subset_tracks_dependency_calls() -> None:
    """EventSubset correctly tracks if it includes dependency calls."""
    trace = build_test_trace()

    # Subset with only run markers
    subset_no_deps = EventSubset(
        events=(trace.events[0], trace.events[-1]),
        includes_dependency_calls=False,
    )
    assert not subset_no_deps.includes_dependency_calls

    # Subset with tool calls
    subset_with_deps = EventSubset(
        events=tuple(trace.events),
        includes_dependency_calls=True,
    )
    assert subset_with_deps.includes_dependency_calls


def test_minimize_with_specific_failure_requirement() -> None:
    """Minimize finds subset that meets specific requirement."""
    trace = build_test_trace()

    # Predicate: succeeds if we have exactly the first tool call
    first_tool_call_idx = 1

    def predicate(subset: EventSubset) -> bool:
        tool_calls = [
            i
            for i, e in enumerate(trace.events)
            if e.type == "tool_call" and e.id in {ev.id for ev in subset.events}
        ]
        return first_tool_call_idx in tool_calls

    debugger = DeltaDebugger(trace, predicate=predicate)
    result = debugger.minimize()

    # Should include the first tool call
    tool_call_ids = {e.id for e in result.events if e.type == "tool_call"}
    assert trace.events[first_tool_call_idx].id in tool_call_ids


def test_get_all_ancestors() -> None:
    """_get_all_ancestors correctly finds all ancestor events."""
    trace = build_test_trace()
    debugger = DeltaDebugger(trace, predicate=lambda _: False)

    # Last event should have multiple ancestors
    last_event_idx = len(trace.events) - 1
    ancestors = debugger._get_all_ancestors(last_event_idx)

    # Should have at least a few ancestors
    assert len(ancestors) > 0

    # All ancestors should come before the target event
    assert all(idx < last_event_idx for idx in ancestors)
