# Failure Minimization

Stepfork v0.2 introduces automatic failure minimization using dependency-aware delta debugging. When an AI agent execution fails, minimization helps identify the smallest reproducible trace that preserves the original failure.

## Overview

Minimization takes a failing trace and systematically removes events while verifying that the failure still reproduces. The result is a minimal trace that:

- Preserves the original failure signature
- Maintains all dependency relationships (parent-child event links)
- Includes only the events necessary to reproduce the failure
- Passes structural validation

This makes debugging easier by eliminating irrelevant execution paths and focusing attention on the core failure.

## Quick Start

```bash
# Record a failing execution
python my_agent.py  # Creates failure.sftrace

# Minimize the trace
stepfork minimize failure.sftrace \
    --entrypoint my_agent:run \
    --output minimal.sftrace

# The minimal trace reproduces the same failure with fewer events
stepfork replay minimal.sftrace --entrypoint my_agent:run --mode frozen
```

## How It Works

### 1. Failure Signature Detection

Minimization begins by replaying the original trace to detect its failure signature. The signature captures:

- **Exception type and message pattern** (e.g., `ValueError: invalid flight ID`)
- **Replay divergence type** (e.g., `ReplayMismatchError: tool call order changed`)
- **Output mismatch** (when expected output is provided)

The signature is used throughout minimization to verify that candidate traces preserve the same failure.

### 2. Delta Debugging

Stepfork uses a dependency-aware variant of delta debugging:

1. Start with the full trace
2. Try removing subsets of events (tool calls, LLM requests, state changes)
3. For each subset, add back required parent events automatically
4. Replay the candidate trace and check if it matches the failure signature
5. If the failure still reproduces, keep the smaller trace and continue
6. Repeat with progressively smaller subsets until no further reduction is possible

### 3. Dependency Preservation

Events are connected through `parent_id` relationships. When minimizing:

- If event B has `parent_id = A.id`, removing A would break the trace structure
- The minimizer automatically includes all ancestor events when testing a subset
- `run_start` and `run_end` events are always preserved for structural integrity

### 4. Verification

After minimization completes, the minimized trace is replayed one final time to confirm:

- The failure signature matches the original
- The trace passes structural validation
- No additional events can be removed without losing the failure

## Command Reference

```bash
stepfork minimize <trace> --entrypoint MODULE:FUNCTION [OPTIONS]
```

### Required Arguments

| Argument | Description |
|----------|-------------|
| `<trace>` | Path to the `.sftrace` bundle to minimize |
| `--entrypoint`, `-e` | Agent entrypoint as `MODULE:FUNCTION` |

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--expect-output FILE` | JSON file with expected output for comparison | None |
| `--mode`, `-m` | Replay mode: `frozen`, `live`, or `hybrid` | `frozen` |
| `--output`, `-o` | Path for the minimized `.sftrace` bundle | `<trace>-minimized.sftrace` |
| `--overwrite` | Overwrite the output bundle if it exists | `false` |
| `--timeout SECONDS` | Timeout for each replay attempt | `30.0` |
| `--attempts N` | Number of attempts per subset test (for nondeterminism detection) | `1` |

## Example

Let's minimize a failing agent that books the wrong flight:

```python
# agent.py
from stepfork import record, trace_tool


@trace_tool(name="search_flights")
def search_flights(destination: str) -> list[dict]:
    return [
        {"id": "FL123", "dest": "KTM", "price": 800},
        {"id": "FL456", "dest": "NYC", "price": 600},
    ]


@trace_tool(name="book_flight")
def book_flight(flight_id: str) -> dict:
    return {"id": flight_id, "status": "confirmed"}


def run_agent(destination: str = "KTM") -> dict:
    flights = search_flights(destination)
    # BUG: books the second flight instead of checking destination
    booked = book_flight(flights[1]["id"])
    return {"booking": booked, "destination": destination}


if __name__ == "__main__":
    with record("booking-agent", output="failure.sftrace") as session:
        result = run_agent()
        session.set_output(result)
