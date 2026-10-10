# Results

Actual, observed outcomes from this case study. No numbers are fabricated; the
supporting outputs are captured in `evidence/`.

## Provider and model

| Item | Value |
| --- | --- |
| Provider | Google Gemini API (AI Studio), OpenAI-compatible endpoint |
| Model | `gemini-2.5-flash` |
| Integration | `stepfork[openai]==0.1.0a6` OpenAI SDK adapter |
| Package | `stepfork==0.1.0a6` from PyPI, used unmodified |
| Access | `GEMINI_API_KEY` kept in gitignored `.env`, never printed |

## Real request count

Exact cap seen: **3 real requests**, matching the approved plan (1 recording,
2 optional hybrid evaluations).

| # | Purpose | Prompt tokens | Completion tokens | Total tokens | Output-side (incl. thinking) |
| --- | --- | --- | --- | --- | --- |
| 1 | Record buggy run | 854 | 311 | 1584 | 730 |
| 2 | Hybrid baseline prompt | 854 | 196 | 2093 | 1239 |
| 3 | Hybrid revised prompt | 884 | 248 | 2018 | 1134 |

Notes: `total_tokens` includes Gemini 2.5 "thinking" tokens billed as output.

## Estimated cost

Using Gemini 2.5 Flash list pricing ≈ $0.30 / 1M input tokens and $2.50 / 1M
output tokens (output-side = total − prompt):

- Request 1: 854 × 0.30/1e6 + 730 × 2.50/1e6 ≈ $0.00208
- Request 2: 854 × 0.30/1e6 + 1239 × 2.50/1e6 ≈ $0.00335
- Request 3: 884 × 0.30/1e6 + 1134 × 2.50/1e6 ≈ $0.00310
- **Total ≈ $0.0085** (well under the $0.50 maximum budget)

Uncertainty: current tier pricing may differ, thinking-token billing may vary,
and the account may have a free-tier allowance. These are estimates only.

## Trace bundle (`traces/incident-triage.sftrace`)

`stepfork validate --verify-integrity` → `Structure: PASS`, `Integrity: VERIFIED`
(manifest, events, redactions all verified).

- Events: **14** (run_start, 5× tool_call, 5× tool_result, 1× llm_request,
  1× llm_response, run_end)
- Dependency calls: **6** (5 tools + 1 LLM)
- Recorded LLM label: `openai/gemini-2.5-flash`
- Raw model severity in the recording: **P0** (the model was correct)
- Buggy final output: severity **P1**, escalation **false**
- Secret scan of the bundle: no credential-shaped strings found

## Red → green

Established with the **same generated test** (`tests/test_incident_regression.py`)
and the **same trace**, differing only in `agent.py`.

- **Red** (buggy snapshot `snapshots/agent_buggy.py`): `1 failed`
  - `AssertionError: behavior mismatch at 'escalation_required': expected true, got false`
- **Green** (fixed `agent.py`): `1 passed`

The application fix (`fix.diff`, copied to `evidence/fix.diff`): the
deployment-correlation post-processor no longer overwrites severity; the policy
floor stands.

## Frozen replay verification

`scripts/verify_frozen.py` (and `tests/test_frozen_replay_guards.py`):

- Instrumented tool bodies executed: **0**
- Live LLM attempts: **0**
- Dependency calls matched: **6**, all `substituted`
- Reproduced outcome with the fix: P0 + escalation
- No API key needed; runs offline.

`tests/test_scenario_b_divergence.py` additionally proves the divergent tool
body does not execute (`tool_bodies_executed: 0`).

CLI nuance (verified in `evidence/clean_install_verification.txt`, section 6):
`stepfork replay --mode frozen` diffs the entrypoint output against the
*recorded* outcome. Because the recording captured the buggy output (`P1` /
escalation false), replaying the **fixed** agent reports `Status: DIVERGED` at
`escalation_required` - correct, and proof that the bug was captured. The
generated pytest test, by contrast, asserts against the corrected
`expected.json`, which is the regression workflow.

## Divergence results

| Change | Replay result |
| --- | --- |
| Harmless refactor (Scenario A, `scenario_a.py`) preserving calls, order, args, prompt, result | frozen regression **passes** |
| Reordered tool calls (Scenario B) | `ReplayMismatchError: call #1: expected tool 'lookup_service_health' but the agent called 'get_recent_deployments'` |
| Changed tool argument `window_minutes=60 → 120` (Scenario B) | `ReplayMismatchError: call #3: tool 'get_recent_deployments' input diverged from the recording` |

No Stepfork strictness settings were modified for these runs.

## Hybrid comparison (optional, Section 9)

`scripts/hybrid_prompt_comparison.py` ran the recorded incident under hybrid
replay: tools frozen and strictly matched, the named LLM boundary live
(`mode="hybrid"`, `live_llms={"openai/gemini-2.5-flash"}`).

- Baseline prompt → raw model severity **P0**
- Revised prompt → raw model severity **P0**
- Tool bodies executed: 0 in both runs.

One sample per prompt does not establish improvement; Stepfork does not improve
model quality. Both fixtures are in `evidence/hybrid_comparison.json`.

## Observations and integration notes for Stepfork

These are v0.1 integration observations. None of them required modifying
Stepfork, and none affect the frozen-replay results above.

1. **Token usage is present in the trace payload but not in structured fields.**
   The OpenAI adapter records the full response payload, so
   `traces/incident-triage.sftrace` contains `output.usage` with the exact
   tokens (`prompt_tokens: 854`, `completion_tokens: 311`,
   `total_tokens: 1584`). However, the adapter never copies that usage into the
   trace's structured token fields; `LLMResponse.prompt_tokens`,
   `completion_tokens`, `total_tokens`, and `cost_usd` are all `None`, so
   Stepfork's own inspection surfaces do not expose usage. We reported usage
   from the live response object instead.
2. **Provider label is always `openai`.** The adapter hardcodes
   `provider="openai"`, so a Gemini call is labeled `openai/gemini-2.5-flash` in
   the trace. Mildly misleading, but consistent and replayable.
3. **Client construction runs during frozen replay.** Frozen replay does not
   execute the instrumented LLM call (the SDK method is never invoked), but the
   application code that builds the client still runs before the adapter call.
   Most client constructors make no network request; ours would, because the
   Vertex factory refreshes Google ADCs to mint a token at construction time.
   That is why `provider.py` returns a tripwire stand-in under frozen replay
   and a live client under hybrid replay.
4. **Hybrid vs frozen must be distinguished in client factories** (frozen →
   tripwire, hybrid → live client for the selected model).

## Limitations and skipped work

- Streaming, Responses API, and the OpenAI Agents SDK are not supported by the
  v0.1 OpenAI adapter.
- Frozen replay does not intercept uninstrumented code, time, files, random, or
  arbitrary side effects; replay is not a sandbox.
- Statistical prompt-evaluation was not attempted; two samples are anecdotal.
- No uncontrolled agent loops; strictly 3 requests.

## Final evaluation

- Published Stepfork package worked without modification when installed from
  PyPI: **yes**
- Real model response successfully recorded: **yes** (Gemini `gemini-2.5-flash`)
- Frozen replay made zero additional provider calls: **yes** (counters + tripwire)
- Generated pytest failed on the bug: **yes** (`escalation_required` mismatch)
- Same test passed after the fix: **yes**
- Strict divergence detection: **yes** (order and argument changes detected)
- Total real-model requests / estimated cost: **3 / ≈ $0.009**
- Case study ready for public publication: **yes** (see `CASE_STUDY.md`)

Nothing was committed, pushed, tagged, or published.