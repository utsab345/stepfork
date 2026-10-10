"""Fail-fast evidence that frozen replay makes no live calls.

Runs offline: no API key is required and no network call is made.
"""

from __future__ import annotations

from pathlib import Path

import agent
import counters
from stepfork import ReplaySession

ROOT = Path(__file__).resolve().parent.parent
TRACE = ROOT / "traces" / "incident-triage.sftrace"


def _replay():
    counters.reset()
    with ReplaySession.from_trace(TRACE, mode="frozen") as replay:
        result = agent.run_incident_agent()
        replay.verify_complete()
    return replay, result


def test_no_live_llm_attempt_and_no_tool_body_execution() -> None:
    replay, _ = _replay()
    assert counters.LIVE_LLM_ATTEMPTS["count"] == 0
    assert counters.TOOL_BODY_EXECUTIONS["count"] == 0


def test_every_dependency_call_is_substituted() -> None:
    replay, _ = _replay()
    kinds = {call.kind for call in replay.executed_calls}
    assert kinds == {"tool", "llm"}
    assert all(call.action == "substituted" for call in replay.executed_calls)


def test_fixed_entrypoint_reproduces_p0() -> None:
    _, result = _replay()
    assert result["severity"] == "P0"
    assert result["escalation_required"] is True
