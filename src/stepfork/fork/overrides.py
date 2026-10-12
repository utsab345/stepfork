"""Override handling for fork and replay operations."""

from __future__ import annotations

from stepfork.fork.models import ForkError, OverrideSpec
from stepfork.trace.models import Event, EventType, JsonValue, LLMResponse, ToolResult


class OverrideRegistry:
    """Manages and applies overrides during fork/replay operations."""

    def __init__(self, overrides: list[OverrideSpec] | None = None):
        """Initialize the override registry.

        Args:
            overrides: List of override specifications
        """
        self.overrides = overrides or []
        self._by_step: dict[int, OverrideSpec] = {}
        self._by_event_id: dict[str, OverrideSpec] = {}

        # Index overrides for fast lookup
        for override in self.overrides:
            if override.step is not None:
                if override.step in self._by_step:
                    raise ForkError(f"duplicate override for step {override.step}")
                self._by_step[override.step] = override
            if override.event_id is not None:
                if override.event_id in self._by_event_id:
                    raise ForkError(f"duplicate override for event {override.event_id}")
                self._by_event_id[override.event_id] = override

    def get_override(self, event: Event) -> OverrideSpec | None:
        """Get override for an event, if one exists.

        Args:
            event: The event to check for overrides

        Returns:
            Override spec if found, None otherwise
        """
        # Check by event ID first (more specific)
        if event.id in self._by_event_id:
            return self._by_event_id[event.id]

        # Check by step number
        if event.step in self._by_step:
            return self._by_step[event.step]

        return None

    def apply_override(self, event: Event, override: OverrideSpec) -> Event:
        """Apply an override to an event.

        Args:
            event: The original event
            override: The override specification

        Returns:
            New event with overridden output

        Raises:
            ForkError: If override cannot be applied to this event type
        """
        if event.type == EventType.TOOL_RESULT:
            if not isinstance(event, ToolResult):
                raise ForkError(
                    f"event type is {event.type} but event is not ToolResult"
                )
            return ToolResult(
                id=event.id,
                run_id=event.run_id,
                step=event.step,
                timestamp=event.timestamp,
                name=event.name,
                output=override.output,
                parent_id=event.parent_id,
                status=event.status,
            )
        elif event.type == EventType.LLM_RESPONSE:
            if not isinstance(event, LLMResponse):
                raise ForkError(
                    f"event type is {event.type} but event is not LLMResponse"
                )
            return LLMResponse(
                id=event.id,
                run_id=event.run_id,
                step=event.step,
                timestamp=event.timestamp,
                model=event.model,
                output=override.output,
                parent_id=event.parent_id,
                status=event.status,
            )
        else:
            raise ForkError(
                f"cannot override event type {event.type}; "
                "only tool_result and llm_response are supported"
            )

    def validate_overrides(
        self, events: list[Event], *, strict: bool = True
    ) -> list[str]:
        """Validate that all overrides target valid events.

        Args:
            events: Events in the trace
            strict: If True, raise ForkError on invalid overrides

        Returns:
            List of validation error messages

        Raises:
            ForkError: If strict=True and validation fails
        """
        errors: list[str] = []
        event_ids = {e.id for e in events}
        max_step = max((e.step for e in events), default=-1)

        for override in self.overrides:
            # Check event ID overrides
            if override.event_id is not None:
                if override.event_id not in event_ids:
                    errors.append(
                        f"override targets non-existent event {override.event_id}"
                    )
                    continue

                event = next(e for e in events if e.id == override.event_id)
                if event.type not in (EventType.TOOL_RESULT, EventType.LLM_RESPONSE):
                    errors.append(
                        f"override targets {event.type} event {event.id}; "
                        "only tool_result and llm_response can be overridden"
                    )

            # Check step overrides
            if override.step is not None:
                if override.step > max_step:
                    errors.append(
                        f"override targets step {override.step} but trace only has "
                        f"{max_step + 1} steps (0-{max_step})"
                    )
                    continue

                event = next(e for e in events if e.step == override.step)
                if event.type not in (EventType.TOOL_RESULT, EventType.LLM_RESPONSE):
                    errors.append(
                        f"override targets step {override.step} ({event.type}); "
                        "only tool_result and llm_response can be overridden"
                    )

        if strict and errors:
            raise ForkError(f"invalid overrides: {'; '.join(errors)}")

        return errors


def get_override_for_call(
    overrides: OverrideRegistry, *, step: int, event_id: str
) -> JsonValue | None:
    """Get override output for a specific call during replay.

    Args:
        overrides: Override registry
        step: Step number of the call
        event_id: Event ID of the call

    Returns:
        Override output if found, None otherwise
    """
    # Create a minimal event object for lookup
    from datetime import UTC, datetime

    from stepfork.trace.models import ToolResult

    dummy_event = ToolResult(
        id=event_id,
        run_id="",
        step=step,
        timestamp=datetime(2000, 1, 1, tzinfo=UTC),
        name="dummy",
        output=None,
    )

    override = overrides.get_override(dummy_event)
    return override.output if override else None
