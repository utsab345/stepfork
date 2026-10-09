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

The suite currently has 361 tests and ~93% branch coverage, including
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

Three examples exercise the whole pipeline with real subprocesses and real exit
codes:

```bash
uv run python examples/quickstart/demo.py
uv run python examples/booking_agent/demo.py
uv run python examples/refund_agent/demo.py
```

`quickstart` is a single-tool order-notification agent and the minimal
starting point. `booking_agent` pairs a fake LLM provider with a flight-search
tool; `refund_agent` pairs a fake LLM provider with a refund-policy-check tool.
Each ships a buggy entrypoint that the demonstration converts into a failing
regression test and a fixed entrypoint that passes it.

## Documentation Site

The docs are built with [MkDocs](https://www.mkdocs.org/) and the
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) theme. The
source is `docs/` with `mkdocs.yml` at the repository root.

Build and preview locally:

```bash
uv run mkdocs build --strict
uv run mkdocs serve
```

The `.github/workflows/docs.yml` workflow builds the site (strict mode), uploads
it, and deploys to GitHub Pages. Deployment uses the least-privileged Pages
permissions: `contents: read`, `pages: write`, and `id-token: write`.

One-time setup before the first deploy:

1. Open repository Settings, then Pages.
2. Under Build and deployment, set Source to GitHub Actions.

The Pages URL is https://utsab345.github.io/stepfork/. Wait for the workflow
to finish after enabling Pages; do not assume it deployed until the URL
responds.

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
