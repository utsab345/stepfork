from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from stepfork.trace import FailureInfo, RunStatus, TraceManifest, TraceTotals


def aware_now() -> datetime:
    return datetime(2026, 10, 7, 14, 30, tzinfo=UTC)


def test_valid_manifest() -> None:
    manifest = TraceManifest(
        run_id="run_123",
        agent_name="demo-agent",
        created_at=aware_now(),
        status=RunStatus.COMPLETED,
    )

    assert manifest.format == "stepfork"
    assert manifest.schema_version == "0.1"
    assert manifest.totals.events == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("format", "other"),
        ("schema_version", "1.0"),
        ("run_id", ""),
        ("agent_name", ""),
    ],
)
def test_manifest_rejects_invalid_contract_fields(field: str, value: str) -> None:
    kwargs: dict[str, Any] = {
        "run_id": "run_123",
        "agent_name": "demo-agent",
        "created_at": aware_now(),
        "status": RunStatus.COMPLETED,
        field: value,
    }

    with pytest.raises(ValidationError):
        TraceManifest.model_validate(kwargs)


def test_manifest_rejects_naive_created_at() -> None:
    with pytest.raises(ValidationError):
        TraceManifest(
            run_id="run_123",
            agent_name="demo-agent",
            created_at=datetime(2026, 10, 7, 14, 30),
            status=RunStatus.COMPLETED,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("events", -1),
        ("llm_calls", -1),
        ("tool_calls", -1),
        ("cost_usd", -0.01),
        ("duration_ms", -1),
    ],
)
def test_trace_totals_reject_negative_values(field: str, value: int | float) -> None:
    with pytest.raises(ValidationError):
        TraceTotals.model_validate({field: value})


def test_failed_manifest_requires_failure() -> None:
    with pytest.raises(ValidationError):
        TraceManifest(
            run_id="run_123",
            agent_name="demo-agent",
            created_at=aware_now(),
            status=RunStatus.FAILED,
        )


def test_non_failed_manifest_rejects_failure() -> None:
    with pytest.raises(ValidationError):
        TraceManifest(
            run_id="run_123",
            agent_name="demo-agent",
            created_at=aware_now(),
            status=RunStatus.COMPLETED,
            failure=FailureInfo(type="AssertionError", message="boom", step=2),
        )


def test_failed_manifest_accepts_failure() -> None:
    manifest = TraceManifest(
        run_id="run_123",
        agent_name="demo-agent",
        created_at=aware_now(),
        status=RunStatus.FAILED,
        failure=FailureInfo(type="AssertionError", message="boom", step=2),
    )

    assert manifest.failure is not None
    assert manifest.failure.step == 2


def test_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TraceManifest.model_validate(
            {
                "run_id": "run_123",
                "agent_name": "demo-agent",
                "created_at": aware_now(),
                "status": RunStatus.COMPLETED,
                "unexpected": True,
            }
        )
