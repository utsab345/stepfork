# Your LLM Was Right. Your Agent Still Shipped the Wrong Answer.

*A real-model case study: how Stepfork turned an agent regression into a
deterministic pytest test.*

- **Scenario:** a synthetic IT incident-triage run recorded against a **real
  Google Gemini request**.
- **The twist:** the model was correct (it said **P0**). A three-line
  deterministic bug in ordinary Python post-processing then downgraded the
  output to **P1** and cleared escalation.
- **The fix:** one recorded trace, one generated pytest test. Red before the
  fix, green after, zero further model calls.

Nothing here is a simulation of a real outage: the incident, the service
health, the deployments, and the runbook are **synthetic fixtures**. The bug is
also synthetic, introduced on purpose into the agent's code. What was real is
the **provider request** - one live call to `gemini-2.5-flash` through the
Google Gemini API - and every number in this article is what actually happened.

---

## 1. The incident-triage problem

Small teams build agents that read an incident report, look things up, and
answer: what happened, what severity (P0-P3), which services, what next action,
does it need escalation, and what evidence supports that.

The recorded scenario uses this report:

> "A production API is returning HTTP 500 errors for most customers. Error
> rates increased sharply after a deployment, and the payment checkout endpoint
> is failing."

The agent consults three deterministic, safety-only tools backed by local JSON
fixtures - `lookup_service_health`, `get_recent_deployments`,
`fetch_incident_runbook` - then asks the model for a structured triage, and
finally applies a severity policy written in code, independent of model output.

The fixtures make the correct answer unambiguous:

- `checkout-api` is `down`, `customer_facing`, `tier-0`, error rate `0.72`;
- a deployment to `checkout-api` happened 42 minutes ago;
- the runbook states "Widespread production checkout failure is P0 and
  requires escalation."

The policy floor therefore forces P0 regardless of what the model says. The
model was never the deciding factor - and yet it *still* returned P0 on its
own.

## 2. The application bug

After the policy floor runs, a deployment-correlation function tries to be
helpful. The buggy version (`snapshots/agent_buggy.py`, exact code):

```python
def _correlate_recent_deployment(
    decision: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    recent = (
        evidence["deployments"]
        .get(INCIDENT["primary_service"], {})
        .get("recent_deployment", False)
    )
    if recent:
        decision["severity"] = "P1"
        decision["escalation_required"] = False
    return decision
```

A recent deployment was treated as evidence that the incident is "known and
handled", so severity was overwritten and escalation disabled. Classic
incident-time heuristic: it made sense for the one case it was typed for, and
silently corrupted every conflicting case. The agent run **completes
successfully** - valid JSON, no exception - but a P0 that should page the
payments on-call becomes a "quiet" P1.

That is the regression class unit tests miss: no crash, just wrong business
semantics. This is why the test has to be pinned to the *outcome*, not to "did
it finish".

## 3. What Gemini actually returned

One real request: `gemini-2.5-flash`, temperature 0, via the Google Gemini API
(OpenAI-compatible endpoint) through Stepfork's OpenAI SDK adapter
(`stepfork[openai]`, `stepfork==0.1.0a6` from PyPI, used unmodified).

The response is recorded verbatim in the trace. The JSON content:

```json
{
  "summary": "The production checkout-api is experiencing widespread HTTP 500 errors, with a 72% error rate, making it unavailable for most customers. This issue started shortly after a recent deployment to the checkout-api. The payments-api, a downstream service, is also degraded with elevated error rates.",
  "severity": "P0",
  "affected_services": ["checkout-api", "payments-api"],
  "recommended_next_action": "Declare P0, page the payments on-call team, open an incident channel, and notify customer support. Investigate the recent deployment to checkout-api (version checkout-2026.10.10-3) as a potential cause and prepare for a rollback after incident commander approval.",
  "supporting_evidence": [
    "checkout-api status is 'down' with 0.61 availability and 0.72 error_rate.",
    "checkout-api is customer_facing and tier-0.",
    "POST /checkout returns HTTP 500 for most customers.",
    "A deployment to checkout-api occurred 42 minutes ago.",
    "payments-api status is 'degraded' with 0.88 availability and 0.41 error_rate.",
    "payments-api is customer_facing and tier-0, with elevated timeouts on capture.",
    "Runbook states 'Widespread production checkout failure is P0' and 'If most customers cannot complete checkout, declare P0 and page the payments on-call.'"
  ]
}
```

