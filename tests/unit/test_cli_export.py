from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stepfork import record
from stepfork.cli.main import app

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_FILE = REPO_ROOT / "examples" / "booking_agent" / "expected.json"
FIXED_ENTRYPOINT = "examples.booking_agent:run_agent_fixed"


def _record_booking(destination: Path) -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from examples.booking_agent import agent

    with record("booking-agent", output=destination) as session:
        session.set_output(agent.run_agent())


def test_export_cli_requires_entrypoint(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)

    result = runner.invoke(app, ["export", str(trace), "--pytest"])

    assert result.exit_code == 2
    assert "--entrypoint" in result.stdout


def test_export_cli_rejects_non_pytest(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)

    result = runner.invoke(
        app,
        ["export", str(trace), "--no-pytest", "--entrypoint", FIXED_ENTRYPOINT],
    )

    assert result.exit_code == 2


def test_export_cli_rejects_invalid_mode(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--mode",
            "banana",
        ],
    )

    assert result.exit_code == 2


def test_export_cli_writes_test(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)
    output = tmp_path / "test_regression.py"

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--pytest",
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--expect-output",
            str(EXPECTED_FILE),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert output.is_file()
    assert "run_regression_case" in output.read_text(encoding="utf-8")


def test_export_cli_protects_existing_output(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)
    output = tmp_path / "test_regression.py"
    output.write_text("# keep\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--pytest",
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--expect-output",
            str(EXPECTED_FILE),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert output.read_text(encoding="utf-8") == "# keep\n"


def test_export_cli_invalid_entrypoint(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--pytest",
            "--entrypoint",
            "examples.booking_agent:nope",
            "--output",
            str(tmp_path / "out.py"),
        ],
    )

    assert result.exit_code == 2


def test_export_cli_rejects_invalid_trace(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sftrace"
    bad.mkdir()
    (bad / "manifest.json").write_text("not json", encoding="utf-8")
    (bad / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (bad / "redactions.json").write_text(
        '{"schema_version": "0.1", "entries": []}',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["export", str(bad), "--entrypoint", FIXED_ENTRYPOINT],
    )

    assert result.exit_code == 2
    assert "validation" in result.stdout.lower()


def test_export_cli_rejects_directory_output(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)
    output = tmp_path / "outdir"
    output.mkdir()

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--output",
            str(output),
            "--overwrite",
        ],
    )

    assert result.exit_code == 1
    assert "Export failed" in result.stdout


def test_export_cli_warns_without_expect_output(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)
    output = tmp_path / "out.py"

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert "warning" in result.stdout.lower()
    assert "Expectation: {" in result.stdout


def test_export_cli_reports_no_expectation_for_failed_run(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "failed.sftrace"
    with (
        pytest.raises(ValueError, match="boom"),
        record("failing-agent", output=trace),
    ):
        raise ValueError("boom")

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--output",
            str(tmp_path / "out.py"),
        ],
    )

    assert result.exit_code == 0
    assert "Expectation: none" in result.stdout


def test_export_cli_missing_expect_output_file(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--expect-output",
            str(tmp_path / "nope.json"),
            "--output",
            str(tmp_path / "out.py"),
        ],
    )

    assert result.exit_code == 2
    assert "Cannot read --expect-output" in result.stdout


def test_export_cli_invalid_expect_output_json(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{nope", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "export",
            str(trace),
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--expect-output",
            str(invalid),
            "--output",
            str(tmp_path / "out.py"),
        ],
    )

    assert result.exit_code == 2
    assert "not valid JSON" in result.stdout
