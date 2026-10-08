from __future__ import annotations

import json
import shutil
from pathlib import Path

from stepfork import FailureInfo, ToolCall, Trace
from stepfork.trace import (
    ErrorEvent,
    LLMRequest,
    LLMResponse,
    RunEnd,
    RunStart,
    RunStatus,
    ToolResult,
    validate_trace,
)
from stepfork.trace.integrity import IntegrityStatus, verify_bundle_integrity
from stepfork.trace.redaction import REDACTION_REPLACEMENT

SECRET_ONE = "sk-syntheticsecure123456"
SECRET_TWO = "Bearer syntheticsecuretoken123456"
SECRET_THREE = "ghp_syntheticsecure123456"


def test_secure_trace_roundtrip_redacts_hashes_and_verifies(tmp_path: Path) -> None:
    trace = Trace(agent_name="demo-agent")
    start = trace.add(RunStart(input={"prompt": "book", "api_key": SECRET_ONE}))
    request = trace.add(
        LLMRequest(
            model="gpt-test",
            input={
                "messages": [
                    {"role": "user", "content": f"use {SECRET_TWO}"},
                ],
                "clientSecret": SECRET_THREE,
            },
            parent_id=start.id,
        )
    )
    response = trace.add(
        LLMResponse(
            output={"text": "I cannot book that.", "token": SECRET_ONE},
            parent_id=request.id,
        )
    )
    call = trace.add(
        ToolCall(
            name="search",
            input={"query": "Kathmandu flights", "authorization": SECRET_TWO},
            parent_id=response.id,
        )
    )
    result = trace.add(
        ToolResult(
            name="search",
            output={"status": "failed", "debug": SECRET_THREE},
            parent_id=call.id,
        )
    )
    error = trace.add(
        ErrorEvent(
            error_type="ToolError",
            message=f"tool failed with {SECRET_ONE}",
            details={"password": SECRET_TWO},
            parent_id=result.id,
        )
    )
    end = trace.add(
        RunEnd(
            run_status=RunStatus.FAILED,
            output={"final": "failed", "refresh_token": SECRET_THREE},
            parent_id=error.id,
        )
    )

    path = trace.save(
        tmp_path / "secure.sftrace",
        status=RunStatus.FAILED,
        failure=FailureInfo(
            type="ToolError",
            message=f"failure included {SECRET_ONE}",
            step=error.step,
        ),
    )

    for filename in (
        "manifest.json",
        "events.jsonl",
        "redactions.json",
        "integrity.json",
    ):
        assert (path / filename).is_file()

    persisted = "\n".join(item.read_text() for item in path.iterdir() if item.is_file())
    assert SECRET_ONE not in persisted
    assert SECRET_TWO not in persisted
    assert SECRET_THREE not in persisted

    redactions = json.loads((path / "redactions.json").read_text())
    paths = {entry["path"] for entry in redactions["entries"]}
    assert "/input/api_key" in paths
    assert "/input/clientSecret" in paths
    assert "/details/password" in paths
    assert "/failure/message" in paths
    assert repr(redactions).count("syntheticsecure") == 0

    loaded = Trace.load(path)
    assert verify_bundle_integrity(path).status is IntegrityStatus.VERIFIED
    assert validate_trace(loaded, verify_payload_hashes=True).valid
    assert loaded.events[0].id == start.id
    assert loaded.events[-1].id == end.id
    assert loaded.events[1].parent_id == start.id
    assert loaded.events[5].parent_id == result.id

    for event in loaded.events:
        if hasattr(event, "input"):
            assert event.input_hash is not None
        if hasattr(event, "output") and event.output is not None:
            assert event.output_hash is not None

    assert loaded.events[0].model_dump(mode="json")["input"]["api_key"] == (
        REDACTION_REPLACEMENT
    )
    assert loaded.events[5].model_dump(mode="json")["details"]["password"] == (
        REDACTION_REPLACEMENT
    )
    assert loaded.failure is not None
    assert loaded.failure.message == f"failure included {REDACTION_REPLACEMENT}"

    tampered = tmp_path / "tampered.sftrace"
    shutil.copytree(path, tampered)
    lines = (tampered / "events.jsonl").read_text().splitlines()
    event = json.loads(lines[3])
    event["input"]["query"] = "Pokhara flights"
    lines[3] = json.dumps(event)
    (tampered / "events.jsonl").write_text("\n".join(lines) + "\n")
    assert verify_bundle_integrity(tampered).status is IntegrityStatus.MISMATCH

    legacy = tmp_path / "legacy.sftrace"
    shutil.copytree(path, legacy)
    (legacy / "integrity.json").unlink()
    assert Trace.load(legacy).run_id == trace.run_id
    assert verify_bundle_integrity(legacy).status is IntegrityStatus.UNVERIFIED_LEGACY
