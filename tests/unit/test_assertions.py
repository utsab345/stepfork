from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import ReplaySession, record, trace_tool
from stepfork.assertions import (
    assert_max_steps,
    assert_tool_arguments,
    assert_tool_call_count,
    assert_tool_called,
    assert_tool_not_called,
    assert_tool_order,
    assert_tool_sequence,
    assert_trajectory,
)
from stepfork.replay import RecordedDependencyError, ReplayMismatchError
from stepfork.trace import EventStatus


@trace_tool(name="search")
def search(query: str) -> str:
    return query


@trace_tool(name="book")
def book(code: str) -> str:
    return code


@trace_tool(name="fail")
def fail() -> None:
    raise ValueError("failed")


def _trace(path: Path) -> None:
    with record("assertions", output=path):
        search("first")
        search("second")
        book("A")


def test_assertions_use_executed_calls_and_repeated_occurrences(tmp_path: Path) -> None:
    path = tmp_path / "run.sftrace"
    _trace(path)
    with ReplaySession.from_trace(path) as replay:
        search("first")
        search("second")
        book("A")
        replay.verify_complete()

    assert_tool_called(replay, "search")
    assert_tool_not_called(replay, "charge")
    assert_tool_call_count(replay, "search", 2)
    assert_tool_arguments(replay, "search", {"query": "second"}, occurrence=2)
    assert_tool_order(replay, "search", "book")
    assert_tool_sequence(replay, ["search", "search", "book"])
    assert_tool_sequence(replay, ["search", "book"], strict=False)
    assert_max_steps(replay, 3)
    assert_trajectory(
        replay,
        {
            "called": ["book"],
            "not_called": ["charge"],
            "counts": {"search": 2},
            "arguments": [
                {"name": "search", "value": {"query": "second"}, "occurrence": 2}
            ],
            "order": [["search", "book"]],
            "sequence": ["search", "book"],
            "strict_sequence": False,
            "max_steps": 3,
        },
    )
    with pytest.raises(AssertionError, match="exact tool sequence"):
        assert_tool_sequence(replay, ["search", "book"])
    with pytest.raises(AssertionError, match="at most 2"):
        assert_max_steps(replay, 2)
    with pytest.raises(AssertionError, match="expected arguments"):
        assert_tool_arguments(replay, "search", {"query": "first"}, occurrence=2)


def test_failed_tool_call_counts(tmp_path: Path) -> None:
    path = tmp_path / "run.sftrace"
    with pytest.raises(ValueError), record("failed", output=path):
        fail()
    with (
        ReplaySession.from_trace(path) as replay,
        pytest.raises(RecordedDependencyError),
    ):
        fail()
    assert_tool_call_count(replay, "fail", 1)
    assert replay.executed_calls[0].status is EventStatus.ERROR


def test_incomplete_and_caught_divergence_reject_assertions(tmp_path: Path) -> None:
    path = tmp_path / "run.sftrace"
    _trace(path)
    with ReplaySession.from_trace(path) as replay:
        search("first")
    with pytest.raises(AssertionError, match="incomplete"):
        assert_tool_called(replay, "search")

    with ReplaySession.from_trace(path) as replay:
        with pytest.raises(ReplayMismatchError):
            book("A")
        search("first")
        search("second")
        book("A")
    with pytest.raises(AssertionError, match="diverged"):
        assert_tool_called(replay, "book")


@pytest.mark.parametrize(
    "expectation",
    [
        {"__import__": "os"},
        {"counts": {"search": -1}},
        {"order": [["search"]]},
        {"arguments": [{"name": "search", "value": {}, "eval": "x"}]},
    ],
)
def test_declarative_expectations_reject_bad_shapes(
    tmp_path: Path, expectation: object
) -> None:
    path = tmp_path / "run.sftrace"
    _trace(path)
    with ReplaySession.from_trace(path) as replay:
        search("first")
        search("second")
        book("A")
    with pytest.raises(ValueError):
        assert_trajectory(replay, expectation)
