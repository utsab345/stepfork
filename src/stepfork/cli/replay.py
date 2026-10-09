"""`stepfork replay` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from stepfork.export.entrypoint import EntrypointError, resolve_entrypoint
from stepfork.replay import (
    RecordedDependencyError,
    ReplayError,
    ReplaySession,
)
from stepfork.trace import RunStatus, Trace, TraceStorageError
from stepfork.trace.canonical import canonical_json_bytes
from stepfork.trace.jsonable import TraceSerializationError, to_json_value
from stepfork.trace.redaction import redact_json
from stepfork.trace.replay_policy import ReplayPolicy

console = Console()
PREVIEW_LIMIT = 400


def replay_command(
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
    entrypoint: Annotated[
        str,
        typer.Option(
            "--entrypoint",
            help="Trusted local MODULE:FUNCTION to execute under replay.",
        ),
    ],
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="Replay mode: frozen, live, forbidden, manual, or derived.",
        ),
    ] = "frozen",
) -> None:
    """Execute a trusted entrypoint with dependencies replayed from a trace.

    Only the entrypoint you name is imported and run. Trace bundles are data:
    Stepfork never executes code embedded in a trace.
    """
    try:
        ReplayPolicy(mode)
    except ValueError:
        console.print(f"[red]Invalid replay mode {mode!r}.[/red]")
        raise typer.Exit(2) from None

    try:
        trace = Trace.load(path)
    except TraceStorageError as exc:
        console.print("[red]Unable to read trace.[/red]")
        console.print(_sanitize_text(str(exc)))
        raise typer.Exit(2) from exc

    try:
        entry = resolve_entrypoint(entrypoint, import_root=Path.cwd())
    except EntrypointError as exc:
        console.print("[red]Unable to resolve entrypoint.[/red]")
        console.print(_sanitize_text(str(exc)))
        raise typer.Exit(2) from exc

    divergence: str | None = None
    result_value: Any = None
    agent_exc: BaseException | None = None

    try:
        with ReplaySession.from_trace(trace, mode=mode) as replay:
            try:
                result_value = entry()
            except ReplayError as exc:
                divergence = _sanitize_text(str(exc))
            except Exception as exc:
                agent_exc = exc
            if divergence is None:
                try:
                    replay.verify_complete()
                except ReplayError as exc:
                    divergence = _sanitize_text(str(exc))
            matched = replay.matched
            remaining = replay.pending
    except ReplayError as exc:
        console.print("[red]Replay failed before execution.[/red]")
        console.print(_sanitize_text(str(exc)))
        raise typer.Exit(1) from exc

    status = "completed"
    if divergence is None and agent_exc is not None:
        failure_type = trace.failure.type if trace.failure else None
        raised_type = type(agent_exc).__name__
        if (trace.status is RunStatus.FAILED and raised_type == failure_type) or (
            isinstance(agent_exc, RecordedDependencyError)
            and trace.status is RunStatus.FAILED
            and agent_exc.error_type == failure_type
        ):
            status = "reproduced_failure"
        else:
            recorded = f"status {trace.status.value}"
            if failure_type:
                recorded += f" (failure {failure_type})"
            divergence = (
                f"entrypoint raised {raised_type}: "
                f"{_sanitize_text(str(agent_exc))} but the trace recorded "
                f"{recorded}"
            )
    elif divergence is None and agent_exc is None:
        if trace.status is RunStatus.FAILED:
            divergence = (
                "trace recorded a failed run but the entrypoint completed "
                "without raising"
            )

    _print_report(
        trace=trace,
        path=path,
        entrypoint=entrypoint,
        mode=mode,
        matched=matched,
        remaining=remaining,
        status=status,
        divergence=divergence,
        result_value=result_value,
        agent_exc=agent_exc,
    )

    raise typer.Exit(1 if divergence is not None else 0)


def _print_report(
    *,
    trace: Trace,
    path: Path,
    entrypoint: str,
    mode: str,
    matched: list[Any],
    remaining: int,
    status: str,
    divergence: str | None,
    result_value: Any,
    agent_exc: BaseException | None,
) -> None:
    console.print("[bold]Stepfork Replay[/bold]")
    console.print()

    table = Table.grid(padding=(0, 4))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Trace", str(path))
    table.add_row("Agent", trace.agent_name)
    table.add_row("Entrypoint", entrypoint)
    table.add_row("Mode", mode)
    console.print(table)
    console.print()

    console.print("[bold]Dependency Calls[/bold]")
    if not matched:
        console.print("  (no dependency calls matched)")
    else:
        for item in matched:
            console.print(
                f"  {item.index + 1}. {item.kind} {item.label} "
                f"[green]({item.action})[/green]"
            )
    if remaining:
        console.print(f"  [yellow]{remaining} recorded call(s) unmatched[/yellow]")
    console.print()

    if divergence is not None:
        console.print("Status: [red]DIVERGED[/red]")
        console.print(_sanitize_text(divergence))
        console.print()
        return

    if status == "reproduced_failure" and agent_exc is not None:
        console.print(
            f"Status: [yellow]REPRODUCED FAILURE[/yellow] ({type(agent_exc).__name__})"
        )
    else:
        console.print("Status: [green]COMPLETED[/green]")

    console.print(f"Final result: {_result_preview(result_value)}")
    console.print()


def _result_preview(value: Any) -> str:
    if value is None:
        return "None"
    try:
        payload = to_json_value(value)
        text = canonical_json_bytes(payload).decode("utf-8", errors="replace")
    except TraceSerializationError:
        return f"<non-serializable {type(value).__name__}>"
    except TypeError:
        return "<non-serializable>"
    sanitized = _sanitize_text(text)
    if len(sanitized) > PREVIEW_LIMIT:
        return f"{sanitized[: PREVIEW_LIMIT - 1]}…"
    return sanitized


def _sanitize_text(value: str) -> str:
    sanitized = redact_json(value).value
    if isinstance(sanitized, str):
        return sanitized
    return str(sanitized)
