"""Optional LangGraph / LangChain integration.

The core package never imports LangChain or LangGraph. This module translates
the two external boundaries of a LangGraph agent into Stepfork's
provider-independent recording and replay primitives:

- **Chat model boundary** — :func:`traced_chat_model` wraps a
  ``langchain_core`` ``BaseChatModel`` so each ``_generate`` call is recorded
  through :func:`stepfork.recorder.llm_request` and, during frozen replay, is
  answered from the recording instead of calling the model.
- **Tool boundary** — :func:`traced_tool` wraps a plain function or an existing
  ``BaseTool`` so the tool body is recorded through
  :func:`stepfork.recorder.trace_tool` and, during frozen replay, is not
  executed; the recorded output is returned instead.

Both wrappers are explicit and instance-scoped. Neither installs global
monkeypatches; normal LangGraph behavior is unchanged outside a ``record(...)``
or ``ReplaySession`` context.

Synchronous invocation is supported. Asynchronous model invocation
(``ainvoke``) is intentionally not recorded or replayed yet and raises a clear
error when attempted inside a Stepfork context.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar, overload

from stepfork.recorder import llm_request, trace_tool
from stepfork.recorder.session import active_recorder
from stepfork.replay.session import active_replay
from stepfork.trace import JsonValue, ReplayPolicy
from stepfork.trace.jsonable import Serializer, TraceSerializationError, to_json_value

try:  # pragma: no cover - import guard exercised via subprocess in tests
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import BaseTool, StructuredTool
except ImportError as exc:  # pragma: no cover - see tests/unit/... langgraph
    raise ModuleNotFoundError(
        "The Stepfork LangGraph integration requires the optional "
        "'langgraph' extra. Install it with: pip install 'stepfork[langgraph]'"
    ) from exc

if TYPE_CHECKING:
    from langchain_core.tools import ArgsSchema

JsonObject: TypeAlias = dict[str, JsonValue]

F = TypeVar("F", bound=Callable[..., Any])

_VOLATILE_MESSAGE_KEYS = frozenset({"id", "response_metadata", "usage_metadata"})

_MESSAGE_TYPES: dict[str, type[BaseMessage]] = {
    "ai": AIMessage,
    "tool": ToolMessage,
    "human": HumanMessage,
    "system": SystemMessage,
}


class LangGraphIntegrationError(ValueError):
    """Raised when a LangGraph boundary cannot be safely recorded or replayed."""


def traced_chat_model(
    model: BaseChatModel,
    *,
    provider: str | None = None,
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
) -> BaseChatModel:
    """Return ``model`` with its synchronous generation boundary traced.

    The same instance is returned. Each call to the model is recorded as an
    LLM request/response pair; during frozen replay the recorded response is
    returned and the underlying model is not called. Re-wrapping is a no-op.

    Only ``langchain_core`` ``BaseChatModel`` instances are supported. The
    model's ``bind_tools``/``bind`` behavior is preserved because only the
    instance's ``_generate`` method is wrapped.
    """
    if not isinstance(model, BaseChatModel):
        raise LangGraphIntegrationError(
            "traced_chat_model expects a langchain_core BaseChatModel instance"
        )
    if getattr(model._generate, "__stepfork_langgraph__", False):
        return model

    original_generate = model._generate
    model_id = _model_identifier(model)
    provider_name = provider if provider is not None else _model_provider(model)

    def _generate(
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        request_input = _model_input(messages, stop, kwargs)
        payload = llm_request(
            provider=provider_name,
            model=model_id,
            input=request_input,
            call=lambda: _chat_result_to_json(
                original_generate(
                    messages,
                    stop=stop,
                    run_manager=run_manager,
                    **kwargs,
                )
            ),
            replay_policy=replay_policy,
        )
        return _chat_result_from_json(payload)

    _generate.__stepfork_langgraph__ = True  # type: ignore[attr-defined]
    object.__setattr__(model, "_generate", _generate)
    _guard_async(model)
    return model


@overload
def traced_tool(target: F, /) -> BaseTool: ...


@overload
def traced_tool(target: BaseTool, /) -> BaseTool: ...


@overload
def traced_tool(
    *,
    name: str | None = None,
    description: str | None = None,
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    serializer: Serializer | None = None,
) -> Callable[[F], BaseTool]: ...


def traced_tool(
    target: F | BaseTool | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    replay_policy: ReplayPolicy = ReplayPolicy.FROZEN,
    serializer: Serializer | None = None,
) -> BaseTool | Callable[[F], BaseTool]:
    """Return a LangChain tool whose body runs under Stepfork tracing.

    Accepts either a plain function or an existing ``BaseTool``::

        from langgraph.prebuilt import ToolNode
        from stepfork.integrations.langgraph import traced_tool

        @traced_tool
        def lookup_customer(email: str) -> str:
            '''Look up a customer record.'''
            ...

        tools = [lookup_customer, traced_tool(existing_tool)]

    During recording the tool body executes and its result is captured; during
    frozen replay the body is not executed and the recorded result is returned.
    Values that are not JSON-compatible require an explicit ``serializer``.
    """

    def build(
        func: Callable[..., Any],
        *,
        tool_name: str,
        tool_description: str,
        args_schema: ArgsSchema | None = None,
    ) -> BaseTool:
        traced = trace_tool(
            name=tool_name,
            replay_policy=replay_policy,
            serializer=serializer,
        )(func)
        return StructuredTool.from_function(
            func=traced,
            name=tool_name,
            description=tool_description,
            args_schema=args_schema,
        )

    if target is None:

        def decorator(func: F) -> BaseTool:
            tool_name = name or _callable_name(func)
            return build(
                func,
                tool_name=tool_name,
                tool_description=description or _callable_description(func, tool_name),
            )

        return decorator

    if isinstance(target, BaseTool):
        inner = getattr(target, "func", None)
        if not callable(inner):
            raise LangGraphIntegrationError(
                f"cannot trace tool {target.name!r}: it does not expose a Python "
                "function. Apply @traced_tool to the underlying function instead."
            )
        tool_name = name or target.name
        return build(
            inner,
            tool_name=tool_name,
            tool_description=description
            or target.description
            or _callable_description(inner, tool_name),
            args_schema=target.args_schema,
        )

    if not callable(target):
        raise LangGraphIntegrationError(
            "traced_tool expects a callable or a BaseTool instance"
        )
    tool_name = name or _callable_name(target)
    return build(
        target,
        tool_name=tool_name,
        tool_description=description or _callable_description(target, tool_name),
    )


def _guard_async(model: BaseChatModel) -> None:
    """Stop async model calls from silently bypassing recording/replay."""
    original_agenerate = getattr(model, "_agenerate", None)
    if original_agenerate is None:
        return

    async def _agenerate(
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if active_recorder() is not None or active_replay() is not None:
            raise LangGraphIntegrationError(
                "Stepfork's LangGraph model tracing supports synchronous "
                "invocation only; 'ainvoke' is not recorded or replayed yet"
            )
        result: ChatResult = await original_agenerate(
            messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        )
        return result

    object.__setattr__(model, "_agenerate", _agenerate)


def _model_identifier(model: BaseChatModel) -> str:
    for attribute in ("model_name", "model"):
        value = getattr(model, attribute, None)
        if isinstance(value, str) and value:
            return value
    return _model_provider(model) or "unknown-model"


def _model_provider(model: BaseChatModel) -> str | None:
    llm_type = getattr(model, "_llm_type", None)
    if isinstance(llm_type, str) and llm_type:
        return llm_type
    return None


def _callable_name(func: Callable[..., Any]) -> str:
    name = getattr(func, "__name__", None)
    return name if isinstance(name, str) and name else "tool"


def _callable_description(func: Callable[..., Any], fallback: str) -> str:
    return inspect.getdoc(func) or fallback


def _model_input(
    messages: list[BaseMessage],
    stop: list[str] | None,
    kwargs: dict[str, Any],
) -> JsonObject:
    return {
        "messages": [_canonical_message(message) for message in messages],
        "stop": _jsonable(stop) if stop is not None else None,
        "kwargs": _jsonable(kwargs),
    }


def _canonical_message(message: BaseMessage) -> JsonObject:
    dumped = message.model_dump()
    return {
        key: _jsonable(value)
        for key, value in dumped.items()
        if key not in _VOLATILE_MESSAGE_KEYS
    }


def _jsonable(value: Any) -> JsonValue:
    try:
        return to_json_value(value)
    except TraceSerializationError as exc:
        raise LangGraphIntegrationError(
            "LangGraph boundary payloads must be JSON-compatible for Stepfork "
            f"replay: {exc}"
        ) from exc


def _chat_result_to_json(result: ChatResult) -> JsonObject:
    generations: list[JsonValue] = []
    for generation in result.generations:
        generations.append(
            {
                "message": _jsonable(generation.message.model_dump()),
                "generation_info": _jsonable(generation.generation_info)
                if generation.generation_info is not None
                else None,
                "text": generation.text,
            }
        )
    return {
        "generations": generations,
        "llm_output": _jsonable(result.llm_output)
        if result.llm_output is not None
        else None,
    }


def _chat_result_from_json(payload: JsonValue) -> ChatResult:
    if not isinstance(payload, dict):
        raise LangGraphIntegrationError(
            "recorded LangGraph LLM response is not an object"
        )
    raw_generations = payload.get("generations")
    if not isinstance(raw_generations, list) or not raw_generations:
        raise LangGraphIntegrationError(
            "recorded LangGraph LLM response has no generations"
        )

    generations: list[ChatGeneration] = []
    for item in raw_generations:
        if not isinstance(item, dict):
            raise LangGraphIntegrationError(
                "recorded LangGraph LLM generation is not an object"
            )
        text = item.get("text")
        generations.append(
            ChatGeneration(
                message=_message_from_json(item.get("message")),
                generation_info=_optional_object(item.get("generation_info")),
                text=text if isinstance(text, str) else "",
            )
        )

    llm_output = _optional_object(payload.get("llm_output"))
    return ChatResult(generations=generations, llm_output=llm_output)


def _message_from_json(payload: JsonValue | None) -> BaseMessage:
    if not isinstance(payload, dict):
        raise LangGraphIntegrationError(
            "recorded LangGraph LLM message is not an object"
        )
    kind = payload.get("type")
    message_type = _MESSAGE_TYPES.get(kind) if isinstance(kind, str) else None
    if message_type is None:
        raise LangGraphIntegrationError(
            f"recorded LangGraph LLM message has unsupported type {kind!r}"
        )
    fields = {key: value for key, value in payload.items() if key != "type"}
    try:
        return message_type(**fields)
    except Exception as exc:
        raise LangGraphIntegrationError(
            f"recorded LangGraph LLM message could not be reconstructed: {exc}"
        ) from exc


def _optional_object(value: JsonValue | None) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


__all__ = [
    "LangGraphIntegrationError",
    "traced_chat_model",
    "traced_tool",
]
