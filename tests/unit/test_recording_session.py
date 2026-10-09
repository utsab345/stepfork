from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from stepfork import (
    RecordingSession,
    Trace,
    record,
    trace_tool,
)
from stepfork.recorder.session import active_recorder
from stepfork.trace import EventBase, EventType, RunEnd, RunStatus, ToolCall
from stepfork.trace.jsonable import TraceSerializationError


def test_record_successful_run_totals_and_status(tmp_path: Path) -> None:
    destination = tmp_path / "success.sftrace"

    with record("demo-agent", output=destination) as session:
        session.record_tool_call(name="search", input={"q": "x"})
        session.set_output({"answer": 42})
        run_id = session.run_id

    assert destination.is_dir()
    loaded = Trace.load(destination)
    assert loaded.agent_name == "demo-agent"
    assert loaded.run_id == run_id
    assert loaded.status is RunStatus.COMPLETED
    assert loaded.failure is None
    assert [event.type for event in loaded.events] == [
        EventType.RUN_START,
        EventType.TOOL_CALL,
        EventType.RUN_END,
    ]
    assert cast(RunEnd, loaded.events[-1]).output == {"answer": 42}
    assert loaded.totals.events == 3
    assert loaded.totals.tool_calls == 1


def test_record_failed_run_preserves_exception(tmp_path: Path) -> None:
    destination = tmp_path / "failure.sftrace"

    with (
        pytest.raises(ValueError, match="boom"),
        record("demo-agent", output=destination),
    ):
        raise ValueError("boom")

    loaded = Trace.load(destination)
    assert loaded.status is RunStatus.FAILED
    assert loaded.failure is not None
    assert loaded.failure.type == "ValueError"
    assert loaded.failure.message == "boom"
    assert loaded.events[-1].type is EventType.RUN_END
    assert any(event.type is EventType.ERROR for event in loaded.events)
    assert loaded.events[-1].run_status is RunStatus.FAILED


def test_record_save_failure_does_not_mask_application_error(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing.sftrace"
    existing.mkdir()
    (existing / "keep.txt").write_text("data", encoding="utf-8")

    with (
        pytest.raises(RuntimeError, match="original"),
        record("demo-agent", output=existing),
    ):
        raise RuntimeError("original")


def test_active_recorder_is_scoped(tmp_path: Path) -> None:
    assert active_recorder() is None
    with record("demo-agent", output=tmp_path / "run.sftrace") as session:
        assert active_recorder() is session
    assert active_recorder() is None


def test_recording_session_cannot_be_reentered(tmp_path: Path) -> None:
    session = record("demo-agent", output=tmp_path / "run.sftrace")
    with session:
        pass
    with pytest.raises(RuntimeError, match="re-entered"), session:
        pass


def test_nested_tool_calls_build_parent_chain(tmp_path: Path) -> None:
    destination = tmp_path / "nested.sftrace"

    with record("demo-agent", output=destination) as session:
        outer = session.record_tool_call(name="outer", input={})
        session.push_scope(outer.id)
        inner = session.record_tool_call(name="inner", input={})
        session.push_scope(inner.id)
        session.record_tool_result(inner, {"ok": True})
        session.pop_scope()
        session.record_tool_result(outer, {"ok": True})
        session.pop_scope()

    loaded = Trace.load(destination)
    outer_call = _event(loaded, "tool_call", "outer")
    inner_call = _event(loaded, "tool_call", "inner")
    inner_result = _event(loaded, "tool_result", "inner")
    assert inner_call.parent_id == outer_call.id
    assert inner_result.parent_id == inner_call.id


def test_multiple_tool_calls_are_sequential(tmp_path: Path) -> None:
    destination = tmp_path / "multi.sftrace"

    with record("demo-agent", output=destination) as session:
        for name in ("a", "b", "c"):
            call = session.record_tool_call(name=name, input={"name": name})
            session.record_tool_result(call, {"name": name})

    loaded = Trace.load(destination)
    steps = [event.step for event in loaded.events]
    assert steps == list(range(len(steps)))
    assert [
        event.name for event in loaded.events if event.type is EventType.TOOL_CALL
    ] == [
        "a",
        "b",
        "c",
    ]


def test_serialization_error_is_actionable(tmp_path: Path) -> None:
    with (
        record("demo-agent", output=tmp_path / "run.sftrace") as session,
        pytest.raises(TraceSerializationError, match="cannot serialize"),
    ):
        session.record_tool_call(name="bad", input={"obj": object()})


def test_serializer_hook_is_used(tmp_path: Path) -> None:
    class Point:
        def __init__(self, x: int, y: int) -> None:
            self.x = x
            self.y = y

    def serialize(value: object) -> object:
        if isinstance(value, Point):
            return {"x": value.x, "y": value.y}
        raise TypeError(type(value).__name__)

    with record(
        "demo-agent",
        output=tmp_path / "run.sftrace",
        serializer=serialize,
    ) as session:
        call = session.record_tool_call(name="point", input={"p": Point(1, 2)})
        session.record_tool_result(call, {"ok": True})

    loaded = Trace.load(tmp_path / "run.sftrace")
    assert cast(ToolCall, loaded.events[1]).input == {"p": {"x": 1, "y": 2}}


def test_default_output_path_under_stepfork_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with record("my agent!") as session:
        pass
    assert session.path is not None
    assert session.path.parent == Path(".stepfork") / "traces"
    assert session.path.name.startswith("my-agent-")


def test_llm_call_context_manager_records_request_and_response(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "llm.sftrace"

    with (
        record("demo-agent", output=destination) as session,
        session.llm_call(
            provider="fake",
            model="demo",
            input={"messages": [{"role": "user", "content": "hi"}]},
        ) as call,
    ):
        call.set_output({"content": "hello"}, total_tokens=5)

    loaded = Trace.load(destination)
    request = next(e for e in loaded.events if e.type is EventType.LLM_REQUEST)
    response = next(e for e in loaded.events if e.type is EventType.LLM_RESPONSE)
    assert response.parent_id == request.id
    assert response.output == {"content": "hello"}
    assert response.total_tokens == 5


def test_llm_call_failure_records_error(tmp_path: Path) -> None:
    destination = tmp_path / "llm_fail.sftrace"

    with (
        pytest.raises(RuntimeError, match="provider down"),
        record("demo-agent", output=destination) as session,
        session.llm_call(model="demo", input={}),
    ):
        raise RuntimeError("provider down")

    loaded = Trace.load(destination)
    assert loaded.status is RunStatus.FAILED
    assert any(event.type is EventType.ERROR for event in loaded.events)


def test_recording_inside_replay_is_inert(tmp_path: Path) -> None:
    from stepfork import ReplaySession

    source = tmp_path / "source.sftrace"
    with record("demo-agent", output=source) as session:
        call = session.record_tool_call(name="tool", input={})
        session.record_tool_result(call, {"ok": True})

    inert_target = tmp_path / "inert.sftrace"
    with (
        ReplaySession.from_trace(source, mode="frozen"),
        record("demo-agent", output=inert_target) as inner,
    ):
        inner.record_tool_call(name="tool", input={})

    assert not inert_target.exists()
    assert inner.path is None


def _event(trace: Trace, event_type: str, name: str) -> EventBase:
    matches = [
        event
        for event in trace.events
        if event.type.value == event_type and getattr(event, "name", None) == name
    ]
    assert len(matches) == 1, matches
    return matches[0]


def test_recording_session_type_exposed() -> None:
    assert RecordingSession is not None
    assert callable(trace_tool)
