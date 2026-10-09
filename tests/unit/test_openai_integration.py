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
from stepfork.replay import (
    RecordedDependencyError,
    ReplayExhaustedError,
    ReplayMismatchError,
)
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


class NonJsonCompletion:
    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        assert mode == "json"
        return {"choices": [{"message": {"content": object()}}]}


class ToDictCompletion:
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": "chatcmpl_dict",
            "object": "chat.completion",
            "model": "gpt-test",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "dict response"},
                }
            ],
        }


class FakeCompletions:
    def __init__(
        self,
        calls: list[dict[str, Any]],
        *,
        content: str,
        response: Any | None = None,
        exc: BaseException | None = None,
    ) -> None:
        self._calls = calls
        self._content = content
        self._response = response
        self._exc = exc

    def create(self, **request: Any) -> Any:
        self._calls.append(dict(request))
        if self._exc is not None:
            raise self._exc
        if self._response is not None:
            return self._response
        return FakeChatCompletion(
            content=self._content,
            model=str(request.get("model", "gpt-test")),
        )


class FakeChat:
    def __init__(
        self,
        calls: list[dict[str, Any]],
        *,
        content: str,
        response: Any | None = None,
        exc: BaseException | None = None,
    ) -> None:
        self.completions = FakeCompletions(
            calls,
            content=content,
            response=response,
            exc=exc,
        )


class FakeOpenAI:
    def __init__(
        self,
        *,
        content: str = "approved",
        response: Any | None = None,
        exc: BaseException | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = FakeChat(
            self.calls,
            content=content,
            response=response,
            exc=exc,
        )


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


def test_frozen_replay_detects_changed_prompt(tmp_path: Path) -> None:
    trace_path = tmp_path / "openai.sftrace"
    client = FakeOpenAI()
    with record("openai-agent", output=trace_path):
        _call(client, messages=[{"role": "user", "content": "first prompt"}])

    with (
        ReplaySession.from_trace(trace_path, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="input diverged"),
    ):
        _call(FakeOpenAI(), messages=[{"role": "user", "content": "changed prompt"}])


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


def test_non_json_response_is_reported_as_integration_error() -> None:
    client = FakeOpenAI(response=NonJsonCompletion())

    with pytest.raises(OpenAIIntegrationError, match="response"):
        _call(client)

    assert len(client.calls) == 1


def test_non_object_response_is_reported_as_integration_error() -> None:
    client = FakeOpenAI(response=["not", "an", "object"])

    with pytest.raises(OpenAIIntegrationError, match="JSON object"):
        _call(client)

    assert len(client.calls) == 1


def test_to_dict_response_objects_are_supported() -> None:
    client = FakeOpenAI(response=ToDictCompletion())

    result = _call(client)

    assert result["choices"][0]["message"]["content"] == "dict response"


def test_missing_chat_completions_create_is_reported() -> None:
    class MissingChat:
        pass

    with pytest.raises(OpenAIIntegrationError, match=r"chat\.completions\.create"):
        chat_completions_create(MissingChat(), **_request())


def test_sdk_exception_is_recorded_and_replayed(tmp_path: Path) -> None:
    trace_path = tmp_path / "openai-error.sftrace"
    client = FakeOpenAI(exc=RuntimeError("provider down"))

    with (
        pytest.raises(RuntimeError, match="provider down"),
        record("openai-agent", output=trace_path),
    ):
        _call(client)

    replay_client = FakeOpenAI(content="should not run")
    with (
        ReplaySession.from_trace(trace_path, mode="frozen"),
        pytest.raises(RecordedDependencyError, match="provider down"),
    ):
        _call(replay_client)
    assert replay_client.calls == []


def test_model_is_required() -> None:
    with pytest.raises(OpenAIIntegrationError, match="model"):
        chat_completions_create(
            FakeOpenAI(),
            messages=[{"role": "user", "content": "hello"}],
        )
