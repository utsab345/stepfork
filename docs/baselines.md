# Behavioral baselines

Named baselines keep reviewed `.sftrace` bundles in a local directory so
subsequent runs can be compared in tests or CI. Stepfork stores the original
trace format under `.stepfork/baselines/`; it does not introduce a database or
rewrite trace data.

## Save and inspect a baseline

Save a known-good, completed trace:

```bash
stepfork baseline save orders-v1 known-good.sftrace
stepfork baseline list
stepfork baseline show orders-v1
```

By default, baselines live under `.stepfork/baselines/`. Pass
`--directory PATH` to use another local store. Names must be lowercase and
contain only letters, digits, dots, underscores, or hyphens; names start with
a letter or digit, are limited to 64 characters, and cannot be reserved
Windows device names.

Saving never replaces an existing name. To approve a behavior change, save it
under a new reviewed name and update the baseline selected by CI. Do not copy
a candidate over a baseline without reviewing its behavior.

## Compare a candidate

Record a candidate run with the same deterministic inputs and compare it:

```bash
python record_agent.py --output candidate.sftrace
stepfork baseline compare orders-v1 candidate.sftrace
```

Comparison uses Stepfork's ordered behavioral diff: instrumented tool and LLM
calls, their inputs and outputs, errors, state changes, and final run output.
Timestamps, event IDs, run IDs, and durations do not affect equivalence.

The default `--max-changes 0` fails on any changed, added, or removed behavior
step. A non-negative `--max-changes N` allows up to N such steps; it is a
step-count threshold, not a percentage or a measure of output quality. Prefer
the default for a regression gate. `--json` emits a sanitized report.

Exit codes for `baseline compare`:

- `0`: changes are within the configured threshold.
- `1`: the threshold was exceeded.
- `2`: missing, corrupt, incompatible, or unreadable baseline/candidate.

No model or tool code is executed by `baseline compare`; it only reads and
compares traces. Recording a candidate can call external services, so use
deterministic fakes or frozen replay where possible. Exact comparison of live,
nondeterministic model output is not a reliable quality evaluation.

## GitHub Actions

The repository includes a complete offline example at
`.github/workflows/baseline-regression.yml`. It loads a reviewed baseline,
runs an integration test, records the deterministic quickstart agent, and
fails the job if the candidate differs. The fake tool needs no provider
credentials and makes no network request.

To adapt the workflow, commit a reviewed known-good trace, replace the
quickstart recording command with your deterministic candidate recording
command, and keep `baseline compare` as the CI gate. The candidate must be a
complete, integrity-verified `.sftrace` bundle.

## Compatibility, security, and limitations

- Baseline operations accept strict, complete traces using schema `0.1` with
  verified integrity metadata. Unsupported schema versions, legacy bundles
  without integrity metadata, symlinks, and corrupted bundles are rejected.
- The recorded Stepfork version is shown for diagnosis; compatibility is
  determined by the trace schema, not by requiring an identical package
  version.
- Integrity hashes detect changes to payloads when the integrity record is
  trusted; they are not signatures. A party able to edit both can recompute
  them.
- Redaction is best-effort. Review traces before committing or sharing them;
  they can contain prompts, tool inputs, outputs, and other sensitive data.
- Baselines are data, not a sandbox. Comparison does not execute trace or
  entrypoint code, but candidate recording runs your application with its
  configured privileges.
- Step alignment is ordered and exact. A changed call sequence can produce
  several changed steps; a threshold does not make nondeterministic behavior
  deterministic.

## CLI reference

```text
stepfork baseline save NAME TRACE [--directory PATH]
stepfork baseline list [--json] [--directory PATH]
stepfork baseline show NAME [--json] [--directory PATH]
stepfork baseline compare NAME CANDIDATE [--max-changes N] [--json] [--directory PATH]
```