The model said P0. So the correct answer came from the model, the policy floor
agreed, and then the bug downgraded it to P1 and cleared escalation.

Usage for the recording: 854 prompt tokens, 311 completion tokens, 1584 total
(including Gemini "thinking" output). Full request and response are in
`traces/incident-triage.sftrace`.

## 4. How Stepfork recorded the real interaction

Recording wraps the existing entrypoint in one context manager
(`scripts/record_incident.py`):

```python
TRACE_PATH = ROOT / "traces" / "incident-triage.sftrace"

with record(
    "incident-triage-agent",
    output=TRACE_PATH,
    overwrite=True,
    run_input={"incident_id": agent.INCIDENT["incident_id"]},
) as session:
    result = agent.run_incident_agent()
    session.set_output(result)
```

While inside `record`, Stepfork captures every instrumented boundary: the tool
calls made through `@trace_tool` and the LLM request/response through the
adapter. The `.sftrace` bundle is just JSON files - no credentials, no SDK
needed to read it.

```text
Trace     traces/incident-triage.sftrace
Events    14        (5 tool calls, 1 LLM request/response)
Status    COMPLETED
Integrity: VERIFIED
```

The bundle records the tool-call trajectory (names, arguments, outputs,
order), the full LLM prompt and response, redaction entries, and SHA-256
integrity digests.

## 5. Frozen replay: replay the run, skip the model

Stepfork's frozen replay is strict and local: the entrypoint runs again, but
every recorded dependency boundary is answered from the trace. Tool bodies are
**not** executed and the model is **never** contacted.

We prove it with two fail-fast counters. `TOOL_BODY_EXECUTIONS` is incremented
inside the bodies of the instrumented tools, and `LIVE_LLM_ATTEMPTS` is
incremented by a tripwire client returned whenever frozen replay is active.
`scripts/verify_frozen.py` output:

```text
tool_body_executions : 0
live_llm_attempts    : 0
executed_calls       :
  - tool lookup_service_health    substituted
  - tool lookup_service_health    substituted
  - tool get_recent_deployments   substituted
  - tool get_recent_deployments   substituted
  - tool fetch_incident_runbook   substituted
  - llm openai/gemini-2.5-flash  substituted
matched              : 6
```

Six dependency responses came from the trace, all substituted. Replay produced
the fixed outcome (P0, escalation true) and made zero live calls.

### Why client construction is replay-aware

A precise distinction matters here. Frozen replay does **not** execute the
instrumented LLM request - the SDK `chat.completions.create` method is never
called. But your application code still runs, and the agent calls
`build_client()` before making the "LLM call" adapter call. Building a client
object is not the same as making a network request; most OpenAI-style
constructors just store an API key.

Some client factories do touch the network during initialization. Our Vertex
provider (`provider.py`) refreshes Google Application Default Credentials at
construction time, which mints a token. If that ran during frozen replay,
"offline replay" would quietly reach the network. So `provider.py` returns a
tripwire stand-in whenever a replay session is active, and only constructs a
live client for hybrid replay. No Stepfork code needed to change for this.

## 6. The generated pytest test caught the regression

The expected business outcome is defined separately from any Stepfork output,
in `expected.json` (excerpt):

```json
{
  "incident_id": "INC-2026-1010-001",
  "severity": "P0",
  "escalation_required": true,
  "affected_services": ["checkout-api", "payments-api"]
}
```

Stepfork never guesses this. The human defined it, informed by the model's
correct answer, the policy floor, and the evidence.

Exporting the regression test is one CLI call:

```bash
stepfork export traces/incident-triage.sftrace --pytest \
  --entrypoint agent:run_incident_agent \
  --expect-output expected.json \
  --output tests/test_incident_regression.py --overwrite
```

The generated test replays the trace against `agent:run_incident_agent`,
compares the return value against `expected.json`, and named the exact business
field that regressed:

```text
1 failed in 0.17s

E   AssertionError: behavior mismatch at 'escalation_required':
    expected true, got false
```

An assertion about a *semantic field*, not a stack trace from a crash, and the
red run cost nothing.

## 7. The fix turned the same test green

The fix is one function (`agent.py`, exact code):

