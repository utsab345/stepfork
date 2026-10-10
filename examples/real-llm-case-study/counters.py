"""Observable counters used as fail-fast evidence for frozen replay.

`TOOL_BODY_EXECUTIONS` is incremented inside the *bodies* of instrumented
tools; frozen replay substitutes results without running those bodies, so it
must stay at zero. `LIVE_LLM_ATTEMPTS` is incremented by the tripwire client
that is returned whenever a replay session is active; a frozen replay must
never construct or call a live model client.
"""

from __future__ import annotations

TOOL_BODY_EXECUTIONS: dict[str, int] = {"count": 0}
LIVE_LLM_ATTEMPTS: dict[str, int] = {"count": 0}


def reset() -> None:
    """Reset both counters."""
    TOOL_BODY_EXECUTIONS["count"] = 0
    LIVE_LLM_ATTEMPTS["count"] = 0
