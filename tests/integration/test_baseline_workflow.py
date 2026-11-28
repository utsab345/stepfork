from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from stepfork.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_FIXTURE = REPO_ROOT / "examples/quickstart/baseline.sftrace"


def test_offline_quickstart_baseline_ci_flow(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    candidate = tmp_path / "candidate.sftrace"
    runner = CliRunner()

    save = runner.invoke(
        app,
        [
            "baseline",
            "save",
            "quickstart-order",
            str(BASELINE_FIXTURE),
            "--directory",
            str(store),
        ],
    )
    assert save.exit_code == 0, save.stdout

    record = subprocess.run(
        [
            sys.executable,
            "-m",
            "examples.quickstart.record_candidate",
            "--output",
            str(candidate),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert record.returncode == 0, record.stdout + record.stderr

    compare = runner.invoke(
        app,
        [
            "baseline",
            "compare",
            "quickstart-order",
            str(candidate),
            "--directory",
            str(store),
        ],
    )

    assert compare.exit_code == 0, compare.stdout
    assert "BASELINE MATCH" in compare.stdout
