# Development

## Setup

```bash
uv sync
```

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pytest --cov=stepfork --cov-branch --cov-report=term-missing
uv build
```

The suite currently has 356 tests and ~93% branch coverage, including
Hypothesis property tests under `tests/property/`.

Format changed files:

```bash
uv run ruff format .
```

## CLI Smoke Tests

```bash
uv run stepfork --help
uv run stepfork validate --help
uv run stepfork inspect --help
uv run stepfork inspect tests/golden/successful_run.sftrace
uv run stepfork validate tests/golden/successful_run.sftrace --verify-integrity
uv run stepfork replay --help
uv run stepfork diff --help
uv run stepfork export --help
```

## End-to-End Demos

Two examples exercise the whole pipeline with real subprocesses and real exit
codes:

```bash
uv run python examples/booking_agent/demo.py
uv run python examples/refund_agent/demo.py
```

`booking_agent` pairs a fake LLM provider with a flight-search tool;
`refund_agent` pairs a fake LLM provider with a refund-policy-check tool.
Both ship a buggy entrypoint that the demonstration converts into a failing
regression test and a fixed entrypoint that passes it.

## Synthetic Traces

Use the public API for local fixtures:

```python
from stepfork import Trace, ToolCall

trace = Trace(agent_name="demo-agent")
trace.add(ToolCall(name="search", input={"query": "Kathmandu flights"}))
trace.save("demo.sftrace")
```

Use fixed IDs and timestamps for committed golden fixtures. Never commit real
credentials, API keys, or user traces.

## Golden Fixtures

Golden traces live in `tests/golden/`. They are synthetic and deterministic.
When adding one:

- use fixed run IDs, event IDs, steps, and timestamps
- use synthetic payloads only
- run validation and integrity checks
- add regression tests for the expected behavior