```python
def _correlate_recent_deployment(
    decision: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    """Record deployment correlation without overriding the severity policy.

    FIX: a recent deployment is useful rollback context, but it must never
    lower the severity enforced by the independent policy floor. ...
    """
    return decision
```

A deployment is rollback context, not a license to override severity. The full
diff is in `fix.diff`; it touches only that function.

Rerun the **same test** against the **same trace**:

```text
1 passed in 0.15s
```

Same recorded model response, same tool outputs, same prompt. Only the
deterministic application logic changed, and the outcome flipped P1 -> P0. No
trace was regenerated, and no model call occurred.

## 8. Strict replay detects trajectory changes

Frozen replay is strict about *how* dependencies are called, not just that the
final answer matches. Two scenarios test this honestly (`scenario_b.py`,
asserted in `tests/test_scenario_b_divergence.py`):

- Reordering two tool calls is rejected before the divergent tool body runs:
  `ReplayMismatchError: call #1: expected tool 'lookup_service_health' but the agent called 'get_recent_deployments'`
- Changing a tool argument (`window_minutes: 60 -> 120`) is also rejected:
  `ReplayMismatchError: call #3: tool 'get_recent_deployments' input diverged from the recording`

Meanwhile a harmless refactor that preserves every instrumented call,
argument, order, and prompt payload (`scenario_a.py`) still passes. This is
trajectory verification, separate from outcome verification.

We did not weaken Stepfork's strictness to make the divergence tests behave as
documented.

## 9. What Stepfork actually does not do

- **It does not judge correctness.** The expected outcome lives in
  `expected.json`, defined by you. The model happened to be right; the test
  would have passed a wrong model output too, because the recorded response is
  what replay uses.
- **Frozen replay is not a sandbox.** It freezes *instrumented* boundaries
  (`@trace_tool` and the recorded LLM boundary). Uninstrumented code, file
  access, time, `random`, and environment side effects still execute under
  replay, with your privileges.
- **The hybrid comparison below is anecdotal.** Two samples do not establish
  that a prompt change improves quality, and Stepfork does not improve model
  quality by itself.
- **It only guards what you assert.** If `expected.json` is weak, the test is
  weak.

### Integration notes (v0.1)

Three honest observations from integrating the OpenAI adapter, none requiring
Stepfork changes:

1. The dedicated `llm_response` token fields (`prompt_tokens`,
   `completion_tokens`, `total_tokens`, `cost_usd`) stay `None`. The raw
   recorded payload does contain `output.usage` (854/311/1584 for the
   recording), which is where we read the numbers above.
2. The adapter labels any client-provider call `openai`, so the Gemini call
   shows up as `openai/gemini-2.5-flash` in the trace.
3. As covered in section 5, client construction runs during frozen replay, so
   factories that perform network work at construction time (our Vertex
   token-minting path) must be bypassed with a tripwire.

### Optional: hybrid re-run of the LLM

As a bonus, Stepfork hybrid replay re-runs a *selected* LLM boundary live while
tools stay frozen. We compared the recorded baseline prompt against a revised
prompt that states the severity policy explicitly. Both returned raw P0. Two
samples make no statistical claim about prompt quality, but they do demonstrate
the workflow: evaluate a changed prompt against the same frozen tool
trajectory.

---

## Reproduce it, offline and for free

`RESULTS.md` has the raw numbers; `evidence/` has the captured outputs. Full
reproduction steps and commands are in the README.

```bash
uv sync --extra test        # pins stepfork==0.1.0a6 and pytest==9.1.1
uv run python -m pytest -q            # 7 passed, no keys, no network
uv run stepfork validate traces/incident-triage.sftrace --verify-integrity
uv run python scripts/verify_frozen.py
```

Red -> green, without touching the trace or the test:

```bash
cp snapshots/agent_buggy.py agent.py
uv run python -m pytest -q tests/test_incident_regression.py  # 1 failed
cp snapshots/agent_fixed.py agent.py
uv run python -m pytest -q tests/test_incident_regression.py  # 1 passed
```

Re-recording a new live trace is possible but costs money and is gated behind
`CASE_STUDY_ALLOW_LIVE=1`; the committed trace makes everything in this article
reproducible without it.

This run used exactly **3 real model requests** (about **$0.009** estimated),
kept the key in a gitignored `.env`, and never printed it.

*The agent failed. We made the failure a test.*