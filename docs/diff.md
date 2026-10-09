# Behavioral Diff

The diff compares what two agent runs *did*, not just their final output. It
ignores noisy fields such as timestamps, event IDs, run IDs, and wall-clock
durations, and focuses on dependency order, tool names, LLM models, inputs,
outputs, error types, state changes, and run status.

## Python API

```python
from stepfork import diff_traces

result = diff_traces("baseline.sftrace", "candidate.sftrace")
if not result.equivalent:
    for step in result.steps:
        for change in step.changes:
            print(step.label, change.path, change.expected, change.actual)
```

`diff_traces(baseline, candidate)` accepts `.sftrace` paths or in-memory
`Trace` objects. It returns a `DiffResult`:

- `equivalent`: `True` when no step was added, removed, or changed.
- `baseline` / `candidate`: `TraceSummary` identity metadata.
- `steps`: a list of `StepDiff` entries covering tool calls, LLM calls, state
  changes, errors, and the terminal run result.
- `added`, `removed`, `changed`, `unchanged`: step counts.

Each `StepDiff` carries an `index`, `kind` (`added`, `removed`, `changed`, or
`unchanged`), `step_type`, `label`, the compared `fields`, and a list of
`FieldChange` entries with dotted `path`, `kind`, `expected`, and `actual`.

## CLI

```bash
stepfork diff baseline.sftrace candidate.sftrace
stepfork diff baseline.sftrace candidate.sftrace --json
```

Exit codes:

- `0`: behavior equivalent.
- `1`: meaningful behavioral difference.
- `2`: invalid or unreadable input.

`--json` emits the serialized `DiffResult` to stdout with no Rich markup.
