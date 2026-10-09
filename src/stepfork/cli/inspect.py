"""`stepfork inspect` command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from stepfork.inspect.inspector import filter_timeline, inspect_bundle
from stepfork.inspect.models import TraceInspection
from stepfork.trace import TraceStorageError
from stepfork.trace.redaction import redact_json

console = Console()
MAX_DETAIL_LENGTH = 180


def _sanitize_text(value: str) -> str:
    sanitized = redact_json(value).value
    if isinstance(sanitized, str):
        return sanitized
    return str(sanitized)


def inspect_command(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to a .sftrace directory bundle.",
            exists=False,
            file_okay=False,
            dir_okay=True,
            readable=True,
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit sanitized machine-readable JSON."),
    ] = False,
    events: Annotated[
        bool,
        typer.Option("--events", help="Show sanitized event details."),
    ] = False,
    errors_only: Annotated[
        bool,
        typer.Option("--errors-only", help="Show only error events."),
    ] = False,
    step: Annotated[
        int | None,
        typer.Option("--step", help="Show events at a specific logical step."),
    ] = None,
) -> None:
    """Inspect a `.sftrace` bundle."""
    try:
        inspection = filter_timeline(
            inspect_bundle(path),
            errors_only=errors_only,
            step=step,
        )
    except TraceStorageError as exc:
        message = _sanitize_text(str(exc))
        if json_output:
            _write_json(
                {
                    "error": "unreadable_trace",
                    "message": message,
                }
            )
        else:
            console.print("[red]Unable to inspect trace.[/red]")
            console.print(message)
        raise typer.Exit(2) from exc

    if step is not None and not inspection.timeline:
        message = f"No events found at step {step}."
        if json_output:
            _write_json({"error": "missing_step", "message": message})
        else:
            console.print(f"[red]{message}[/red]")
        raise typer.Exit(1)

    if json_output:
        sys.stdout.write(inspection.model_dump_json())
        sys.stdout.write("\n")
        raise typer.Exit(0)

    _print_summary(inspection)
    _print_timeline(inspection, show_details=events)
    raise typer.Exit(0)


def _print_summary(inspection: TraceInspection) -> None:
    console.print("[bold]Stepfork Trace Inspector[/bold]")
    console.print()

    table = Table.grid(padding=(0, 4))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Agent:", inspection.agent_name)
    table.add_row("Run:", inspection.run_id)
    table.add_row("Status:", inspection.status.upper())
    table.add_row("Events:", str(inspection.events))
    table.add_row("Schema:", inspection.schema_version)
    table.add_row("Created:", inspection.created_at)
    table.add_row("LLM calls:", str(inspection.llm_calls))
    table.add_row("Tool calls:", str(inspection.tool_calls))
    if inspection.duration_ms is not None:
        table.add_row("Duration:", f"{inspection.duration_ms} ms")
    table.add_row("Integrity:", inspection.integrity.upper())
    if inspection.failure:
        table.add_row("Failure:", _compact(inspection.failure))
    console.print(table)
    console.print()


def _print_timeline(inspection: TraceInspection, *, show_details: bool) -> None:
    console.print("[bold]Event Timeline[/bold]")
    console.print()
    table = Table(show_lines=show_details)
    table.add_column("Step", justify="right")
    table.add_column("Type")
    table.add_column("Name/Model")
    table.add_column("Status")
    if show_details:
        table.add_column("Details")

    for event in inspection.timeline:
        row = [
            str(event.step),
            event.type,
            event.label,
            event.status,
        ]
        if show_details:
            row.append(_compact(event.details))
        table.add_row(*row)

    console.print(table)


def _compact(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) <= MAX_DETAIL_LENGTH:
        return text
    return f"{text[: MAX_DETAIL_LENGTH - 1]}…"


def _write_json(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True))
    sys.stdout.write("\n")
