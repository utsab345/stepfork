<p align="center">
  <img src="assets/stepfork-logo.png" alt="Stepfork logo" width="220">
</p>

<h1 align="center">Stepfork</h1>

<p align="center">
  <strong>Your agent failed. Make the failure a test.</strong>
</p>

<p align="center">
  Local-first behavioral regression testing for AI agents.
</p>

<p align="center">
  <a href="https://pypi.org/project/stepfork/"><img alt="PyPI" src="https://img.shields.io/pypi/v/stepfork?include_prereleases&label=PyPI&color=blue"></a>
  <a href="https://github.com/utsab345/stepfork/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/utsab345/stepfork/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://utsab345.github.io/stepfork/"><img alt="Docs" src="https://github.com/utsab345/stepfork/actions/workflows/docs.yml/badge.svg"></a>
  <a href="https://www.apache.org/licenses/LICENSE-2.0"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-blue.svg">
</p>

Product goal:

> Turn a failed AI-agent run into a reproducible pytest regression test,
> locally, in under five minutes.

## The problem

AI agents fail in ways unit tests miss. A flight-search agent books the wrong
flight. A refund agent denies an eligible claim. When you diagnose such a
failure you usually hand-write a fix and hope the regression is covered.

Stepfork records what an agent actually did during a run: every instrumented
tool call, every instrumented LLM request, and the final output. When the agent
misbehaves, you replay that recording and export it as an executable pytest
regression test that asserts the corrected behavior. The test fails on the
buggy code and passes on the fix, using the recorded responses instead of live
services.

## How Stepfork Works

Stepfork turns a failed AI-agent execution into a reproducible pytest
regression test.

<img src="https://raw.githubusercontent.com/utsab345/stepfork/main/assets/stepfork-workflow.png" alt="Stepfork workflow diagram" style="max-width: 100%;">

**Workflow:** Instrument → Record → Inspect → Validate → Frozen Replay →
Compare → Define Expected Behavior → Export pytest → Verify Fix

## Key Capabilities

- **Record** a buggy run into a portable `.sftrace` bundle, including runs
  that raise. Recording is local-first; nothing leaves your machine.
- **Frozen replay** reruns your entrypoint with responses taken from the
  recording, so instrumented tool and LLM bodies never run again. Calls outside
  instrumented boundaries are not intercepted; wrap every external dependency
  you want frozen with `@trace_tool` or `llm_request`.
- **Behavioral diff** compares a buggy run against a corrected run and reports
  exactly which behaviors changed.
- **pytest export** turns a recorded failure into a regression test that
  asserts the corrected behavior.
- **Best-effort redaction** of known credential-shaped values at record time.
- **Integrity verification** via SHA-256 digests that make tampering evident.
- **Python 3.11, 3.12, and 3.13** support.

## Installation

Stepfork is published on PyPI. Install the current alpha with:

```bash
# pip
pip install --pre stepfork

# uv
uv pip install --pre stepfork
```

The `--pre` flag is required while Stepfork is a pre-release. You can also
install from the tagged GitHub repository:

```bash
pip install "git+https://github.com/utsab345/stepfork.git@v0.1.0a2"
```

Requires Python 3.11, 3.12, or 3.13. This installs the `stepfork` CLI and the
Python package. For contributors working from a checkout, use `uv sync`.

## Five-minute quickstart

Fully offline, no API keys, nothing invented. Save the file below as
`quickstart.py`:

```python
from stepfork import record, trace_tool


@trace_tool(name="order_status")
def order_status(order_id: str) -> dict:
    # Stand-in for your real shipping service. Offline and deterministic.
    return {"order_id": order_id, "status": "shipped", "carrier": "FedEx"}


def run_agent(order_id: str = "ORD-1001") -> dict:
    status = order_status(order_id)
    should_notify = status["status"] == "delivered"  # bug: notifies only on delivery
    return {
        "order_id": order_id,
        "should_notify": should_notify,
        "carrier": status["carrier"],
    }


def run_agent_fixed(order_id: str = "ORD-1001") -> dict:
    status = order_status(order_id)
    should_notify = status["status"] == "shipped"  # fix: notifies when it ships
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

The order has shipped, but the buggy agent only notifies on *delivery*, so it
skips the notification. Record that failure:

```bash
python quickstart.py
```

```text
{'order_id': 'ORD-1001', 'should_notify': False, 'carrier': 'FedEx'}
```

Inspect and validate the trace:

```bash
stepfork inspect failure.sftrace
stepfork validate failure.sftrace --verify-integrity
```

Replay the buggy agent with dependencies frozen. The recorded response is
substituted; the real tool body never runs:

```bash
stepfork replay failure.sftrace --entrypoint quickstart:run_agent --mode frozen
```

```text
Stepfork Replay

Trace         failure.sftrace
Agent         notify-agent
Entrypoint    quickstart:run_agent
Mode          frozen

Dependency Calls
  1. tool order_status (substituted)

Status: COMPLETED
Final result: {"carrier":"FedEx","order_id":"ORD-1001","should_notify":false}
```

Define the corrected behavior and export a regression test for both the buggy
and the fixed implementation:

```bash
printf '{"order_id": "ORD-1001", "should_notify": true, "carrier": "FedEx"}' > expected.json

stepfork export failure.sftrace --pytest \
  --entrypoint quickstart:run_agent \
  --expect-output expected.json \
  --output test_notify_buggy.py --overwrite

stepfork export failure.sftrace --pytest \
  --entrypoint quickstart:run_agent_fixed \
  --expect-output expected.json \
  --output test_notify_fixed.py --overwrite
