# Security Notes

Stepfork is local-first trace tooling. Its Day 4 security features are designed
to reduce accidental leakage and make saved traces tamper-evident, not to prove
that a trace is safe to publish.

## Threat Model

Stepfork assumes traces are created and inspected locally by the developer. The
integrity record helps detect file changes after save when the expected record
is trusted.

Stepfork does not currently provide:

- authenticated signatures
- encryption
- key management
- sandboxing for untrusted code
- complete data-loss prevention

## Redaction

On save, Stepfork recursively redacts known sensitive keys and common
credential-looking strings before persistence and before payload hashes are
computed. Examples include `api_key`, `authorization`, `password`, bearer
tokens, GitHub token shapes, and common `sk-...` API-key-like strings.

This is best effort. It can miss sensitive data in unusual tool outputs,
domain-specific identifiers, free-form model text, screenshots, binary blobs, or
provider-specific credential formats that are not recognized yet.

Inspect traces before sharing them.

## Integrity

New bundles include `integrity.json` with SHA-256 digests for the three payload
files. SHA-256 is not encryption. The integrity file is not a digital signature.
An attacker who can modify both the trace files and `integrity.json` can
recompute the record.

Integrity statuses:

- `verified`: recorded digests match current files
- `mismatch`: at least one digest or payload hash does not match
- `unverified_legacy`: no Day 4 integrity metadata is present

## Safe Sharing Practices

- Prefer sharing minimized synthetic traces.
- Run `stepfork validate --verify-integrity` before relying on a fixture.
- Run `stepfork inspect` and review payloads before sending a bundle anywhere.
- Treat legacy bundles as unverified unless independently trusted.
