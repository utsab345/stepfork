from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from stepfork import ReplaySession, record, trace_tool
from stepfork.export.generator import ExportError, generate_pytest_source
from stepfork.export.runtime import run_regression_case
from stepfork.replay import ReplayMismatchError, ReplayPolicyError

EFFECTS: list[str] = []


@trace_tool(name="send_email")
def send_email(address: str) -> str:
    EFFECTS.append(address)
    return "sent"


@trace_tool(name="charge_card")
def charge_card(amount: int) -> str:
    EFFECTS.append(f"charged {amount}")
    return "charged"


@trace_tool(name="book_flight")
async def book_flight(destination: str) -> str:
    EFFECTS.append(destination)
    return "booked"


def send_notification() -> str:
    return send_email("customer@example.test")


def test_live_tool_requires_explicit_authorization_before_body(tmp_path: Path) -> None:
    path = tmp_path / "email.sftrace"
    with record("email", output=path):
        assert send_notification() == "sent"
    EFFECTS.clear()

    with ReplaySession.from_trace(path, mode="live") as replay:
        with pytest.raises(ReplayPolicyError, match="requires explicit authorization"):
            send_notification()
        assert replay.pending == 1
        assert replay.matched == []
        assert isinstance(replay.divergence, ReplayPolicyError)
    assert EFFECTS == []

    with ReplaySession.from_trace(
        path, mode="live", allow_live_tools={"send_email"}
    ) as replay:
        assert send_notification() == "sent"
        replay.verify_complete()
    assert EFFECTS == ["customer@example.test"]
    assert replay.executed_calls[0].action == "executed"


def test_live_authorization_is_per_tool_name(tmp_path: Path) -> None:
    path = tmp_path / "payment.sftrace"
    with record("payment", output=path):
        send_notification()
        charge_card(100)
    EFFECTS.clear()

    with ReplaySession.from_trace(
        path, mode="live", allow_live_tools={"send_email"}
    ) as replay:
        send_notification()
        with pytest.raises(ReplayPolicyError, match="charge_card"):
            charge_card(100)
        assert replay.pending == 1
    assert EFFECTS == ["customer@example.test"]

    with pytest.raises(ValueError, match="only valid with mode='live'"):
        ReplaySession.from_trace(path, mode="frozen", allow_live_tools={"send_email"})
    with pytest.raises(ValueError, match="only valid with mode='live'"):
        ReplaySession.from_trace(
            path,
            mode="hybrid",
            live_llms={"fake/model"},
            allow_live_tools={"send_email"},
        )
    with pytest.raises(ValueError, match="not found in trace"):
        ReplaySession.from_trace(path, mode="live", allow_live_tools={"delete_db"})


def test_authorization_does_not_weaken_strict_matching(tmp_path: Path) -> None:
    path = tmp_path / "payment.sftrace"
    with record("payment", output=path):
        charge_card(100)
    EFFECTS.clear()

    with ReplaySession.from_trace(
        path, mode="live", allow_live_tools={"charge_card"}
    ) as replay:
        with pytest.raises(ReplayMismatchError, match="input diverged"):
            charge_card(200)
        assert replay.pending == 1
    assert EFFECTS == []


def test_async_live_tool_requires_authorization(tmp_path: Path) -> None:
    path = tmp_path / "booking.sftrace"

    async def scenario() -> None:
        async with record("booking", output=path):
            assert await book_flight("LIS") == "booked"
        EFFECTS.clear()
        async with ReplaySession.from_trace(path, mode="live") as replay:
            with pytest.raises(ReplayPolicyError, match="book_flight"):
                await book_flight("LIS")
            assert replay.pending == 1
        assert EFFECTS == []
        async with ReplaySession.from_trace(
            path, mode="live", allow_live_tools={"book_flight"}
        ) as replay:
            assert await book_flight("LIS") == "booked"
            replay.verify_complete()

    asyncio.run(scenario())
    assert EFFECTS == ["LIS"]


def test_exported_live_case_requires_tool_authorization(tmp_path: Path) -> None:
    path = tmp_path / "email.sftrace"
    with record("email", output=path):
        send_notification()
    EFFECTS.clear()
    with pytest.raises(AssertionError, match="requires explicit authorization"):
        run_regression_case(
            trace_path=path,
            import_root=Path(__file__).parent,
            entrypoint="test_live_tool_authorization:send_notification",
            expectation="sent",
            mode="live",
        )
    assert EFFECTS == []
    assert (
        run_regression_case(
            trace_path=path,
            import_root=Path(__file__).parent,
            entrypoint="test_live_tool_authorization:send_notification",
            expectation="sent",
            mode="live",
            allow_live_tools={"send_email"},
        )
        == "sent"
    )

    source = generate_pytest_source(
        trace_path=path,
        output_path=tmp_path / "test_email.py",
        entrypoint="test_live_tool_authorization:send_notification",
        expectation="sent",
        mode="live",
        allow_live_tools={"send_email"},
    )
    assert "ALLOW_LIVE_TOOLS = set(['send_email'])" in source
    with pytest.raises(ExportError, match="only valid"):
        generate_pytest_source(
            trace_path=path,
            output_path=tmp_path / "test_email.py",
            entrypoint="test_live_tool_authorization:send_notification",
            allow_live_tools={"send_email"},
        )
