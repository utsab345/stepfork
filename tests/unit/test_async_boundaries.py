from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from stepfork import ReplaySession, allm_request, llm_request, record, trace_tool
from stepfork.replay import RecordedDependencyError, ReplayMismatchError
from stepfork.trace import ErrorEvent, LLMRequest, ToolCall, Trace

BODY_CALLS: list[str] = []


@trace_tool(name="outer")
async def outer(value: str) -> str:
    BODY_CALLS.append("outer")
    return await inner(value)


@trace_tool(name="inner")
async def inner(value: str) -> str:
    BODY_CALLS.append("inner")
    await asyncio.sleep(0)
    return value


@trace_tool(name="sync")
def sync_tool(value: str) -> str:
    BODY_CALLS.append("sync")
    return value


async def fake_llm(value: str) -> dict[str, str]:
    BODY_CALLS.append("llm")
    await asyncio.sleep(0)
    return {"value": value}


def test_nested_async_and_sync_interoperability(tmp_path: Path) -> None:
    path = tmp_path / "nested.sftrace"
    BODY_CALLS.clear()

    async def scenario() -> None:
        async with record("nested", output=path):
            assert await outer("a") == "a"
            assert sync_tool("b") == "b"
            assert await allm_request(
                model="fake", input={"v": "c"}, call=lambda: fake_llm("c")
            ) == {"value": "c"}
            assert llm_request(model="sync", input={}, call=lambda: {"value": "d"}) == {
                "value": "d"
            }
        assert BODY_CALLS == ["outer", "inner", "sync", "llm"]
        BODY_CALLS.clear()
        async with ReplaySession.from_trace(path) as replay:
            assert await outer("a") == "a"
            assert sync_tool("b") == "b"
            assert await allm_request(
                model="fake", input={"v": "c"}, call=lambda: fake_llm("c")
            ) == {"value": "c"}
            assert llm_request(
                model="sync", input={}, call=lambda: {"value": "live"}
            ) == {"value": "d"}
            replay.verify_complete()
        assert BODY_CALLS == []

    asyncio.run(scenario())
    trace = Trace.load(path)
    calls = [event for event in trace.events if isinstance(event, ToolCall)]
    assert calls[1].parent_id == calls[0].id


def test_concurrent_async_tasks_keep_parent_scopes(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.sftrace"
    BODY_CALLS.clear()

    async def task(value: str) -> None:
        await outer(value)
        await allm_request(
            model="fake", input={"v": value}, call=lambda: fake_llm(value)
        )

    async def scenario() -> None:
        async with record("concurrent", output=path):
            await asyncio.gather(task("a"), task("b"))

    asyncio.run(scenario())
    trace = Trace.load(path)
    calls = [event for event in trace.events if isinstance(event, ToolCall)]
    outers: dict[str, ToolCall] = {}
    for event in calls:
        if event.name == "outer":
            assert isinstance(event.input, dict)
            value = event.input["value"]
            assert isinstance(value, str)
            outers[value] = event
    inners = [event for event in calls if event.name == "inner"]
    assert len(outers) == len(inners) == 2
    for event in inners:
        assert isinstance(event.input, dict)
        value = event.input["value"]
        assert isinstance(value, str)
        assert event.parent_id == outers[value].id
    requests = [event for event in trace.events if isinstance(event, LLMRequest)]
    root_id = trace.events[0].id
    assert len(requests) == 2
    assert all(request.parent_id == root_id for request in requests)


def test_concurrent_replay_keeps_strict_invocation_order(tmp_path: Path) -> None:
    path = tmp_path / "ordered.sftrace"

    async def scenario() -> None:
        async with record("ordered", output=path):
            await asyncio.gather(inner("a"), inner("b"))
        async with ReplaySession.from_trace(path) as replay:
            await asyncio.gather(inner("a"), inner("b"))
            replay.verify_complete()
        async with ReplaySession.from_trace(path):
            with pytest.raises(ReplayMismatchError):
                await asyncio.gather(inner("b"), inner("a"))

    asyncio.run(scenario())


def test_async_llm_failure_and_replay_divergence(tmp_path: Path) -> None:
    path = tmp_path / "failure.sftrace"

    async def failed() -> None:
        raise ValueError("provider failed")

    async def scenario() -> None:
        with pytest.raises(ValueError), record("failure", output=path):
            await allm_request(model="fake", input={"v": 1}, call=failed)
        async with ReplaySession.from_trace(path) as replay:
            with pytest.raises(RecordedDependencyError):
                await allm_request(model="fake", input={"v": 1}, call=failed)
            replay.verify_complete()
        async with ReplaySession.from_trace(path):
            with pytest.raises(ReplayMismatchError):
                await allm_request(model="fake", input={"v": 2}, call=failed)

    asyncio.run(scenario())
    trace = Trace.load(path)
    assert any(isinstance(event, ErrorEvent) for event in trace.events)


def test_async_tool_failure_does_not_run_body_during_replay(tmp_path: Path) -> None:
    path = tmp_path / "tool_failure.sftrace"
    calls: list[str] = []

    @trace_tool(name="failed_async_tool")
    async def failed_tool() -> None:
        calls.append("called")
        raise ValueError("tool failed")

    async def scenario() -> None:
        with pytest.raises(ValueError), record("failure", output=path):
            await failed_tool()
        calls.clear()
        async with ReplaySession.from_trace(path) as replay:
            with pytest.raises(RecordedDependencyError):
                await failed_tool()
            replay.verify_complete()
        assert calls == []

    asyncio.run(scenario())
