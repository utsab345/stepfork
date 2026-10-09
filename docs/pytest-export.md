# pytest Export

`stepfork export` turns a trace into an executable pytest regression test that
replays a trusted entrypoint and asserts the expected behavior.

## The key idea: the recorded failure is not the expectation

A trace records what the agent *did*, including the bug. If you generate a test
that asserts the recorded output, it passes against the very code that produced
the recording, which is not a regression test.

The regression test needs a separate **expected outcome**: the behavior you want
after the bug is fixed. Pass it with `--expect-output`.

```bash
stepfork export failure.sftrace \
  --pytest \
  --entrypoint examples.booking_agent:run_agent \
  --expect-output expected.json \
  --output test_booking_regression.py \
  --overwrite
```

- Fails against the buggy implementation that produced the recording.
- Passes against the corrected implementation.

Without `--expect-output`, Stepfork warns that the test asserts the recorded run
output and that it will pass against the code that produced the recording. It is
useful for replay-fidelity checks, not for regression testing.

Review the desired JSON output before export. One practical workflow is to copy
the recorded result into a separate `expected.json`, edit the fields that define
the fix, review the file in code review, then pass it with `--expect-output`.
Do not treat the recorded result or the first output from changed code as an
approved oracle automatically. A future assisted workflow could prepare a
draft expected-output file for review, but it should require an explicit user
approval before exporting a regression assertion.

## Options

- `--pytest` / `--no-pytest`: only `pytest` is supported in v0.1.
- `--entrypoint MODULE:FUNCTION`: required; the trusted local callable the test
  executes.
- `--expect-output PATH`: JSON file with the expected outcome.
- `--output PATH`: destination file (default `test_<trace>_regression.py`).
- `--overwrite`: replace an existing destination.
- `--mode`: replay mode used by the generated test (`frozen` recommended).

The trace must pass strict validation before export.

Running the generated file requires `pytest`, an installed `stepfork` package,
an importable trusted entrypoint and its dependencies, and the referenced
`.sftrace` directory. The generated test refers to the bundle by path; it does
not embed or copy the fixture. If moving the test to another project or CI,
copy the bundle with it and verify `TRACE_PATH` resolves there. These are test
environment requirements; `pytest` is not a Stepfork runtime dependency.

## Generated test

The generated file is produced from a fixed, reviewed template. Trace payloads
are never interpolated into executable code: only sanitized JSON literals,
relative paths, and the entrypoint specification are embedded. No `eval` or
`exec` is used on trace data.

```python
from stepfork.export.runtime import run_regression_case

TRACE_PATH = ...
ENTRYPOINT = "examples.booking_agent:run_agent"
EXPECTATION = {"destination": "Lisbon", "selected_flight": "B", ...}
HAS_EXPECTATION = True


def test_stepfork_regression_failure() -> None:
    run_regression_case(...)
```

`run_regression_case` loads the frozen trace, resolves the entrypoint, replays
it, verifies that every recorded dependency call was consumed, and compares the
returned value to the expectation. Any divergence raises an actionable
`AssertionError`, for example:

```
AssertionError: behavior mismatch at 'selected_flight': expected "B", got "A"
```

## End-to-end example

`examples/booking_agent/demo.py` runs the full workflow (record, validate,
inspect, frozen replay, diff, export, pytest) and proves that the generated test
fails on the buggy agent and passes on the fixed one:

```bash
uv run python examples/booking_agent/demo.py
```
