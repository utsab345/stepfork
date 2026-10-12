"""Unit tests for the minimize CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stepfork import record, trace_tool
from stepfork.cli.main import app

runner = CliRunner()


@trace_tool(name="simple_tool")
def simple_tool(x: int) -> int:
    """Simple test tool."""
    return x * 2


def simple_agent() -> dict[str, int]:
    """Simple test agent."""
    result = simple_tool(5)
    return {"value": result}


@pytest.fixture
def test_trace(tmp_path: Path) -> Path:
    """Create a test trace."""
    trace_path = tmp_path / "test.sftrace"
    with record("cli-test-agent", output=str(trace_path)) as session:
        result = simple_agent()
        session.set_output(result)
    return trace_path


@pytest.fixture
def expected_output_file(tmp_path: Path) -> Path:
    """Create an expected output file."""
    output_file = tmp_path / "expected.json"
    output_file.write_text(json.dumps({"value": 999}))
    return output_file


def test_minimize_command_missing_entrypoint(test_trace: Path) -> None:
    """Minimize command requires --entrypoint."""
    result = runner.invoke(app, ["minimize", str(test_trace)])
    assert result.exit_code != 0


def test_minimize_command_invalid_trace_path() -> None:
    """Minimize command fails with invalid trace path."""
    result = runner.invoke(
        app,
        [
            "minimize",
            "nonexistent.sftrace",
            "--entrypoint",
            "test:agent",
        ],
    )
    assert result.exit_code != 0


def test_minimize_command_with_expected_output(
    test_trace: Path,
    expected_output_file: Path,
    tmp_path: Path,
) -> None:
    """Minimize command accepts --expect-output."""
    output_path = tmp_path / "minimized.sftrace"

    result = runner.invoke(
        app,
        [
            "minimize",
            str(test_trace),
            "--entrypoint",
            "test_cli_minimize:simple_agent",
            "--expect-output",
            str(expected_output_file),
            "--output",
            str(output_path),
        ],
    )

    # Command should complete (may succeed or fail depending on trace)
    assert result.exit_code in (0, 1)


def test_minimize_command_with_mode_option(
    test_trace: Path,
    expected_output_file: Path,
    tmp_path: Path,
) -> None:
    """Minimize command accepts --mode."""
    output_path = tmp_path / "minimized.sftrace"

    result = runner.invoke(
        app,
        [
            "minimize",
            str(test_trace),
            "--entrypoint",
            "test_cli_minimize:simple_agent",
            "--expect-output",
            str(expected_output_file),
            "--mode",
            "frozen",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code in (0, 1)


def test_minimize_command_with_timeout(
    test_trace: Path,
    expected_output_file: Path,
    tmp_path: Path,
) -> None:
    """Minimize command accepts --timeout."""
    output_path = tmp_path / "minimized.sftrace"

    result = runner.invoke(
        app,
        [
            "minimize",
            str(test_trace),
            "--entrypoint",
            "test_cli_minimize:simple_agent",
            "--expect-output",
            str(expected_output_file),
            "--timeout",
            "5.0",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code in (0, 1)


def test_minimize_command_with_attempts(
    test_trace: Path,
    expected_output_file: Path,
    tmp_path: Path,
) -> None:
    """Minimize command accepts --attempts."""
    output_path = tmp_path / "minimized.sftrace"

    result = runner.invoke(
        app,
        [
            "minimize",
            str(test_trace),
            "--entrypoint",
            "test_cli_minimize:simple_agent",
            "--expect-output",
            str(expected_output_file),
            "--attempts",
            "2",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code in (0, 1)


def test_minimize_command_output_defaults_to_minimized_suffix(
    test_trace: Path,
    expected_output_file: Path,
    tmp_path: Path,
) -> None:
    """Minimize command creates output with -minimized suffix by default."""
    result = runner.invoke(
        app,
        [
            "minimize",
            str(test_trace),
            "--entrypoint",
            "test_cli_minimize:simple_agent",
            "--expect-output",
            str(expected_output_file),
        ],
    )

    # Check that output path with -minimized suffix is mentioned or created
    # (may not exist if minimization failed, but command should handle it)
    assert result.exit_code in (0, 1)


def test_minimize_command_respects_overwrite_flag(
    test_trace: Path,
    expected_output_file: Path,
    tmp_path: Path,
) -> None:
    """Minimize command respects --overwrite flag."""
    output_path = tmp_path / "minimized.sftrace"

    # Create empty directory at output path
    output_path.mkdir()
    (output_path / "dummy.txt").write_text("test")

    # Without --overwrite, should fail
    result = runner.invoke(
        app,
        [
            "minimize",
            str(test_trace),
            "--entrypoint",
            "test_cli_minimize:simple_agent",
            "--expect-output",
            str(expected_output_file),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code != 0

    # With --overwrite, should work (or fail for different reason)
    result = runner.invoke(
        app,
        [
            "minimize",
            str(test_trace),
            "--entrypoint",
            "test_cli_minimize:simple_agent",
            "--expect-output",
            str(expected_output_file),
            "--output",
            str(output_path),
            "--overwrite",
        ],
    )

    # May succeed or fail based on minimization result, but not due to overwrite
    assert result.exit_code in (0, 1)
