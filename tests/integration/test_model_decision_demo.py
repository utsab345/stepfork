from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_offline_model_decision_demo() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "examples/model_decision/demo.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Frozen replay rejected the changed prompt" in result.stdout
    assert "Exported buggy pytest test: FAIL" in result.stdout
    assert "Exported fixed pytest test: PASS" in result.stdout
