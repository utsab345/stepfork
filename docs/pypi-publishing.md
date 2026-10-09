# PyPI Publishing Checklist

This checklist covers publishing Stepfork to PyPI using **trusted publishing**
(OpenID Connect), so no API tokens are stored. It is a procedure to follow only
after a release is explicitly approved. Nothing in this document uploads a
package on its own.

Current status: **published.** `pip install --pre stepfork` resolves to the
latest available alpha on PyPI. Each subsequent release uses a new version;
published versions are not overwritten. Follow the procedure below.

## 0. Preconditions

- [ ] A release is explicitly approved; publishing is a deliberate decision,
      not a side effect of merging.
- [ ] `main` is green (CI and docs) and the working tree is clean.
- [ ] The version in `src/stepfork/version.py` is final for this release.
      Alpha releases use a PEP 440 pre-release such as `0.1.0a1`.
- [ ] `CHANGELOG.md` has an entry for the version.
- [ ] No secrets, credentials, or real user traces are present in the
      repository, tests, examples, fixtures, or docs.

## 1. Confirm the name

- [ ] The intended name (`stepfork`) is not already taken:
      `curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/stepfork/json`
      returns `404`.
- [ ] If it is taken, choose a distinct distribution name and update
      `[project].name` in `pyproject.toml` (the import package can stay
      `stepfork`).

## 2. Validate metadata and artifacts

- [ ] `uv build` produces `dist/stepfork-<version>.tar.gz` and
      `dist/stepfork-<version>-py3-none-any.whl`.
- [ ] `uvx twine check dist/*` passes for both artifacts.
- [ ] The wheel contains `stepfork/py.typed`, the CLI entry point
      (`stepfork = stepfork.cli.main:app`), `METADATA`, `LICENSE`, and `WHEEL`.
- [ ] `Requires-Python` and classifiers match reality
      (`>=3.11,<3.14`; classifiers for 3.11, 3.12, 3.13).
- [ ] Runtime dependencies are correct and minimal
      (`pydantic>=2.0`, `rich>=13.0`, `typer>=0.12`).
- [ ] `README.md` renders as the long description
      (`Description-Content-Type: text/markdown`).

Known rendering limitation: PyPI does not resolve relative image or link paths
from the repository. `assets/stepfork-logo.png` and `assets/stepfork-workflow.png`
and relative links such as `docs/cli.md` will not resolve on the PyPI project
page. This does not fail `twine check`, but consider using absolute
`https://raw.githubusercontent.com/...` image URLs for the README shown on PyPI.

## 3. Test on TestPyPI first

The committed workflow targets PyPI. For a TestPyPI dry run, use a temporary
variant that adds `repository-url: https://test.pypi.org/legacy/` to the
publish step and register a TestPyPI trusted publisher.

- [ ] Configure a trusted publisher for TestPyPI (see below).
- [ ] Publish to TestPyPI and verify a clean install:
      `pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --pre stepfork`
- [ ] Run `stepfork --version` and the five-minute quickstart from the
      installed package.

## 4. Configure trusted publishing

On the package index:

- [ ] Create a **pending publisher** for the project (PyPI, "Publishing",
      "Add a pending publisher" for a name that does not exist yet, or the
      existing project's "Publishing" settings):
      - Owner: `utsab345`
      - Repository: `stepfork`
      - Workflow name: `publish.yml`
      - Environment: `pypi`
- [ ] In the GitHub repository, create an environment named `pypi` under
      Settings, Environments. Optionally require reviewers so a human approves
      each publish.
- [ ] No PyPI API token or password is stored in GitHub.

## 5. Publishing workflow

The trusted-publishing workflow is committed at
[`.github/workflows/publish.yml`](https://github.com/utsab345/stepfork/blob/main/.github/workflows/publish.yml).
It:

- runs only when a GitHub Release is published (never on pushes, pull requests,
  or manual dispatch);
- builds the sdist and wheel, runs `twine check`, and verifies that
  `src/stepfork/version.py` matches the release tag exactly;
- publishes from a job bound to the `pypi` environment with `id-token: write`,
  using `pypa/gh-action-pypi-publish`, so no API token is stored.

Because the `publish` job targets the `pypi` environment, add required
reviewers to that environment if you want a human to approve each publish.

## 6. Publish and verify

- [ ] Tag the release commit (`git tag v<version>`) and push the tag.
- [ ] Create the GitHub Release with the built artifacts. Publishing the
      release triggers the trusted publish workflow; there is no manual trigger.
- [ ] Confirm the wheel and sdist appear on the PyPI project page.
- [ ] In a brand-new venv:
      `pip install --pre stepfork` (pre-release requires `--pre` until a final
      release exists), then run `stepfork --version` and the quickstart.

## 7. If something is wrong

- [ ] A published file can be **yanked** (hidden from new resolutions) but not
      deleted; yank the broken artifact rather than reusing the version.
- [ ] Never re-upload the same version with different contents; bump the
      version instead.
- [ ] Record what went wrong in this checklist and in `CHANGELOG.md`.

## Related

- [Release checklist](release-checklist.md)
- [Development](development.md)
- [Security notes](security.md)
