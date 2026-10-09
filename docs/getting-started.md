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

The agent below looks up an order status with an instrumented tool and decides
whether to notify the customer. The buggy version only notifies when an order
is *delivered*, so a shipped order is skipped. Save this as `agent.py`:

```python
from stepfork import record, trace_tool


@trace_tool(name="order_status")
def order_status(order_id: str) -> dict:
    # Stand-in for your real dependency. Offline and deterministic.
    return {"order_id": order_id, "status": "shipped", "carrier": "FedEx"}


def run_agent(order_id: str = "ORD-1001") -> dict:
    status = order_status(order_id)
    should_notify = status["status"] == "delivered"  # bug: shipped orders skipped
    return {
        "order_id": order_id,
        "should_notify": should_notify,
        "carrier": status["carrier"],
    }


def run_agent_fixed(order_id: str = "ORD-1001") -> dict:
    status = order_status(order_id)
    should_notify = status["status"] == "shipped"  # fix: notify on shipment
    return {
        "order_id": order_id,
        "should_notify": should_notify,
        "carrier": status["carrier"],
    }


if __name__ == "__main__":
    with record("notify-agent", output="failure.sftrace") as session:
        result = run_agent()
        session.set_output(result)
    print(result)
```

Record the failure:

```bash
python agent.py
```

```text
{'order_id': 'ORD-1001', 'should_notify': False, 'carrier': 'FedEx'}
```

Define the corrected behavior and export a regression test for both
entrypoints:

```bash
printf '{"order_id": "ORD-1001", "should_notify": true, "carrier": "FedEx"}' > expected.json

stepfork export failure.sftrace --pytest \
  --entrypoint agent:run_agent \
  --expect-output expected.json \
  --output test_notify_buggy.py --overwrite

stepfork export failure.sftrace --pytest \
  --entrypoint agent:run_agent_fixed \
  --expect-output expected.json \
  --output test_notify_fixed.py --overwrite
```

`expected.json` holds the behavior you want after the fix. The generated test
fails on the buggy entrypoint and passes on the fixed one:

```bash
python -m pytest -q test_notify_buggy.py   # 1 failed (behavior mismatch)
python -m pytest -q test_notify_fixed.py   # 1 passed
```

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
   the recorded responses for instrumented tool and LLM calls instead of
   calling those dependencies again, so a replayed run does not re-execute
   those real services.
3. Fix the agent, then [diff](diff.md) the recorded failure against a corrected
   run to see exactly which behaviors changed.
4. [Export](pytest-export.md) a pytest regression test from the recorded
   failure. Supply the corrected output with `--expect-output`; the generated
   test fails on the buggy code and passes on the fix.

## Next steps

- Learn the vocabulary in [Concepts](concepts.md).
- Run the three example agents in [Examples](examples.md).
- Read [Troubleshooting](troubleshooting.md) for common errors.