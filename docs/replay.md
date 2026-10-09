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

`verify_complete()` raises `ReplayExhaustedError` if recorded dependency calls
were left unmatched, which catches agents that skip a recorded step.

## Modes

| Mode | Behavior |
| --- | --- |
| `frozen` | Return the recorded result; never execute the dependency body. |
| `live` | Match against the recording, then execute the real dependency. |
| `forbidden` | Reject any dependency call with `ReplayPolicyError`. |
| `manual` | Reject dependency calls that are not explicitly approved. |
| `derived` | Reserved; not supported in v0.1. |

In `frozen`, `live`, and `manual` a call whose name, inputs, or model does not
match the recording raises `ReplayMismatchError` before anything executes.

## Errors

- `ReplayMismatchError`: the entrypoint diverged from the recording (wrong tool
  name, inputs, or model) or a recorded result is missing.
- `ReplayExhaustedError`: a recorded call was consumed twice, or
  `verify_complete()` found unmatched calls.
- `ReplayPolicyError`: the mode or per-call policy forbids execution.
- `RecordedDependencyError`: a dependency that failed during recording is
  re-raised during replay, preserving the original error type.
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

The report lists each matched dependency call, any unmatched calls, the final
result, and whether the recorded failure was reproduced.
