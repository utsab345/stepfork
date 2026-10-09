"""Behavioral trace comparison."""

from stepfork.diff.compare import collect_field_changes, first_difference, values_equal
from stepfork.diff.engine import BehaviorStep, diff_traces, extract_behavior
from stepfork.diff.models import (
    ChangeKind,
    DiffResult,
    FieldChange,
    StepDiff,
    TraceSummary,
)

__all__ = [
    "BehaviorStep",
    "ChangeKind",
    "DiffResult",
    "FieldChange",
    "StepDiff",
    "TraceSummary",
    "collect_field_changes",
    "diff_traces",
    "extract_behavior",
    "first_difference",
    "values_equal",
]
