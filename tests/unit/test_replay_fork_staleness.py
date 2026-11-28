"""Replay classification for forked traces with potentially stale outputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import record, trace_tool
from stepfork.fork import ForkPoint, OverrideSpec, fork_trace
from stepfork.replay import ReplayMismatchError, ReplaySession

SEARCH_RESULT_STEP = 2
BOOK_RESULT_STEP = 4


@trace_tool(name="search")
def search(query: str) -> dict[str, object]:
    return {"query": query, "results": ["a", "b"]}


@trace_tool(name="book")
def book(item: str) -> dict[str, object]:
    return {"item": item, "status": "ok"}


def build_agent(search_value: str = "a,b", book_item: str = "a") -> dict[str, object]:
    search_result = search("flights")
    item = book_item if search_value else "none"
    booking = book(item)
    return {"search": search_result, "booking": booking}


def record_trace(path: Path) -> Path:
    with record("agent", output=path) as session:
        session.set_output(build_agent())
    return path


def forked_trace(path: Path, output: Path) -> Path:
    result = fork_trace(
        path,
        ForkPoint(event_id=None, step=BOOK_RESULT_STEP),
        overrides=[
            OverrideSpec(
                step=SEARCH_RESULT_STEP,
                output={"query": "flights", "results": ["x"]},
            )
        ],
        output_path=output,
    )
    assert result.success, result.error_message
    assert result.forked_trace_path is not None
    return Path(result.forked_trace_path)


def test_replay_marks_substituted_output_after_fork_override_as_stale(
    tmp_path: Path,
) -> None:
    trace_path = record_trace(tmp_path / "base.sftrace")
    fork_path = forked_trace(trace_path, tmp_path / "fork.sftrace")

    with ReplaySession.from_trace(fork_path, mode="frozen") as replay:
        result = build_agent()
        replay.verify_complete()

    assert result["booking"] == {"item": "a", "status": "ok"}
    assert [call.evidence for call in replay.matched] == [
        "recorded",
        "potentially_stale",
    ]
    assert replay.matched[1].action == "substituted"
    assert replay.matched[1].stale_reason is not None


def test_replay_diverges_when_stale_downstream_input_changes(tmp_path: Path) -> None:
    trace_path = record_trace(tmp_path / "base.sftrace")
    fork_path = forked_trace(trace_path, tmp_path / "fork.sftrace")

    with (
        pytest.raises(ReplayMismatchError, match="input diverged"),
        ReplaySession.from_trace(fork_path, mode="frozen") as replay,
    ):
        search("flights")
        book("x")
        replay.verify_complete()


def test_replay_without_fork_provenance_keeps_recorded_evidence(tmp_path: Path) -> None:
    trace_path = record_trace(tmp_path / "base.sftrace")

    with ReplaySession.from_trace(trace_path, mode="frozen") as replay:
        build_agent()
        replay.verify_complete()

    assert [call.evidence for call in replay.matched] == ["recorded", "recorded"]
