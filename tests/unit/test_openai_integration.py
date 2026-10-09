from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from stepfork import ReplaySession, Trace, record
from stepfork.integrations.openai import (
    CHAT_COMPLETIONS_METHOD,
    OpenAIIntegrationError,
    chat_completions_create,
)
from stepfork.replay import ReplayExhaustedError, ReplayMismatchError
from stepfork.trace import EventType, RunEnd, RunStart, RunStatus


class FakeChatCompletion:
    def __init__(self, *, content: str, model: str = "gpt-test") -> None:
        self.content = content
        self.model = model

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        assert mode == "json"
        return {
            "id": "chatcmpl_test",
            "object": "chat.completion",
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": self.content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "total_tokens": 10,
            },
        }


class FakeCompletions:
    def __init__(self, calls: list[dict[str, Any]], *, content: str) -> None:
        self._calls = calls
        self._content = content

    def create(self, **request: Any) -> FakeChatCompletion:
        self._calls.append(dict(request))
        return FakeChatCompletion(
            content=self._content,
            model=str(request.get("model", "gpt-test")),
        )


class FakeChat:
    def __init__(self, calls: list[dict[str, Any]], *, content: str) -> None:
        self.completions = FakeCompletions(calls, content=content)


class FakeOpenAI:
    def __init__(self, *, content: str = "approved") -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = FakeChat(self.calls, content=content)


def _request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "Approve this refund?"}],
        "temperature": 0,
    }
    request.update(overrides)
    return request


def _call(client: FakeOpenAI, **overrides: Any) -> dict[str, Any]:
    return chat_completions_create(client, **_request(**overrides))


def test_openai_chat_completion_records_request_and_response(tmp_path: Path) -> None:
    trace_path = tmp_path / "openai.sftrace"
    client = FakeOpenAI(content="approved")

    with record("openai-agent", output=trace_path):
        result = _call(client)

    assert result["choices"][0]["message"]["content"] == "approved"
    assert len(client.calls) == 1

    trace = Trace.load(trace_path)
    request = next(
        event for event in trace.events if event.type is EventType.LLM_REQUEST
    )
    response = next(
        event for event in trace.events if event.type is EventType.LLM_RESPONSE
    )
    assert request.provider == "openai"
    assert request.model == "gpt-test"
    assert request.input == {"method": CHAT_COMPLETIONS_METHOD, "request": _request()}
    output = cast(dict[str, Any], response.output)
    assert output["choices"][0]["message"]["content"] == "approved"


def test_frozen_replay_returns_recorded_response_without_sdk_call(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "openai.sftrace"
    recording_client = FakeOpenAI(content="approved")
    with record("openai-agent", output=trace_path):
        _call(recording_client)

    replay_client = FakeOpenAI(content="live response should not be used")
    with ReplaySession.from_trace(trace_path, mode="frozen") as replay:
        result = _call(replay_client)
        replay.verify_complete()

    assert result["choices"][0]["message"]["content"] == "approved"
    assert replay_client.calls == []


def test_frozen_replay_detects_changed_request_parameter(tmp_path: Path) -> None:
    trace_path = tmp_path / "openai.sftrace"
    client = FakeOpenAI()
    with record("openai-agent", output=trace_path):
        _call(client, temperature=0)

    with (
        ReplaySession.from_trace(trace_path, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="input diverged"),
    ):
        _call(FakeOpenAI(), temperature=1)


def test_frozen_replay_detects_changed_model(tmp_path: Path) -> None:
    trace_path = tmp_path / "openai.sftrace"
    client = FakeOpenAI()
    with record("openai-agent", output=trace_path):
        _call(client, model="gpt-test")

    with (
        ReplaySession.from_trace(trace_path, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="expected LLM model"),
    ):
        _call(FakeOpenAI(), model="gpt-other")


def test_missing_recording_fails_clearly() -> None:
    trace = Trace(agent_name="empty")
    trace.add(RunStart())
    trace.add(RunEnd(run_status=RunStatus.COMPLETED))

    with (
        ReplaySession.from_trace(trace, mode="frozen"),
        pytest.raises(ReplayExhaustedError, match="unexpected llm call"),
    ):
        _call(FakeOpenAI())


def test_streaming_requests_are_rejected_before_sdk_call() -> None:
    client = FakeOpenAI()

    with pytest.raises(OpenAIIntegrationError, match="streaming"):
        _call(client, stream=True)

    assert client.calls == []


def test_non_json_request_parameters_are_rejected_before_sdk_call() -> None:
    client = FakeOpenAI()

    with pytest.raises(OpenAIIntegrationError, match="JSON-compatible"):
        _call(client, metadata={"not_json": object()})

    assert client.calls == []


def test_model_is_required() -> None:
    with pytest.raises(OpenAIIntegrationError, match="model"):
        chat_completions_create(
            FakeOpenAI(),
            messages=[{"role": "user", "content": "hello"}],
        )
