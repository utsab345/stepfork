"""End-to-end refund-agent failure-to-test integration test.

Exercises the complete v0.1 workflow against the second example agent:
record, validate, inspect, frozen replay, behavioral diff, and generated
pytest regression tests executed as real subprocesses.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from stepfork import ReplaySession, diff_traces, record
from stepfork.export import export_pytest_test
from stepfork.inspect import inspect_bundle
from stepfork.trace import RunStatus, Trace, validate_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "decision": "approve",
    "order_id": "ORD-2024-7717",
    "refund_amount": 59.99,
    "reason": "Refund approved.",
    "plan": "Decide refund eligibility from the policy, then approve or deny.",
}


def _example_agent() -> Any:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from examples import refund_agent

    return refund_agent


def _record(agent: Any, destination: Path, *, fixed: bool) -> dict[str, Any]:
    runner = agent.run_agent_fixed if fixed else agent.run_agent
    with record("refund-agent", output=destination) as session:
        result: dict[str, Any] = runner()
        session.set_output(result)
    return result


def test_refund_failure_to_test_pipeline(tmp_path: Path) -> None:
    agent = _example_agent()
    agent.TOOL_EXECUTIONS.clear()

    failure = tmp_path / "refund_failure.sftrace"
    fixed = tmp_path / "refund_fixed.sftrace"

    buggy_result = _record(agent, failure, fixed=False)
    fixed_result = _record(agent, fixed, fixed=True)
    assert buggy_result["decision"] == "deny"
    assert fixed_result["decision"] == "approve"

    # 1. Structural validation + integrity.
    result = validate_bundle(failure, strict=True, verify_integrity=True)
    assert result.valid, result.issues
    assert Trace.load(failure).status is RunStatus.COMPLETED

    # 2. Inspection.
    inspection = inspect_bundle(failure)
    assert inspection.agent_name == "refund-agent"
    assert inspection.events == 6
    assert inspection.integrity == "verified"

    # 3. Frozen replay must not execute the external policy tool body.
    agent.TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(failure, mode="frozen") as replay:
        replayed = agent.run_agent()
        replay.verify_complete()
    assert replayed == buggy_result
    assert agent.TOOL_EXECUTIONS == []

    # 4. Behavioral diff detects the incorrect deny decision.
    diff = diff_traces(failure, fixed)
    assert not diff.equivalent
    paths = {change.path for step in diff.steps for change in step.changes}
    assert "output.decision" in paths

    # 5. Export executable regression tests for both implementations.
    buggy_test = export_pytest_test(
        trace_path=failure,
        output_path=tmp_path / "test_refund_buggy.py",
        entrypoint="examples.refund_agent:run_agent",
        expectation=EXPECTED,
        has_expectation=True,
        import_root=REPO_ROOT,
    )
    fixed_test = export_pytest_test(
        trace_path=failure,
        output_path=tmp_path / "test_refund_fixed.py",
        entrypoint="examples.refund_agent:run_agent_fixed",
        expectation=EXPECTED,
        has_expectation=True,
        import_root=REPO_ROOT,
    )

    buggy_proc = _run_pytest(buggy_test)
    assert buggy_proc.returncode != 0, buggy_proc.stdout
    assert "behavior mismatch" in buggy_proc.stdout
    assert "decision" in buggy_proc.stdout

    fixed_proc = _run_pytest(fixed_test)
    assert fixed_proc.returncode == 0, fixed_proc.stdout


def test_refund_replay_never_executes_external_dependency(tmp_path: Path) -> None:
    agent = _example_agent()
    trace = tmp_path / "run.sftrace"
    _record(agent, trace, fixed=False)

    agent.TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(trace, mode="frozen"):
        agent.run_agent()
    assert agent.TOOL_EXECUTIONS == []

    # Running the untouched agent does execute the policy tool body.
    agent.run_agent()
    assert agent.TOOL_EXECUTIONS == ["ORD-2024-7717"]


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
