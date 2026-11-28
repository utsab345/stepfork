# Architecture

Stepfork turns a failed agent run into a reproducible pytest regression test.
The pipeline is:

```text
failed agent run
      |
    record        src/stepfork/recorder/
      |
    inspect       src/stepfork/inspect/
      |
  frozen replay   src/stepfork/replay/
      |
 behavioral diff  src/stepfork/diff/
      |
 minimize failure src/stepfork/minimize/
       |
  pytest export   src/stepfork/export/
```

`fork/` creates a trace from a selected step. `score/` assesses expectations
in exported tests; neither is required for the record-to-regression workflow.

The `.sftrace` format and its storage, validation, redaction, and integrity
logic all live under `src/stepfork/trace/` and are documented in
[trace-format.md](trace-format.md).

## Modules

### `trace/`

The core data layer. Pydantic v2 models for all event types, directory-bundle
storage (`storage.py`), structural validation (`validation.py`), best-effort
redaction (`redaction.py`), canonical JSON (`canonical.py`), payload hashing
(`hashing.py`), and the bundle integrity record (`integrity.py`). Everything
else builds on this layer.

### `recorder/`

Turns a live agent run into a trace.

- `session.py`: `record()` context manager and `RecordingSession`, which appends
  events, tracks parent scope, and finalizes the `run_end` event on exit.
- `tooling.py`: `@trace_tool`, the sync and async tool boundary.
- `llm.py`: `llm_request`, the provider-independent LLM boundary.

Recording never touches the network itself; it records whatever the wrapped
dependencies return.

### `replay/`

Executes a trusted entrypoint while serving dependency calls from a recording.

- `plan.py`: `extract_recorded_calls` builds the ordered list of recorded
  dependency calls.
- `session.py`: `ReplaySession` exposes the active replay process-wide and maps
  each incoming call to a recorded one. `frozen` modes substitute the recorded
  result; `live` executes after matching.
- `exceptions.py`: `ReplayError` and its subclasses.

### `diff/`

Compares two traces as behavior. `engine.py` extracts ordered `BehaviorStep`
entries and aligns them; `compare.py` computes structural field differences;
`models.py` defines the machine-readable `DiffResult`.

### `export/`

Generates the regression test.

- `entrypoint.py`: resolves `MODULE:FUNCTION` against a trusted import root.
- `generator.py`: renders a fixed, reviewed template. Trace payloads become
  sanitized JSON literals only; no code is generated from trace data.
- `runtime.py`: `run_regression_case`, the small reviewed helper the generated
  test calls to replay and assert.
- `entrypoint.py` and `runtime.py` together are the only code the generated test
  depends on beyond the public API.

### `inspect/`

Read-only summaries of a bundle for the `stepfork inspect` command.

### `cli/`

Typer commands: `validate`, `inspect`, `replay`, `diff`, `export`, `minimize`,
`fork`, `score`, and `run`, wired in `cli/main.py`.
`src/stepfork/__main__.py` provides `python -m stepfork`.

## Security boundaries

- Trace bundles are data. Stepfork never executes code, imports modules, or
  evaluates expressions found in a trace.
- Replay imports only the entrypoint the user names on the command line.
- Redaction runs before persistence and before hashes are computed.
- Integrity metadata is a checksum, not a signature; see
  [security.md](security.md).

## Trace operations

- `fork/` builds a new trace from a selected step and supports event-output
  overrides through the Python API.
- `minimize/` reduces a trace while checking whether the selected failure
  continues to reproduce.
- `score/` is part of `export/`; it evaluates exported expectations without
  executing the entrypoint.
