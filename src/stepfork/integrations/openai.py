"""Optional OpenAI Python SDK integration.

The core package never imports the OpenAI SDK. This module accepts a caller
supplied client object and records the supported synchronous SDK call through
Stepfork's provider-independent LLM boundary.
"""

from __future__ import annotations

from typing import Any, TypeAlias, cast

from stepfork.recorder import llm_request
from stepfork.trace import JsonValue, ReplayPolicy
from stepfork.trace.jsonable import TraceSerializationError, to_json_value

CHAT_COMPLETIONS_METHOD = "chat.completions.create"
PROVIDER = "openai"

JsonObject: TypeAlias = dict[str, JsonValue]


class OpenAIIntegrationError(ValueError):
    """Raised when an OpenAI SDK call cannot be safely recorded or replayed."""


def chat_completions_create(
    client: Any,
    /,
    *,
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    **request: Any,
) -> JsonObject:
    """Call ``client.chat.completions.create`` through Stepfork recording.

    Supported in this first adapter:

    - synchronous OpenAI-style clients,
    - ``chat.completions.create`` only,
    - non-streaming requests only,
    - JSON-compatible request parameters and response payloads.

    The returned value is a JSON-compatible dictionary, both during live
    recording and frozen replay. This keeps exported regression tests
    independent of the OpenAI SDK package.
    """
    normalized = _normalize_chat_request(request)
    model = _required_model(normalized)

    return cast(
        JsonObject,
        llm_request(
            provider=PROVIDER,
            model=model,
            input={"method": CHAT_COMPLETIONS_METHOD, "request": normalized},
            call=lambda: _call_chat_completions(client, request),
            replay_policy=replay_policy,
        ),
    )


def _normalize_chat_request(request: dict[str, Any]) -> JsonObject:
    if request.get("stream") is True:
        raise OpenAIIntegrationError(
            "streaming chat completions are not supported by the OpenAI "
            "Stepfork adapter yet"
        )
    try:
        normalized = to_json_value(request)
    except TraceSerializationError as exc:
        raise OpenAIIntegrationError(
            "OpenAI chat completion request parameters must be JSON-compatible "
            "for Stepfork replay"
        ) from exc
    if not isinstance(normalized, dict):
        raise OpenAIIntegrationError("OpenAI chat completion request must be an object")
    return normalized


def _required_model(request: JsonObject) -> str:
    model = request.get("model")
    if not isinstance(model, str) or model == "":
        raise OpenAIIntegrationError(
            "OpenAI chat completions require a non-empty string `model`"
        )
    return model


def _call_chat_completions(client: Any, request: dict[str, Any]) -> JsonObject:
    try:
        create = client.chat.completions.create
    except AttributeError as exc:
        raise OpenAIIntegrationError(
            "client must expose chat.completions.create"
        ) from exc

    response = create(**request)
    try:
        payload = _json_payload(response)
    except TraceSerializationError as exc:
        raise OpenAIIntegrationError(
            "OpenAI chat completion response must be JSON-compatible for "
            "Stepfork replay"
        ) from exc
    if not isinstance(payload, dict):
        raise OpenAIIntegrationError(
            "OpenAI chat completion response must serialize to a JSON object"
        )
    return payload


def _json_payload(value: Any) -> JsonValue:
    """Convert common OpenAI SDK response objects into JSON-compatible data."""
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return to_json_value(dumped)
    if hasattr(value, "to_dict"):
        dumped = value.to_dict()
        return to_json_value(dumped)
    return to_json_value(value)


__all__ = [
    "CHAT_COMPLETIONS_METHOD",
    "OpenAIIntegrationError",
    "chat_completions_create",
]
