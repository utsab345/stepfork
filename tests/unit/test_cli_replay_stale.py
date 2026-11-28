"""CLI replay reporting for potentially stale fork outputs."""

from __future__ import annotations

import textwrap
from pathlib import Path

from typer.testing import CliRunner

from stepfork import record, trace_tool
from stepfork.cli.main import app
from stepfork.fork import ForkPoint, OverrideSpec, fork_trace

runner = CliRunner()


@trace_tool(name="search")
def search(query: str) -> dict[str, object]:
    return {"query": query, "results": ["a", "b"]}


@trace_tool(name="book")
def book(item: str) -> dict[str, object]:
    return {"item": item, "status": "ok"}


def agent() -> dict[str, object]:
    search_result = search("flights")
    booking = book("a")
    return {"search": search_result, "booking": booking}


TARGETS = """
from stepfork import trace_tool

@trace_tool(name="search")
def search(query: str) -> dict[str, object]:
    return {"query": query, "results": ["x"]}

@trace_tool(name="book")
def book(item: str) -> dict[str, object]:
    return {"item": item, "status": "ok"}

def run_agent() -> dict[str, object]:
    search_result = search("flights")
    booking = book("a")
    return {"search": search_result, "booking": booking}
"""


def write_targets(tmp_path: Path) -> None:
    pkg = tmp_path / "targetpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "targets.py").write_text(textwrap.dedent(TARGETS), encoding="utf-8")


def test_replay_cli_reports_potentially_stale_outputs(
    tmp_path: Path, monkeypatch
) -> None:
    trace_path = tmp_path / "base.sftrace"
    with record("agent", output=trace_path) as session:
        session.set_output(agent())

    fork_result = fork_trace(
        trace_path,
        ForkPoint(event_id=None, step=4),
        overrides=[OverrideSpec(step=2, output={"query": "flights", "results": ["x"]})],
        output_path=tmp_path / "fork.sftrace",
    )
    assert fork_result.success

    write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "replay",
            str(tmp_path / "fork.sftrace"),
            "--entrypoint",
            "targetpkg.targets:run_agent",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "potentially stale" in result.stdout.lower()
    assert "POTENTIALLY STALE" in result.stdout
    assert "not verified against the modified path" in result.stdout.replace("\n", " ")
