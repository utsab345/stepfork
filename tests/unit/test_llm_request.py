from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import ReplaySession, llm_request, record
from stepfork.replay import ReplayMismatchError
from stepfork.trace import EventType, Trace


def _record_llm(destination: Path, *, model: str = "demo") -> None:
    with record("demo-agent", output=destination):
        llm_request(
            provider="fake",
            model=model,
            input={"messages": [{"role": "user", "content": "hi"}]},
            call=lambda: {"content": "hello"},
        )


def _recording_call(calls: list[str], value: str) -> dict[str, str]:
    calls.append(value)
    return {"content": value}


def test_llm_request_outside_context_calls_dependency() -> None:
    calls: list[str] = []

    result = llm_request(
        model="demo",
        input={},
        call=lambda: _recording_call(calls, "called"),
    )

    assert result == {"content": "called"}
    assert calls == ["called"]


def test_llm_request_records_request_and_response(tmp_path: Path) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    loaded = Trace.load(destination)
    request = next(e for e in loaded.events if e.type is EventType.LLM_REQUEST)
    response = next(e for e in loaded.events if e.type is EventType.LLM_RESPONSE)
    assert request.provider == "fake"
    assert request.model == "demo"
    assert response.parent_id == request.id
    assert response.output == {"content": "hello"}


def test_frozen_replay_substitutes_without_calling(tmp_path: Path) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    calls: list[str] = []
    with ReplaySession.from_trace(destination, mode="frozen") as replay:
        result = llm_request(
            provider="fake",
            model="demo",
            input={"messages": [{"role": "user", "content": "hi"}]},
            call=lambda: _recording_call(calls, "live"),
        )
        replay.verify_complete()

    assert result == {"content": "hello"}
    assert calls == []


def test_frozen_replay_detects_input_mismatch(tmp_path: Path) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="input fingerprint"),
    ):
        llm_request(
            provider="fake",
            model="demo",
            input={"messages": [{"role": "user", "content": "different"}]},
            call=lambda: {"content": "live"},
        )


def test_frozen_replay_detects_model_mismatch(tmp_path: Path) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="expected LLM model"),
    ):
        llm_request(
            provider="fake",
            model="other-model",
            input={"messages": [{"role": "user", "content": "hi"}]},
            call=lambda: {"content": "live"},
        )


def test_frozen_replay_detects_prompt_change(tmp_path: Path) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="input fingerprint"),
    ):
        llm_request(
            provider="fake",
            model="demo",
            input={"messages": [{"role": "user", "content": "changed prompt"}]},
            call=lambda: {"content": "live"},
        )


def test_frozen_replay_detects_provider_mismatch(tmp_path: Path) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    with (
        ReplaySession.from_trace(destination, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="expected provider"),
    ):
        llm_request(
            provider=None,
            model="demo",
            input={"messages": [{"role": "user", "content": "hi"}]},
            call=lambda: {"content": "live"},
        )


def test_frozen_replay_detects_added_provider_on_legacy_request(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination, model="demo")
    trace = Trace.load(destination)
    for index, event in enumerate(trace.events):
        if event.type is EventType.LLM_REQUEST:
            trace.events[index] = event.model_copy(update={"provider": None})
            break

    with (
        ReplaySession.from_trace(trace, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="expected provider None"),
    ):
        llm_request(
            provider="fake",
            model="demo",
            input={"messages": [{"role": "user", "content": "hi"}]},
            call=lambda: {"content": "live"},
        )


def test_live_replay_executes_dependency(tmp_path: Path) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    calls: list[str] = []
    with ReplaySession.from_trace(destination, mode="live") as replay:
        result = llm_request(
            provider="fake",
            model="demo",
            input={"messages": [{"role": "user", "content": "hi"}]},
            call=lambda: _recording_call(calls, "live"),
        )
        replay.verify_complete()

    assert result == {"content": "live"}
    assert calls == ["live"]


def test_replay_exhausted_after_all_calls(tmp_path: Path) -> None:
    from stepfork.replay import ReplayExhaustedError

    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    with ReplaySession.from_trace(destination, mode="frozen"):
        llm_request(
            provider="fake",
            model="demo",
            input={"messages": [{"role": "user", "content": "hi"}]},
            call=lambda: {"content": "x"},
        )
        with pytest.raises(ReplayExhaustedError, match="already consumed"):
            llm_request(
                provider="fake",
                model="demo",
                input={"messages": [{"role": "user", "content": "hi"}]},
                call=lambda: {"content": "x"},
            )


def test_verify_complete_reports_unconsumed(tmp_path: Path) -> None:
    destination = tmp_path / "llm.sftrace"
    _record_llm(destination)

    with (
        ReplaySession.from_trace(destination, mode="frozen") as replay,
        pytest.raises(ReplayMismatchError, match="before consuming"),
    ):
        replay.verify_complete()
