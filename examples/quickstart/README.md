# Quickstart agent

A minimal, fully offline agent that demonstrates the complete Stepfork
workflow. No API keys, no network, no cloud account, no LLM dependency.

The agent answers a single question: should we notify the customer about an
order?

- The order has already shipped (status `shipped`, carrier `FedEx`).
- `run_agent` has a bug: it only notifies once the order is *delivered*, so a
  shipped order is skipped.
- `run_agent_fixed` is the corrected implementation: it notifies on
  *shipped*.

## Files

- `agent.py` - the agent, its single instrumented dependency
  (`order_status`), and both implementations.
- `demo.py` - a self-checking demonstration of the whole failure-to-test
  workflow.
- `expected.json` - the corrected expected output used by
  `stepfork export --expect-output`.

## Run the demo

From the repository root:

```bash
uv run python examples/quickstart/demo.py
```

`uv sync` installs pytest for the demo; the generated regression test is run
with pytest, which is not a runtime dependency of the Stepfork package itself.

The demo:

1. Records the buggy run to `failure.sftrace`.
2. Records the corrected run to `fixed.sftrace`.
3. Validates both bundles and verifies integrity.
4. Replays the buggy agent with frozen dependencies (the real tool body never
   runs, which the demo verifies).
5. Diffs buggy vs corrected behavior (expect `should_notify` to differ).
6. Exports a pytest regression test that expects `should_notify: true`.
7. Runs that test against the buggy code (fails) and the corrected code
   (passes).

## Key concepts shown

- `stepfork.record` wraps an agent call and saves a `.sftrace` bundle.
- `@trace_tool` marks an external dependency as recordable and replayable.
- `ReplaySession` reruns the agent with recorded responses, executing no
  dependency bodies.
- `stepfork diff <buggy> <fixed>` reports which behaviors changed.
- `stepfork export --pytest --expect-output <expected.json>` turns a recorded
  failure into a regression test for the corrected behavior.

See `docs/` for the full concepts.