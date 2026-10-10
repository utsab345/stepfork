# LangGraph

Stepfork includes an optional adapter for [LangGraph](https://langchain-ai.github.io/langgraph/)
and the `langchain_core` chat-model and tool interfaces. The core package does
not import LangChain or LangGraph; install the extra only when you use the
adapter:

```bash
pip install "stepfork[langgraph]"
```

The adapter translates the two external boundaries of a LangGraph agent into
Stepfork's provider-independent recording and replay primitives:

- the **chat model** boundary (`BaseChatModel._generate` or `_agenerate`), and
- the **tool** boundary (a plain function or an existing `BaseTool`).

Everything else — graph compilation, checkpointers, routing, and node logic —
runs unchanged.

## How it works

Both wrappers are explicit and instance-scoped. Stepfork never installs global
monkeypatches, so agent behavior outside a `record(...)` or `ReplaySession`
context is identical to stock LangGraph.

- `traced_chat_model(model)` returns the **same** model instance with its
  synchronous and asynchronous generation wrapped. Each call is recorded as an `llm_request`;
  during frozen replay the recorded `ChatResult` is returned and the model is
  not called. Because only the instance method is wrapped, `bind_tools` and
  `bind` keep working and the tracing carries through the runnable they return.
- `traced_tool(...)` wraps a function (or an existing `BaseTool`) as a
  LangChain tool whose body runs through `stepfork.trace_tool`. During
  recording the body executes and its result is captured; during frozen replay
  the body is not executed and the recorded result is returned.

The model input is canonicalized before it is hashed: volatile message fields
(`id`, `response_metadata`, `usage_metadata`) are removed so a run is
reproducible across processes. This is why replay matching does not depend on
random message identifiers.

## Usage

The example below is complete and fully offline: a deterministic scripted chat
model stands in for a real provider, so you can run it without an API key. It
wraps the model with `traced_chat_model`, wraps the tool with `@traced_tool`,
routes the model's tool call through a `ToolNode`, and records the run.

<!-- langgraph-example:start -->
```python
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import Field
from typing_extensions import TypedDict

from stepfork import record
from stepfork.integrations.langgraph import traced_chat_model, traced_tool

LOOKUPS: list[str] = []


@traced_tool
def lookup_customer(email: str) -> str:
    """Look up a customer record by email."""
    LOOKUPS.append(email)
    return f"customer={email};tier=gold"


SCRIPT = [
    AIMessage(
        content="",
        tool_calls=[
            {
                "name": "lookup_customer",
                "args": {"email": "ada@example.com"},
                "id": "call_lookup",
            }
        ],
    ),
    AIMessage(content="Ada is a gold customer."),
]


class ScriptedChatModel(BaseChatModel):
    """Deterministic stand-in for a real chat model; no API key required."""

    model_name: str = "scripted-triage"
    script: list[AIMessage] = Field(default_factory=lambda: list(SCRIPT))
    cursor: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self.script[min(self.cursor, len(self.script) - 1)]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


class TriageState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    answer: str


def build_graph() -> Any:
    model = traced_chat_model(ScriptedChatModel())
    tools = [lookup_customer]
    model_with_tools = model.bind_tools(tools)

    def agent(state: TriageState) -> dict[str, Any]:
        return {"messages": [model_with_tools.invoke(state["messages"])]}

    def route(state: TriageState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else "finish"

    def finish(state: TriageState) -> dict[str, Any]:
        results = [m.content for m in state["messages"] if isinstance(m, ToolMessage)]
        return {"answer": results[-1] if results else ""}

    graph = StateGraph(TriageState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("finish", finish)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", "finish": "finish"})
    graph.add_edge("tools", "agent")
    graph.add_edge("finish", END)

    return graph.compile()


def run_agent() -> dict[str, Any]:
    result = build_graph().invoke(
        {"messages": [HumanMessage(content="Is ada@example.com a gold customer?")]}
    )
    return {"answer": result["answer"]}


if __name__ == "__main__":
    with record("langgraph-triage", output="triage.sftrace") as session:
        result = run_agent()
        session.set_output(result)
    print(result)
```
<!-- langgraph-example:end -->

Save it as `langgraph_example.py` and run it; the instrumented tool executes once
and the run is recorded:

```bash
python langgraph_example.py
```

```text
{'answer': 'customer=ada@example.com;tier=gold'}
```

A frozen replay reruns `run_agent()` with the recorded model and tool responses.
`LOOKUPS` stays empty because the instrumented tool body never runs again:

```python
from stepfork import ReplaySession

import langgraph_example

langgraph_example.LOOKUPS.clear()
with ReplaySession.from_trace("triage.sftrace", mode="frozen") as replay:
    result = langgraph_example.run_agent()
    replay.verify_complete()
assert result == {"answer": "customer=ada@example.com;tier=gold"}
assert langgraph_example.LOOKUPS == []
```

Export the recording as a committed regression test against your trusted fixed
entrypoint exactly as with any other Stepfork entrypoint (shown here as
`myapp.agent:run_agent_fixed`):

```python
from stepfork.export import export_pytest_test

export_pytest_test(
    trace_path="triage.sftrace",
    output_path="tests/test_triage.py",
    entrypoint="myapp.agent:run_agent_fixed",
    expectation={"answer": "customer=ada@example.com;tier=gold"},
    has_expectation=True,
)
```

See the CLI guide for the equivalent `stepfork export` command.

## Recording model calls

Each chat-model call is recorded as an `llm_request` event:

- **provider**: the model's `_llm_type` (for example `openai-chat`), or the
  `provider=` argument if you pass one to `traced_chat_model`.
- **model**: the model's `model_name` (or `model`) attribute.
- **input**: the canonicalized messages, `stop`, and generation keyword
  arguments.
- **output**: the serialized `ChatResult`, including the generated message,
  its tool calls, and `generation_info`.

Because the full message list is part of the input hash, any change to the
prompt, the tool schema exposed to the model, or the graph's message history
surfaces as a replay divergence instead of a silent pass.

## Offline example

The repository ships a complete, fully offline LangGraph example:

```bash
uv run python examples/langgraph_agent/demo.py
```

It builds a real `StateGraph` around a refund-triage decision, records a buggy
run, freeze-replays it with **zero** model and tool executions, diffs it against
the corrected run, and proves the exported regression test fails for the buggy
agent and passes for the fixed one. No API keys and no network calls.

## What is and is not captured

Captured:

- synchronous and asynchronous chat-model generation (`invoke` / `ainvoke`),
- tool execution for tools created with `traced_tool`,
- the agent's final output,
- exceptions raised inside traced boundaries.

Not captured:

- streaming responses,
- retrieval/vector-store calls, checkpointers, or any other dependency you did
  not wrap,
- non-JSON tool return values, unless you pass an explicit `serializer=`.

Frozen replay returns exactly what was recorded. If your agent composes
parallel or nondeterministic branches, replay surfaces the divergence at the
first boundary whose input no longer matches; it does not mask it.

## Security

Model inputs, including message content and tool arguments, are written to the
local `.sftrace` bundle. Stepfork's redaction rules run before persistence
(known sensitive keys and credential-shaped strings such as `sk-...`), but
redaction is best-effort. Do not place API keys or other secrets in message
content, tool parameters, or metadata.

The adapter does not create or configure a provider client for you. Configure
credentials through the provider's normal mechanisms and keep them out of the
traced payload.

## Troubleshooting

- **`ModuleNotFoundError: ... requires the optional 'langgraph' extra`** —
  install `pip install "stepfork[langgraph]"`. The core package intentionally
  does not depend on LangGraph.
- **`LangGraphIntegrationError: streaming ... not supported`** — use `invoke`
  or `ainvoke` for a non-streaming recorded boundary.
- **`ReplayMismatchError: ... input diverged from the recording`** — the model
  received different messages, a different prompt, or a different tool schema
  than when recorded. Re-check the change that produced the difference; if it
  is intentional, re-record.
- **A custom `BaseTool` cannot be traced** — `traced_tool` needs a Python
  function. Apply `@traced_tool` to the underlying function and rebuild the
  tool, instead of wrapping a tool that has no `func`.
- **Tool output is not JSON-compatible** — pass `serializer=` to
  `traced_tool` to encode and decode the value.

## CI

`.github/workflows/agent-regression.yml` shows the intended CI shape:

- install with `uv sync --locked --extra langgraph`,
- run committed tests generated by `stepfork export` under frozen replay,
- run the offline integration tests,
- configure **no** provider credentials.

Replay never dials a remote endpoint and never re-records. If an agent's
behavior changes, the committed test fails and the pull request fails with it.
See the committed example under `examples/langgraph_agent/regression/`.
