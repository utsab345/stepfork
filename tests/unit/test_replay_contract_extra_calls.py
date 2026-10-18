"""Contract test for extra calls case matching issue #17."""

from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import record, trace_tool
from stepfork.replay import ReplayMismatchError, ReplaySession


@trace_tool(name="get_advice")
def get_advice(ticket: str) -> str:
    return "advice"


@trace_tool(name="escalate")
def escalate(priority: str) -> dict:
    return {"escalated": True, "priority": priority}


def run_crash() -> dict:
    # Only first call is made before crash
    get_advice("T-1")
    # escalate is never called (bug/crash)
    return {"ok": True}


def run_fixed() -> dict:
    get_advice("T-1")
    escalate("high")  # extra call beyond recorded trace
    return {"ok": True}


def test_extra_calls_cause_divergence(tmp_path: Path) -> None:
    # Record trace from crash version
    trace_path = tmp_path / "crash.sftrace"
    with record("crash-agent", output=trace_path) as session:
        session.set_output(run_crash())

    # Fixed version makes an extra call not in recording
    with (
        pytest.raises(ReplayMismatchError),
        ReplaySession.from_trace(trace_path, mode="frozen"),
    ):
        run_fixed()
