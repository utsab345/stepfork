# Future Integrations

Stepfork's core is framework-independent by design. Recording and replay do
not depend on LangGraph, OpenAI Agents, MCP, or any agent runtime. That keeps
the core small, fast, and offline.

This page is a proposal for v0.3. Nothing here is implemented in v0.1.

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

## Proposed Adapters

### LangGraph

- Record `StateGraph` executables via a wrapper or checkpointer hook that
  emits a `tool_call`/`tool_result`/LLM events into a `Trace`.
- Replay a graph node under frozen replay by returning recorded responses from
  the surrounding tools/LLM.
- Status: design only, not implemented.

### OpenAI Agents SDK

- Recording at the function-tool boundary (equivalent to `@trace_tool`) and
  at `Runner.run`, reusing the same runtime recording primitives the offline
  API already exposes.
- Export unchanged: the exported pytest test drives the entrypoint under
  frozen replay.
- Status: design only, not implemented.

### MCP

- A status source only: MCP servers respond to services, not recording. An
  adapter could observe tool invocations going to an MCP server and record
  them in the same `Trace`.
- Status: design only, not implemented.

### GitHub Actions

- A `stepfork` action that runs `validate --verify-integrity` and, on demand,
  a regression test, in CI. It builds on the existing CLI; it does not ship
  special test tooling.
- Status: design only, not implemented.

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