from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from stepfork import FailureInfo, ToolCall, Trace
from stepfork.cli.main import app
from stepfork.trace import (
    ErrorEvent,
    EventStatus,
    RunEnd,
    RunStart,
    RunStatus,
    ToolResult,
)

runner = CliRunner()


def failed_trace() -> Trace:
    trace = Trace(agent_name="booking-agent")
    start = trace.add(RunStart(input={"prompt": "book"}))
    call = trace.add(
        ToolCall(
            name="flight_search",
            input={"query": "काठमाडौँ flights", "api_key": "sk-syntheticcli123456"},
            parent_id=start.id,
        )
    )
    result = trace.add(
        ToolResult(
            name="flight_search",
            output={"ok": False},
            parent_id=call.id,
            status=EventStatus.ERROR,
        )
    )
    error = trace.add(
        ErrorEvent(error_type="ToolError", message="failed", parent_id=result.id)
    )
    trace.add(RunEnd(run_status=RunStatus.FAILED, parent_id=error.id))
    return trace


def save_failed(tmp_path: Path) -> Path:
    return failed_trace().save(
        tmp_path / "failed.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolError", message="failed", step=3),
    )


def test_inspect_default_output(tmp_path: Path) -> None:
    path = save_failed(tmp_path)

    result = runner.invoke(app, ["inspect", str(path)])

    assert result.exit_code == 0
    assert "Stepfork Trace Inspector" in result.stdout
    assert "booking-agent" in result.stdout
    assert "flight_search" in result.stdout
    assert "sk-syntheticcli" not in result.stdout


def test_inspect_json_output_is_parseable_without_ansi(tmp_path: Path) -> None:
    path = save_failed(tmp_path)

    result = runner.invoke(app, ["inspect", str(path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["agent_name"] == "booking-agent"
    assert payload["timeline"][1]["label"] == "flight_search"
    assert "\x1b[" not in result.stdout


def test_inspect_events_shows_sanitized_details(tmp_path: Path) -> None:
    path = save_failed(tmp_path)

    result = runner.invoke(app, ["inspect", str(path), "--events"])

    assert result.exit_code == 0
    assert "[REDACTED]" in result.stdout
    assert "sk-syntheticcli" not in result.stdout


def test_inspect_errors_only(tmp_path: Path) -> None:
    path = save_failed(tmp_path)

    result = runner.invoke(app, ["inspect", str(path), "--errors-only", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [event["type"] for event in payload["timeline"]] == ["tool_result", "error"]


def test_inspect_step_filter(tmp_path: Path) -> None:
    path = save_failed(tmp_path)

    result = runner.invoke(app, ["inspect", str(path), "--step", "1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["timeline"]) == 1
    assert payload["timeline"][0]["step"] == 1


def test_inspect_missing_step(tmp_path: Path) -> None:
    path = save_failed(tmp_path)

    result = runner.invoke(app, ["inspect", str(path), "--step", "99"])

    assert result.exit_code == 1
    assert "No events found" in result.stdout


def test_inspect_missing_bundle(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", str(tmp_path / "missing.sftrace")])

    assert result.exit_code == 2
    assert "Unable to inspect trace" in result.stdout


def test_inspect_help() -> None:
    result = runner.invoke(app, ["inspect", "--help"])

    assert result.exit_code == 0
    assert "--json" in result.stdout
    assert "--errors-only" in result.stdout
