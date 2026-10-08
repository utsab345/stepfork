"""`stepfork validate` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from stepfork.trace import TraceStorageError, ValidationResult, validate_bundle
from stepfork.trace.integrity import IntegrityStatus, verify_bundle_integrity
from stepfork.trace.storage import load_trace

console = Console()

UNREADABLE_CODES = {
    "missing_file",
    "invalid_json",
    "invalid_manifest",
    "invalid_event",
    "unsupported_schema",
    "integrity_metadata_invalid",
    "integrity_algorithm_unsupported",
}


def validate_command(
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
    partial: Annotated[
        bool,
        typer.Option(
            "--partial",
            help="Allow incomplete in-progress traces without run_start checks.",
        ),
    ] = False,
    verify_integrity: Annotated[
        bool,
        typer.Option(
            "--verify-integrity",
            help="Verify Day 4 payload hashes and bundle integrity metadata.",
        ),
    ] = False,
) -> None:
    """Validate a `.sftrace` bundle."""
    strict = not partial
    structure_result = validate_bundle(path, strict=strict)
    result = validate_bundle(
        path,
        strict=strict,
        verify_integrity=verify_integrity,
    )

    _print_header(path, strict=strict)
    _print_metadata(path, strict=strict)
    if verify_integrity and structure_result.valid:
        _print_integrity(path)

    if result.valid:
        console.print("[green]✓[/green] Manifest valid")
        console.print("[green]✓[/green] Event structure valid")
        console.print("[green]✓[/green] Event IDs unique")
        console.print("[green]✓[/green] Parent references valid")
        console.print("[green]✓[/green] Run IDs consistent")
        console.print("[green]✓[/green] Event count matches")
        console.print()
        console.print("[green]Validation passed.[/green]")
        raise typer.Exit(0)

    for issue in result.issues:
        console.print(f"[red]✗[/red] {issue.code}")
        console.print(f"  {issue.message}")
        if issue.location:
            console.print(f"  [dim]{issue.location}[/dim]")
        console.print()

    console.print(f"[red]Validation failed: {len(result.issues)} issues.[/red]")
    if verify_integrity and _has_legacy_integrity_issue(result):
        raise typer.Exit(3)
    has_unreadable_issue = any(
        issue.code in UNREADABLE_CODES for issue in result.issues
    )
    exit_code = 2 if has_unreadable_issue else 1
    raise typer.Exit(exit_code)


def _print_header(path: Path, *, strict: bool) -> None:
    console.print("[bold]Stepfork Trace Validation[/bold]")
    console.print()

    table = Table.grid(padding=(0, 4))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Trace", str(path))
    if not path.exists():
        table.add_row("Mode", "strict" if strict else "partial")
    console.print(table)
    console.print()


def _print_metadata(path: Path, *, strict: bool) -> None:
    try:
        trace = load_trace(path)
    except TraceStorageError:
        return

    table = Table.grid(padding=(0, 4))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Schema", "0.1")
    table.add_row("Events", str(len(trace.events)))
    table.add_row("Mode", "strict" if strict else "partial")
    console.print(table)
    console.print()


def _print_integrity(path: Path) -> None:
    result = verify_bundle_integrity(path)
    status_label = (
        "UNVERIFIED (legacy bundle)"
        if result.status is IntegrityStatus.UNVERIFIED_LEGACY
        else result.status.value.upper()
    )
    console.print("Structure: [green]PASS[/green]")
    style = "green" if result.status is IntegrityStatus.VERIFIED else "yellow"
    if result.status is IntegrityStatus.MISMATCH:
        style = "red"
    console.print(f"Integrity: [{style}]{status_label}[/{style}]")
    console.print()

    table = Table.grid(padding=(0, 4))
    table.add_column()
    table.add_column()
    for filename in ("manifest.json", "events.jsonl", "redactions.json"):
        if filename in result.verified_files:
            table.add_row(filename, "verified")
            continue
        issue = next((item for item in result.issues if item.file == filename), None)
        table.add_row(filename, issue.message if issue else "unverified")
    if result.status is IntegrityStatus.UNVERIFIED_LEGACY:
        table.add_row("integrity.json", "missing legacy metadata")
    console.print(table)
    console.print()


def _has_legacy_integrity_issue(result: ValidationResult) -> bool:
    return any(
        issue.code == "integrity_unverified" and issue.location == "integrity.json"
        for issue in result.issues
    )
