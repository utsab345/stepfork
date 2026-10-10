# Your LLM Was Right. Your Agent Still Shipped the Wrong Answer.

A real-model case study in which a correct model answer was silently corrupted
by ordinary application code - and Stepfork turned that regression into a
deterministic pytest test that replays offline.

Full example:
[`examples/real-llm-case-study`](https://github.com/utsab345/stepfork/tree/main/examples/real-llm-case-study).
Full write-up:
[CASE_STUDY.md](https://github.com/utsab345/stepfork/blob/main/examples/real-llm-case-study/CASE_STUDY.md).

!!! warning "What is synthetic and what was real"
    The incident, the service health, the deployments, and the runbook are
    **synthetic fixtures**. The application bug was **intentionally
    introduced**. The **provider request was real**: one live call to
    `gemini-2.5-flash` through the Google Gemini API using Stepfork's OpenAI
    SDK adapter (`stepfork[openai]==0.1.0a6`, used unmodified). Every number in
    the case study is an observed result.

## 1. The synthetic incident

The agent reads a short incident report:

> "A production API is returning HTTP 500 errors for most customers. Error
> rates increased sharply after a deployment, and the payment checkout endpoint
> is failing."

It consults three deterministic tools backed by local JSON fixtures -
`lookup_service_health`, `get_recent_deployments`, and `fetch_incident_runbook`
- then asks the model for a structured triage and applies a severity policy
written in code, independent of the model output. The fixtures make the correct
answer unambiguous: `checkout-api` is `down`, customer-facing, tier-0, with a
72% error rate; a deployment landed 42 minutes ago; and the runbook says
widespread production checkout failure is P0 and requires escalation.

## 2. The real Gemini response

One real request to `gemini-2.5-flash` returned `severity: "P0"` with a
`recommended_next_action` to declare P0, page the payments on-call, and prepare
a rollback. The model was right on its own, and the policy floor independently
agreed. The request and the verbatim response are recorded in the committed
trace.

## 3. The deterministic Python bug

After the policy floor runs, a deployment-correlation helper treats a recent
deployment as "known and handled" and overwrites the result:

```python
if recent:
    decision["severity"] = "P1"
    decision["escalation_required"] = False
```

The run **completes successfully** - valid JSON, no exception - so a
"did the agent crash?" check passes while a policy-mandated P0 silently
degrades to a quiet P1. This is the regression class that outcome-blind tests
miss.

## 4. Recording with Stepfork

Recording wraps the existing entrypoint in one context manager. Inside it,
Stepfork captures every instrumented boundary: the five tool calls made through
`@trace_tool` and the model request/response through the adapter. The resulting
`.sftrace` bundle is plain JSON with SHA-256 integrity digests and no
credentials. The committed trace has 14 events: 5 tool calls and 1 LLM
request/response.

## 5. Frozen replay

Frozen replay reruns the entrypoint while Stepfork answers every recorded
dependency from the trace. Failure-fast counters prove the guarantees: the
instrumented tool **bodies never execute** and the model is **never contacted**.

```text
tool_body_executions : 0
live_llm_attempts    : 0
matched              : 6   (5 tools + 1 LLM, all substituted)
```

## 6. Red-to-green regression testing

The expected business outcome is defined separately from any Stepfork output in
`expected.json`. `stepfork export --pytest` generates a test that replays the
trace against `agent:run_incident_agent` and asserts that outcome. Against the
buggy logic it fails on a semantic field:

```text
AssertionError: behavior mismatch at 'escalation_required':
    expected true, got false
```

After a one-function fix, the **same test against the same trace** passes. No
trace was regenerated and no model call occurred.

## 7. Strict tool trajectory checking

Frozen replay is strict about *how* dependencies are called, not only the final
answer. Reordering two tool calls is rejected before the divergent tool body
runs, and changing a tool argument is rejected too - both raise
`ReplayMismatchError`. A harmless refactor that preserves every call, argument,
order, and prompt payload still passes. This trajectory verification is
separate from outcome verification.

## 8. Reproduce it, offline and for free

The committed trace makes the whole case study reproducible with no API key and
no network for the agent itself:

```bash
cd examples/real-llm-case-study
uv sync --locked --extra test
uv run python -m pytest -q
uv run python scripts/verify_frozen.py
uv run stepfork validate traces/incident-triage.sftrace --verify-integrity
```

Red-to-green, without touching the trace or the test:

```bash
cp snapshots/agent_buggy.py agent.py
uv run python -m pytest -q tests/test_incident_regression.py   # 1 failed
cp snapshots/agent_fixed.py agent.py
uv run python -m pytest -q tests/test_incident_regression.py   # 1 passed
```

## 9. Limitations

- **Stepfork does not judge correctness.** The expected outcome lives in
  `expected.json`, defined by a human; the tool does not automatically know the
  right business answer. The recorded response is what replay uses, so the test
  would pass a wrong model output just as readily.
- **Frozen replay substitutes only instrumented dependencies** - the
  `@trace_tool` boundaries and the recorded LLM boundary.
- **Replay is not a sandbox.** Uninstrumented code, file access, time,
  `random`, and environment side effects still execute under replay with your
  privileges.
- **Replay diffs against the recorded output.** Because the recording captured
  the buggy P1 result, the CLI's `stepfork replay --mode frozen` reports
  `DIVERGED` for the fixed agent. That is correct and expected: the generated
  pytest test asserts against the independently specified `expected.json`. The
  fixed agent can therefore differ from the buggy trace's recorded final output
  even when the exported pytest test passes.
- The optional hybrid prompt comparison is a two-sample anecdote, not evidence
  that a prompt change improves model quality.
