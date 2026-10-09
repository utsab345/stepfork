"""Offline OpenAI chat-completions example for Stepfork.

The fake client mirrors the synchronous shape of the OpenAI Python SDK call
used by the integration: ``client.chat.completions.create(...)``. No API key,
network access, or OpenAI account is required for this example.
"""

from __future__ import annotations

from typing import Any

from stepfork.integrations.openai import chat_completions_create

MODEL = "gpt-test"
PROMPT = "Classify this support message as positive or negative: I love it."

SDK_CALLS: list[dict[str, Any]] = []


class FakeChatCompletion:
    """Small response object with the SDK's Pydantic-style dump method."""

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        return {
            "id": "chatcmpl_offline",
            "object": "chat.completion",
            "model": MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "positive"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 1,
                "total_tokens": 13,
            },
        }


class FakeCompletions:
    def create(self, **request: Any) -> FakeChatCompletion:
        SDK_CALLS.append(dict(request))
        return FakeChatCompletion()


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeCompletions()


class FakeOpenAI:
    def __init__(self) -> None:
        self.chat = FakeChat()


CLIENT = FakeOpenAI()


def _completion_content(response: dict[str, Any]) -> str:
    return str(response["choices"][0]["message"]["content"])


def classify() -> str:
    response = chat_completions_create(
        CLIENT,
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0,
    )
    return _completion_content(response)


def run_agent() -> dict[str, str]:
    """Buggy implementation: flips the model's positive classification."""
    classify()
    return {"sentiment": "negative"}


def run_agent_fixed() -> dict[str, str]:
    """Corrected implementation: uses the recorded OpenAI-style response."""
    return {"sentiment": classify()}


EXPECTED_OUTPUT = {"sentiment": "positive"}
