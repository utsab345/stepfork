from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from stepfork import record, trace_tool
from stepfork.cli.main import app

runner = CliRunner()


@trace_tool(name="echo")
def echo(value: str) -> dict[str, str]:
    return {"value": value}


def _record(destination: Path, value: str) -> None:
    with record("demo-agent", output=destination):
        echo(value)


def test_diff_cli_equivalent_exits_zero(tmp_path: Path) -> None:
    baseline = tmp_path / "b.sftrace"
    candidate = tmp_path / "c.sftrace"
    _record(baseline, "same")
    _record(candidate, "same")

    result = runner.invoke(app, ["diff", str(baseline), str(candidate)])

    assert result.exit_code == 0
    assert "BEHAVIOR EQUIVALENT" in result.stdout


def test_diff_cli_changed_exits_one(tmp_path: Path) -> None:
    baseline = tmp_path / "b.sftrace"
    candidate = tmp_path / "c.sftrace"
    _record(baseline, "one")
    _record(candidate, "two")

    result = runner.invoke(app, ["diff", str(baseline), str(candidate)])

    assert result.exit_code == 1
    assert "BEHAVIOR CHANGED" in result.stdout


def test_diff_cli_json_is_machine_readable(tmp_path: Path) -> None:
    baseline = tmp_path / "b.sftrace"
    candidate = tmp_path / "c.sftrace"
    _record(baseline, "one")
    _record(candidate, "two")

    result = runner.invoke(app, ["diff", str(baseline), str(candidate), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["equivalent"] is False
    assert payload["changed"] >= 1


def test_diff_cli_invalid_input_exits_two(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["diff", str(tmp_path / "a.sftrace"), "missing.sftrace"]
    )

    assert result.exit_code == 2
