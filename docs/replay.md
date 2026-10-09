# Replay

Replay executes a trusted, locally defined entrypoint while dependency calls are
served according to the recording. Trace bundles are treated as data; Stepfork
never executes code embedded in a trace.

## Python API

```python
from stepfork import ReplaySession

with ReplaySession.from_trace("failure.sftrace", mode="frozen") as replay:
    result = run_agent()
    replay.verify_complete()
```

`ReplaySession.from_trace(source, mode="frozen")` accepts either a path to a
bundle or an in-memory `Trace`. The active session is available process-wide, so
instrumented tools and `llm_request` calls inside `run_agent()` observe it.

`verify_complete()` raises `ReplayMismatchError` if recorded dependency calls
were left unmatched, which catches agents that skip a recorded step.

## Matching guarantees

Replay is strict about the recorded dependency sequence. For each intercepted
dependency call, Stepfork checks:

- call order,
- dependency kind (`tool` or `llm`),
- tool name,
- LLM provider and model,
- redacted canonical JSON input, including prompt payloads passed to
  `llm_request`,
- recorded input and output fingerprints when the bundle contains them.

Tool arguments are normalized with Python signature binding before recording
and replay. Defaulted parameters are included in the normalized input, so a
changed tool default is treated as argument drift instead of silently reusing a
stale result.

When a call diverges, diagnostics show the expected and actual call metadata,
redacted input previews, and SHA-256 fingerprints of the redacted canonical
inputs or recorded outputs. LLM model/provider diagnostics also include a model metadata
fingerprint. These fingerprints help compare runs without adding new secret
material to the trace.

Legacy or hand-built traces that do not contain input hashes remain replayable
when their full recorded input still matches the live call. The diagnostic
marks those fingerprints as computed from the loaded trace. If a stored input
or output fingerprint is present but does not match the recorded payload,
replay rejects the bundle and recommends `stepfork validate --verify-integrity`.

## Modes

| Mode | Behavior |
| --- | --- |
| `frozen` | Return the recorded result; never execute the dependency body. |
| `live` | Match against the recording, then execute the real dependency. |
| `forbidden` | Reject any dependency call with `ReplayPolicyError`. |
| `manual` | Reject dependency calls that are not explicitly approved. |
| `derived` | Reserved; not supported in v0.1. |

In `frozen` and `live`, a call whose name, provider, model, inputs, or
fingerprints do not match the recording raises `ReplayMismatchError` before
the dependency body executes. `manual` and `forbidden` reject calls before
matching because those modes require explicit policy handling.

## Errors

- `ReplayMismatchError`: the entrypoint diverged from the recording (wrong tool
  name, LLM provider/model, inputs, prompt payload, fingerprint, or a recorded
  result is missing.
- `ReplayExhaustedError`: a recorded call was consumed twice, or
  `verify_complete()` found unmatched calls.
- `ReplayPolicyError`: the mode or per-call policy forbids execution.
- `RecordedDependencyError`: a dependency that failed during recording is
  represented by a dedicated replay exception carrying the recorded error type
  and sanitized message.
- `ReplayError`: base class for all of the above.

## CLI

```bash
stepfork replay failure.sftrace --entrypoint examples.booking_agent:run_agent
stepfork replay failure.sftrace --entrypoint mypkg.agent:main --mode frozen
```

`--entrypoint` is a trusted `MODULE:FUNCTION` resolved against the current
working directory. Only that callable is imported and run.

Exit codes:

- `0`: the run completed, or it reproduced the recorded failure.
- `1`: the run diverged from the recording.
- `2`: invalid mode, unreadable trace, or unresolvable entrypoint.

The report separates entrypoint execution, dependency-call matching, and the
comparison with the recorded run output. A completed entrypoint with all calls
matched can still return a different value; the CLI reports `DIVERGED` and exits
`1` in that case. When the successful trace has no final output, the comparison
is `NOT RECORDED`. A reproduced exception currently matches the recorded
failure **type**, not the full exception message or every side effect.

Frozen replay does not intercept `random.random()`, time, files, environment
variables, network calls outside instrumented boundaries, or arbitrary Python
side effects. Record a final output with `session.set_output(...)` so the CLI
can detect changes to that value. A matching final output is evidence about
the recorded return value after secret redaction; it does not prove that every
side effect or a redacted secret value matched.

CLI diagnostics abbreviate SHA-256 fingerprints for readability. Pass
`--verbose` to see the full fingerprints. The Python replay exceptions retain
full fingerprints for programmatic diagnostics.
