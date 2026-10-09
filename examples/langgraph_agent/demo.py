"""End-to-end LangGraph integration demo.

Run from the repository root::

    uv run python examples/langgraph_agent/demo.py

The demo is fully offline. A deterministic scripted chat model stands in for a
real LLM, so no API key, network access, or paid provider call is required.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = Path(__file__).resolve().parent
ARTIFACTS = EXAMPLE_DIR / ".artifacts"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FAILURE_TRACE = ARTIFACTS / "langgraph_failure.sftrace"
FIXED_TRACE = ARTIFACTS / "langgraph_fixed.sftrace"
EXPECTED_FILE = EXAMPLE_DIR / "expected.json"
BUGGY_TEST = ARTIFACTS / "test_langgraph_buggy.py"
FIXED_TEST = ARTIFACTS / "test_langgraph_fixed.py"

BUGGY_ENTRYPOINT = "examples.langgraph_agent:run_agent"
FIXED_ENTRYPOINT = "examples.langgraph_agent:run_agent_fixed"


def main() -> int:
    if not (REPO_ROOT / "pyproject.toml").is_file():
        print("Run this demo from the Stepfork repository root.", file=sys.stderr)
        return 2

    shutil.rmtree(ARTIFACTS, ignore_errors=True)
    ARTIFACTS.mkdir(parents=True)

    from examples.langgraph_agent import agent
    from stepfork import ReplaySession, diff_traces, record

    agent.MODEL_EXECUTIONS.clear()
    agent.TOOL_EXECUTIONS.clear()

    print("=" * 68)
    print("STEPFORK LANGGRAPH DEMO")
    print("=" * 68)

    _step("1. Record the buggy agent run")
    with record("langgraph-triage", output=str(FAILURE_TRACE)) as session:
        buggy_result = agent.run_agent()
        session.set_output(buggy_result)
    print(f"   recorded {FAILURE_TRACE.name} -> {buggy_result}")

    _step("2. Record the corrected agent run")
    with record("langgraph-triage-fixed", output=str(FIXED_TRACE)) as session:
        fixed_result = agent.run_agent_fixed()
        session.set_output(fixed_result)
    print(f"   recorded {FIXED_TRACE.name} -> {fixed_result}")

    _step("3. Validate and verify integrity")
    for trace in (FAILURE_TRACE, FIXED_TRACE):
        _run_cli(["validate", str(trace), "--verify-integrity"], expected=0)
    print("   both bundles are structurally valid and integrity verified")

    _step("4. Replay the buggy agent with frozen model and tool results")
    agent.MODEL_EXECUTIONS.clear()
    agent.TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(FAILURE_TRACE, mode="frozen") as replay:
        replayed = agent.run_agent()
        replay.verify_complete()
        matched = len(replay.matched)
    print(f"   replayed {matched} dependency call(s) -> {replayed}")
    if agent.MODEL_EXECUTIONS or agent.TOOL_EXECUTIONS:
        _fail(
            "frozen replay executed an external dependency: "
            f"model={agent.MODEL_EXECUTIONS!r} tools={agent.TOOL_EXECUTIONS!r}"
        )
        return 1
    print("   no model or tool body executed during frozen replay")

    _step("5. Diff buggy vs corrected behavior")
    diff = diff_traces(FAILURE_TRACE, FIXED_TRACE)
    if diff.equivalent:
        _fail("behavioral diff reported buggy and fixed runs as equivalent")
        return 1
    print(f"   behavior changed: {diff.changed} changed step(s)")

    _step("6. Export pytest regression tests")
    _run_cli(
        [
            "export",
            str(FAILURE_TRACE),
            "--pytest",
            "--entrypoint",
            BUGGY_ENTRYPOINT,
            "--expect-output",
            str(EXPECTED_FILE),
            "--output",
            str(BUGGY_TEST),
            "--overwrite",
        ],
        expected=0,
    )
    _run_cli(
        [
            "export",
            str(FAILURE_TRACE),
            "--pytest",
            "--entrypoint",
            FIXED_ENTRYPOINT,
            "--expect-output",
            str(EXPECTED_FILE),
            "--output",
            str(FIXED_TEST),
            "--overwrite",
        ],
        expected=0,
    )

    _step("7a. Run generated regression test against the BUGGY agent")
    buggy_proc = _run_pytest(BUGGY_TEST)
    if buggy_proc.returncode == 0:
        _fail("expected the buggy implementation to FAIL")
        return 1
    if "behavior mismatch" not in buggy_proc.stdout:
        _fail("buggy test failed for the wrong reason:\n" + _tail(buggy_proc.stdout))
        return 1
    print(_indent(_extract_failure_line(buggy_proc.stdout)))

    _step("7b. Run the SAME expectation against the FIXED agent")
    fixed_proc = _run_pytest(FIXED_TEST)
    if fixed_proc.returncode != 0:
        _fail("expected the fixed implementation to PASS")
        print(_tail(fixed_proc.stdout))
        return 1
    print("   corrected implementation PASSED the regression test")

    print()
    print("=" * 68)
    print("DEMO COMPLETE: LangGraph run -> frozen replay -> regression test")
    print(f"   buggy agent: FAIL (rc={buggy_proc.returncode}), fixed agent: PASS")
    print(f"   artifacts:   {ARTIFACTS}")
    print("=" * 68)
    return 0


def _step(title: str) -> None:
    print()
    print(f"[{title}]")


def _run_cli(args: list[str], *, expected: int) -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "stepfork", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != expected:
        _fail(
            f"command {' '.join(args)} exited {completed.returncode}, "
            f"expected {expected}"
        )
        print(_tail(completed.stdout))
        print(_tail(completed.stderr))
        raise SystemExit(1)
    return completed.stdout


def _run_pytest(test_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            str(test_file),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _extract_failure_line(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if "behavior mismatch" in stripped and "AssertionError" in stripped:
            return stripped
    for line in output.splitlines():
        if "behavior mismatch" in line:
            return line.strip()
    return _tail(output)


def _tail(text: str, limit: int = 800) -> str:
    text = text.strip()
    if not text:
        return "<no output>"
    return text if len(text) <= limit else "..." + text[-limit:]


def _indent(text: str) -> str:
    return "\n".join(f"   {line}" for line in text.splitlines())


def _fail(message: str) -> None:
    print(f"   ERROR: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
