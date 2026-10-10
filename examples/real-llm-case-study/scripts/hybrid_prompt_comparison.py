"""Optional Section 9: hybrid baseline-vs-revised prompt comparison.

Runs the recorded incident twice under Stepfork *hybrid* replay: instrumented
tools stay frozen and strictly matched, while the named LLM boundary runs live.
Makes TWO real model requests. Requires the same live credentials as recording.

This is a qualitative demonstration, not a statistical evaluation. One or two
samples cannot establish that a prompt change improves model quality, and
Stepfork does not itself improve model quality.

Usage::

    CASE_STUDY_ALLOW_LIVE=1 GEMINI_API_KEY=... \
        uv run python scripts/hybrid_prompt_comparison.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import counters  # noqa: E402
from stepfork import ReplaySession  # noqa: E402

TRACE = ROOT / "traces" / "incident-triage.sftrace"
LIVE_LLM_LABEL = f"openai/{agent.MODEL}"


def run_variant(variant: str) -> dict:
    agent._PROMPT_VARIANT = variant  # type: ignore[attr-defined]
    counters.reset()
    with ReplaySession.from_trace(
        TRACE, mode="hybrid", live_llms={LIVE_LLM_LABEL}
    ) as replay:
        result = agent.run_incident_agent()
        replay.verify_complete()
    return {
        "variant": variant,
        "raw_model_severity": agent.LAST_RAW_DECISION.get("severity"),
        "raw_model_escalation_signal": agent.LAST_RAW_DECISION.get("recommended_next_action", "")[:80],
        "final_after_policy": {
            "severity": result["severity"],
            "escalation_required": result["escalation_required"],
        },
        "usage": dict(agent.LAST_LLM_USAGE),
        "tool_bodies_executed": counters.TOOL_BODY_EXECUTIONS["count"],
        "live_llm_attempts": counters.LIVE_LLM_ATTEMPTS["count"],
        "actions": [
            f"{c.kind}:{c.label}:{c.action}" for c in replay.executed_calls
        ],
    }


def main() -> int:
    if os.environ.get("CASE_STUDY_ALLOW_LIVE") != "1":
        print("refusing live calls: set CASE_STUDY_ALLOW_LIVE=1", file=sys.stderr)
        return 2
    results = [run_variant("baseline"), run_variant("revised")]
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
