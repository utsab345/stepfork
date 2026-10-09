"""Deterministically rebuild the diff/regression golden fixtures.

Run from the repository root::

    uv run python tests/golden/build_fixtures.py

The fixtures are synthetic, contain no real data or credentials, and use fixed
run IDs, event IDs, and timestamps so regeneration is reproducible. The files
are committed; run this only when the fixture contract changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from stepfork.trace import (
    RunEnd,
    RunStart,
    RunStatus,
    ToolCall,
    ToolResult,
    Trace,
    save_trace,
)

GOLDEN_ROOT = Path(__file__).resolve().parent
CREATED_AT = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)


def _build(selected: str, price: int) -> Trace:
    trace = Trace(
        run_id="run_diff_baseline" if price == 320 else "run_diff_changed",
        agent_name="golden-diff-agent",
        created_at=CREATED_AT,
    )
    start = trace.add(RunStart(input={"destination": "Lisbon"}))
    call = trace.add(
        ToolCall(
            name="flight_search", input={"destination": "Lisbon"}, parent_id=start.id
        )
    )
    result = trace.add(
        ToolResult(
            name="flight_search",
            output={"selected_flight": selected, "price": price},
            parent_id=call.id,
        )
    )
    trace.add(
        RunEnd(
            run_status=RunStatus.COMPLETED,
            output={"selected_flight": selected},
            parent_id=result.id,
        )
    )
    return trace


def main() -> None:
    fixtures = {
        "diff_baseline.sftrace": _build("B", 320),
        "diff_changed.sftrace": _build("A", 450),
    }
    for name, trace in fixtures.items():
        destination = GOLDEN_ROOT / name
        save_trace(trace, destination, overwrite=True)
        print(f"wrote {destination}")


if __name__ == "__main__":
    main()
