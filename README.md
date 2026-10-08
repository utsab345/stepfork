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

Stepfork now includes the initial typed `.sftrace` v0.1 model, directory
storage, and structural validation. Runtime agent recording, replay, diffing,
and export remain planned work.

## Offline Trace API

```python
from stepfork import ToolCall, Trace

trace = Trace(agent_name="demo-agent")

event = trace.add(
    ToolCall(
        name="search",
        input={"query": "Kathmandu flights"},
    )
)

trace.save("demo.sftrace")
```

Validate this development trace in partial mode:

```bash
stepfork validate demo.sftrace --partial
```

The `--partial` flag is required here because the example intentionally saves
only a `tool_call` event. Strict execution validation expects a complete trace
with a `run_start` event.

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
publish. Pattern-based redaction can miss sensitive information embedded in
unusual tool outputs, model responses, or domain-specific payloads. SHA-256 is
not encryption, and the unkeyed integrity file is not a digital signature. An
attacker who can modify both the trace files and `integrity.json` can rewrite
the record. Inspect traces carefully before sharing them.

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
