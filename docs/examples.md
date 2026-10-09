# Examples

Five runnable, fully offline example agents ship in this repository. No API
keys, no network access: each uses a fake provider that stands in for a real
model or service, so the demos are deterministic and repeatable.

Clone the repository and sync dependencies once:

```bash
git clone https://github.com/utsab345/stepfork.git
cd stepfork
uv sync
```

## Quickstart agent

`examples/quickstart` is the minimal entry point. A single tool
(`order_status`) and a single decision (should we notify the customer?). The
buggy implementation only notifies when an order is delivered; the fix
notifies when it is shipped.

```bash
uv run python examples/quickstart/demo.py
```

```text
DEMO COMPLETE: failure -> frozen trace -> regression test
   buggy agent: FAIL (rc=1), fixed agent: PASS
```

See
[the quickstart README](https://github.com/utsab345/stepfork/blob/main/examples/quickstart/README.md)
for the files and the workflow it demonstrates.

## Booking agent

`examples/booking_agent` pairs a fake LLM provider with a flight-search tool.
The agent plans a trip and books the wrong flight. The demo records the buggy
run, freeze-replays it without touching the search tool, diffs it against the
corrected run, and exports a regression test.

```bash
uv run python examples/booking_agent/demo.py
```

## Refund agent

`examples/refund_agent` pairs a fake LLM provider with a refund-policy-check
tool. The agent misreads the policy and denies an eligible refund. The demo
runs the full pipeline: record both sides, validate with integrity, replay
frozen, diff, and export a regression test that denies the buggy run and
approves the fixed one.

```bash
uv run python examples/refund_agent/demo.py
```

## OpenAI SDK-style adapter

`examples/openai_chat` exercises the optional OpenAI Python SDK adapter through
a fake OpenAI-shaped synchronous client. It records a chat-completions response,
replays it without executing the SDK call, and exports a regression test for a
buggy sentiment decision.

```bash
uv run python examples/openai_chat/demo.py
```

## LangGraph agent

`examples/langgraph_agent` builds a real LangGraph `StateGraph` around a refund
triage decision and wires it to Stepfork through the optional
`stepfork.integrations.langgraph` adapter. The buggy node inverts the refund
eligibility comparison. The demo records the buggy run, freezes and replays it
with zero model and tool executions, diffs it against the corrected run, and
proves the exported regression test fails for the buggy agent and passes for
the fixed one.

```bash
uv run python examples/langgraph_agent/demo.py
```

See
[the LangGraph guide](https://github.com/utsab345/stepfork/blob/main/docs/langgraph.md)
and the example README for details.

## What every demo proves

All five demos end with the same assertions:

- the buggy implementation FAILS the generated regression test,
- the corrected implementation PASSES the same test,
- frozen replay never executed any external dependency call.

The demos print real results from real subprocesses; they never fabricate
output.
