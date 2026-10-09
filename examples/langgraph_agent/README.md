# LangGraph agent example

This example traces a small LangGraph agent with the optional
`stepfork[langgraph]` extra. It runs entirely offline: a deterministic
scripted chat model stands in for a real LLM, so no API key, network access,
or paid provider call is required.

The agent has two tools, `lookup_customer` and `get_refund_policy`, and a
reproducible behavioral bug: the buggy decision inverts the refund
eligibility comparison.

Run from the repository root:

```bash
uv run python examples/langgraph_agent/demo.py
```

The demo:

1. records the buggy run and the corrected run into `.sftrace` bundles,
2. validates both bundles and verifies their integrity,
3. replays the buggy run under frozen replay with **zero** model or tool
   executions,
4. diffs the buggy and corrected behavior,
5. exports pytest regression tests from the buggy trace, and
6. shows the exported test failing on the buggy agent and passing on the
   corrected agent.

See [`docs/langgraph.md`](../../docs/langgraph.md) for the integration API.
