from __future__ import annotations

import json
from pathlib import Path

from stepfork import FailureInfo, ToolCall, Trace
from stepfork.inspect.inspector import filter_timeline, inspect_bundle
from stepfork.trace import (
    ErrorEvent,
    EventStatus,
    RunEnd,
    RunStart,
    RunStatus,
    ToolResult,
)


def failed_trace(secret: str = "sk-syntheticinspect123456") -> Trace:
    trace = Trace(agent_name="booking-agent")
    start = trace.add(RunStart(input={"prompt": "book"}))
    call = trace.add(
        ToolCall(
            name="flight_search",
            input={"query": "Kathmandu flights", "api_key": secret},
            parent_id=start.id,
        )
    )
    result = trace.add(
        ToolResult(
            name="flight_search",
            output={"ok": False, "debug": "timeout"},
            parent_id=call.id,
            status=EventStatus.ERROR,
        )
    )
    error = trace.add(
        ErrorEvent(
            error_type="ToolError",
            message=f"failed with {secret}",
            parent_id=result.id,
        )
    )
    trace.add(RunEnd(run_status=RunStatus.FAILED, parent_id=error.id))
    return trace


def test_inspect_bundle_summarizes_failed_trace(tmp_path: Path) -> None:
    trace = failed_trace()
    path = trace.save(
        tmp_path / "failed.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolError", message="failed", step=3),
    )

    inspection = inspect_bundle(path)

    assert inspection.agent_name == "booking-agent"
    assert inspection.status == "failed"
    assert inspection.events == 5
    assert inspection.tool_calls == 1
    assert inspection.integrity == "verified"
    assert [event.type for event in inspection.timeline] == [
        "run_start",
        "tool_call",
        "tool_result",
        "error",
        "run_end",
    ]


def test_inspect_bundle_supports_error_filter(tmp_path: Path) -> None:
    path = failed_trace().save(
        tmp_path / "failed.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolError", message="failed", step=3),
    )

    inspection = filter_timeline(inspect_bundle(path), errors_only=True)

    assert [event.type for event in inspection.timeline] == ["tool_result", "error"]


def test_inspect_bundle_supports_step_filter(tmp_path: Path) -> None:
    path = failed_trace().save(
        tmp_path / "failed.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolError", message="failed", step=3),
    )

    inspection = filter_timeline(inspect_bundle(path), step=1)

    assert len(inspection.timeline) == 1
    assert inspection.timeline[0].label == "flight_search"


def test_inspection_json_model_serializes(tmp_path: Path) -> None:
    path = failed_trace().save(
        tmp_path / "failed.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolError", message="failed", step=3),
    )

    payload = json.loads(inspect_bundle(path).model_dump_json())

    assert payload["agent_name"] == "booking-agent"
    assert payload["timeline"][1]["type"] == "tool_call"


def test_inspector_applies_presentation_time_sanitization(tmp_path: Path) -> None:
    secret = "sk-syntheticlegacyinspect123456"
    path = failed_trace(secret).save(
        tmp_path / "legacyish.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolError", message=f"failed {secret}", step=3),
    )
    lines = (path / "events.jsonl").read_text().splitlines()
    event = json.loads(lines[1])
    event["input"]["note"] = f"legacy carried {secret}"
    lines[1] = json.dumps(event)
    (path / "events.jsonl").write_text("\n".join(lines) + "\n")

    inspection = inspect_bundle(path)

    assert secret not in inspection.model_dump_json()


def test_inspection_does_not_mutate_bundle(tmp_path: Path) -> None:
    path = failed_trace().save(
        tmp_path / "failed.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(type="ToolError", message="failed", step=3),
    )
    before = {item.name: item.read_bytes() for item in path.iterdir() if item.is_file()}

    inspect_bundle(path)

    after = {item.name: item.read_bytes() for item in path.iterdir() if item.is_file()}
    assert after == before


def test_empty_trace_inspects(tmp_path: Path) -> None:
    path = Trace(agent_name="demo-agent").save(tmp_path / "empty.sftrace")

    inspection = inspect_bundle(path)

    assert inspection.events == 0
    assert inspection.timeline == []
