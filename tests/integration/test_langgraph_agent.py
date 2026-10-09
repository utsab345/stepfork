"""End-to-end LangGraph failure-to-test integration test.

This exercises the optional LangGraph integration with a real ``StateGraph``,
real recording, real frozen replay, real diff, real generated pytest files,
and real subprocess exit codes. It is fully offline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from stepfork import ReplaySession, diff_traces, record
from stepfork.export import export_pytest_test
from stepfork.trace import RunStatus, Trace, validate_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {"approved": True, "customer_id": "c-100"}


def _example_agent() -> Any:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from examples import langgraph_agent

    return langgraph_agent


def _record(agent: Any, destination: Path, *, fixed: bool) -> dict[str, Any]:
    runner = agent.run_agent_fixed if fixed else agent.run_agent
    with record("langgraph-triage", output=destination) as session:
        result: dict[str, Any] = runner()
        session.set_output(result)
    return result


def test_langgraph_failure_to_test_pipeline(tmp_path: Path) -> None:
    agent = _example_agent()
    agent.MODEL_EXECUTIONS.clear()
    agent.TOOL_EXECUTIONS.clear()

    failure = tmp_path / "langgraph_failure.sftrace"
    fixed_trace = tmp_path / "langgraph_fixed.sftrace"

    buggy_result = _record(agent, failure, fixed=False)
    fixed_result = _record(agent, fixed_trace, fixed=True)
    assert buggy_result == {"approved": False, "customer_id": "c-100"}
    assert fixed_result == EXPECTED

    result = validate_bundle(failure, strict=True, verify_integrity=True)
    assert result.valid, result.issues
    assert Trace.load(failure).status is RunStatus.COMPLETED

    # Frozen replay must execute neither the model nor the tool bodies.
    agent.MODEL_EXECUTIONS.clear()
    agent.TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(failure, mode="frozen") as replay:
        replayed = agent.run_agent()
        replay.verify_complete()
        matched = list(replay.matched)
    assert replayed == buggy_result
    assert agent.MODEL_EXECUTIONS == []
    assert agent.TOOL_EXECUTIONS == []
    assert [call.kind for call in matched] == ["llm", "tool", "llm", "tool", "llm"]

    diff = diff_traces(failure, fixed_trace)
    assert not diff.equivalent
    paths = {change.path for step in diff.steps for change in step.changes}
    assert "output.approved" in paths

    buggy_test = export_pytest_test(
        trace_path=failure,
        output_path=tmp_path / "test_langgraph_buggy.py",
        entrypoint="examples.langgraph_agent:run_agent",
        expectation=EXPECTED,
        has_expectation=True,
        import_root=REPO_ROOT,
    )
    fixed_test = export_pytest_test(
        trace_path=failure,
        output_path=tmp_path / "test_langgraph_fixed.py",
        entrypoint="examples.langgraph_agent:run_agent_fixed",
        expectation=EXPECTED,
        has_expectation=True,
        import_root=REPO_ROOT,
    )

    buggy_proc = _run_pytest(buggy_test)
    assert buggy_proc.returncode != 0, buggy_proc.stdout
    assert "behavior mismatch" in buggy_proc.stdout
    assert "approved" in buggy_proc.stdout

    fixed_proc = _run_pytest(fixed_test)
    assert fixed_proc.returncode == 0, fixed_proc.stdout


def test_langgraph_replay_never_executes_dependencies(tmp_path: Path) -> None:
    agent = _example_agent()
    trace = tmp_path / "run.sftrace"
    _record(agent, trace, fixed=False)

    agent.MODEL_EXECUTIONS.clear()
    agent.TOOL_EXECUTIONS.clear()
    with ReplaySession.from_trace(trace, mode="frozen"):
        agent.run_agent()
    assert agent.MODEL_EXECUTIONS == []
    assert agent.TOOL_EXECUTIONS == []

    # Running the untouched agent does execute the model and tool bodies.
    agent.MODEL_EXECUTIONS.clear()
    agent.TOOL_EXECUTIONS.clear()
    agent.run_agent()
    assert len(agent.MODEL_EXECUTIONS) == 3
    assert [name for name, _ in agent.TOOL_EXECUTIONS] == [
        "lookup_customer",
        "get_refund_policy",
    ]


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