```

The original trace has 8 events:
1. `run_start`
2. `tool_call` (search_flights)
3. `tool_result` (search results)
4. `tool_call` (book_flight)
5. `tool_result` (booking confirmation)
6. `state_change` (internal state update)
7. `error` (failure detected)
8. `run_end`

Minimize the trace:

```bash
# Create expected output file
echo '{"booking": {"id": "FL123", "status": "confirmed"}, "destination": "KTM"}' > expected.json

# Run minimization
stepfork minimize failure.sftrace \
    --entrypoint agent:run_agent \
    --expect-output expected.json \
    --output minimal.sftrace
```

Output:
```
Stepfork Minimize

Original trace:  failure.sftrace
Agent:           booking-agent
Events:          8
Entrypoint:      agent:run_agent
Mode:            frozen

Detecting failure signature...
Minimizing trace...

╭─ Minimization Report ─────────╮
│ Original Events     8          │
│ Minimized Events    6          │
│ Reduction           25.0%      │
│ Replay Attempts     12         │
│ Failure Signature   Output Mismatch │
│ Minimal             Yes        │
╰────────────────────────────────╯

✓ Minimized trace saved to: minimal.sftrace
```

The minimized trace removed the `state_change` event (not relevant to the failure) while preserving all dependency calls needed to reproduce the wrong-booking bug.

## Failure Signatures

### Exception-Based Failures

When the replayed agent raises an exception:

```python
# Trace raises ValueError during replay
Failure Signature: Exception: ValueError
```

The minimizer preserves traces that raise the same exception type with similar message patterns.

### Replay Divergence

When the agent's execution diverges from the recorded trace:

```python
# Agent tries to call a different tool than recorded
Failure Signature: Replay Divergence: ReplayMismatchError
```

Divergence failures include:
- Wrong tool called
- Tool called with different arguments
- Extra or missing dependency calls
- Different model used for LLM request

### Output Mismatch

When the agent produces incorrect output (requires `--expect-output`):

```python
# Agent output doesn't match expected output
Failure Signature: Output Mismatch
```

Output comparison uses canonical JSON serialization, so key order and whitespace don't matter.

### Combined Failures

Some traces fail in multiple ways:

```python
Failure Signature: Exception: ValueError + Divergence: ReplayMismatchError + Output Mismatch
```

All components must match for the signature to be preserved.

## Handling Nondeterminism

If your agent has nondeterministic behavior (even with frozen replay), use `--attempts`:

```bash
stepfork minimize failure.sftrace \
    --entrypoint agent:run \
    --attempts 3
```

Each candidate trace is tested 3 times. Only subsets that fail consistently are accepted. Nondeterministic failures are reported in the minimization report with a warning.

## Limitations

- **Minimization is not a sandbox.** The entrypoint runs with your code and privileges.
- **Only instrumented boundaries are frozen.** Uninstrumented code may behave differently across replay attempts.
- **Timeouts may truncate search.** Increase `--timeout` if traces take longer to replay.
- **Cannot minimize successful traces.** The trace must fail during replay to be minimized.
- **Manual reduction may be needed.** Delta debugging finds a minimal trace, but not necessarily the *unique* minimal trace. Manual inspection may reveal further simplifications.

## Integration with Existing Workflows

Minimization fits into the standard Stepfork workflow:

1. **Record** a failing execution → `failure.sftrace`
2. **Minimize** the trace → `minimal.sftrace`
3. **Inspect** the minimal trace → `stepfork inspect minimal.sftrace`
4. **Replay** to verify → `stepfork replay minimal.sftrace --entrypoint agent:run`
5. **Diff** against a fix → `stepfork diff minimal.sftrace fixed.sftrace`
6. **Export** as a regression test → `stepfork export minimal.sftrace --pytest`

Using a minimized trace for regression tests makes the test suite faster and easier to understand.

## See Also

- [Replay](replay.md) - How frozen replay works
- [CLI Reference](cli.md) - Complete command documentation
- [Trace Format](trace-format.md) - Understanding `.sftrace` structure
- [Examples](examples.md) - Runnable examples with minimization
