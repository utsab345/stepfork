# Offline model-decision regression

Run from the repository root:

```bash
uv run python examples/model_decision/demo.py
```

The demo creates `.artifacts/refund_failure.sftrace` and two exported pytest
tests. It records a LangGraph refund workflow whose deterministic fake chat
provider requests a customer lookup, requests the refund policy, and makes the
final decision from the system prompt and tool results. The buggy prompt tells
the provider to approve only amounts above the policy limit; the reviewed
expectation approves the $80 refund under a $100 limit. The corrected prompt
says to approve amounts at or below the limit.

Frozen replay repeats the recorded denial and rejects the changed prompt.
Hybrid replay explicitly runs the fake model again and substitutes both tool
responses. The demo exports a test for each prompt. The buggy test fails and
the fixed test passes. To rerun them individually after the demo:

```bash
uv run pytest -q examples/model_decision/.artifacts/test_refund_buggy.py
uv run pytest -q examples/model_decision/.artifacts/test_refund_fixed.py
```

The fake provider is deterministic and offline. Its passing result validates
Stepfork's replay and assertion mechanics; it does **not** show that a real
model's judgment improved. A real-model run would require a configured client,
network access, tokens, and latency, and its behavior could vary. Hybrid tools
remain frozen; a new tool path raises replay divergence before its instrumented
body runs. Fork-at-step is not implemented.
