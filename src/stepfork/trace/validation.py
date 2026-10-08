"""Structured validation for Stepfork traces and `.sftrace` bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from stepfork.trace.manifest import RunStatus
from stepfork.trace.models import EventType, Trace
from stepfork.trace.storage import REQUIRED_FILES, TraceStorageError, load_trace


class ValidationIssue(BaseModel):
    """Machine-readable validation issue."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    event_id: str | None = None
    step: int | None = None
    location: str | None = None


class ValidationResult(BaseModel):
    """Structured validation result."""

    model_config = ConfigDict(extra="forbid")

    valid: bool = True
    issues: list[ValidationIssue]

    @model_validator(mode="after")
    def valid_matches_issues(self) -> Self:
        """Keep `valid` derived from the issue list."""
        self.valid = not self.issues
        return self


def validate_trace(trace: Trace, *, strict: bool = True) -> ValidationResult:
    """Validate cross-event structure for an in-memory trace."""
    issues: list[ValidationIssue] = []

    if trace.totals.events != len(trace.events):
        issues.append(
            ValidationIssue(
                code="event_count_mismatch",
                message=(
                    "Manifest event count "
                    f"{trace.totals.events} does not match {len(trace.events)}."
                ),
                location="manifest.json:totals.events",
            )
        )

    seen: dict[str, int] = {}
    first_positions: dict[str, int] = {}
    for index, event in enumerate(trace.events):
        first_positions.setdefault(event.id, index)
    previous_step: int | None = None
    run_start_count = 0
    has_error_event = False

    for index, event in enumerate(trace.events):
        if event.id in seen:
            issues.append(
                ValidationIssue(
                    code="duplicate_event_id",
                    message=f"Event {event.id} appears more than once.",
                    event_id=event.id,
                    step=event.step,
                )
            )
        else:
            seen[event.id] = index

        if event.run_id != trace.run_id:
            issues.append(
                ValidationIssue(
                    code="run_id_mismatch",
                    message=(
                        f"Event {event.id} run_id {event.run_id!r} does not "
                        f"match manifest run_id {trace.run_id!r}."
                    ),
                    event_id=event.id,
                    step=event.step,
                )
            )

        if previous_step is not None and event.step < previous_step:
            issues.append(
                ValidationIssue(
                    code="step_order",
                    message=(
                        f"Event {event.id} step {event.step} is less than "
                        f"the previous step {previous_step}."
                    ),
                    event_id=event.id,
                    step=event.step,
                )
            )
        previous_step = event.step

        if event.parent_id is not None:
            parent_index = first_positions.get(event.parent_id)
            if parent_index is None:
                issues.append(
                    ValidationIssue(
                        code="invalid_parent",
                        message=(
                            f"Event {event.id} references missing parent "
                            f"{event.parent_id}."
                        ),
                        event_id=event.id,
                        step=event.step,
                    )
                )
            elif parent_index >= index:
                issues.append(
                    ValidationIssue(
                        code="parent_not_earlier",
                        message=(
                            f"Event {event.id} parent {event.parent_id} does "
                            "not appear earlier in the trace."
                        ),
                        event_id=event.id,
                        step=event.step,
                    )
                )

        if event.type is EventType.RUN_START:
            run_start_count += 1
        if event.type is EventType.ERROR:
            has_error_event = True

    if strict and run_start_count != 1:
        issues.append(
            ValidationIssue(
                code="run_start_count",
                message=(
                    "Strict validation requires exactly one run_start; "
                    f"found {run_start_count}."
                ),
                location="events.jsonl",
            )
        )

    if strict and trace.status is RunStatus.FAILED and not has_error_event:
        issues.append(
            ValidationIssue(
                code="missing_error_event",
                message=(
                    "Failed traces require at least one error event in strict mode."
                ),
                location="events.jsonl",
            )
        )

    return ValidationResult(issues=issues)


def validate_bundle(path: str | Path, *, strict: bool = True) -> ValidationResult:
    """Load and validate a `.sftrace` bundle."""
    bundle_path = Path(path)
    missing = _missing_files(bundle_path)
    if missing:
        return ValidationResult(
            issues=[
                ValidationIssue(
                    code="missing_file",
                    message=f"Missing required file: {file_path}.",
                    location=str(file_path),
                )
                for file_path in missing
            ]
        )

    try:
        trace = load_trace(bundle_path)
    except TraceStorageError as exc:
        message = str(exc)
        return ValidationResult(
            issues=[
                ValidationIssue(
                    code=_storage_error_code(message),
                    message=message,
                    location=_storage_error_location(message),
                )
            ]
        )

    return validate_trace(trace, strict=strict)


def _missing_files(path: Path) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return [path]
    return [
        path / filename
        for filename in REQUIRED_FILES
        if not (path / filename).is_file()
    ]


def _storage_error_code(message: str) -> str:
    if "unsupported" in message:
        return "unsupported_schema"
    if "invalid JSON" in message or "blank JSONL line" in message:
        return "invalid_json"
    if "invalid manifest" in message:
        return "invalid_manifest"
    if "invalid event" in message:
        return "invalid_event"
    if "missing required file" in message:
        return "missing_file"
    return "invalid_manifest"


def _storage_error_location(message: str) -> str | None:
    if ":" not in message:
        return None
    first, second, *_ = message.split(":")
    if second.isdigit():
        return f"{first}:{second}"
    return first
