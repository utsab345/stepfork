from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import record, trace_tool
from stepfork.trace import EventStatus, EventType, Trace


@trace_tool
def add(a: int, b: int) -> int:
    return a + b


@trace_tool(name="search")
def search(destination: str) -> dict[str, object]:
    return {"destination": destination, "results": ["one"]}


@trace_tool
def explode() -> None:
    raise ValueError("tool failed")


@trace_tool
async def async_add(a: int, b: int) -> int:
    return a + b


def test_tool_passthrough_outside_recording() -> None:
    assert add(1, 2) == 3
    assert search("Lisbon") == {"destination": "Lisbon", "results": ["one"]}


def test_tool_call_and_result_recorded(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"

    with record("demo-agent", output=destination):
        assert add(2, 3) == 5

    loaded = Trace.load(destination)
    call = next(e for e in loaded.events if e.type is EventType.TOOL_CALL)
    result = next(e for e in loaded.events if e.type is EventType.TOOL_RESULT)
    assert call.name == "add"
    assert call.input == {"a": 2, "b": 3}
    assert result.parent_id == call.id
    assert result.output == 5
    assert result.status is EventStatus.OK


def test_tool_custom_name_and_keyword_binding(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"

    with record("demo-agent", output=destination):
        search(destination="Lisbon")

    loaded = Trace.load(destination)
    call = next(e for e in loaded.events if e.type is EventType.TOOL_CALL)
    assert call.name == "search"
    assert call.input == {"destination": "Lisbon"}


def test_tool_exception_is_preserved_and_recorded(tmp_path: Path) -> None:
    destination = tmp_path / "run.sftrace"

    with (
        pytest.raises(ValueError, match="tool failed"),
        record("demo-agent", output=destination),
    ):
        explode()

    loaded = Trace.load(destination)
    result = next(e for e in loaded.events if e.type is EventType.TOOL_RESULT)
    assert result.status is EventStatus.ERROR
    assert result.output == {"error_type": "ValueError", "message": "tool failed"}
    assert any(e.type is EventType.ERROR for e in loaded.events)


def test_tool_serialization_error_raises(tmp_path: Path) -> None:
    @trace_tool
    def bad(payload: object) -> object:
        return payload

    with (
        record("demo-agent", output=tmp_path / "run.sftrace"),
        pytest.raises(TypeError, match="cannot serialize"),
    ):
        bad(object())


def test_async_tool_records_and_replays(tmp_path: Path) -> None:
    import asyncio

    destination = tmp_path / "run.sftrace"

    async def scenario() -> int:
        with record("demo-agent", output=destination):
            return await async_add(4, 5)

    assert asyncio.run(scenario()) == 9
    loaded = Trace.load(destination)
    result = next(e for e in loaded.events if e.type is EventType.TOOL_RESULT)
    assert result.output == 9


def test_async_tool_passthrough() -> None:
    import asyncio

    assert asyncio.run(async_add(6, 7)) == 13


def test_streaming_tools_are_rejected_explicitly() -> None:
    def stream() -> object:
        yield "chunk"

    async def astream() -> object:
        yield "chunk"

    with pytest.raises(ValueError, match="streaming tool"):
        trace_tool(stream)
    with pytest.raises(ValueError, match="streaming tool"):
        trace_tool(astream)


def test_tool_result_redaction_removes_secret(tmp_path: Path) -> None:
    @trace_tool
    def leak() -> dict[str, str]:
        return {"api_key": "super-secret-value", "safe": "ok"}

    destination = tmp_path / "run.sftrace"
    with record("demo-agent", output=destination):
        leak()

    raw = (destination / "events.jsonl").read_text(encoding="utf-8")
    assert "super-secret-value" not in raw
    assert "[REDACTED]" in raw
