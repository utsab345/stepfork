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
      `pytest` and the optional extras under test, then run all demos and
      check the CLI:
      ```bash
      pip install --pre "stepfork[openai,langgraph]"
      python examples/quickstart/demo.py
      python examples/booking_agent/demo.py
      python examples/refund_agent/demo.py
      python examples/openai_chat/demo.py
      python examples/langgraph_agent/demo.py
      stepfork --version
      ```
- [ ] `CHANGELOG.md` has an entry for the new version.
- [ ] `docs/` reflects current behavior (recording, replay, diff, pytest
      export, trace format, security, development).
- [ ] All bundled end-to-end examples run to completion (`rc 0`).
- [ ] `git diff --check` reports no whitespace errors.
- [ ] The GitHub repo description and topics are current, and the README's
      Status section matches reality.

## Publishing

See the [PyPI publishing checklist](pypi-publishing.md) for the trusted
publishing procedure, TestPyPI dry run, and verification steps.

- [ ] Decide whether to change the `Development Status` classifier and bump
      `src/stepfork/version.py` accordingly.
- [ ] Commit the version bump and changelog; tag with `git tag v<version>`.
- [ ] Publish to the package index (only when a release was explicitly
      approved). Preferred: create the GitHub Release; the committed
      `publish.yml` workflow publishes via trusted publishing (OIDC) with no
      stored token. Manual fallback:
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
