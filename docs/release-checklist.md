# Release Checklist

This checklist applies to publishing Stepfork publicly. The current version is
tracked as a single source of truth in `src/stepfork/version.py` and read by
hatchling via `[tool.hatch.version]`.

## Before the release

- [ ] `git status` is clean on `main`.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run ruff format --check .` passes.
- [ ] `uv run mypy` passes.
- [ ] `uv run pytest` passes.
- [ ] `uv run pytest --cov=stepfork --cov-branch --cov-report=term-missing`
      is at or above the documented coverage target.
- [ ] `uv build` produces `dist/stepfork-<version>-py3-none-any.whl` and a
      `.tar.gz` with the expected version.
- [ ] Fresh-install smoke: in a clean virtualenv, install the wheel plus
      `pytest`, then run both demos and check the CLI:
      ```bash
      python examples/booking_agent/demo.py
      python examples/refund_agent/demo.py
      stepfork --version
      ```
- [ ] `CHANGELOG.md` has an entry for the new version.
- [ ] `docs/` reflects current behavior (recording, replay, diff, pytest
      export, trace format, security, development).
- [ ] Both end-to-end examples run to completion (`rc 0`).
- [ ] `git diff --check` reports no whitespace errors.
- [ ] The GitHub repo description and topics are current, and the README's
      Status section matches reality.

## Publishing

- [ ] Decide whether to change the `Development Status` classifier and bump
      `src/stepfork/version.py` accordingly.
- [ ] Commit the version bump and changelog; tag with `git tag v<version>`.
- [ ] Publish to the package index (only when a release was explicitly
      approved):
      ```bash
      uv publish
      ```
- [ ] Create a GitHub Release with the built artifacts and notes from
      `CHANGELOG.md` (only when explicitly approved):
      ```bash
      gh release create v<version> dist/stepfork-<version>*.whl dist/stepfork-<version>*.tar.gz \
        --title "Stepfork v<version>" --notes "$(tail -n +3 CHANGELOG.md)"
      ```

## After the release

- [ ] Re-run the full gate once on the tagged commit.
- [ ] Confirm the release page shows the wheel and sdist assets.
- [ ] Update this checklist with anything that tripped you up.