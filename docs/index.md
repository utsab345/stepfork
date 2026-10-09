# Getting Started

Stepfork turns a failed AI-agent run into a reproducible pytest regression
test. This page walks through the core workflow and points to the detailed
docs for each step.

## Install

```bash
pip install "git+https://github.com/utsab345/stepfork.git@v0.1.0a1"
```

Requires Python 3.11, 3.12, or 3.13. See [the README](../README.md#installation)
for alternatives, including `uv`.

## The core workflow

```text
failed agent run
      ↓
record        capture tools, LLM calls, output, and failure
      ↓
inspect       review events, integrity, and error details
      ↓
frozen replay rerun the entrypoint without touching dependencies
      ↓
behavioral diff
      ↓
pytest regression test
```

1. [Record](recording.md) the failing run. Wrap the agent call in
   `stepfork.record` and mark each external dependency with `@trace_tool`
   (and, for LLM calls, `stepfork.llm_request`). The run is saved as a
   `.sftrace` bundle, including when the block raises.
2. [Replay](replay.md) the failure with frozen dependencies. Stepfork returns
   the recorded responses instead of calling real services, so a replayed run
   touches nothing external.
3. Fix the agent, then [diff](diff.md) the recorded failure against a corrected
   run to see exactly which behaviors changed.
4. [Export](pytest-export.md) a pytest regression test from the recorded
   failure. Supply the corrected output with `--expect-output`; the generated
   test fails on the buggy code and passes on the fix.

## 60-second example

The minimal [quickstart agent](../examples/quickstart/README.md) shows the whole
flow against a tiny order-notification agent. Run it with:

```bash
uv run python examples/quickstart/demo.py
```

It records a buggy run, freeze-replays it, diffs it against a corrected run,
and exports a regression test that fails on the buggy entrypoint and passes on
the fixed one.

## Where to go next

- [Trace format](trace-format.md): what a `.sftrace` bundle contains.
- [Validating and inspecting](recording.md): integrity and local inspection.
- [Security](security.md): redaction, integrity checks, and their limits.
- [Architecture](architecture.md): how the pieces fit together.
- [Development](development.md): build, test, and lint this repository.
- [Release notes](releases/v0.1.0a1.md) and the [changelog](../CHANGELOG.md).