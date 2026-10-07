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

## Status

Stepfork is experimental. The API, CLI, and `.sftrace` trace format may change
before v1.0.

Day 1 of the project is repository and tooling setup only. The architectural
packages are intentionally empty, and runtime agent-recording functionality is
not implemented yet.

## Planned Workflow

```text
failed agent run
      ↓
record
      ↓
inspect
      ↓
frozen replay
      ↓
behavioral diff
      ↓
pytest regression test
```

## Planned Quickstart

The examples in this section describe the intended future workflow. They are
not implemented yet.

```python
from stepfork import record

with record("checkout-agent"):
    agent.run("Book the cheapest flight")
```

```bash
stepfork inspect latest
stepfork replay latest --mode frozen
stepfork diff baseline.sftrace latest.sftrace
stepfork export latest.sftrace --pytest
```

## Roadmap

### v0.1

- Portable `.sftrace`
- Recording
- Inspect
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
