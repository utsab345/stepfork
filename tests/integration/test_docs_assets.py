"""Regression tests for top-level documentation assets.

These guard the onboarding deliverables: the README workflow diagram and
terminal demo must exist and be referenced, and new documentation pages must
be wired into the MkDocs navigation.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
MKDOCS = REPO_ROOT / "mkdocs.yml"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
GIF_SIGNATURE = b"GIF8"


def test_readme_references_existing_workflow_diagram() -> None:
    text = README.read_text(encoding="utf-8")
    assert "assets/stepfork-workflow.png" in text
    image = REPO_ROOT / "assets" / "stepfork-workflow.png"
    assert image.is_file()
    assert image.read_bytes()[:8] == PNG_SIGNATURE


def test_readme_references_existing_terminal_demo() -> None:
    text = README.read_text(encoding="utf-8")
    assert "scripts/terminal-demo/stepfork-demo.gif" in text
    gif = REPO_ROOT / "scripts" / "terminal-demo" / "stepfork-demo.gif"
    assert gif.is_file()
    assert gif.read_bytes()[:4] == GIF_SIGNATURE


def test_new_docs_pages_exist_and_are_navigable() -> None:
    nav = MKDOCS.read_text(encoding="utf-8")
    for page in ("cli.md", "integrations.md"):
        assert (REPO_ROOT / "docs" / page).is_file(), page
        assert page in nav, f"{page} missing from mkdocs nav"
