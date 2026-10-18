"""Contract test for changed arguments case matching issue #17."""

from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import record, trace_tool
from stepfork.replay import ReplayMismatchError, ReplaySession


@trace_tool(name="issue_refund")
def issue_refund(customer_id: str, amount_cents: int) -> dict:
    return {"customer_id": customer_id, "refunded_cents": amount_cents}


def run_buggy() -> dict:
    issue_refund("c-1", 49)  # records 49
    return {"refunded": 49}


def run_fixed() -> dict:
    issue_refund("c-1", 4999)  # changes to 4999
    return {"refunded": 4999}


def test_changed_args_causes_divergence(tmp_path: Path) -> None:
    # Record from buggy version
    trace_path = tmp_path / "failure.sftrace"
    with record("triage-agent", output=trace_path) as session:
        session.set_output(run_buggy())

    # Replay against fixed version - arguments changed
    with (
        pytest.raises(ReplayMismatchError, match="input diverged"),
        ReplaySession.from_trace(trace_path, mode="frozen"),
    ):
        run_fixed()
