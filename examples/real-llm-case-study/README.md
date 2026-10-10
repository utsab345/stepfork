# Stepfork Real-LLM Case Study

A real Google Gemini call is recorded, replayed offline, and turned into a
pytest test that catches a real application bug a crash-check would miss.

The agent was right (the model said **P0**), the policy floor agreed, and three
lines of plain Python post-processing still shipped **P1 without escalation**.
Stepfork `0.1.0a6` (from PyPI, used unmodified) turns that into a
deterministic regression test: red before the fix, green after, zero further
model calls.

Facts: 3 real model requests, about $0.009, 14 recorded events, 5 tool calls,
1 LLM call. See [RESULTS.md](RESULTS.md) and [CASE_STUDY.md](CASE_STUDY.md).

## The bug in one example

For "production API returning HTTP 500s to most customers, checkout endpoint
failing", the correct triage is **P0 with escalation**. The severity policy
says so, and the real Gemini response agreed. Then this ran last:

```python
if recent:
    decision["severity"] = "P1"              # BUG
    decision["escalation_required"] = False  # BUG
```

The run completed successfully (valid JSON, no exception), so a
"did the agent crash?" check would pass. The regression is a business-semantics
failure, the kind unit tests usually miss. `fix.diff` shows the one-function
fix.

## Red to green with the same trace

Both runs use the **same recorded trace** and the **same generated test**
(`tests/test_incident_regression.py`), differing only in `agent.py`:

```text
cp snapshots/agent_buggy.py agent.py
pytest -q tests/test_incident_regression.py
1 failed:
E   AssertionError: behavior mismatch at 'escalation_required':
        expected true, got false

cp snapshots/agent_fixed.py agent.py
pytest -q tests/test_incident_regression.py
1 passed
```

## Quickstart (no API key, no network)

Python 3.13 and [uv](https://docs.astral.sh/uv/) are the only requirements.
The committed trace is self-contained.

```bash
uv sync --extra test
uv run python -m pytest -q                # 7 passed
uv run stepfork validate traces/incident-triage.sftrace --verify-integrity
uv run python scripts/verify_frozen.py    # zero live calls, all 6 substituted
```

Reproduce red -> green safely (this temporarily replaces `agent.py`; restore
it afterward):

```bash
cp agent.py /tmp/agent.py.orig            # save the fixed working copy
cp snapshots/agent_buggy.py agent.py
uv run python -m pytest -q tests/test_incident_regression.py   # 1 failed
cp /tmp/agent.py.orig agent.py            # restore the fixed version
uv run python -m pytest -q tests/test_incident_regression.py   # 1 passed
```

Or just `cp snapshots/agent_fixed.py agent.py` to restore. Do not forget; the
repository's working copy is the fixed one. The two snapshots differ only in
the bug.

## What frozen replay does

Frozen replay reruns `agent:run_incident_agent` while Stepfork answers every
instrumented dependency from the trace:

- The bodies of the three `@trace_tool` functions never execute
  (`TOOL_BODY_EXECUTIONS` stays 0), and the model is never contacted
  (`LIVE_LLM_ATTEMPTS` stays 0).
- Calls, argument order, argument values, and prompt payload must match the
  recording. Reordering a tool call or changing `window_minutes` raises
  `ReplayMismatchError` before the divergent tool body runs
  (`tests/test_scenario_b_divergence.py`); a harmless refactor that preserves
  the trajectory still passes (`tests/test_scenario_a_refactor.py`).
- Replay is strict and local; it is **not** a sandbox, and it only freezes
  instrumented boundaries.

## Recording a real trace (costs money, optional)

The committed trace makes the whole case study reproducible for free. To record
a new trace, put a key in a gitignored `.env` and opt in explicitly:

```bash
set -a; . ./.env; set +a
CASE_STUDY_ALLOW_LIVE=1 CASE_STUDY_LLM_PROVIDER=gemini \
  uv run python scripts/record_incident.py
```

This makes **one** request, writes `traces/incident-triage.sftrace`, and
refuses to run without `CASE_STUDY_ALLOW_LIVE=1`. Re-recording produces a new
trace that will no longer match `expected.json`, so the committed trace is the
publication artifact. Providers: `gemini` (default, `GEMINI_API_KEY`),
`openai` (`OPENAI_API_KEY`), and `vertex` (Google Cloud ADC).

## Project layout

```
agent.py                 agent, tools, severity policy (fixed)
provider.py              replay-aware client construction (never logs secrets, tripwire under frozen replay)
counters.py              fail-fast counters that prove zero live calls
scenario_a.py            harmless refactor (trajectory preserved)
scenario_b.py            divergent variants (trajectory changed)
fixtures/                synthetic service health, deployments, runbooks
expected.json            the correct outcome, defined independently of Stepfork
traces/incident-triage.sftrace   the recorded bundle (and the evidence)
tests/                   generated regression test + guard/scenario tests
scripts/                 record / verify_frozen / hybrid helper scripts
snapshots/               agent_buggy.py and agent_fixed.py (only the bug differs)
fix.diff                 the one-function application fix
evidence/                captured red/green/frozen/divergence/hybrid outputs
```

## Evidence and limitations

- [RESULTS.md](RESULTS.md): real request count and token usage, cost estimate,
  red/green outputs, frozen-replay verification, divergence results, and
  honest notes on Stepfork v0.1 integration.
- [evidence/](evidence/): captured outputs and a copy of `fix.diff`.
- The incident and the bug are **synthetic and intentional**; only the provider
  request was real. `expected.json` was defined by a human after the fact,
  informed by policy and model output - Stepfork does not know the right
  answer.
- The hybrid prompt comparison is a 2-sample anecdote, not evidence that a
  prompt improves quality.

## Links

- Stepfork repository: https://github.com/utsab345/stepfork
- Stepfork documentation: https://utsab345.github.io/stepfork/
- Package: `stepfork==0.1.0a6` on PyPI (`pip install --pre stepfork`)