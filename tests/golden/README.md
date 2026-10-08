# Golden `.sftrace` Fixtures

These bundles are deterministic synthetic traces used by Stepfork regression
tests. They do not contain real user data, real credentials, or network-derived
payloads.

- `successful_run.sftrace`: complete successful run.
- `failed_tool_run.sftrace`: failed tool execution with redaction metadata.
- `failed_llm_run.sftrace`: failed LLM request path.
- `partial_run.sftrace`: intentionally incomplete; valid only in partial mode.
- `legacy_v01.sftrace`: Day 3-compatible bundle without `integrity.json`.

Fixtures use fixed run IDs, event IDs, timestamps, payloads, and statuses.
