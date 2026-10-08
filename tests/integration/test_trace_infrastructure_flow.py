from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from stepfork import FailureInfo, Trace
from stepfork.cli.main import app
from stepfork.trace import (
    ErrorEvent,
    EventStatus,
    LLMRequest,
    LLMResponse,
    RunEnd,
    RunStart,
    RunStatus,
    StateChange,
    ToolCall,
    ToolResult,
    validate_bundle,
)
from stepfork.trace.integrity import IntegrityStatus, verify_bundle_integrity

runner = CliRunner()
SECRET = "sk-syntheticflow123456"


def test_full_trace_infrastructure_flow(tmp_path: Path) -> None:
    trace = Trace(agent_name="flow-agent")
    start = trace.add(RunStart(input={"prompt": "book", "api_key": SECRET}))
    llm_request = trace.add(
        LLMRequest(
            model="gpt-test",
            input={"messages": [{"role": "user", "content": "book"}]},
            parent_id=start.id,
        )
    )
    llm_response = trace.add(
        LLMResponse(
            model="gpt-test",
            output={"plan": "call search"},
            parent_id=llm_request.id,
        )
    )
    tool_call = trace.add(
        ToolCall(
            name="search",
            input={"query": "Kathmandu flights", "authorization": f"Bearer {SECRET}"},
            parent_id=llm_response.id,
        )
    )
    tool_result = trace.add(
        ToolResult(
            name="search",
            output={"ok": False, "reason": "timeout"},
            status=EventStatus.ERROR,
            parent_id=tool_call.id,
        )
    )
    state = trace.add(
        StateChange(
            key="attempt",
            before={"count": 0},
            after={"count": 1},
            parent_id=tool_result.id,
        )
    )
    error = trace.add(
        ErrorEvent(
            error_type="ToolTimeout",
            message=f"timeout {SECRET}",
            details={"retryable": True},
            parent_id=state.id,
        )
    )
    trace.add(RunEnd(run_status=RunStatus.FAILED, parent_id=error.id))

    path = trace.save(
        tmp_path / "flow.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolTimeout", message=f"timeout {SECRET}", step=6),
    )
    persisted = "\n".join(item.read_text() for item in path.iterdir() if item.is_file())
    assert SECRET not in persisted

    loaded = Trace.load(path)
    assert [event.type for event in loaded.events] == [
        event.type for event in trace.events
    ]
    assert loaded.failure is not None
    assert loaded.failure.message == "timeout [REDACTED]"
    assert validate_bundle(path, verify_integrity=True).valid
    assert verify_bundle_integrity(path).status is IntegrityStatus.VERIFIED

    moved = tmp_path / "moved.sftrace"
    shutil.copytree(path, moved)
    assert Trace.load(moved).run_id == loaded.run_id
    assert verify_bundle_integrity(moved).status is IntegrityStatus.VERIFIED

    inspect_result = runner.invoke(app, ["inspect", str(moved), "--json"])
    assert inspect_result.exit_code == 0
    assert SECRET not in inspect_result.stdout
    assert json.loads(inspect_result.stdout)["events"] == 8

    validate_result = runner.invoke(
        app,
        ["validate", str(moved), "--verify-integrity"],
    )
    assert validate_result.exit_code == 0


def test_public_day3_api_remains_compatible(tmp_path: Path) -> None:
    from stepfork import ToolCall

    trace = Trace(agent_name="demo-agent")
    trace.add(ToolCall(name="search", input={"query": "Kathmandu flights"}))
    path = trace.save(tmp_path / "demo.sftrace")
    loaded = Trace.load(path)

    assert loaded.agent_name == "demo-agent"
    assert runner.invoke(app, ["validate", str(path), "--partial"]).exit_code == 0
    assert runner.invoke(app, ["inspect", str(path)]).exit_code == 0
