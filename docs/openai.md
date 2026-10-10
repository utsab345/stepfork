# OpenAI Python SDK

Stepfork includes a small optional adapter for the OpenAI Python SDK. The core
package still works without OpenAI installed; install the extra only when you
want to use the adapter:

```bash
pip install "stepfork[openai]"
```

The official OpenAI documentation shows the Python SDK using an `OpenAI`
client object, and the Chat Completions API reference documents
`chat.completions.create` for Python. Stepfork's first adapter supports that
synchronous and asynchronous non-streaming calls only.

## Supported API

```python
from openai import OpenAI
from stepfork.integrations.openai import chat_completions_create

client = OpenAI()

response = chat_completions_create(
    client,
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Classify this support message."}],
    temperature=0,
)
```

`chat_completions_create(client, **request)` calls:

```python
client.chat.completions.create(**request)
```

For an async client, use `await achat_completions_create(client, **request)`
inside `async with record(...)`. It uses the same trace schema and frozen
matching rules.

When used inside `stepfork.record`, Stepfork records an `llm_request` with:

- provider: `openai`
- model: the `model` request parameter
- method: `chat.completions.create`
- the full JSON-compatible request payload, including messages and relevant
  parameters such as `temperature`, `max_tokens`, `tools`, and `response_format`

During frozen replay, the SDK method is not executed. The recorded response is
returned from the trace, and any changed model, message content, or request
parameter causes replay divergence.

## Return Value

The adapter returns a JSON-compatible dictionary in both live recording and
frozen replay. This is deliberate: generated pytest tests can run without the
OpenAI package installed and without reconstructing SDK response classes.

OpenAI SDK responses that expose `model_dump(mode="json")` are serialized with
that method. Dictionary responses are accepted as-is if they are JSON
compatible.

## Offline Example

The repository includes a complete offline example:

```bash
uv run python examples/openai_chat/demo.py
```

It uses a fake OpenAI-shaped client, so it requires no API key and makes no
network or paid API calls. The demo records a buggy run, validates and replays
the trace, exports pytest regression tests, and proves that the buggy
entrypoint fails while the fixed entrypoint passes.

## Security

OpenAI request payloads are recorded locally in the `.sftrace` bundle. Existing
Stepfork redaction rules apply before persistence, including known sensitive
keys and credential-shaped strings, but redaction is best-effort. Do not put API
keys or other secrets inside message content, tool parameters, metadata, or
custom fields.

The adapter does not import or create an OpenAI client for you. You remain
responsible for configuring credentials through the SDK's normal mechanisms.

## Limitations

Not supported in this first iteration:

- streaming responses (`stream=True`)
- Responses API
- OpenAI Agents SDK
- automatic monkeypatching of existing SDK clients
- non-JSON request parameters or response payloads

Calls outside `chat_completions_create` are ordinary Python calls and are not
recorded or frozen unless you wrap them with Stepfork instrumentation.
