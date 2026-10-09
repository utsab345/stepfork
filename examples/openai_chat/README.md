# OpenAI SDK-style example

This example exercises the optional OpenAI adapter without using the network.
It uses a fake client with the same synchronous call shape as the OpenAI Python
SDK:

```python
client.chat.completions.create(...)
```

Run from the repository root:

```bash
uv run python examples/openai_chat/demo.py
```

The demo records a buggy run, validates the `.sftrace` bundle, replays the
recorded OpenAI-style response without executing the SDK call, diffs buggy and
fixed behavior, exports pytest regression tests, and verifies that the buggy
entrypoint fails while the fixed entrypoint passes.
