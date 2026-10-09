# Security Notes

Stepfork is local-first trace tooling. Its security features are designed
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

## Handling Untrusted Bundles

A `.sftrace` bundle is a directory of JSON files you may receive from someone
else. Treat it like any other untrusted input:

- **Traces are not executed.** Stepfork imports only the `MODULE:FUNCTION`
  entrypoint you name. It never imports or runs code embedded in a bundle.
- **Symlinks are followed.** Payload files inside a bundle are opened by
  name, so a hostile bundle could point `events.jsonl` at any readable file.
  The target must still parse as valid trace JSON, and Stepfork never executes
  it, so the exposure is bounded, but inspect a bundle's file types before
  replaying or exporting with it.
- **Payloads are loaded into memory.** Stepfork reads whole payload files.
  Oversized bundles can consume memory; keep shared bundles small.
- **Redaction happens at record time, not load time.** A bundle created by an
  older tool, or hand-edited, may contain values redaction would remove today.
  Use `stepfork inspect --events` to review payloads before sharing them.

## Integrity

New bundles include `integrity.json` with SHA-256 digests for the three payload
files. SHA-256 is not encryption. The integrity file is not a digital signature.
An attacker who can modify both the trace files and `integrity.json` can
recompute the record.

Integrity statuses:

- `verified`: recorded digests match current files
- `mismatch`: at least one digest or payload hash does not match
- `unverified_legacy`: no integrity metadata is present

Integrity is verified on demand. `stepfork validate --verify-integrity` and
`stepfork inspect` check it; `stepfork replay` and `stepfork export` do not by
default, so use `validate --verify-integrity` before relying on a bundle from
an untrusted source.

## Trace Data Is Not Code

Trace bundles are treated strictly as data. Stepfork never executes code,
imports modules, or evaluates expressions found in a trace. Replay and export
import only the trusted `MODULE:FUNCTION` entrypoint you name on the command
line. Generated pytest tests come from a fixed, reviewed template; trace payloads
become sanitized JSON literals and are never interpolated into executable code.
No `eval` or `exec` is used on trace data.

Running an entrypoint under replay still executes your own code with your own
privileges. Replay is not a sandbox.

## Redaction

On save, Stepfork recursively redacts known sensitive keys and common
credential-looking strings before persistence and before payload hashes are
computed. Examples include `api_key`, `authorization`, `password`, bearer
tokens, GitHub token shapes, and common `sk-...` API-key-like strings.

This is best effort. It can miss sensitive data in unusual tool outputs,
domain-specific identifiers, free-form model text, screenshots, binary blobs, or
provider-specific credential formats that are not recognized yet.

Inspect traces before sharing them.

## Safe Sharing Practices

- Prefer sharing minimized synthetic traces.
- Run `stepfork validate --verify-integrity` before relying on a fixture.
- Run `stepfork inspect` and review payloads before sending a bundle anywhere.
- Treat legacy bundles as unverified unless independently trusted.
