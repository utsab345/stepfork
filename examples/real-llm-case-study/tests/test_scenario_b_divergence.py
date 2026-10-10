"""Scenario B: strict replay detects trajectory divergence."""

from __future__ import annotations

from pathlib import Path

import counters
import pytest
import scenario_b
from stepfork import ReplaySession
from stepfork.replay import ReplayMismatchError

ROOT = Path(__file__).resolve().parent.parent
TRACE = ROOT / "traces" / "incident-triage.sftrace"


def test_reordered_calls_are_detected() -> None:
    counters.reset()
    with pytest.raises(ReplayMismatchError):
        with ReplaySession.from_trace(TRACE, mode="frozen") as replay:
            scenario_b.run_incident_agent_divergent()
            replay.verify_complete()
    assert counters.TOOL_BODY_EXECUTIONS["count"] == 0


def test_changed_tool_argument_is_detected() -> None:
    counters.reset()
    with pytest.raises(ReplayMismatchError):
        with ReplaySession.from_trace(TRACE, mode="frozen") as replay:
            scenario_b.run_incident_agent_divergent_argument()
            replay.verify_complete()
    assert counters.TOOL_BODY_EXECUTIONS["count"] == 0
