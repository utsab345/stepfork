# CLI Reference

The `stepfork` CLI manages `.sftrace` bundles. This page documents every
command as of v0.1.0a5. Run `stepfork --help` for an up-to-date summary.

```text
Usage: stepfork [OPTIONS] COMMAND [ARGS]...
```

Global options:

| Option | Description |
|---|---|
| `--version`, `-V` | Show the Stepfork version and exit. |
| `--install-completion` | Install shell completion for the current shell. |
| `--show-completion` | Show shell completion for the current shell. |
| `--help` | Show global help and exit. |

Commands:

- [validate](#validate)
- [inspect](#inspect)
- [replay](#replay)
- [diff](#diff)
- [export](#export)

Exit code conventions:

- `0` success (or a replayed failure reproduced intentionally).
- `1` the run behaved differently, or the operation could not complete safely.
- `2` invalid, unreadable, or unresolvable input.
- `3` `validate --verify-integrity` on a legacy bundle without integrity
  metadata.

---

## validate

Validate a `.sftrace` bundle.

```text
Usage: stepfork validate [OPTIONS] PATH
```

Arguments:

| Argument | Description |
|---|---|
| `PATH` | Path to a `.sftrace` directory bundle. Required. |

Options:

| Option | Description |
|---|---|
| `--partial` | Allow incomplete in-progress traces, skipping `run_start` checks. |
| `--verify-integrity` | Verify per-event payload hashes and bundle integrity metadata. |
| `--help` | Show command help and exit. |

Strict mode (default) requires exactly one `run_start` and an error event for
failed runs. `--partial` relaxes those execution checks for in-progress or
intentionally incomplete bundles.

Example:

```bash
stepfork validate failure.sftrace --verify-integrity
```

```text
✓ Manifest structure valid
✓ Event payloads parse
✓ Run IDs consistent
✓ Event count matches
✓ Strict execution checks
✓ Integrity verified

Validation passed.
```

Common errors:

- `Validation failed: <N> issues.` with a code per issue (for example
  `duplicate_event_id`, `step_order`, `event_count_mismatch`). Exit `1`.
- Unreadable bundles (`missing_file`, `invalid_json`, `invalid_manifest`,
  `invalid_event`, `unsupported_schema`). Exit `2`.
- `Bundle has no integrity.json metadata.` (`UNVERIFIED (legacy bundle)`). Exit
  `3` with `--verify-integrity`.

---

## inspect

Inspect a `.sftrace` bundle locally.

```text
Usage: stepfork inspect [OPTIONS] PATH
```

Arguments:

| Argument | Description |
|---|---|
| `PATH` | Path to a `.sftrace` directory bundle. Required. |

Options:

| Option | Description |
|---|---|
| `--json` | Emit sanitized machine-readable JSON. |
| `--events` | Show sanitized event details. |
| `--errors-only` | Show only error events. |
| `--step <int>` | Show events at a specific logical step. |
| `--help` | Show command help and exit. |

Default output shows a summary (agent name, run id, status, event count,
schema, timestamps, tool/LLM call counts, duration, integrity state) plus an
event timeline table.

Example:

```bash
stepfork inspect failure.sftrace
```

```text
Stepfork Trace Inspector

Agent:         notify-agent
Run:           run_37bf09a918054efda5034cc500a700e8
Status:        COMPLETED
Events:        4
Schema:        0.1
Tool calls:    1
Integrity:     VERIFIED

Event Timeline

┏━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Step ┃ Type        ┃ Name/Model   ┃ Status ┃
┡━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━┩
│    0 │ run_start   │ run_start    │ ok     │
│    1 │ tool_call   │ order_status │ ok     │
│    2 │ tool_result │ order_status │ ok     │
│    3 │ run_end     │ completed    │ ok     │
└──────┴─────────────┴──────────────┴────────┘
```

`--events` adds a `Details` column showing each sanitized payload. `--step <n>`
limits the timeline to one logical step, and `--errors-only` shows only error
events.

`--json` writes sanitized JSON for scripts. In JSON mode, errors are emitted as
`{"error": "unreadable_trace", "message": "..."}` and
`{"error": "missing_step", "message": "..."}`.

Common errors:

- `--step <n>` matches no events: `No events found at step <n>.` Exit `1`.
- Unreadable bundle. Exit `2`.

---

## replay

Execute a trusted entrypoint with dependencies replayed from a trace.

```text
Usage: stepfork replay [OPTIONS] PATH
```

Only the entrypoint you name is imported and run. Trace bundles are data:
Stepfork never executes code embedded in a trace.

Arguments:

| Argument | Description |
|---|---|
| `PATH` | Path to a `.sftrace` directory bundle. Required. |

Options:

| Option | Description |
|---|---|
| `--entrypoint <str>` | Trusted local `MODULE:FUNCTION` to execute under replay. Required. |
| `--mode <str>` | Replay mode: `frozen`, `live`, `forbidden`, or `manual`. Default `frozen`. |
| `--verbose` | Show full diagnostic fingerprints instead of abbreviated ones. |
| `--help` | Show command help and exit. |

Modes:

- `frozen` answers every dependency call from the recording; mismatches fail
  loudly (recommended for regression work).
- `live` lets unrecorded calls pass through to the real dependency.
- `forbidden` rejects any dependency call.
- `manual` requires approval for each call.
- `derived` exists in the data model but is not supported in v0.1.

Example:

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
Dependency matching: COMPLETE

Execution: COMPLETED
Recorded behavior: MATCHED
Status: COMPLETED
Final result: {"order_id":"ORD-1001","should_notify":false}
```

Exit codes:

- `0` the run replayed without divergence, including when a recorded failure
  is reproduced intentionally (`REPRODUCED FAILURE`).
- `1` the entrypoint diverged from the recording.
- `2` invalid mode, unreadable trace, or unresolvable entrypoint.

Common errors:

- `Unable to resolve entrypoint.` followed by a detail line (`invalid
  entrypoint ...; expected the form MODULE:FUNCTION`, `cannot import module
  ...`, `module ... has no attribute ...`, `entrypoint ... is not callable`).
- Replay divergence messages, for example `call #1: input diverged from the
  recording` or `replay ended before consuming 1 recorded dependency call(s)`.
- `Invalid replay mode <mode>.`

---

## diff

Compare the behavior of two recorded agent runs.

```text
Usage: stepfork diff [OPTIONS] BASELINE CANDIDATE
```

Exit codes: `0` behavior equivalent, `1` meaningful behavioral difference,
`2` invalid or unreadable input.

Arguments:

| Argument | Description |
|---|---|
| `BASELINE` | Baseline `.sftrace` directory bundle. Required. |
| `CANDIDATE` | Candidate `.sftrace` directory bundle. Required. |

Options:

| Option | Description |
|---|---|
| `--json` | Emit machine-readable JSON (no Rich markup). |
| `--help` | Show command help and exit. |

Human output lists each changed location with its old and new value:

```text
  output:
    expected: false
    actual:   true
    at:       output.should_notify
  run_status: unchanged

Steps: 2 total (1 changed, 0 added, 0 removed, 1 unchanged)

Result: BEHAVIOR CHANGED
```

---

## export

Export an executable pytest regression test from a trace.

```text
Usage: stepfork export [OPTIONS] PATH
```

The generated test loads the frozen trace, executes your trusted entrypoint
under replay, and fails when the behavior diverges from the expected outcome.

Arguments:

| Argument | Description |
|---|---|
| `PATH` | Path to a `.sftrace` directory bundle. Required. |

Options:

| Option | Description |
|---|---|
| `--pytest` / `--no-pytest` | Export a pytest test (the only v0.1 format). |
| `--entrypoint <str>` | Trusted local `MODULE:FUNCTION` the generated test executes. |
| `--expect-output <path>` | JSON file defining the expected regression outcome. |
| `--output <path>` | Destination test file. Default `./test_<trace>_regression.py`. |
| `--overwrite` | Replace the output file if it already exists. |
| `--mode <str>` | Replay mode used by the generated test. Default `frozen`. |
| `--help` | Show command help and exit. |

Example:

```bash
stepfork export failure.sftrace --pytest \
  --entrypoint quickstart:run_agent_fixed \
  --expect-output expected.json \
  --output test_notify_fixed.py --overwrite
```

```text
Wrote test_notify_fixed.py
Entrypoint: quickstart:run_agent_fixed
Mode:       frozen
Expectation: {"order_id": "ORD-1001", "should_notify": true, "carrier": "FedEx"}
```

Without `--expect-output`, the generated test asserts the recorded run output,
which passes against the code that produced the recording. Pass
`--expect-output` to assert the corrected behavior instead.

The generated test produces standard `AssertionError` messages:

- `behavior mismatch at '<path>': expected <value>, got <value>` when the
  runtime output diverges from the expectation.
- `stepfork replay divergence: ...` when the entrypoint does not replay
  according to the trace.

Common errors:

- Export requires strict validation and the pytest format; it prints
  `v0.1 supports pytest export only (--pytest).` otherwise.
- `An executable regression test needs --entrypoint MODULE:FUNCTION.`
- `<path> already exists; pass --overwrite to replace it.`
- `--expect-output is not valid JSON: <detail>`.

---

## Error handling

Command output is sanitized before display: secrets in trace-derived text
appear as `[REDACTED]`. See [Security notes](security.md) and
[Troubleshooting](troubleshooting.md) for the full error catalogue and the
security model.
