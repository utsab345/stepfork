# Contributing to Stepfork

Thanks for helping build Stepfork.

Stepfork currently targets Python 3.11+ and uses `uv` for dependency and
environment management.

## Local Setup

```bash
uv sync
```

## Checks

Before opening a pull request, run:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## Pull Requests

Keep pull requests focused. Include tests for behavioral changes, and update
documentation when user-facing behavior changes.

Do not include credentials, API keys, tokens, private data, or sensitive trace
data in issues, tests, examples, fixtures, or commits.

## Current Scope

The current product scope is:

```text
trace → inspect → replay → diff → pytest
```

Hosted services, unrelated observability features, and broad framework
integrations are currently out of scope.
