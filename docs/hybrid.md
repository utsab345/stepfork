# Hybrid replay foundation

Hybrid replay is an opt-in Python API for evaluating a changed LLM request
against reviewed output and trajectory expectations. It is **not deterministic**:
the selected model runs again and can produce a different response. It may
incur network traffic, token cost, and model latency.

```python
from stepfork import ReplaySession
from stepfork.assertions import assert_tool_not_called

with ReplaySession.from_trace(
    "failure.sftrace", mode="hybrid", live_llms={"openai/gpt-example"}
) as replay:
    result = run_agent_with_changed_prompt()
    replay.verify_complete()

assert result == {"approved": True}  # reviewed expectation
assert_tool_not_called(replay, "charge_card")
assert [call.action for call in replay.executed_calls] == [
    "executed", "substituted"
]
```

The example labels and expected output are illustrative. The live LLM label
must exist in the trace and is the recorded `provider/model` pair (or the model
name when no provider was recorded). The caller supplies the actual model
client. Stepfork does not create a client or perform a network request on its
own. Frozen replay remains the default.

Hybrid replay checks the selected LLM's provider and model but permits its
request input to change. It checks that the stored original input fingerprint
is valid, then runs the selected LLM body. All tool calls remain frozen and
must match their recorded names, arguments, and order. A new or reordered tool
call raises before the instrumented tool body executes. Uninstrumented calls
and side effects remain outside Stepfork's control.

`replay.executed_calls` and `replay.matched` mark each response as `executed`
or `substituted`. For live calls, `ExecutedCall.status` is `None` because the
recorded status does not describe the new response. Catching a replay mismatch
does not make trajectory assertions valid.

For an executable reviewed test, use `run_regression_case(..., mode="hybrid",
live_llms={...}, expectation=..., trajectory_expectation=...)` or pass the same
arguments to `generate_pytest_source`. Keep live tests outside ordinary CI
unless their provider is a deterministic fake; real-model evaluations have
variable cost, latency, and behavior.

This foundation does not allow live tools in hybrid mode. It does not fork at a
trace step, choose individual repeated LLM occurrences, or realign a changed
tool path to a different recorded response. Those features need a separate
reviewed design. The older `mode="live"` API re-executes matching LLM calls.
Matching tools require an explicit `allow_live_tools` name allowlist; see
[live-tool authorization](replay.md#modes). Authorized tools can cause real
side effects. Neither live nor hybrid replay is deterministic.
