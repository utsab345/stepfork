"""Record the buggy incident-triage run into a Stepfork trace bundle.

This makes ONE real model request. It refuses to run unless the operator
explicitly opts in with ``CASE_STUDY_ALLOW_LIVE=1`` so it can never spend money
by accident.

Usage::

    CASE_STUDY_ALLOW_LIVE=1 CASE_STUDY_LLM_PROVIDER=vertex \
        uv run python scripts/record_incident.py

The provider and credentials are read from the environment by ``provider.py``.
No credential values are printed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
from stepfork import record  # noqa: E402

TRACE_PATH = ROOT / "traces" / "incident-triage.sftrace"


def main() -> int:
    if os.environ.get("CASE_STUDY_ALLOW_LIVE") != "1":
        print(
            "refusing to make a live model call: set CASE_STUDY_ALLOW_LIVE=1 "
            "to opt in (this spends money)",
            file=sys.stderr,
        )
        return 2

    provider = os.environ.get("CASE_STUDY_LLM_PROVIDER", "gemini")
    print(f"provider={provider} model={agent.MODEL}")
    print(f"writing trace to {TRACE_PATH}")

    with record(
        "incident-triage-agent",
        output=TRACE_PATH,
        overwrite=True,
        run_input={"incident_id": agent.INCIDENT["incident_id"]},
    ) as session:
        result = agent.run_incident_agent()
        session.set_output(result)

    print("--- agent output ---")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("--- llm usage ---")
    print(json.dumps(agent.LAST_LLM_USAGE, indent=2, sort_keys=True))
    print(f"--- trace written: {session.path} ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
