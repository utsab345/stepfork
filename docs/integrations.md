# Integrations

Stepfork's core is framework-independent by design. Recording and replay do
not depend on LangGraph, OpenAI Agents, MCP, or any agent runtime. That keeps
the core small, fast, and offline.

Two adapters are implemented today:

- [LangGraph](langgraph.md): synchronous `BaseChatModel` generation and
  function-based tools, through explicit instance-scoped wrappers.
- [OpenAI Python SDK](openai.md): synchronous, non-streaming
  `chat.completions.create` through an explicit wrapper.

The remaining adapters below are proposals.

## Design Principle

Keep the core framework-independent. Add optional adapters, one small module
per integration, installed on demand. The core never imports an adapter, and
adapters never change the core.

This mirrors an adapter pattern with three layers:

- **Core (implemented):** `Trace`, `ToolCall`, replay, diff, export. No
  framework imports.
- **Adapters (proposed):** thin, framework-specific translation modules. Each
  depends only on the public core API and may bring its own optional
  dependencies.
- **Entry points:** a way to activate the right adapter for a given run.

## Adapters

### LangGraph

- Implemented for synchronous chat-model generation and function-based tools.
  `traced_chat_model` wraps a `BaseChatModel` instance's `_generate`;
  `traced_tool` wraps a function (or an existing `BaseTool` with a `func`) and
  records its body. Both are explicit and instance-scoped; no global
  monkeypatching.
- Replay is frozen: the model and tool bodies are not executed, and recorded
  responses are returned from the `Trace`.
- Captures the model boundary and wrapped tools only. Async invocation,
  streaming, and unwrapped dependencies are surfaced rather than masked.
- Install with `stepfork[langgraph]`.
- See [LangGraph](langgraph.md).

### OpenAI Agents SDK

- Recording at the function-tool boundary (equivalent to `@trace_tool`) and
  at `Runner.run`, reusing the same runtime recording primitives the offline
  API already exposes.
- Export unchanged: the exported pytest test drives the entrypoint under
  frozen replay.
- Status: design only, not implemented.

### OpenAI Python SDK

- Implemented for synchronous, non-streaming `chat.completions.create`.
- Uses the core `llm_request` boundary and does not change the trace format.
- Install with `stepfork[openai]` when using the real SDK.
- Status: minimal adapter implemented; streaming, async, Responses API, and
  automatic monkeypatching are future work.

### MCP

- A status source only: MCP servers respond to services, not recording. An
  adapter could observe tool invocations going to an MCP server and record
  them in the same `Trace`.
- Status: design only, not implemented.

### GitHub Actions

- Implemented as an example workflow (`.github/workflows/agent-regression.yml`):
  it installs the optional extra, runs committed `stepfork export` tests under
  frozen replay, and configures no provider credentials. It builds on the
  existing CLI and runtime; it ships no special test tooling.
- Status: example implemented; a reusable published Action is future work.

## Constraints

- **Optional dependencies.** Each adapter lives behind extras
  (`stepfork[langgraph]`, `stepfork[openai]`). `pip install stepfork` stays
  dependency-light.
- **Offline preserved.** Recording and replay never dial a remote endpoint.
  An adapter may *use* real transports (e.g. MCP) but the trace stays local.
- **No avoidable abstractions.** One module per integration, documented,
  thin. If the core requires adapter-specific plumbing to remain runnable,
  that plumbing is a leak; the core must stay able to capture an ordinary
  offline run end to end with no adapter installed.
- **Tradeoffs, in writing:** for each integration, state what the adapter does
  and does not capture (for example, LangGraph parallel branches are recorded
  per node; cross-node nondeterminism is surfaced by replay divergence, not
  masked).

## What This Means for the Core

- The public API already is the integration surface: `record`,
  `trace_tool`, `Trace.from_recording`, and the CLI entrypoints.
- A future integration must not add behavior to the models or the exporter;
  it only translates runtime events into core events.
- Automated tooling around `gh` releases, `tox`, or CI matrices are
  repository workflows, not library features, and stay in
  [development](development.md).

## Not in Scope for v0.3

- A hosted viewer or cloud service (local viewer only).
- Webhooks or event sinks; the trace format is a filesystem directory.
- Framework plugins for frameworks that do not exist yet.
