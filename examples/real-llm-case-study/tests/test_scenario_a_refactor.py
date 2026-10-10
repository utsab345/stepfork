"""Scenario A: a harmless refactor preserves the frozen regression."""

from __future__ import annotations

import json
from pathlib import Path

from stepfork.export.runtime import run_regression_case

ROOT = Path(__file__).resolve().parent.parent
TRACE = ROOT / "traces" / "incident-triage.sftrace"
EXPECTATION = json.loads((ROOT / "expected.json").read_text(encoding="utf-8"))


def test_refactor_preserving_trajectory_passes() -> None:
    run_regression_case(
        trace_path=TRACE,
        import_root=ROOT,
        entrypoint="scenario_a:run_incident_agent_refactored",
        expectation=EXPECTATION,
        has_expectation=True,
        mode="frozen",
    )
