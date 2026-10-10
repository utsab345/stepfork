"""Smoke test for the runnable LangGraph example in ``docs/langgraph.md``.

The LangGraph guide once shipped an example that called
``StateGraph.compile(tools=[...])``, which is not part of the supported
LangGraph API and never invoked the instrumented tool. This test extracts the
documented example and runs it end to end in a clean subprocess, so the guide
cannot silently regress to non-executable code.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LANGGRAPH_DOC = REPO_ROOT / "docs" / "langgraph.md"

START_MARKER = "<!-- langgraph-example:start -->"
END_MARKER = "<!-- langgraph-example:end -->"

# Run inside the recording directory written by the example's ``__main__`` block.
# It imports the example, replays the recorded run with dependencies frozen, and
# proves the instrumented tool body was not executed again.
REPLAY_RUNNER = """\
import json
from pathlib import Path

import langgraph_example
from stepfork import ReplaySession

langgraph_example.LOOKUPS.clear()
with ReplaySession.from_trace("triage.sftrace", mode="frozen") as replay:
    replayed = langgraph_example.run_agent()
    replay.verify_complete()

assert replayed == {"answer": "customer=ada@example.com;tier=gold"}, replayed
assert langgraph_example.LOOKUPS == [], "frozen replay executed the tool body"

events = [
    json.loads(line)["type"]
    for line in Path("triage.sftrace/events.jsonl").read_text().splitlines()
]
assert "tool_call" in events, events
print("DOC_EXAMPLE_OK")
"""


def _extract_langgraph_example() -> str:
    text = LANGGRAPH_DOC.read_text(encoding="utf-8")
    start = text.index(START_MARKER) + len(START_MARKER)
    end = text.index(END_MARKER)
    block = text[start:end]
    match = re.search(r"```python\n(.*?)```", block, re.DOTALL)
    assert match is not None, "no python code block between the example markers"
    return match.group(1)


def _clean_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("STEPFORK_")
    }
    env.pop("PYTHONPATH", None)
    return env


def test_docs_langgraph_example_has_no_invalid_compile() -> None:
    text = LANGGRAPH_DOC.read_text(encoding="utf-8")
    assert "compile(tools=" not in text


def test_docs_langgraph_example_records_and_replays(tmp_path: Path) -> None:
    example = tmp_path / "langgraph_example.py"
    example.write_text(_extract_langgraph_example(), encoding="utf-8")
    runner = tmp_path / "replay_runner.py"
    runner.write_text(REPLAY_RUNNER, encoding="utf-8")
    env = _clean_env()

    recorded = subprocess.run(
        [sys.executable, str(example)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert recorded.returncode == 0, recorded.stderr
    assert "customer=ada@example.com;tier=gold" in recorded.stdout
    assert (tmp_path / "triage.sftrace").is_dir()

    replayed = subprocess.run(
        [sys.executable, str(runner)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert replayed.returncode == 0, replayed.stderr
    assert "DOC_EXAMPLE_OK" in replayed.stdout

    bundle = tmp_path / "triage.sftrace" / "events.jsonl"
    event_types = [json.loads(line)["type"] for line in bundle.read_text().splitlines()]
    assert "tool_call" in event_types
    assert "llm_request" in event_types
