"""Tests for the optional LangGraph integration boundary wrappers."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any, cast

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import Field
from typing_extensions import TypedDict

from stepfork import ReplaySession, Trace, record
from stepfork.integrations.langgraph import (
    LangGraphIntegrationError,
    traced_chat_model,
    traced_tool,
)
from stepfork.replay import (
    RecordedDependencyError,
    ReplayExhaustedError,
    ReplayMismatchError,
)
from stepfork.trace import (
    EventType,
    LLMResponse,
    RunEnd,
    RunStart,
    RunStatus,
)

TOOL_EXECUTIONS: list[tuple[str, Any]] = []


class GraphState(TypedDict):
    """Message state used by the nested graph test."""

    messages: Annotated[list[BaseMessage], add_messages]


class FakeChatModel(BaseChatModel):
    """Deterministic chat model that records its invocations."""

    model_name: str = "fake-model"
    responses: list[AIMessage] = Field(default_factory=list)
    error_message: str | None = None
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if self.error_message is not None:
            raise RuntimeError(self.error_message)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return ChatResult(generations=[ChatGeneration(message=self.responses[index])])


def _model(
    *,
    model_name: str = "fake-model",
    responses: list[str] | None = None,
    error_message: str | None = None,
) -> FakeChatModel:
    return FakeChatModel(
        model_name=model_name,
        responses=[AIMessage(content=text) for text in (responses or ["hello"])],
        error_message=error_message,
    )


def _invoke(
    model: BaseChatModel,
    prompt: str = "hi",
) -> BaseMessage:
    return model.invoke([HumanMessage(content=prompt)])


def _record_llm(path: Path, *, responses: list[str], prompt: str = "hi") -> None:
    model = traced_chat_model(_model(responses=responses))
    with record("llm-agent", output=path):
        _invoke(model, prompt)


def test_traced_chat_model_records_and_replays(tmp_path: Path) -> None:
    path = tmp_path / "llm.sftrace"
    _record_llm(path, responses=["recorded"])

    live = _model(responses=["live value must not be used"])
    replay_model = traced_chat_model(live)
    with ReplaySession.from_trace(path, mode="frozen") as replay:
        result = _invoke(replay_model)
        replay.verify_complete()

    assert result.content == "recorded"
    assert live.calls == []


def test_traced_chat_model_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "llm.sftrace"
    model = _model(responses=["one"])
    traced = traced_chat_model(model)

    assert traced_chat_model(traced) is traced

    with record("llm-agent", output=path):
        _invoke(traced)

    trace = Trace.load(path)
    requests = [event for event in trace.events if event.type is EventType.LLM_REQUEST]
    assert len(requests) == 1


def test_traced_chat_model_rejects_non_model() -> None:
    with pytest.raises(LangGraphIntegrationError, match="BaseChatModel"):
        traced_chat_model(object())  # type: ignore[arg-type]


def test_frozen_replay_detects_changed_model(tmp_path: Path) -> None:
    path = tmp_path / "llm.sftrace"
    _record_llm(path, responses=["recorded"])

    replay_model = traced_chat_model(_model(model_name="other-model"))
    with (
        ReplaySession.from_trace(path, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="expected LLM model"),
    ):
        _invoke(replay_model)


def test_frozen_replay_detects_changed_prompt(tmp_path: Path) -> None:
    path = tmp_path / "llm.sftrace"
    _record_llm(path, responses=["recorded"], prompt="first prompt")

    replay_model = traced_chat_model(_model(responses=["recorded"]))
    with (
        ReplaySession.from_trace(path, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="input diverged"),
    ):
        _invoke(replay_model, prompt="changed prompt")


def test_model_exception_is_recorded_and_replayed(tmp_path: Path) -> None:
    path = tmp_path / "llm-error.sftrace"
    model = traced_chat_model(_model(error_message="provider down"))

    with (
        pytest.raises(RuntimeError, match="provider down"),
        record("llm-agent", output=path),
    ):
        _invoke(model)

    live = _model(responses=["should not run"])
    replay_model = traced_chat_model(live)
    with (
        ReplaySession.from_trace(path, mode="frozen"),
        pytest.raises(RecordedDependencyError, match="provider down"),
    ):
        _invoke(replay_model)
    assert live.calls == []


def test_missing_model_recording_is_rejected(tmp_path: Path) -> None:
    trace = Trace(agent_name="empty")
    trace.add(RunStart())
    trace.add(RunEnd(run_status=RunStatus.COMPLETED))

    with (
        ReplaySession(trace, mode="frozen"),
        pytest.raises(ReplayExhaustedError, match="unexpected llm call"),
    ):
        _invoke(traced_chat_model(_model()))


def test_malformed_llm_response_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "llm.sftrace"
    _record_llm(path, responses=["recorded"])

    trace = Trace.load(path)
    for index, event in enumerate(trace.events):
        if isinstance(event, LLMResponse):
            trace.events[index] = event.model_copy(
                update={"output": "not-an-object", "output_hash": None}
            )

    with (
        ReplaySession(trace, mode="frozen"),
        pytest.raises(LangGraphIntegrationError, match="not an object"),
    ):
        _invoke(traced_chat_model(_model(responses=["unused"])))


def test_async_invocation_records_and_replays(tmp_path: Path) -> None:
    path = tmp_path / "llm.sftrace"
    source_model = _model(responses=["async"])
    model = traced_chat_model(source_model)

    async def run() -> None:
        async with record("llm-agent", output=path):
            result = await model.ainvoke([HumanMessage(content="hi")])
            assert result.content == "async"
        async with ReplaySession.from_trace(path) as replay:
            result = await model.ainvoke([HumanMessage(content="hi")])
            replay.verify_complete()
            assert result.content == "async"

    asyncio.run(run())
    assert len(source_model.calls) == 1


def test_streaming_model_is_rejected_inside_recording(tmp_path: Path) -> None:
    model = traced_chat_model(_model(responses=["chunk"]))
    with (
        record("stream", output=tmp_path / "stream.sftrace"),
        pytest.raises(LangGraphIntegrationError, match="streaming"),
    ):
        list(model.stream([HumanMessage(content="hi")]))

    async def scenario() -> None:
        async with record("astream", output=tmp_path / "astream.sftrace"):
            with pytest.raises(LangGraphIntegrationError, match="streaming"):
                async for _ in model.astream([HumanMessage(content="hi")]):
                    pass

    asyncio.run(scenario())


def test_traced_tool_records_and_replays(tmp_path: Path) -> None:
    path = tmp_path / "tool.sftrace"
    TOOL_EXECUTIONS.clear()

    def double(value: int) -> int:
        """Double an integer."""
        TOOL_EXECUTIONS.append(("double", value))
        return value * 2

    traced = traced_tool(double)
    assert isinstance(traced, BaseTool)

    with record("tool-agent", output=path):
        assert traced.invoke({"value": 21}) == 42

    assert TOOL_EXECUTIONS == [("double", 21)]

    TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(path, mode="frozen") as replay:
        assert traced.invoke({"value": 21}) == 42
        replay.verify_complete()
    assert TOOL_EXECUTIONS == []


def test_traced_tool_decorator_form(tmp_path: Path) -> None:
    path = tmp_path / "tool.sftrace"
    TOOL_EXECUTIONS.clear()

    @traced_tool(name="add")
    def add(left: int, right: int) -> int:
        """Add two integers."""
        TOOL_EXECUTIONS.append(("add", left + right))
        return left + right

    assert add.name == "add"
    with record("tool-agent", output=path):
        assert add.invoke({"left": 2, "right": 3}) == 5

    TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(path, mode="frozen"):
        assert add.invoke({"left": 2, "right": 3}) == 5
    assert TOOL_EXECUTIONS == []


def test_traced_tool_accepts_existing_langchain_tool(tmp_path: Path) -> None:
    path = tmp_path / "tool.sftrace"
    TOOL_EXECUTIONS.clear()

    @tool
    def square(value: int) -> int:
        """Square an integer."""
        TOOL_EXECUTIONS.append(("square", value))
        return value * value

    traced = traced_tool(square)
    assert traced.name == "square"

    with record("tool-agent", output=path):
        assert traced.invoke({"value": 6}) == 36

    TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(path, mode="frozen"):
        assert traced.invoke({"value": 6}) == 36
    assert TOOL_EXECUTIONS == []


def test_traced_tool_rejects_non_callable() -> None:
    with pytest.raises(LangGraphIntegrationError, match="callable"):
        cast("Any", traced_tool)(123)


class _CustomTool(BaseTool):
    name: str = "custom"
    description: str = "custom tool without a Python function"

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "custom"


def test_traced_tool_rejects_custom_base_tool() -> None:
    with pytest.raises(LangGraphIntegrationError, match="underlying function"):
        traced_tool(_CustomTool())


def test_tool_changed_arguments_detected(tmp_path: Path) -> None:
    path = tmp_path / "tool.sftrace"

    def echo(value: str) -> str:
        """Echo a value."""
        return value

    traced = traced_tool(echo)
    with record("tool-agent", output=path):
        traced.invoke({"value": "first"})

    with (
        ReplaySession.from_trace(path, mode="frozen"),
        pytest.raises(ReplayMismatchError, match="input diverged"),
    ):
        traced.invoke({"value": "second"})


def test_tool_exception_is_recorded_and_replayed(tmp_path: Path) -> None:
    path = tmp_path / "tool-error.sftrace"
    TOOL_EXECUTIONS.clear()

    def explode(value: int) -> int:
        """Always raise."""
        TOOL_EXECUTIONS.append(("explode", value))
        raise ValueError("boom")

    traced = traced_tool(explode)
    with pytest.raises(ValueError, match="boom"), record("tool-agent", output=path):
        traced.invoke({"value": 1})

    TOOL_EXECUTIONS.clear()
    with (
        ReplaySession.from_trace(path, mode="frozen"),
        pytest.raises(RecordedDependencyError, match="boom"),
    ):
        traced.invoke({"value": 1})
    assert TOOL_EXECUTIONS == []


def test_missing_tool_call_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "tool.sftrace"

    def first(value: int) -> int:
        """First tool."""
        return value

    def second(value: int) -> int:
        """Second tool."""
        return value

    first_traced = traced_tool(first)
    second_traced = traced_tool(second)
    with record("tool-agent", output=path):
        first_traced.invoke({"value": 1})
        second_traced.invoke({"value": 2})

    with (
        ReplaySession.from_trace(path, mode="frozen") as replay,
        pytest.raises(ReplayMismatchError, match="replay ended before consuming"),
    ):
        first_traced.invoke({"value": 1})
        replay.verify_complete()


def test_extra_tool_call_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "tool.sftrace"

    def single(value: int) -> int:
        """Single tool."""
        return value

    traced = traced_tool(single)
    with record("tool-agent", output=path):
        traced.invoke({"value": 1})

    with (
        ReplaySession.from_trace(path, mode="frozen"),
        pytest.raises(ReplayExhaustedError, match="unexpected tool call"),
    ):
        traced.invoke({"value": 1})
        traced.invoke({"value": 1})


def test_redaction_is_preserved_across_replay(tmp_path: Path) -> None:
    path = tmp_path / "tool.sftrace"
    TOOL_EXECUTIONS.clear()
    secret = "sk-abcdefghijklmnop"

    def call_api(api_key: str) -> str:
        """Call an API with a key."""
        TOOL_EXECUTIONS.append(("call_api", api_key))
        return "ok"

    traced = traced_tool(call_api)
    with record("tool-agent", output=path):
        assert traced.invoke({"api_key": secret}) == "ok"

    trace = Trace.load(path)
    call = next(event for event in trace.events if event.type is EventType.TOOL_CALL)
    assert call.input == {"api_key": "[REDACTED]"}
    assert secret not in path.joinpath("events.jsonl").read_text(encoding="utf-8")

    TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(path, mode="frozen") as replay:
        assert traced.invoke({"api_key": secret}) == "ok"
        replay.verify_complete()
    assert TOOL_EXECUTIONS == []


def test_nested_graph_execution_replays_without_calls(tmp_path: Path) -> None:
    live = _model(responses=["inner"])
    model = traced_chat_model(live)

    def inner_node(state: GraphState) -> dict[str, list[BaseMessage]]:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    inner_builder: StateGraph[GraphState] = StateGraph(GraphState)
    inner_builder.add_node("inner", inner_node)
    inner_builder.add_edge(START, "inner")
    inner_builder.add_edge("inner", END)
    subgraph = inner_builder.compile()

    def outer_node(state: GraphState) -> dict[str, list[BaseMessage]]:
        return dict(subgraph.invoke(state))

    outer_builder: StateGraph[GraphState] = StateGraph(GraphState)
    outer_builder.add_node("outer", outer_node)
    outer_builder.add_edge(START, "outer")
    outer_builder.add_edge("outer", END)
    graph = outer_builder.compile()

    path = tmp_path / "nested.sftrace"
    with record("nested-agent", output=path):
        graph.invoke({"messages": [HumanMessage(content="hi")]})

    live.calls.clear()
    with ReplaySession.from_trace(path, mode="frozen") as replay:
        graph.invoke({"messages": [HumanMessage(content="hi")]})
        replay.verify_complete()
    assert live.calls == []


def test_import_without_langchain_reports_extra() -> None:
    script = (
        "import sys\n"
        "sys.modules['langchain_core'] = None\n"
        "try:\n"
        "    import stepfork.integrations.langgraph  # noqa: F401\n"
        "except ModuleNotFoundError as exc:\n"
        "    assert 'stepfork[langgraph]' in str(exc), str(exc)\n"
        "else:\n"
        "    raise SystemExit('expected ModuleNotFoundError')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
