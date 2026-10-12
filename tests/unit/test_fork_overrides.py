"""Unit tests for override functionality."""

from __future__ import annotations

import pytest

from stepfork import ToolCall, Trace
from stepfork.fork import (
    ForkEngine,
    ForkError,
    ForkPoint,
    OverrideRegistry,
    OverrideSpec,
)
from stepfork.trace import RunStart, RunStatus, ToolResult


def build_test_trace() -> Trace:
    """Build a test trace with tool calls."""
    trace = Trace(agent_name="test-agent", status=RunStatus.COMPLETED)
    start = trace.add(RunStart(input={"query": "test"}))

    call1 = trace.add(ToolCall(name="search", input={"q": "test"}, parent_id=start.id))
    result1 = trace.add(
        ToolResult(name="search", output={"count": 5}, parent_id=call1.id)
    )

    call2 = trace.add(
        ToolCall(name="book", input={"id": "123"}, parent_id=result1.id)
    )
    trace.add(
        ToolResult(name="book", output={"status": "confirmed"}, parent_id=call2.id)
    )

    return trace


def test_override_spec_requires_target() -> None:
    """OverrideSpec requires either step or event_id."""
    with pytest.raises(ValueError, match="requires either step or event_id"):
        OverrideSpec(step=None, event_id=None, output={"new": "value"})


def test_override_spec_cannot_specify_both() -> None:
    """OverrideSpec cannot specify both step and event_id."""
    with pytest.raises(ValueError, match="cannot specify both"):
        OverrideSpec(step=1, event_id="evt_123", output={"new": "value"})


def test_override_registry_basic() -> None:
    """Override registry indexes overrides correctly."""
    overrides = [
        OverrideSpec(step=2, output={"new": "value1"}),
        OverrideSpec(event_id="evt_123", output={"new": "value2"}),
    ]

    registry = OverrideRegistry(overrides)
    assert len(registry.overrides) == 2
    assert 2 in registry._by_step
    assert "evt_123" in registry._by_event_id


def test_override_registry_rejects_duplicates() -> None:
    """Override registry rejects duplicate targets."""
    overrides = [
        OverrideSpec(step=2, output={"v1": 1}),
        OverrideSpec(step=2, output={"v2": 2}),
    ]

    with pytest.raises(ForkError, match="duplicate override for step 2"):
        OverrideRegistry(overrides)


def test_get_override_by_step() -> None:
    """Can retrieve override by step number."""
    trace = build_test_trace()
    overrides = [OverrideSpec(step=2, output={"count": 10})]
    registry = OverrideRegistry(overrides)

    event = trace.events[2]
    override = registry.get_override(event)
    assert override is not None
    assert override.output == {"count": 10}


def test_get_override_by_event_id() -> None:
    """Can retrieve override by event ID."""
    trace = build_test_trace()
    event_id = trace.events[2].id
    overrides = [OverrideSpec(event_id=event_id, output={"count": 10})]
    registry = OverrideRegistry(overrides)

    event = trace.events[2]
    override = registry.get_override(event)
    assert override is not None
    assert override.output == {"count": 10}


def test_get_override_prefers_event_id() -> None:
    """Override lookup prefers event ID over step."""
    trace = build_test_trace()
    event_id = trace.events[2].id
    overrides = [
        OverrideSpec(step=2, output={"from": "step"}),
        OverrideSpec(event_id=event_id, output={"from": "event_id"}),
    ]
    registry = OverrideRegistry(overrides)

    event = trace.events[2]
    override = registry.get_override(event)
    assert override.output == {"from": "event_id"}


def test_apply_override_to_tool_result() -> None:
    """Can apply override to tool result event."""
    trace = build_test_trace()
    event = trace.events[2]  # ToolResult
    override = OverrideSpec(step=2, output={"new_count": 100})

    registry = OverrideRegistry([override])
    overridden = registry.apply_override(event, override)

    assert overridden.output == {"new_count": 100}
    assert overridden.id == event.id
    assert overridden.step == event.step


def test_apply_override_rejects_non_result_events() -> None:
    """Cannot override non-result events."""
    trace = build_test_trace()
    event = trace.events[1]  # ToolCall
    override = OverrideSpec(step=1, output={"new": "value"})

    registry = OverrideRegistry([override])
    with pytest.raises(ForkError, match="only tool_result and llm_response"):
        registry.apply_override(event, override)


def test_validate_overrides_rejects_invalid_step() -> None:
    """Validation rejects overrides targeting non-existent steps."""
    trace = build_test_trace()
    overrides = [OverrideSpec(step=999, output={"x": 1})]
    registry = OverrideRegistry(overrides)

    with pytest.raises(ForkError, match="targets step 999"):
        registry.validate_overrides(trace.events, strict=True)


def test_validate_overrides_rejects_invalid_event_id() -> None:
    """Validation rejects overrides targeting non-existent events."""
    trace = build_test_trace()
    overrides = [OverrideSpec(event_id="evt_nonexistent", output={"x": 1})]
    registry = OverrideRegistry(overrides)

    with pytest.raises(ForkError, match="non-existent event"):
        registry.validate_overrides(trace.events, strict=True)


def test_validate_overrides_rejects_non_result_target() -> None:
    """Validation rejects overrides targeting non-result events."""
    trace = build_test_trace()
    # Step 1 is a ToolCall, not a result
    overrides = [OverrideSpec(step=1, output={"x": 1})]
    registry = OverrideRegistry(overrides)

    with pytest.raises(ForkError, match="only tool_result and llm_response"):
        registry.validate_overrides(trace.events, strict=True)


def test_fork_with_override() -> None:
    """Fork with override modifies the output."""
    trace = build_test_trace()
    fork_point = ForkPoint(event_id=None, step=4)
    overrides = [OverrideSpec(step=2, output={"count": 100})]

    engine = ForkEngine(trace, fork_point, overrides=overrides)
    forked_trace, fork_info = engine.fork()

    # Check override was applied
    assert fork_info.overrides_applied == 1
    overridden_event = forked_trace.events[2]
    assert overridden_event.output == {"count": 100}  # type: ignore


def test_fork_with_multiple_overrides() -> None:
    """Fork can apply multiple overrides."""
    trace = build_test_trace()
    fork_point = ForkPoint(event_id=None, step=4)
    overrides = [
        OverrideSpec(step=2, output={"count": 100}),
        OverrideSpec(step=4, output={"status": "modified"}),
    ]

    engine = ForkEngine(trace, fork_point, overrides=overrides)
    forked_trace, fork_info = engine.fork()

    assert fork_info.overrides_applied == 2
    assert forked_trace.events[2].output == {"count": 100}  # type: ignore
    assert forked_trace.events[4].output == {"status": "modified"}  # type: ignore


def test_fork_validates_overrides() -> None:
    """Fork validates overrides before applying."""
    trace = build_test_trace()
    fork_point = ForkPoint(event_id=None, step=4)
    overrides = [OverrideSpec(step=999, output={"x": 1})]

    engine = ForkEngine(trace, fork_point, overrides=overrides)
    with pytest.raises(ForkError, match="targets step 999"):
        engine.fork()
