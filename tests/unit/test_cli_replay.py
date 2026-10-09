from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

from stepfork import ReplaySession, record, trace_tool
from stepfork.cli.main import app

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = "examples.booking_agent:run_agent"


@trace_tool(name="step")
def step(value: str) -> dict[str, str]:
    return {"value": value}


def _record_step(destination: Path) -> None:
    with record("demo-agent", output=destination):
        step("a")


def _record_booking(destination: Path) -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from examples.booking_agent import agent

    with record("booking-agent", output=destination) as session:
        session.set_output(agent.run_agent())


def test_replay_cli_frozen_success(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", ENTRYPOINT, "--mode", "frozen"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "COMPLETED" in result.stdout


def test_replay_cli_rejects_invalid_mode(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_step(trace)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", ENTRYPOINT, "--mode", "banana"],
    )

    assert result.exit_code == 2
    assert "Invalid replay mode" in result.stdout


def test_replay_cli_missing_trace_exits_two(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["replay", str(tmp_path / "missing.sftrace"), "--entrypoint", ENTRYPOINT],
    )

    assert result.exit_code == 2


def test_replay_cli_invalid_entrypoint_exits_two(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_step(trace)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", "not_a_module:func"],
    )

    assert result.exit_code == 2
    assert "entrypoint" in result.stdout.lower()


def test_replay_api_is_importable() -> None:
    assert ReplaySession is not None
