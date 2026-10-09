# Changelog

All notable changes to Stepfork are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.1.0a1] - 2026-10-09

Prepared for first public alpha.

### Added

- Second end-to-end example: `examples/refund_agent/` (buggy vs fixed refund
  eligibility agent) with integration tests in
  `tests/integration/test_refund_failure_to_test.py`.
- Hypothesis property tests for the behavioral diff engine
  (`first_difference`/`values_equal` agreement, dict key-order independence).
- CLI error-path tests for `replay` and `export`.
- Expanded unit coverage for storage, diffing, JSON encoding, runtime replay
  planning, and export runtime error paths.
- `CHANGELOG.md`, `docs/release-checklist.md`.
- Top-level `SECURITY.md` documenting the security model and a private
  vulnerability-reporting path.
- `docs/releases/v0.1.0a1.md` with the public release notes.

### Changed

- README documents installing directly from the public GitHub repository via
  `pip`/`uv` (`git+https://...@v0.1.0a1`); PyPI install is not offered for the
  alpha. The conceptual quickstart is labeled as a sketch and links to the
  runnable demos.

- Version is now a single source of truth via hatchling dynamic versioning
  (`[tool.hatch.version] path = "src/stepfork/version.py"`); bumped to
  `0.1.0a1`.
- `src/stepfork/export/generator.py`: docstrings interpolated into generated
  pytest files are collapsed, escaped, and length-limited, preventing hostile
  trace metadata from breaking out of the generated module docstring.
- `src/stepfork/cli/inspect.py`: error output is sanitized before display,
  matching diff, export, and replay.

### Fixed

- Generated pytest tests no longer allow `"""`-containing trace names or
  entrypoints to terminate the generated docstring early (regression test:
  `test_generated_source_escapes_hostile_trace_name_and_entrypoint`).
- Inspect CLI surfaced unsanitized trace payloads in error messages.

### Security

- `docs/security.md` documents how to handle untrusted bundles: symlink
  following, integrity not verified by default on replay/export, in-memory
  payload loading, and redaction-at-record-time semantics.

[0.1.0a1]: https://github.com/utsab345/stepfork/releases/tag/v0.1.0a1