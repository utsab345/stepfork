"""Semantic comparison of two recorded agent behaviors.

Timestamps, event IDs, run IDs, and wall-clock durations are ignored by
default. Comparison covers dependency call order, tool names, LLM models,
inputs, outputs, error types, state changes, and run status.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stepfork.diff.compare import collect_field_changes, values_equal
from stepfork.diff.models import DiffResult, FieldChange, StepDiff, TraceSummary
from stepfork.replay.plan import extract_recorded_calls
from stepfork.trace import (
    ErrorEvent,
    JsonValue,
    LLMRequest,
    RunEnd,
    StateChange,
    ToolCall,
    Trace,
)
from stepfork.trace.redaction import redact_json

TraceInput = str | Path | Trace


@dataclass(frozen=True)
class BehaviorStep:
    """One comparable unit of agent behavior extracted from a trace."""

    step_type: str
    label: str
    payload: dict[str, JsonValue]


def diff_traces(
    baseline: TraceInput,
    candidate: TraceInput,
) -> DiffResult:
    """Compare baseline and candidate traces as structured behavior.

    Accepts `.sftrace` paths or already-loaded :class:`Trace` objects and
    raises `TraceStorageError` for unreadable bundles.
    """
    baseline_trace = _load(baseline)
    candidate_trace = _load(candidate)

    baseline_steps = extract_behavior(baseline_trace)
    candidate_steps = extract_behavior(candidate_trace)
    # The terminal run event describes the whole run. Align it with the other
    # terminal run event even when one side inserted an error event before it.
    if (
        baseline_steps
        and candidate_steps
        and baseline_steps[-1].step_type == "run"
        and candidate_steps[-1].step_type == "run"
    ):
        steps = _diff_steps(baseline_steps[:-1], candidate_steps[:-1])
        run_diff = _diff_steps(baseline_steps[-1:], candidate_steps[-1:])[0]
        steps.append(run_diff.model_copy(update={"index": len(steps)}))
    else:
        steps = _diff_steps(baseline_steps, candidate_steps)

    added = sum(step.kind == "added" for step in steps)
    removed = sum(step.kind == "removed" for step in steps)
    changed = sum(step.kind == "changed" for step in steps)
    unchanged = sum(step.kind == "unchanged" for step in steps)

    return DiffResult(
        equivalent=added == 0 and removed == 0 and changed == 0,
        baseline=_summary(baseline_trace, baseline),
        candidate=_summary(candidate_trace, candidate),
        steps=steps,
        added=added,
        removed=removed,
        changed=changed,
        unchanged=unchanged,
    )


def extract_behavior(trace: Trace) -> list[BehaviorStep]:
    """Extract the ordered, sanitized behavior steps from a trace."""
    calls = {call.call_event_id: call for call in extract_recorded_calls(trace)}
    steps: list[BehaviorStep] = []

    for event in trace.events:
        if isinstance(event, ToolCall | LLMRequest):
            call = calls.get(event.id)
            if call is None:  # pragma: no cover - defensive
                continue
            steps.append(
                BehaviorStep(
                    step_type=call.kind,
                    label=call.label,
                    payload=_sanitized_payload(
                        input=call.input,
                        output=call.output,
                        status=call.status.value,
                    ),
                )
            )
        elif isinstance(event, StateChange):
            steps.append(
                BehaviorStep(
                    step_type="state",
                    label=event.key or "state",
                    payload={
                        "before": _sanitize(event.before),
                        "after": _sanitize(event.after),
                    },
                )
            )
        elif isinstance(event, ErrorEvent):
            steps.append(
                BehaviorStep(
                    step_type="error",
                    label=event.error_type,
                    payload={"message": _sanitize(event.message)},
                )
            )
        elif isinstance(event, RunEnd):
            steps.append(
                BehaviorStep(
                    step_type="run",
                    label="run",
                    payload={
                        "run_status": event.run_status.value,
                        "output": _sanitize(event.output),
                    },
                )
            )

    return steps


def _diff_steps(
    baseline_steps: list[BehaviorStep],
    candidate_steps: list[BehaviorStep],
) -> list[StepDiff]:
    diffs: list[StepDiff] = []
    total = max(len(baseline_steps), len(candidate_steps))

    for index in range(total):
        if index >= len(baseline_steps):
            step = candidate_steps[index]
            diffs.append(
                StepDiff(
                    index=index,
                    kind="added",
                    step_type=step.step_type,
                    label=step.label,
                    changes=[],
                )
            )
            continue
        if index >= len(candidate_steps):
            step = baseline_steps[index]
            diffs.append(
                StepDiff(
                    index=index,
                    kind="removed",
                    step_type=step.step_type,
                    label=step.label,
                    changes=[],
                )
            )
            continue

        baseline_step = baseline_steps[index]
        candidate_step = candidate_steps[index]
        changes: list[FieldChange] = []

        if baseline_step.step_type != candidate_step.step_type:
            changes.append(
                FieldChange(
                    path="type",
                    kind="changed",
                    expected=baseline_step.step_type,
                    actual=candidate_step.step_type,
                )
            )
        if baseline_step.label != candidate_step.label:
            changes.append(
                FieldChange(
                    path="label",
                    kind="changed",
                    expected=baseline_step.label,
                    actual=candidate_step.label,
                )
            )

        keys = sorted(set(baseline_step.payload) | set(candidate_step.payload))
        for key in keys:
            if key not in baseline_step.payload:
                changes.append(
                    FieldChange(
                        path=key,
                        kind="added",
                        expected=None,
                        actual=candidate_step.payload[key],
                    )
                )
            elif key not in candidate_step.payload:
                changes.append(
                    FieldChange(
                        path=key,
                        kind="removed",
                        expected=baseline_step.payload[key],
                        actual=None,
                    )
                )
            else:
                collect_field_changes(
                    baseline_step.payload[key],
                    candidate_step.payload[key],
                    path=key,
                    output=changes,
                )

        diffs.append(
            StepDiff(
                index=index,
                kind="changed" if changes else "unchanged",
                step_type=baseline_step.step_type,
                label=baseline_step.label,
                fields=keys,
                changes=changes,
            )
        )

    return diffs


def _sanitized_payload(
    *,
    input: JsonValue,
    output: JsonValue | None,
    status: str,
) -> dict[str, JsonValue]:
    return {
        "input": _sanitize(input),
        "output": _sanitize(output),
        "status": status,
    }


def _sanitize(value: JsonValue | None) -> JsonValue:
    return redact_json(value).value


def _summary(trace: Trace, source: TraceInput) -> TraceSummary:
    path = str(source) if isinstance(source, str | Path) else None
    return TraceSummary(
        path=path,
        agent_name=trace.agent_name,
        run_id=trace.run_id,
        status=trace.status.value,
        events=len(trace.events),
    )


def _load(source: TraceInput) -> Trace:
    if isinstance(source, Trace):
        return source
    return Trace.load(Path(source))


def steps_equivalent(left: BehaviorStep, right: BehaviorStep) -> bool:
    """Return True when two behavior steps describe identical behavior."""
    if left.step_type != right.step_type or left.label != right.label:
        return False
    if set(left.payload) != set(right.payload):
        return False
    return all(
        values_equal(left.payload[key], right.payload[key]) for key in left.payload
    )
