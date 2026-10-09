# Security Policy

## Supported versions

Only the latest release is supported. Stepfork is pre-1.0; alpha releases
receive fixes on the `main` branch and, when warranted, as patch releases.

## Reporting a vulnerability

Please report security issues privately so they can be fixed before a public
disclosure:

- Open a [GitHub Security Advisory][advisory] (preferred), or
- For issues that are not security-sensitive, open a regular
  [GitHub issue][issues].

Do not include real credentials, API keys, or live traces in a public issue.
If a report contains secrets, they will be redacted or the issue closed.

## What to include

- The Stepfork version (`stepfork --version`).
- The Python version and platform.
- A minimal `.sftrace` bundle or reproduction steps.
- The expected and actual behavior.

## Security model

Stepfork is local-first trace tooling. It does **not** provide encryption,
authenticated signatures, key management, or a general-purpose sandbox.

- **Trace data is never executed.** Stepfork imports only the trusted
  `MODULE:FUNCTION` entrypoint you name. Replay and export run your own code
  with your own privileges; they are not a sandbox.
- **Redaction is best-effort.** Known credential-shaped values are redacted at
  record time. Redaction can miss sensitive data. Inspect traces before
  sharing them.
- **Integrity is SHA-256 based and unkeyed.** `integrity.json` detects
  accidental modification, not malicious tampering. `replay` and `export` do
  not verify integrity by default; validate before trusting an untrusted
  bundle.
- **Untrusted bundles are untrusted input.** Treat `.sftrace` files from other
  people like any other untrusted data. See [docs/security.md](docs/security.md)
  for the full model and handling guidance.

[advisory]: https://github.com/utsab345/stepfork/security/advisories/new
[issues]: https://github.com/utsab345/stepfork/issues