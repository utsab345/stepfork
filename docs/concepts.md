# Concepts

Stepfork's vocabulary maps onto the shape of an agent run. This page defines
the terms used across the documentation.

## Agent

The Python code under test. Stepfork does not call a framework. It instruments
two kinds of boundaries inside your code (tools and LLM requests) and records
the rest of the run as ordinary function execution.

## Dependency call

A moment where the agent touches the outside world: an external API, a
database, or a model provider. Stepfork records the input and output of every
dependency call so it can later be replayed without the real dependency.

## Tool

An external function the agent calls (for example a flight-search API), wrapped
with `@trace_tool`. Under recording the call and its result or exception are
captured. Under frozen replay the recorded response is returned and the real
body never runs.

## LLM request

A call to a model provider, wrapped with `stepfork.llm_request`. Stepfork
records the messages sent and the response received. In offline demos a fake
provider stands in for a real model, so the examples require no API keys.

## Trace

The full record of one agent run. It holds the run metadata, every recorded
event (tool calls, LLM requests, terminal output, failures) in order, and the
redaction and integrity files.

## `.sftrace` bundle

A trace persisted as a directory:

```text
failure.sftrace/
  manifest.json
  events.jsonl
  redactions.json
  integrity.json
```

Each file is canonical JSON. See [Trace format](trace-format.md) for details.

## Recording

The act of capturing one run. Use the `stepfork.record` context manager. The
bundle is written when the block exits, including when the block raises.

## Replay

Rerunning the agent entrypoint with the trace as its source of truth. In
`frozen` mode every dependency call is answered from the recording, so nothing
external executes. See [Replay](replay.md).

## Replay mode

Replays accept a matching mode. `frozen` requires exact recorded matches.
Approximate matching is planned work; replay rejects unmatched calls loudly.

## Behavioral diff

A comparison of two traces that finds mismatches in tool results, outputs, and
failures, while ignoring equivalent ordering. The diff report lists every
changed location. A run whose behavior is equivalent to a corrected baseline
is your regression signal. See [Diff](diff.md).

## Expectation

The corrected behavior you want the exported regression test to assert. Passed
to `stepfork export` with `--expect-output` (a JSON file). The generated test
fails on the buggy agent and passes on the fixed one. See
[pytest export](pytest-export.md).

## Redaction

Best-effort scrubbing of known sensitive keys such as `api_key` and
`authorization` before a bundle is written. Redaction metadata is stored in
`redactions.json` without the original secret. See [Security](security.md).

## Integrity

SHA-256 digests of the bundle files and of each event payload, enabling
`stepfork validate --verify-integrity` to detect tampering or corruption. See
[Security](security.md).

## Entrypoint

The `pkg.module:function` reference passed to `stepfork replay` and
`stepfork export`. Replay runs it, answered from the trace; export wraps it in
the generated test.

## Frozen

The replay mode used for regression testing: every instrumented dependency call
is answered from the recording. The assurance that "no instrumented external
dependency executed" comes from never calling the real tool body during replay;
calls outside instrumented boundaries are not intercepted.