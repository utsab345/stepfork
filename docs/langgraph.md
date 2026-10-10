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

```python
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from stepfork import record
from stepfork.integrations.langgraph import traced_chat_model, traced_tool


@traced_tool
def lookup_customer(email: str) -> str:
    """Look up a customer record by email."""
    return f"customer={email};tier=gold"


def build_agent(model):
    agent = traced_chat_model(model)

    def node(state: MessagesState):
        response = agent.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile(tools=[lookup_customer])
```

Record a run and export a regression test exactly as with any other Stepfork
entrypoint:

```python
from stepfork import record
from stepfork.export import export_pytest_test

with record("triage", output="triage.sftrace") as session:
    session.set_output(run_agent())

export_pytest_test(
    trace_path="triage.sftrace",
    output_path="tests/test_triage.py",
    entrypoint="myapp.agent:run_agent_fixed",
    expectation={"approved": True},
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
