# Getting Started

This guide installs Stepfork and walks through the full workflow with a
60-second example. A complete, runnable version of the example ships in
`examples/quickstart`.

## Install

```bash
pip install "git+https://github.com/utsab345/stepfork.git@v0.1.0a1"
```

Requires Python 3.11, 3.12, or 3.13. This installs the `stepfork` CLI and the
Python package.

Prefer the `uv` equivalent? `uv pip install` with the same URL works. For
contributors working from a checkout, use `uv sync` in the repository root
instead.

## 60-second example

The agent below looks up an order status with an external tool and decides
whether to notify the customer. The buggy version only notifies when an order
is *delivered*, so a shipped order is skipped.

```python
from stepfork import record, trace_tool


@trace_tool(name="order_status")
def order_status(order_id: str) -> dict:
    return shipping_service.status(order_id)  # your real dependency


def run_agent(order_id: str) -> dict:
    status = order_status(order_id)
    # bug: "delivered" never fires for a shipped order
    should_notify = status["status"] == "delivered"
    return {"order_id": order_id, "should_notify": should_notify}


with record("notify-agent", output="failure.sftrace") as session:
    result = run_agent("ORD-1001")
    session.set_output(result)
```

The shipped order is skipped (`{"should_notify": false}`). Fix the agent, then
turn the recorded failure into a regression test that expects the corrected
behavior:

```bash
stepfork export failure.sftrace --pytest \
  --entrypoint yourpkg.agent:run_agent \
  --expect-output expected.json \
  --output test_notify.py --overwrite
```

`expected.json` holds the behavior you want after the fix. The generated test
fails on the buggy agent and passes on the fixed one.

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

## Next steps

- Learn the vocabulary in [Concepts](concepts.md).
- Run the three example agents in [Examples](examples.md).
- Read [Troubleshooting](troubleshooting.md) for common errors.