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
uv build
```

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

## End-to-End Demo

The booking example exercises the whole pipeline with real subprocesses and
real exit codes:

```bash
uv run python examples/booking_agent/demo.py
```

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
