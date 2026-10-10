# Evidence files

These files capture the observed outputs from the runs described in
`RESULTS.md`. They are kept as-is from real runs; do not edit the factual
content.

- `red_failure.txt` - the generated regression test failing against the buggy
  snapshot (`1 failed`, `AssertionError: behavior mismatch at
  'escalation_required': expected true, got false`).
- `green_pass.txt` - the same test passing against the fixed `agent.py`.
- `full_suite.txt` - `pytest -q` over the whole suite.
- `frozen_replay.txt` - `scripts/verify_frozen.py` output (zero live calls).
- `divergence.txt` - Scenario B strict-replay mismatch errors.
- `hybrid_comparison.json` - Section 9 hybrid baseline/revised results.
- `fix.diff` - a copy of the root `fix.diff` (buggy snapshot -> fixed agent).

Note: `red_failure.txt` comes from a real `pytest` run, so the traceback shows
the absolute repository root of the machine it was captured on. The path has
been normalized to `<repo>` for publication; the assertion and failure text are
unchanged.

`clean_install_verification.txt` is the log of an independent offline run inside
a fresh virtual environment with provider credentials removed. It references a
temporary directory that is specific to the verification machine; treat those
paths as local only.