"""End-to-end failure-to-test demonstration for Stepfork.

Run from the repository root::

    uv run python examples/booking_agent/demo.py

The demo performs the full v0.1 workflow with real subprocesses and real exit
codes. It never prints fabricated results:

1.  Record the buggy agent run into ``failure.sftrace``.
2.  Record the corrected agent run into ``fixed.sftrace``.
3.  Validate both bundles and verify integrity.
4.  Inspect the failing bundle.
5.  Replay the buggy agent with frozen dependencies.
6.  Diff the buggy and corrected behavior.
7.  Export executable pytest regression tests for both entrypoints.
8.  Run the generated test against the buggy code (must FAIL) and the
    corrected code (must PASS).
9.  Confirm the external tool body did not execute during frozen replay.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = Path(__file__).resolve().parent
ARTIFACTS = EXAMPLE_DIR / ".artifacts"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FAILURE_TRACE = ARTIFACTS / "booking_failure.sftrace"
FIXED_TRACE = ARTIFACTS / "booking_fixed.sftrace"
EXPECTED_FILE = EXAMPLE_DIR / "expected.json"
BUGGY_TEST = ARTIFACTS / "test_booking_buggy.py"
FIXED_TEST = ARTIFACTS / "test_booking_fixed.py"

BUGGY_ENTRYPOINT = "examples.booking_agent:run_agent"
FIXED_ENTRYPOINT = "examples.booking_agent:run_agent_fixed"


def main() -> int:
    if not (REPO_ROOT / "pyproject.toml").is_file():
        print("Run this demo from the Stepfork repository root.", file=sys.stderr)
        return 2

    shutil.rmtree(ARTIFACTS, ignore_errors=True)
    ARTIFACTS.mkdir(parents=True)

    from examples.booking_agent import agent

    agent.TOOL_EXECUTIONS.clear()

    print("=" * 68)
    print("STEPFORK FAILURE-TO-TEST DEMO")
    print("=" * 68)

    _step("1. Record the buggy agent run")
    from stepfork import record

    with record("booking-agent", output=str(FAILURE_TRACE)) as session:
        buggy_result = agent.run_agent()
        session.set_output(buggy_result)
    print(f"   recorded {FAILURE_TRACE.name} -> {buggy_result}")

    _step("2. Record the corrected agent run")
    with record("booking-agent-fixed", output=str(FIXED_TRACE)) as session:
        fixed_result = agent.run_agent_fixed()
        session.set_output(fixed_result)
    print(f"   recorded {FIXED_TRACE.name} -> {fixed_result}")

    if buggy_result == fixed_result:
        _fail("buggy and corrected runs produced identical output; demo is invalid")
        return 1

    _step("3. Validate and verify integrity")
    for trace in (FAILURE_TRACE, FIXED_TRACE):
        _run_cli(["validate", str(trace), "--verify-integrity"], expected=0)
    print("   both bundles are structurally valid and integrity verified")

    _step("4. Inspect the failing bundle")
    inspection = json.loads(
        _run_cli(["inspect", str(FAILURE_TRACE), "--json"], capture=True, expected=0)
    )
    print(
        f"   agent={inspection['agent_name']} "
        f"status={inspection['status']} events={inspection['events']} "
        f"integrity={inspection['integrity']}"
    )

    _step("5. Replay the buggy agent with frozen dependencies")
    from stepfork import ReplaySession

    agent.TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(FAILURE_TRACE, mode="frozen") as replay:
        replayed = agent.run_agent()
        replay.verify_complete()
        matched = len(replay.matched)
    print(f"   replayed {matched} dependency call(s) -> {replayed}")
    if replayed != buggy_result:
        _fail("frozen replay did not reproduce the recorded behavior")
        return 1
    if agent.TOOL_EXECUTIONS:
        _fail(
            f"frozen replay executed the external tool body: {agent.TOOL_EXECUTIONS!r}"
        )
        return 1
    print("   no external dependency executed (tool body untouched)")

    _step("6. Diff buggy vs corrected behavior")
    from stepfork import diff_traces

    diff = diff_traces(FAILURE_TRACE, FIXED_TRACE)
    if diff.equivalent:
        _fail("behavioral diff reported the buggy and fixed runs as equivalent")
        return 1
    changed_paths = sorted(
        {change.path for step in diff.steps for change in step.changes}
    )
    print(f"   behavior changed: {diff.changed} changed step(s); {changed_paths}")

    _step("7. Export pytest regression tests (expectation = cheapest flight)")
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
    print(f"   wrote {BUGGY_TEST.name} and {FIXED_TEST.name}")

    _step("8a. Run generated regression test against the BUGGY agent")
    buggy_proc = _run_pytest(BUGGY_TEST)
    if buggy_proc.returncode == 0:
        _fail("expected the buggy implementation to FAIL the regression test")
        return 1
    if "behavior mismatch" not in buggy_proc.stdout:
        _fail(
            "buggy test failed for the wrong reason; expected a 'behavior "
            "mismatch' assertion, got:\n" + _tail(buggy_proc.stdout)
        )
        return 1
    print(_indent(_extract_failure_line(buggy_proc.stdout)))

    _step("8b. Run the SAME expectation against the FIXED agent")
    fixed_proc = _run_pytest(FIXED_TEST)
    if fixed_proc.returncode != 0:
        _fail("expected the corrected implementation to PASS")
        print(_tail(fixed_proc.stdout))
        return 1
    print("   corrected implementation PASSED the regression test")

    _step("9. External dependency execution count")
    print(f"   tool bodies executed during frozen replay: {len(agent.TOOL_EXECUTIONS)}")

    print()
    print("=" * 68)
    print("DEMO COMPLETE: failure -> frozen trace -> regression test")
    print(f"   buggy agent: FAIL (rc={buggy_proc.returncode}), fixed agent: PASS")
    print(f"   artifacts:   {ARTIFACTS}")
    print("=" * 68)
    return 0


def _step(title: str) -> None:
    print()
    print(f"[{title}]")


def _run_cli(
    args: list[str],
    *,
    expected: int,
    capture: bool = False,
) -> str:
    command = [sys.executable, "-m", "stepfork", *args]
    completed = subprocess.run(
        command,
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
    return completed.stdout if capture else ""


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
