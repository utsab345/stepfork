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

Product goal:

> Turn a failed AI-agent run into the smallest reproducible pytest regression
> test, locally, in under five minutes.

## What Stepfork does

Stepfork records what an AI agent actually did during a run: every external
tool call, every LLM request, and the final output. When the agent misbehaves,
you replay that recording in frozen mode and export it as an executable
regression test that asserts the corrected behavior.

- **Record** a buggy run into a portable `.sftrace` bundle.
- **Replay** it with dependencies frozen: responses come from the recording, so
  no external service or tool body ever runs.
- **Diff** the buggy behavior against a corrected run.
- **Export** a pytest regression test. It fails on the buggy code and passes on
  the fix.

The result is a test you already trust: it reproduces the exact failure that
started this, without fakes, mocks, or network calls.

## Why you would use it

AI agents fail in ways unit tests miss. A flight-search agent books the wrong
flight. A refund agent denies an eligible claim. When you diagnose such a
failure, you usually hand-write a fix and hope the regression is covered.

Stepfork captures the real run, so the failure becomes a deterministic,
offline regression test that encodes the corrected behavior. You get a failing
test you can commit to CI the moment you fix the bug.

## How it works

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

## Installation

V0.1.0a1 is the first public alpha. It is not on PyPI yet; install from the
public GitHub repository:

```bash
# pip
pip install "git+https://github.com/utsab345/stepfork.git@v0.1.0a1"

# uv
uv pip install "git+https://github.com/utsab345/stepfork.git@v0.1.0a1"
```

Python 3.11, 3.12, or 3.13 is required. This installs the `stepfork` CLI and
Python package.

For contributors working from a checkout, use `uv sync` from the repository
root instead.

## 60-second example

The code below is a complete, runnable agent (this exact file ships in
`examples/quickstart/agent.py`). It looks up an order status with an external
tool and decides whether to notify the customer. The buggy version only
notifies when an order is *delivered*; the fix notifies when it is *shipped*.

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

The shipped order is skipped (`{"should_notify": false}`). After you fix the
agent, turn that recorded failure into a regression test that expects the
corrected outcome:

```bash
stepfork export failure.sftrace --pytest \
  --entrypoint yourpkg.agent:run_agent \
  --expect-output expected.json \
  --output test_notify.py --overwrite
```

`expected.json` holds the behavior you want after the fix (here
`{"should_notify": true}`). The generated test fails on the buggy agent and
passes on the fixed one. Run the whole flow, including recording the fixed
side and diffing the two behaviors, with:

```bash
uv run python examples/quickstart/demo.py
```

## Demonstration

Two more complete demos ship in this repository, both fully offline (a fake LLM
provider stands in for a real model, so no API keys or network access are
needed):

- `examples/quickstart` - the minimal example above.
- `examples/booking_agent` - pairs a fake LLM provider with a flight-search
  tool and books the wrong flight.
- `examples/refund_agent` - pairs a fake LLM provider with a
  refund-policy-check tool and denies an eligible refund.

```bash
git clone https://github.com/utsab345/stepfork.git
cd stepfork
uv sync
uv run python examples/quickstart/demo.py
uv run python examples/booking_agent/demo.py
uv run python examples/refund_agent/demo.py
```

Each demo records the buggy run, freeze-replays it without touching the
external tool body, diffs it against the fixed run, and exports a regression
test that fails on the buggy entrypoint and passes on the fixed one.

## CLI

```bash
stepfork validate demo.sftrace --verify-integrity
stepfork inspect demo.sftrace --json
stepfork replay demo.sftrace --entrypoint pkg.module:func --mode frozen
stepfork diff baseline.sftrace candidate.sftrace --json
stepfork export demo.sftrace --pytest --entrypoint pkg.module:func
```

## Supported functionality

V0.1.0a1 ships a typed `.sftrace` v0.1 model, directory storage, structural
validation, best-effort redaction, integrity verification, local inspection,
runtime recording, frozen replay, behavioral diffing, and executable pytest
export. The suite is backed by 361 tests at 93% branch coverage. See the
[documentation](#documentation) for how each feature works.

## Limitations

Stepfork is experimental. The API, CLI, and `.sftrace` trace format may change
before v1.0.

- **No automatic failure minimization yet.** The exported regression test uses
  the recorded steps. Reducing it to the smallest failing subset and
  fork-at-step are planned work, not automatic behavior.
- **No framework integrations yet.** LangGraph, OpenAI Agents, and MCP support
  are planned, not shipped.
- **Replay requires determinism.** Dependencies that do not honor the recorded
  responses (for example approximate matching or nondeterministic code paths)
  can make frozen replay diverge from the recording.
- **Redaction is best-effort.** Pattern-based redaction can miss sensitive
  information embedded in unusual payloads. Inspect traces carefully before
  sharing them.

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

Inspect a saved trace locally:

```bash
stepfork inspect demo.sftrace
stepfork inspect demo.sftrace --json
stepfork inspect demo.sftrace --errors-only
```

## Integrity and Redaction

Stepfork applies best-effort redaction when saving `.sftrace` bundles. It
recursively redacts known sensitive keys such as `api_key`, `authorization`,
`password`, and common credential-looking strings before writing trace files.
Redaction metadata is stored in `redactions.json` without the original secret.

Persisted event payloads also receive SHA-256 hashes computed from Stepfork's
v0.1 canonical JSON profile after redaction. New bundles include an
`integrity.json` file with SHA-256 digests for `manifest.json`, `events.jsonl`,
and `redactions.json`.

Verify bundle integrity explicitly:

```bash
stepfork validate demo.sftrace --verify-integrity
```

Integrity status means:

- `verified`: the bundle's recorded file digests match the current files.
- `mismatch`: at least one recorded digest or payload hash does not match.
- `unverified_legacy`: the bundle predates `integrity.json`; it can still be
  structurally valid, but it has not been verified.

These checks are a release prerequisite, not proof that a trace is safe to
publish. SHA-256 is not encryption, and the unkeyed integrity file is not a
digital signature. An attacker who can modify both the trace files and
`integrity.json` can rewrite the record.

## Documentation

- [Getting started](docs/index.md)
- [Recording](docs/recording.md)
- [Replay](docs/replay.md)
- [Behavioral diff](docs/diff.md)
- [pytest export](docs/pytest-export.md)
- [Trace format](docs/trace-format.md)
- [Security notes](docs/security.md)
- [Security policy](SECURITY.md)
- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
- [Release checklist](docs/release-checklist.md)
- [v0.1.0a1 release notes](docs/releases/v0.1.0a1.md)
- [Changelog](CHANGELOG.md)

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

## Development

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Run linting and formatting checks:

```bash
uv run ruff check .
uv run ruff format --check .
```

Run static typing:

```bash
uv run mypy
```

Check the CLI:

```bash
uv run stepfork --help
```

## License

Stepfork is licensed under the Apache License, Version 2.0.