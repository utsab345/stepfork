"""Dependency-aware delta debugging for trace minimization.

Implements a variant of delta debugging that preserves event dependencies
(parent-child relationships) and structural integrity while searching for
minimal failing subsets.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from stepfork.trace.models import Event, EventType, Trace


@dataclass(frozen=True)
class EventSubset:
    """A subset of events with preserved dependencies."""

    events: tuple[Event, ...]
    includes_dependency_calls: bool


class DeltaDebugger:
    """Delta debugging engine with dependency awareness.

    Searches for a minimal subset of events that preserves a failure while
    respecting parent-child relationships and structural requirements.
    """

    def __init__(
        self,
        original_trace: Trace,
        *,
        predicate: Callable[[EventSubset], bool],
        preserve_run_markers: bool = True,
    ):
        """Initialize the delta debugger.

        Args:
            original_trace: The full trace to minimize
            predicate: Function that returns True if a subset reproduces the failure
            preserve_run_markers: Whether to always include run_start/run_end events
        """
        self.original_trace = original_trace
        self.predicate = predicate
        self.preserve_run_markers = preserve_run_markers
        self.attempts = 0

        # Build dependency graph
        self.parents = self._build_parent_map()
        self.children = self._build_children_map()

        # Identify minimizable events (dependency events + state changes)
        self.minimizable = self._identify_minimizable_events()

    def minimize(self) -> EventSubset:
        """Find a minimal failing subset using delta debugging.

        Returns:
            EventSubset containing the minimal set of events that reproduces the failure
        """
        # Start with all events
        current = set(range(len(self.original_trace.events)))

        # If there are no minimizable events, return the original
        if not self.minimizable:
            return self._build_subset(current)

        # Track the best (smallest) failing subset found
        best_failing = current.copy()

        # Use complement-based delta debugging: try removing subsets
        granularity = 2
        max_iterations = 100  # Prevent infinite loops
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            minimizable_list = sorted(self.minimizable & current)

            # If no minimizable events left in current, we're done
            if not minimizable_list:
                break

            subset_size = max(1, len(minimizable_list) // granularity)

            # If we've reached individual events, do final pass and exit
            if subset_size == 1 and granularity > len(minimizable_list):
                break

            progress_made = False

            for i in range(0, len(minimizable_list), subset_size):
                chunk = set(minimizable_list[i : i + subset_size])

                # Try removing this chunk
                candidate = current - chunk
                candidate_subset = self._build_subset(candidate)

                if self._test_subset(candidate_subset):
                    # Failure still reproduces without this chunk
                    current = candidate
                    best_failing = candidate.copy()
                    progress_made = True
                    break

            if progress_made:
                # Reset granularity to try larger chunks again
                granularity = 2
            else:
                # Increase granularity (try smaller chunks)
                granularity *= 2
                # If granularity is too large, we're done
                if granularity > len(minimizable_list):
                    break

        # Final pass: try removing individual events one at a time
        current = best_failing.copy()
        minimizable_in_best = sorted(best_failing & self.minimizable)

        for event_idx in minimizable_in_best:
            candidate = current - {event_idx}
            candidate_subset = self._build_subset(candidate)

            if self._test_subset(candidate_subset):
                current = candidate

        return self._build_subset(current)

    def _test_subset(self, subset: EventSubset) -> bool:
        """Test if a subset reproduces the failure."""
        self.attempts += 1
        return self.predicate(subset)

    def _build_subset(self, event_indices: set[int]) -> EventSubset:
        """Build an EventSubset from indices, adding required dependencies."""
        # Add all required parents
        required = event_indices.copy()
        for idx in event_indices:
            required.update(self._get_all_ancestors(idx))

        # Add structural events if configured
        if self.preserve_run_markers:
            for idx, event in enumerate(self.original_trace.events):
                if event.type in (EventType.RUN_START, EventType.RUN_END):
                    required.add(idx)
                    # Also add ancestors of run markers
                    required.update(self._get_all_ancestors(idx))

        # Sort by original step order
        sorted_indices = sorted(required)
        events = tuple(self.original_trace.events[idx] for idx in sorted_indices)

        includes_dependency_calls = any(
            self.original_trace.events[idx].type
            in (EventType.TOOL_CALL, EventType.LLM_REQUEST, EventType.STATE_CHANGE)
            for idx in event_indices
        )

        return EventSubset(
            events=events,
            includes_dependency_calls=includes_dependency_calls,
        )

    def _get_all_ancestors(self, event_idx: int) -> set[int]:
        """Get all ancestor events (parents, grandparents, etc.)."""
        ancestors: set[int] = set()
        event = self.original_trace.events[event_idx]

        if event.parent_id is None:
            return ancestors

        parent_idx = self.parents.get(event.id)
        if parent_idx is None:
            return ancestors

        ancestors.add(parent_idx)
        ancestors.update(self._get_all_ancestors(parent_idx))
        return ancestors

    def _build_parent_map(self) -> dict[str, int]:
        """Build mapping from event ID to parent event index."""
        parent_map: dict[str, int] = {}
        for event in self.original_trace.events:
            if event.parent_id is not None:
                parent_map[event.id] = self._find_event_index(event.parent_id)
        return parent_map

    def _build_children_map(self) -> dict[int, list[int]]:
        """Build mapping from event index to child event indices."""
        children_map: dict[int, list[int]] = {}
        for idx, event in enumerate(self.original_trace.events):
            if event.parent_id is not None:
                parent_idx = self._find_event_index(event.parent_id)
                children_map.setdefault(parent_idx, []).append(idx)
        return children_map

    def _find_event_index(self, event_id: str) -> int:
        """Find the index of an event by its ID."""
        for idx, event in enumerate(self.original_trace.events):
            if event.id == event_id:
                return idx
        raise ValueError(f"event {event_id} not found in trace")

    def _identify_minimizable_events(self) -> set[int]:
        """Identify events that can potentially be removed during minimization."""
        minimizable: set[int] = set()

        for idx, event in enumerate(self.original_trace.events):
            # Dependency events and state changes are minimizable
            if event.type in (
                EventType.TOOL_CALL,
                EventType.TOOL_RESULT,
                EventType.LLM_REQUEST,
                EventType.LLM_RESPONSE,
                EventType.STATE_CHANGE,
                EventType.ERROR,
            ) or (
                event.type in (EventType.RUN_START, EventType.RUN_END)
                and not self.preserve_run_markers
            ):
                minimizable.add(idx)

        return minimizable


def create_minimized_trace(
    original: Trace,
    subset: EventSubset,
) -> Trace:
    """Create a new trace from an event subset.

    Renormalizes event IDs, steps, and run metadata while preserving
    relative relationships.
    """
    # Create new trace with original metadata
    minimized = Trace(
        agent_name=original.agent_name,
        run_id=original.run_id,
        created_at=original.created_at,
        status=original.status,
        failure=original.failure,
        environment=original.environment,
    )

    # Add events with renormalized steps
    for event in subset.events:
        minimized.add(event.model_copy(deep=True))

    return minimized
