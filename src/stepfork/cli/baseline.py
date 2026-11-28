"""Commands for saving and comparing local behavioral baselines."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from rich.console import Console

from stepfork.baseline import (
    BASELINE_DIRECTORY,
    Baseline,
    BaselineError,
    compare_baseline,
    list_baselines,
    load_baseline,
    save_baseline,
)
from stepfork.cli.diff import print_diff
from stepfork.trace.redaction import redact_json
from stepfork.trace.storage import SCHEMA_VERSION

console = Console()
baseline_app = typer.Typer(help="Manage local behavioral regression baselines.")


@baseline_app.command("save")
def save_command(
    name: Annotated[str, typer.Argument(help="New baseline name.")],
    trace: Annotated[Path, typer.Argument(help="Verified .sftrace bundle to save.")],
    directory: Annotated[
        Path,
        typer.Option("--directory", help="Baseline store directory."),
    ] = BASELINE_DIRECTORY,
) -> None:
    """Save an integrity-verified trace as a named baseline."""
    try:
        path = save_baseline(name, trace, directory=directory)
    except BaselineError as exc:
        _error(exc)
    console.print(f"Saved baseline {name} at {_safe_text(str(path))}", markup=False)


@baseline_app.command("list")
def list_command(
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
    directory: Annotated[
        Path,
        typer.Option("--directory", help="Baseline store directory."),
    ] = BASELINE_DIRECTORY,
) -> None:
    """List and verify baselines in the local store."""
    try:
        baselines = list_baselines(directory=directory)
    except BaselineError as exc:
        _error(exc)

    if json_output:
        _write_json([_baseline_data(baseline) for baseline in baselines])
    elif not baselines:
        console.print(f"No baselines found in {_safe_text(str(directory))}.")
    else:
        for baseline in baselines:
            console.print(
                f"{_safe_text(baseline.name)}  "
                f"{_safe_text(baseline.trace.agent_name)}  "
                f"{baseline.trace.status.value}  "
                f"{len(baseline.trace.events)} events",
                markup=False,
            )


@baseline_app.command("show")
def show_command(
    name: Annotated[str, typer.Argument(help="Baseline name.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
    directory: Annotated[
        Path,
        typer.Option("--directory", help="Baseline store directory."),
    ] = BASELINE_DIRECTORY,
) -> None:
    """Show metadata for one verified baseline."""
    try:
        baseline = load_baseline(name, directory=directory)
    except BaselineError as exc:
        _error(exc)

    if json_output:
        _write_json(_baseline_data(baseline))
        return

    environment = baseline.trace.environment
    fields = [
        ("Name", baseline.name),
        ("Path", str(baseline.path)),
        ("Agent", baseline.trace.agent_name),
        ("Run ID", baseline.trace.run_id),
        ("Status", baseline.trace.status.value),
        ("Schema", SCHEMA_VERSION),
        ("Stepfork version", environment.stepfork_version or "unknown"),
        ("Events", str(len(baseline.trace.events))),
        ("LLM calls", str(baseline.trace.totals.llm_calls)),
        ("Tool calls", str(baseline.trace.totals.tool_calls)),
    ]
    for label, value in fields:
        console.print(f"{label}: {_safe_text(value)}", markup=False)


@baseline_app.command("compare")
def compare_command(
    name: Annotated[str, typer.Argument(help="Named baseline to compare against.")],
    candidate: Annotated[Path, typer.Argument(help="Candidate .sftrace bundle.")],
    max_changes: Annotated[
        int,
        typer.Option(
            "--max-changes",
            min=0,
            help="Maximum changed, added, or removed behavior steps allowed.",
        ),
    ] = 0,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
    directory: Annotated[
        Path,
        typer.Option("--directory", help="Baseline store directory."),
    ] = BASELINE_DIRECTORY,
) -> None:
    """Compare a candidate trace; exit 1 when the threshold is exceeded."""
    try:
        result = compare_baseline(name, candidate, directory=directory)
    except BaselineError as exc:
        _error(exc)

    if result.baseline.path is not None:
        result.baseline.path = _safe_text(result.baseline.path)
    if result.candidate.path is not None:
        result.candidate.path = _safe_text(result.candidate.path)
    change_count = result.changed + result.added + result.removed
    regression = change_count > max_changes
    if json_output:
        _write_json(
            {
                "baseline_name": name,
                "candidate_path": result.candidate.path,
                "change_count": change_count,
                "max_changes": max_changes,
                "regression": regression,
                "diff": result.model_dump(mode="json"),
            }
        )
    else:
        print_diff(result)
        console.print(
            f"Behavior steps changed: {change_count} (allowed: {max_changes})",
            markup=False,
        )
        if regression:
            console.print("Result: REGRESSION", style="red", markup=False)
        elif change_count:
            console.print("Result: within configured threshold", style="yellow")
        else:
            console.print("Result: BASELINE MATCH", style="green", markup=False)

    raise typer.Exit(1 if regression else 0)


def _baseline_data(baseline: Baseline) -> dict[str, Any]:
    trace = baseline.trace
    return {
        "name": baseline.name,
        "path": str(baseline.path),
        "agent_name": trace.agent_name,
        "run_id": trace.run_id,
        "status": trace.status.value,
        "schema_version": SCHEMA_VERSION,
        "stepfork_version": trace.environment.stepfork_version,
        "events": len(trace.events),
        "llm_calls": trace.totals.llm_calls,
        "tool_calls": trace.totals.tool_calls,
    }


def _write_json(payload: Any) -> None:
    sanitized = redact_json(payload).value
    sys.stdout.write(json.dumps(sanitized, sort_keys=True))
    sys.stdout.write("\n")


def _safe_text(value: str) -> str:
    sanitized = redact_json(value).value
    return sanitized if isinstance(sanitized, str) else str(sanitized)


def _error(error: BaselineError) -> NoReturn:
    console.print(
        f"Baseline error: {_safe_text(str(error))}", style="red", markup=False
    )
    raise typer.Exit(2) from error
