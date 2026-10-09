from __future__ import annotations

import sys
from pathlib import Path

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
