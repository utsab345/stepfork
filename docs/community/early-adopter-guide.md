# Early Adopter Guide

Thank you for trying Stepfork before v1.0. This guide explains how to use it
with your own agent, what to expect from the alpha, and how to send feedback
that is easy to act on.

Stepfork is experimental. The API, CLI, and `.sftrace` format may change before
v1.0, and some capabilities you might expect are intentionally not implemented
yet.

## What Stepfork is (and is not)

Stepfork is a local-first tool for turning a failed agent run into a pytest
regression test. It records instrumented tool and LLM calls, replays them with
dependencies frozen, diffs corrected behavior against the recording, and
exports a test that fails on the buggy code and passes on the fix.

It is **not**:

- an observability platform or hosted service,
- a sandbox (replay runs your own code with your own privileges),
- an automatic minimizer (the exported test uses the full recorded run; see the
  [roadmap](https://github.com/utsab345/stepfork/blob/main/README.md#roadmap)),
- a framework integration layer (the OpenAI Python SDK and LangGraph adapters
  are optional add-ons; OpenAI Agents and MCP support are planned. See
  [Integrations](../integrations.md)).

## Install the alpha

Stepfork is on PyPI. Install the current alpha:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --pre stepfork
pip install pytest
stepfork --version
```

The `--pre` flag is required while Stepfork is a pre-release. Alternatively,
install the tagged repository build:
`pip install "git+https://github.com/utsab345/stepfork.git@v0.1.0a6"`.

Requires Python 3.11, 3.12, or 3.13.

## Instrument your own agent

Two boundaries are instrumented: tools and LLM requests. Wrap each external
dependency you want recorded and frozen.

```python
from stepfork import llm_request, record, trace_tool


@trace_tool(name="search_flights")
def search_flights(destination: str, budget: int) -> list[dict]:
    return flights_api.search(destination, budget)


def run_agent(prompt: str) -> dict:
    proposals = search_flights("Lisbon", 400)
    reply = llm_request(
        provider="openai",
        model="gpt-4o-mini",
        input={"messages": [{"role": "user", "content": prompt}]},
        call=lambda: client.chat(prompt),
    )
    return {"proposals": proposals, "message": reply}


with record("my-agent", output="failure.sftrace") as session:
    session.set_output(run_agent("Book the cheapest flight to Lisbon"))
```

Everything outside `@trace_tool` and `llm_request` runs as ordinary Python.
If you call an external service outside those boundaries, it is neither
recorded nor frozen. Wrap every dependency you want covered.

## Try the full loop on a real failure

```bash
# 1. Reproduce a real buggy run and record it (failure.sftrace).
python my_agent.py

# 2. Inspect and verify the bundle.
stepfork inspect failure.sftrace
stepfork validate failure.sftrace --verify-integrity

# 3. Freeze-replay it: instrumented dependencies are not called again.
stepfork replay failure.sftrace --entrypoint my_agent:run_agent --mode frozen

# 4. Fix the agent, then diff the corrected behavior.
stepfork diff failure.sftrace fixed.sftrace

# 5. Turn the failure into a regression test.
stepfork export failure.sftrace --pytest \
  --entrypoint my_agent:run_agent \
  --expect-output expected.json \
  --output test_my_agent_regression.py --overwrite
python -m pytest -q test_my_agent_regression.py
```

Adjust the entrypoint to the module and function that triggers the run. See
the [CLI reference](../cli.md) for every command and its exit codes.

## Before you share a trace

Traces can contain real inputs and outputs. Redaction is best-effort and runs
at record time, so review a bundle before sending it anywhere:

```bash
stepfork inspect failure.sftrace --events   # review payloads
```

Never attach credentials, tokens, or private user data. When in doubt, share a
small synthetic reproduction instead of a real trace. See
[Security notes](../security.md) for the full model.

## How to report feedback

Open an issue at
[github.com/utsab345/stepfork/issues](https://github.com/utsab345/stepfork/issues)
using the bug report or documentation template. A useful report includes:

- Stepfork version (`stepfork --version`) and Python version,
- operating system,
- the exact commands you ran and their full output,
- the smallest reproduction you can share (a synthetic trace and entrypoint
  are ideal),
- whether the problem is a wrong result, a crash, a confusing error, or a
  documentation gap.

If you cannot share a trace, describe the event sequence (`stepfork inspect
--events`) with secrets removed.

## What feedback is most valuable now

- Real agents where instrumentation was awkward or where a failure could not
  be frozen.
- Frozen replay diverging from a recording you believe is deterministic.
- Export tests that failed for reasons other than the expected behavior
  mismatch.
- Cases where redaction missed something it should have caught.
- Anything the documentation claims that does not match what you observed.
  Accuracy matters more than optimism in the alpha.

We especially want to know about framework usage. The OpenAI Python SDK and
LangGraph adapters are available now, and your instrumentation patterns will
shape the remaining integrations (see [Integrations](../integrations.md)).
