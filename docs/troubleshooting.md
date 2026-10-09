# Troubleshooting

Common error scenarios, their causes, and fixes. Exit codes: `1` means the
run diverged or the operation could not complete, `2` means the input was
invalid or unreadable, and `3` is reserved for `validate --verify-integrity`
on a legacy bundle without integrity metadata.

## Trace is not a valid bundle

| Error | Cause | Fix |
|---|---|---|
| `{path} does not exist` | Wrong path or working directory. | Run from the directory that holds the `.sftrace` bundle. |
| `trace bundle path must end with .sftrace` | Path does not point at a `.sftrace` directory. | Point at the bundle directory, not a `.sftrace` file inside it. |
| `{path} is not a directory` | The path is a plain file. | Point at the bundle directory. |
| `missing required file: {path}/manifest.json` | The bundle is incomplete. | Restore the file or re-record. |
| `{path}:{line}: invalid JSON: ...` | `events.jsonl` (or a manifest) has malformed JSON. | Re-record. |
| `{path}: unsupported schema version ...` | Bundle was written by a different Stepfork version. | Re-record with a supported schema. |
| `Unable to read trace.` / `Unable to inspect trace.` | A wrapper around one of the causes above. | Read the second line for the specific cause. |

## Replay diverges from the recording

Replay is strict: calls are matched in order, and inputs must match exactly.
Any deviation fails loudly rather than guessing.

- `replay ended before consuming N recorded dependency call(s)` - the agent
  skipped dependency calls that the recording contains. Compare the entrypoint
  with the recording.
- `unexpected {tool|llm} call ...: all N recorded dependency call(s) were
  already consumed` - the agent made an extra call that is not in the
  recording.
- `call #N: expected tool {label!r} but the agent called {name!r}` - tool name
  or instrumentation mismatch.
- `call #N: ... input diverged from the recording` - inputs are not
  deterministic, a prompt changed, or a tool default/argument changed. The
  diagnostic includes redacted expected/actual previews and input
  fingerprints. Make the inputs deterministic and re-record.
- `expected provider ... but the agent used ...` - the LLM provider metadata
  changed or was omitted. Re-record the trace for the new provider/model
  boundary.
- `recorded ... has an invalid input fingerprint` or `recorded ... has an
  invalid output fingerprint` - the event payload no longer
  matches its stored hash. Run `stepfork validate --verify-integrity`; do not
  use the bundle for strict replay unless you independently trust and repair
  it.
- `Invalid replay mode {mode!r}.` - use one of `frozen`, `live`, `forbidden`,
  or `manual`. `derived` exists in the data model but is not supported in
  v0.1.

Exit code `1`. If the replay intentionally reproduces a recorded failure, it
finishes with exit code `0` and reports `REPRODUCED FAILURE`.

## Entrypoint cannot be resolved

- `invalid entrypoint {spec!r}; expected the form MODULE:FUNCTION` - the
  reference is malformed. Use `pkg.module:function`.
- `cannot import module {module_name!r}: ModuleNotFoundError: ...` - the module
  is not importable, or not on `sys.path`. Run from your project root (the
  current directory is prepended to `sys.path`).
- `module {module_name!r} has no attribute {part!r}` - the function name is
  wrong, or the function lives in a submodule and is not exported from the
  package. Add the import to the package `__init__.py`.
- `entrypoint {spec!r} is not callable` - the attribute is not a zero-arg
  callable.

Exit code `2`.

## Export

- `v0.1 supports pytest export only (--pytest).` - only pytest format exists.
- `An executable regression test needs --entrypoint MODULE:FUNCTION.` - pass
  `--entrypoint` to `stepfork export`.
- `Trace failed validation.` - export requires strict validation. Run
  `stepfork validate` on the bundle first.
- `--expect-output is not valid JSON: ...` - the expectation file must contain
  one JSON document. No comments, no trailing prose.
- `{destination} already exists; pass --overwrite to replace it.` - pass
  `--overwrite`.
- `Export failed: {output_path} is a directory, not a file` - choose a file
  path.
- The warning about a missing `--expect-output`: the generated test will assert
  the recorded run output, which passes against the code that produced the
  recording. Pass `--expect-output` to assert the corrected behavior.

## The generated test fails

The generated pytest test produces standard `AssertionError` lines:

- `behavior mismatch at '{path}': expected {expected}, got {actual}` - the
  entrypoint produced different output than the expectation. This is the
  intended signal when you run the test against the buggy agent.
- `stepfork replay divergence: ...` - the entrypoint did not replay according
  to the trace.
- `stepfork: trace bundle not found: {bundle}` - the test moved away from its
  trace. Point the test at the bundle path, or regenerate it.

## Validation and integrity

- `Validation failed: {N} issues.` (exit 1) - structural problems. Each issue
  prints `{code}` and a message, for example `duplicate_event_id`,
  `step_order`, or `event_count_mismatch`. See
  [Trace format](trace-format.md) for the event model.
- `Strict validation requires exactly one run_start; found {n}.` - a partial
  trace. Use `--partial` only for intentionally incomplete bundles.
- `Failed traces require at least one error event in strict mode.` - a failed
  trace should contain its error event.
- `Bundle has no integrity.json metadata.` - a legacy bundle. It can still be
  structurally valid; there is just nothing to verify against.
- `integrity_mismatch` / `SHA-256 mismatch.` - a file digest does not match
  the recording. The bundle was modified or corrupted.

## Session misuse (library API)

- `RecordingSession cannot be re-entered` - do not nest `record(...)` blocks
  for the same session.
- `ReplaySession cannot be re-entered` - enter a replay session with
  `with ReplaySession.from_trace(...)`.
- `ReplaySession is not active; enter it with 'with ...' before running the
  agent` - run the agent inside the `with` block.

## Serialization

- `non-finite float at {path} cannot be recorded as JSON` - `NaN` and
  infinities are not JSON-compatible.
- `cannot serialize {type} at {path}; pass JSON-compatible values or provide a
  serializer hook via record(..., serializer=...) or trace_tool(...,
  serializer=...)` - record only JSON-compatible values, or register a
  serializer.

If the fix is not obvious, open an issue at
[https://github.com/utsab345/stepfork/issues](https://github.com/utsab345/stepfork/issues)
with the exact error text and the command you ran.
