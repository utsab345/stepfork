"""`stepfork diff` command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from stepfork.diff import DiffResult, FieldChange, StepDiff, diff_traces
from stepfork.trace import TraceStorageError
from stepfork.trace.redaction import redact_json

console = Console()
VALUE_LIMIT = 120

RESULT_EQUIVALENT = "BEHAVIOR EQUIVALENT"
RESULT_CHANGED = "BEHAVIOR CHANGED"


def diff_command(
    baseline: Annotated[
        Path,
        typer.Argument(
            help="Baseline .sftrace directory bundle.",
            exists=False,
            file_okay=False,
            dir_okay=True,
        ),
    ],
    candidate: Annotated[
        Path,
        typer.Argument(
            help="Candidate .sftrace directory bundle.",
            exists=False,
            file_okay=False,
            dir_okay=True,
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON (no Rich markup)."),
    ] = False,
) -> None:
    """Compare the behavior of two recorded agent runs.

    Exit codes: 0 behavior equivalent, 1 meaningful behavioral difference,
    2 invalid or unreadable input.
    """
    try:
        result = diff_traces(baseline, candidate)
    except (TraceStorageError, OSError) as exc:
        if json_output:
            _write_json(
                {
                    "error": "unreadable_trace",
                    "message": _sanitize_text(str(exc)),
                }
            )
        else:
            console.print("[red]Unable to compare traces.[/red]")
            console.print(_sanitize_text(str(exc)))
        raise typer.Exit(2) from exc

    if json_output:
        sys.stdout.write(result.model_dump_json())
        sys.stdout.write("\n")
        raise typer.Exit(0 if result.equivalent else 1)

    _print_diff(result)
    raise typer.Exit(0 if result.equivalent else 1)


def _print_diff(result: DiffResult) -> None:
    console.print("[bold]Stepfork Behavioral Diff[/bold]")
    console.print()
    console.print(f"Baseline:  {result.baseline.path or '(in-memory trace)'}")
    console.print(f"Candidate: {result.candidate.path or '(in-memory trace)'}")
    console.print()

    for step in result.steps:
        _print_step(step)

    if result.changed or result.added or result.removed:
        console.print(
            f"Steps: {len(result.steps)} total "
            f"({result.changed} changed, {result.added} added, "
            f"{result.removed} removed, {result.unchanged} unchanged)"
        )
        console.print()
        console.print(f"[red]Result: {RESULT_CHANGED}[/red]")
    else:
        console.print(f"Steps: {len(result.steps)} total (all unchanged)")
        console.print()
        console.print(f"[green]Result: {RESULT_EQUIVALENT}[/green]")


def _print_step(step: StepDiff) -> None:
    header = f"{step.step_type}: {step.label}"
    if step.kind == "added":
        console.print(f"[green]+[/green] {header} [green](added)[/green]")
        return
    if step.kind == "removed":
        console.print(f"[red]-[/red] {header} [red](removed)[/red]")
        return

    console.print(header)
    if not step.changes:
        console.print("  unchanged")
        return

    groups: dict[str, list[FieldChange]] = {}
    for change in step.changes:
        key = change.path.split(".", 1)[0].split("[", 1)[0]
        groups.setdefault(key, []).append(change)
    for field in step.fields:
        groups.setdefault(field, [])

    for key, changes in groups.items():
        if not changes:
            console.print(f"  {key}: unchanged")
            continue
        console.print(f"  {key}:")
        for change in changes:
            console.print(f"    expected: {_short(change.expected, absent=True)}")
            console.print(f"    actual:   {_short(change.actual, absent=True)}")
            if change.path != key:
                console.print(f"    at:       {change.path}")


def _short(value: Any, *, absent: bool = False) -> str:
    if value is None:
        return "(absent)" if absent else "None"
    sanitized = redact_json(value).value
    try:
        text = json.dumps(sanitized, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return "<unserializable>"
    if len(text) > VALUE_LIMIT:
        return f"{text[: VALUE_LIMIT - 1]}…"
    return text


def _sanitize_text(value: str) -> str:
    sanitized = redact_json(value).value
    if isinstance(sanitized, str):
        return sanitized
    return str(sanitized)


def _write_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    sys.stdout.write("\n")
