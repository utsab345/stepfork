# Contributing to Stepfork

Thanks for helping build Stepfork.

Stepfork targets Python 3.11, 3.12, and 3.13 and uses `uv` for dependency and
environment management.

## Local Setup

```bash
git clone https://github.com/utsab345/stepfork.git
cd stepfork
uv sync
```

This creates a venv with runtime and development dependencies, including
ruff, mypy, pytest, and MkDocs.

## Day-to-Day Workflow

Start a feature branch:

```bash
git checkout -b my-feature
```

Make your change, then run every check before committing:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv run mkdocs build --strict
```

- `uv run ruff format .` will fix formatting in place.
- `uv build` builds the sdist and wheel; verify the artifact names and that
  the package imports from a fresh venv of the wheel.

## Demo and Regression Tests

Run the runnable demos to confirm they still work end to end:

```bash
uv run python examples/quickstart/demo.py
uv run python examples/booking_agent/demo.py
uv run python examples/refund_agent/demo.py
```

Each demo records a buggy run, freeze-replays it, diffs it against the
corrected run, and exports a pytest regression test that fails on the buggy
entrypoint and passes on the fixed one. Add integration tests alongside new
behaviors; existing integration tests live in `tests/integration/`.

## Pull Requests

Keep pull requests focused and conventional. Commit messages use a single-line
Conventional Commits subject:

```text
feat: add --dry-run to replay
fix: report divergence path in replay mismatch
docs: document the trace format
test: add integration test for redaction
chore: bump dev toolchain
```

Confine each PR to one logical change. Include tests for behavioral changes,
and update documentation when user-facing behavior changes. No force-push, no
empty commits.

Do not include credentials, API keys, tokens, private data, or sensitive trace
data in issues, tests, examples, fixtures, or commits.

## Documentation and Docs Site

The documentation site builds from `docs/` with MkDocs:

```bash
uv run mkdocs serve   # local preview
uv run mkdocs build --strict   # CI runs this; strict mode catches broken links
```

New pages go in `docs/` and are added to the `nav` block in `mkdocs.yml`.
Pages with code output should use output verified by actually running the
documented commands.

## Current Scope

The current product scope is:

```text
trace → inspect → replay → diff → pytest
```

Hosted services, unrelated observability features, and broad framework
integrations are currently out of scope (the proposed integration design is in
`docs/integrations.md`).