from __future__ import annotations

from pathlib import Path

from stepfork import ToolCall, Trace
from stepfork.trace import RunEnd, RunStart, RunStatus, ToolResult, validate_trace


def test_complete_trace_save_load_validate_roundtrip(tmp_path: Path) -> None:
    trace = Trace(agent_name="demo-agent")
    start = trace.add(RunStart(input={"prompt": "book the cheapest flight"}))
    call = trace.add(
        ToolCall(
            name="search",
            input={"query": "Kathmandu flights", "filters": {"max_stops": 1}},
            parent_id=start.id,
        )
    )
    result = trace.add(
        ToolResult(
            name="search",
            output={"results": [{"price": 500, "currency": "USD"}]},
            parent_id=call.id,
        )
    )
    end = trace.add(
        RunEnd(
            run_status=RunStatus.COMPLETED,
            output={"selected": 0},
            parent_id=result.id,
        )
    )

    path = trace.save(tmp_path / "booking.sftrace", status=RunStatus.COMPLETED)
    loaded = Trace.load(path)

    assert validate_trace(loaded).valid
    assert loaded.run_id == trace.run_id
    assert loaded.agent_name == "demo-agent"
    assert loaded.status is RunStatus.COMPLETED
    assert [event.id for event in loaded.events] == [
        start.id,
        call.id,
        result.id,
        end.id,
    ]
    assert [event.type for event in loaded.events] == [
        start.type,
        call.type,
        result.type,
        end.type,
    ]
    assert loaded.events[1].parent_id == start.id
    assert loaded.events[2].parent_id == call.id
    assert loaded.events[3].parent_id == result.id
    assert loaded.events[1].model_dump(mode="json")["input"] == {
        "query": "Kathmandu flights",
        "filters": {"max_stops": 1},
    }
