"""Replay the recorded trace in frozen mode and print fail-fast evidence.

Proves that frozen replay makes no live model call and executes no instrumented
tool body. Works offline with no API key: the recorded responses are used.

Usage::

    uv run python scripts/verify_frozen.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import counters  # noqa: E402
from stepfork import ReplaySession  # noqa: E402

TRACE_PATH = ROOT / "traces" / "incident-triage.sftrace"


def main() -> int:
    counters.reset()
    with ReplaySession.from_trace(TRACE_PATH, mode="frozen") as replay:
        result = agent.run_incident_agent()
        replay.verify_complete()

    print(f"tool_body_executions : {counters.TOOL_BODY_EXECUTIONS['count']}")
    print(f"live_llm_attempts    : {counters.LIVE_LLM_ATTEMPTS['count']}")
    print("executed_calls       :")
    for call in replay.executed_calls:
        print(f"  - {call.kind:3} {call.label:24} {call.action}")
    print(f"matched              : {len(replay.matched)}")
    print(f"max_steps            : {len(replay.executed_calls)}")
    print("--- replay output ---")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
