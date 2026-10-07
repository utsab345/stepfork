"""Stepfork command-line interface."""

from typing import Annotated

import typer
from rich.console import Console

from stepfork import __version__

app = typer.Typer(
    name="stepfork",
    help="Behavioral regression testing for AI agents.",
    invoke_without_command=True,
)

console = Console()


def version_callback(value: bool) -> None:
    """Print the Stepfork version and exit."""
    if value:
        console.print(f"stepfork {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            is_eager=True,
            help="Show the Stepfork version and exit.",
        ),
    ] = None,
) -> None:
    """Turn failed AI-agent runs into reproducible regression tests."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()
