# Stepfork Trace Format

Stepfork stores traces as UTF-8 directory bundles with the `.sftrace` suffix.
The v0.1 layout is:

```text
example.sftrace/
├── manifest.json
├── events.jsonl
├── redactions.json
└── integrity.json
```

`integrity.json` was added after the initial v0.1 storage work. Older bundles
without it remain loadable but are reported as `unverified_legacy`.

## Manifest

`manifest.json` contains bundle-level metadata:

- `format`: always `stepfork`
- `schema_version`: currently `0.1`
- `run_id`
- `agent_name`
- `created_at`
- `status`: `running`, `completed`, or `failed`
- `failure`: required for failed runs
- `environment`
- `totals`

## Events

`events.jsonl` stores one complete JSON event per non-blank line. Blank lines
are invalid. Event order is significant and preserved by `Trace.load()`.

Supported event types:

- `run_start`
- `llm_request`
- `llm_response`
- `tool_call`
- `tool_result`
- `state_change`
- `error`
- `run_end`

Events share structural fields such as `id`, `run_id`, `parent_id`, `step`,
`timestamp`, `status`, and `replay_policy`. Payload hashes are stored in
`input_hash` and `output_hash` where applicable.

`input_hash` and `output_hash` are SHA-256 digests over Stepfork's canonical
JSON profile after redaction has been applied. During replay, dependency
inputs are re-normalized, redacted, canonicalized, and compared against the
recording. For LLM requests this means prompt payload changes, model changes,
and provider changes are treated as replay divergence.

## Redactions

`redactions.json` stores non-secret metadata describing redactions:

```json
{
  "schema_version": "0.1",
  "entries": [
    {
      "event_id": "evt_002",
      "path": "/input/api_key",
      "reason": "sensitive_key",
      "replacement": "[REDACTED]"
    }
  ]
}
```

Paths use JSON Pointer escaping for `~` and `/`. Redaction metadata must never
store original secrets, reversible encodings, or hashes of secret values.

## Integrity

`integrity.json` stores SHA-256 digests of the exact persisted bytes of:

- `manifest.json`
- `events.jsonl`
- `redactions.json`

It does not include itself. This detects accidental modification and ordinary
tampering when the expected integrity record is trusted. It is not a digital
signature.

## Compatibility

The schema version is currently `0.1`. New readers should keep loading older
valid v0.1 bundles where possible. Missing integrity metadata means unverified
legacy, not verified. Older or hand-built events may also lack payload hashes;
they can still replay if their stored inputs exactly match the live calls, but
Stepfork reports computed fingerprints in diagnostics rather than silently
treating them as integrity-verified.
