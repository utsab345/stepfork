# Recording Agent Runs

Recording captures one agent run as a `.sftrace` bundle so it can later be
replayed, diffed, and turned into a regression test.

## The `record` context manager

```python
from stepfork import record

with record("booking-agent", output="failure.sftrace") as session:
    result = agent.run("Book the cheapest flight to Lisbon")
    session.set_output(result)
```

- `record(agent_name, *, output=None, overwrite=False, serializer=None, run_input=None)`
  opens a recording session. When `output` is omitted the bundle is written
  under `.stepfork/traces/`.
- Call `session.set_output(value)` to store the final run output. It is written
  to the terminal `run_end` event.
- The trace is persisted when the block exits, **including when the block
  raises**. The original exception is always re-raised after the bundle is
  written, so a failed run becomes a failed trace with a `failure` record.
- Inside an active replay the session is inert: the block runs, but nothing is
  recorded or written. Replaying an entrypoint never creates new bundles.

## Instrumenting tools

Wrap each external dependency with `@trace_tool`:

```python
from stepfork import trace_tool


@trace_tool(name="flight_search")
def search_flights(destination: str) -> dict:
    return flights_api.search(destination)
```

- Inside a recording, the call and its result (or its raised exception) are
  captured.
- Outside any Stepfork context, the function runs unchanged.
- During frozen replay the function body is **not** executed; the captured
  result is returned instead.
- Both synchronous and `async def` tools are supported.
- Generator and async-generator tools are rejected; streaming is unsupported.
- Signature binding is used so inputs are recorded by parameter name; the
  binding is stored as JSON.

Options:

- `name`: override the recorded tool name. Defaults to the function name.
- `replay_policy`: `frozen` (default), `live`, `forbidden`, `manual`, or
  `derived`.
- `serializer`: hook for converting otherwise unsupported objects to JSON.

## Instrumenting LLM calls

`llm_request` records a provider-independent LLM boundary:

```python
from stepfork import llm_request

response = llm_request(
    provider="openai",
    model="gpt-4o-mini",
    input={"messages": messages},
    call=lambda: client.chat(messages),
)
```

- While recording, the request and response are captured and `call()` executes.
- During frozen replay, `call()` is **not** executed; the recorded response is
  returned.
- During live replay, the call must match the recording, then `call()` executes.
- With no active context, `call()` executes unchanged.

`llm_request` is the replay-safe wrapper. Prefer it over calling the provider
directly. The lower-level `session.llm_call(...)` context manager exists for
manual instrumentation, but it does not substitute during replay.

For async agents, use `async with record(...)` and `await allm_request(...)`:

```python
from stepfork import allm_request, record

async with record("agent", output="run.sftrace") as session:
    response = await allm_request(
        provider="fake",
        model="demo",
        input={"messages": messages},
        call=lambda: async_client.create(messages),
    )
    session.set_output(response)
```

`async with` writes the bundle without blocking the event loop on disk I/O.
Parent scopes are task-local, so concurrent child tasks keep their own parent
links. Event order records the order in which boundaries are reached. A replay
uses that same strict order; concurrent scheduling changes can cause a
`ReplayMismatchError`. Stepfork does not guarantee deterministic scheduling.

## Serialization

Tool inputs, results, LLM payloads, and run output are converted to JSON before
they are stored. Objects that cannot be serialized raise
`TraceSerializationError` with an actionable message. Supply a `serializer`
callable that accepts a value and either returns a JSON-compatible value or
raises `TypeError`, for example:

```python
def serialize(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


with record("billing-agent", serializer=serialize) as session:
    ...
```

## Redaction and integrity

Redaction is applied before persistence and before payload hashes are computed.
Write path and hashing behavior is described in
[trace-format.md](trace-format.md) and [security.md](security.md).
