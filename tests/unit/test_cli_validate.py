from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from stepfork import ToolCall, Trace
from stepfork.cli.main import app
from stepfork.trace import RunEnd, RunStart, RunStatus, ToolResult

runner = CliRunner()


def complete_trace() -> Trace:
    trace = Trace(agent_name="demo-agent")
    start = trace.add(RunStart(input={"prompt": "book"}))
    call = trace.add(
        ToolCall(
            name="search",
            input={"query": "Kathmandu flights"},
            parent_id=start.id,
        )
    )
    result = trace.add(
        ToolResult(name="search", output={"flights": []}, parent_id=call.id)
    )
    trace.add(RunEnd(run_status=RunStatus.COMPLETED, parent_id=result.id))
    return trace


def test_validate_valid_trace(tmp_path: Path) -> None:
    path = complete_trace().save(
        tmp_path / "valid.sftrace",
        status=RunStatus.COMPLETED,
    )

    result = runner.invoke(app, ["validate", str(path)])

    assert result.exit_code == 0
    assert "Validation passed" in result.stdout
    assert "Mode" in result.stdout
    assert "strict" in result.stdout


def test_validate_with_integrity_verification(tmp_path: Path) -> None:
    path = complete_trace().save(
        tmp_path / "valid.sftrace",
        status=RunStatus.COMPLETED,
    )

    result = runner.invoke(app, ["validate", str(path), "--verify-integrity"])

    assert result.exit_code == 0
    assert "Integrity" in result.stdout
    assert "VERIFIED" in result.stdout


def test_validate_with_integrity_mismatch(tmp_path: Path) -> None:
    path = complete_trace().save(
        tmp_path / "tampered.sftrace",
        status=RunStatus.COMPLETED,
    )
    lines = (path / "events.jsonl").read_text().splitlines()
    event = json.loads(lines[1])
    event["input"]["query"] = "Pokhara flights"
    lines[1] = json.dumps(event)
    (path / "events.jsonl").write_text("\n".join(lines) + "\n")

    result = runner.invoke(app, ["validate", str(path), "--verify-integrity"])

    assert result.exit_code == 1
    assert "MISMATCH" in result.stdout
    assert "events.jsonl" in result.stdout


def test_validate_legacy_integrity_returns_unavailable(tmp_path: Path) -> None:
    path = complete_trace().save(
        tmp_path / "valid.sftrace",
        status=RunStatus.COMPLETED,
    )
    legacy = tmp_path / "legacy.sftrace"
    shutil.copytree(path, legacy)
    (legacy / "integrity.json").unlink()

    result = runner.invoke(app, ["validate", str(legacy), "--verify-integrity"])

    assert result.exit_code == 3
    assert "UNVERIFIED" in result.stdout


def test_validate_invalid_trace(tmp_path: Path) -> None:
    trace = complete_trace()
    trace.events[1] = trace.events[1].model_copy(update={"id": trace.events[0].id})
    path = trace.save(tmp_path / "invalid.sftrace", status=RunStatus.COMPLETED)

    result = runner.invoke(app, ["validate", str(path)])

    assert result.exit_code == 1
    assert "duplicate_event_id" in result.stdout
    assert "Validation failed" in result.stdout


def test_validate_partial_trace_with_partial_flag(tmp_path: Path) -> None:
    trace = Trace(agent_name="demo-agent")
    trace.add(ToolCall(name="search", input={"query": "Kathmandu flights"}))
    path = trace.save(tmp_path / "partial.sftrace")

    result = runner.invoke(app, ["validate", str(path), "--partial"])

    assert result.exit_code == 0
    assert "Validation passed" in result.stdout
    assert "partial" in result.stdout


def test_validate_missing_trace_returns_unreadable(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path / "missing.sftrace")])

    assert result.exit_code == 2
    assert "missing_file" in result.stdout


def test_validate_help() -> None:
    result = runner.invoke(app, ["validate", "--help"])

    assert result.exit_code == 0
    assert "--partial" in result.stdout
    assert ".sftrace" in result.stdout