```

Run the tests. The buggy implementation fails; the fix passes:

```bash
python -m pytest -q test_notify_buggy.py   # 1 failed (behavior mismatch)
python -m pytest -q test_notify_fixed.py   # 1 passed
```

That regression test reproduces the exact failure you started with, and now
pins the corrected behavior.

## Real Demonstration

This terminal recording runs the complete failure-to-test flow using the
minimal example agent:

![Stepfork terminal demo](scripts/terminal-demo/stepfork-demo.gif)

Three runnable demo agents ship in this repository (all fully offline, with a
fake provider standing in for a real model):

- `examples/quickstart` - a single-tool order-notification agent; the minimal
  starting point shown above.
- `examples/booking_agent` - a fake LLM provider paired with a flight-search
  tool; books the wrong flight.
- `examples/refund_agent` - a fake LLM provider paired with a
  refund-policy-check tool; denies an eligible refund.

```bash
git clone https://github.com/utsab345/stepfork.git
cd stepfork
uv sync
uv run python examples/quickstart/demo.py
uv run python examples/booking_agent/demo.py
uv run python examples/refund_agent/demo.py
```

Each demo records the buggy run, freeze-replays it without touching the
external tool body, diffs it against the corrected run, and exports a
regression test that fails on the buggy entrypoint and passes on the fixed one.
The demos print real results from real subprocesses; they never fabricate
output.

## CLI Reference

| Command | Purpose |
|---|---|
| `stepfork validate [PATH] [--partial] [--verify-integrity]` | Check a `.sftrace` bundle structurally (and its integrity). |
| `stepfork inspect [PATH] [--json] [--events] [--errors-only] [--step N]` | Review a bundle locally. |
| `stepfork replay [PATH] --entrypoint MODULE:FUNCTION [--mode M]` | Rerun the entrypoint with dependencies answered from the trace. |
| `stepfork diff [BASELINE] [CANDIDATE] [--json]` | Compare the behavior of two runs. |
| `stepfork export [PATH] --pytest --entrypoint MODULE:FUNCTION [--expect-output JSON] [--output FILE] [--overwrite]` | Generate an executable pytest regression test. |

The full reference (arguments, examples, expected output, and common errors)
is in [docs/cli.md](docs/cli.md).

## Offline Trace API

```python
from stepfork import ToolCall, Trace

trace = Trace(agent_name="demo-agent")

trace.add(ToolCall(name="search", input={"query": "Kathmandu flights"}))

trace.save("demo.sftrace")
loaded = Trace.load("demo.sftrace")
```

Validate traces:

```bash
stepfork validate demo.sftrace --partial
stepfork validate demo.sftrace
stepfork validate demo.sftrace --verify-integrity
```

The `--partial` flag is required here because the example intentionally saves
only a `tool_call` event. Strict execution validation expects a complete trace
with a `run_start` event.

## Documentation

The full documentation is published at
[https://utsab345.github.io/stepfork/](https://utsab345.github.io/stepfork/);
sources live in `docs/`.

- [Getting started](docs/index.md)
- [How recording works](docs/recording.md)
- [Replay](docs/replay.md)
- [Behavioral diff](docs/diff.md)
- [pytest export](docs/pytest-export.md)
- [CLI reference](docs/cli.md)
- [Trace format](docs/trace-format.md)
- [Security notes](docs/security.md)
- [Architecture](docs/architecture.md)
- [Future integrations](docs/integrations.md)
- [Development](docs/development.md)
- [Release checklist](docs/release-checklist.md)
- [PyPI publishing checklist](docs/pypi-publishing.md)
- [Early adopter guide](docs/community/early-adopter-guide.md)
- [v0.1.0a1 release notes](docs/releases/v0.1.0a1.md)
- [Changelog](CHANGELOG.md)

## Security and Limitations

Stepfork is experimental. The API, CLI, and `.sftrace` trace format may change
before v1.0.

- **Alpha on PyPI.** `pip install --pre stepfork` installs the current
  pre-release; the API and trace format may still change.
- **No automatic failure minimization.** The exported regression test uses the
  recorded steps. Reducing it to the smallest failing subset and fork-at-step
  are planned work, not automatic behavior.
- **No framework integrations yet.** LangGraph, OpenAI Agents, and MCP support
  are planned, not shipped. The proposed design is in
  [docs/integrations.md](docs/integrations.md).
- **Replay is not a sandbox.** Running an entrypoint under replay executes
  your own code with your own privileges. Trace data is never executed, but
  the entrypoint you name is.
- **Only instrumented boundaries are frozen.** Frozen replay substitutes calls
  made through `@trace_tool` and `llm_request`. Any external call your code
  makes outside those boundaries is not recorded and is not intercepted.
- **Redaction is best-effort.** Pattern-based redaction can miss sensitive
  information embedded in unusual tool outputs or domain-specific payloads.
- **Replay requires determinism.** Dependencies that do not honor the recorded
  responses can make frozen replay diverge from the recording.

Full details, including the integrity model and how to handle untrusted
bundles, are in [docs/security.md](docs/security.md).

## Roadmap

### v0.1 (released as v0.1.0a1)

- Portable `.sftrace`
- Trace save/load
- Structural validation
- Best-effort redaction
- Integrity verification
- Validate CLI
- Inspect CLI
- Runtime recording
- Frozen replay
- Behavioral diff
- pytest export

### v0.2

- Failure minimization
- Fork-at-step
- Baselines

### v0.3

- LangGraph
- OpenAI Agents
- MCP
- GitHub Action
- Local viewer

## Contributing

Contributions are welcome. Start with
[CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md).
Local development instructions live in [docs/development.md](docs/development.md).
If you find a security issue, report it privately per
[SECURITY.md](SECURITY.md). Please do not include secrets, credentials, or
sensitive trace data in issues, tests, examples, or commits.

## License

Stepfork is licensed under the Apache License, Version 2.0.