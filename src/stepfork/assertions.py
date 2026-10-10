"""Assertions over dependency calls actually reached during replay."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from stepfork.replay.exceptions import ReplayError
from stepfork.replay.session import ExecutedCall, ReplaySession
from stepfork.trace.canonical import canonical_json_bytes
from stepfork.trace.jsonable import to_json_value
from stepfork.trace.redaction import redact_json


def _calls(replay: ReplaySession) -> tuple[ExecutedCall, ...]:
    if replay.divergence is not None:
        raise AssertionError(f"stepfork replay diverged: {replay.divergence}")
    try:
        replay.verify_complete()
    except ReplayError as exc:
        raise AssertionError(f"stepfork replay incomplete: {exc}") from exc
    return replay.executed_calls


def _tools(replay: ReplaySession) -> tuple[ExecutedCall, ...]:
    return tuple(call for call in _calls(replay) if call.kind == "tool")


def _names(calls: Sequence[ExecutedCall]) -> list[str]:
    return [call.label for call in calls]


def assert_tool_called(replay: ReplaySession, name: str) -> None:
    """Require at least one call, including calls with a recorded error."""
    names = _names(_tools(replay))
    assert name in names, f"expected tool {name!r} to be called; actual: {names!r}"


def assert_tool_not_called(replay: ReplaySession, name: str) -> None:
    """Require that no call to ``name`` occurred."""
    names = _names(_tools(replay))
    assert name not in names, (
        f"expected tool {name!r} not to be called; actual: {names!r}"
    )


def assert_tool_call_count(replay: ReplaySession, name: str, count: int) -> None:
    """Require exactly ``count`` calls to ``name``; failures count."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count must be a non-negative integer")
    actual = _names(_tools(replay)).count(name)
    assert actual == count, f"tool {name!r}: expected {count} call(s), got {actual}"


def assert_tool_arguments(
    replay: ReplaySession,
    name: str,
    arguments: Any,
    *,
    occurrence: int | None = None,
) -> None:
    """Require exact JSON arguments on any or one 1-based occurrence."""
    expected = redact_json(to_json_value(arguments)).value
    calls = [call for call in _tools(replay) if call.label == name]
    if occurrence is not None:
        if (
            not isinstance(occurrence, int)
            or isinstance(occurrence, bool)
            or occurrence < 1
        ):
            raise ValueError("occurrence must be a positive integer")
        assert len(calls) >= occurrence, (
            f"tool {name!r}: occurrence {occurrence} was not called; "
            f"got {len(calls)} call(s)"
        )
        calls = [calls[occurrence - 1]]
    actual = [call.input for call in calls]
    assert any(
        canonical_json_bytes(item) == canonical_json_bytes(expected) for item in actual
    ), f"tool {name!r}: expected arguments {expected!r}; actual: {actual!r}"


def assert_tool_order(replay: ReplaySession, before: str, after: str) -> None:
    """Require a distinct occurrence of ``before`` preceding ``after``."""
    names = _names(_tools(replay))
    valid = any(
        first == before and after in names[index + 1 :]
        for index, first in enumerate(names)
    )
    assert valid, f"expected {before!r} before {after!r}; actual: {names!r}"


def assert_tool_sequence(
    replay: ReplaySession, sequence: Sequence[str], *, strict: bool = True
) -> None:
    """Require exact tool sequence, or an ordered subsequence when non-strict."""
    expected = list(sequence)
    if not expected or any(not isinstance(name, str) or not name for name in expected):
        raise ValueError("sequence must contain non-empty tool names")
    actual = _names(_tools(replay))
    if strict:
        assert actual == expected, (
            f"expected exact tool sequence {expected!r}; actual: {actual!r}"
        )
        return
    cursor = 0
    for name in actual:
        if cursor < len(expected) and name == expected[cursor]:
            cursor += 1
    assert cursor == len(expected), (
        f"expected ordered tool subsequence {expected!r}; actual: {actual!r}"
    )


def assert_max_steps(replay: ReplaySession, maximum: int) -> None:
    """Limit matched dependency calls (tools and LLMs), including failures."""
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
        raise ValueError("maximum must be a non-negative integer")
    actual = len(_calls(replay))
    assert actual <= maximum, (
        f"expected at most {maximum} dependency step(s), got {actual}"
    )


def _apply_trajectory(replay: ReplaySession | None, expectation: Any) -> None:
    """Validate and optionally apply a JSON trajectory expectation.

    Supported keys: ``called``, ``not_called``, ``counts``, ``arguments``,
    ``order``, ``sequence``, ``strict_sequence``, and ``max_steps``.
    """
    if not isinstance(expectation, dict):
        raise ValueError("trajectory expectation must be a JSON object")
    allowed = {
        "called",
        "not_called",
        "counts",
        "arguments",
        "order",
        "sequence",
        "strict_sequence",
        "max_steps",
    }
    unknown = set(expectation) - allowed
    if unknown:
        raise ValueError(f"unknown trajectory expectation key(s): {sorted(unknown)!r}")

    def names(key: str) -> list[str]:
        value = expectation.get(key, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise ValueError(f"{key} must be a list of non-empty tool names")
        return value

    called = names("called")
    not_called = names("not_called")
    counts = expectation.get("counts", {})
    if not isinstance(counts, dict) or any(
        not isinstance(name, str)
        or not name
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        for name, count in counts.items()
    ):
        raise ValueError("counts must map tool names to non-negative integers")
    arguments = expectation.get("arguments", [])
    if not isinstance(arguments, list) or any(
        not isinstance(item, dict)
        or set(item) - {"name", "value", "occurrence"}
        or "value" not in item
        or not isinstance(item.get("name"), str)
        or not item["name"]
        or (
            "occurrence" in item
            and (
                not isinstance(item["occurrence"], int)
                or isinstance(item["occurrence"], bool)
                or item["occurrence"] < 1
            )
        )
        for item in arguments
    ):
        raise ValueError("arguments must contain name, value and optional occurrence")
    order = expectation.get("order", [])
    if not isinstance(order, list) or any(
        not isinstance(pair, list)
        or len(pair) != 2
        or any(not isinstance(name, str) or not name for name in pair)
        for pair in order
    ):
        raise ValueError("order must be a list of two-name lists")
    sequence = names("sequence") if "sequence" in expectation else None
    strict = expectation.get("strict_sequence", True)
    if not isinstance(strict, bool) or (
        "strict_sequence" in expectation and sequence is None
    ):
        raise ValueError("strict_sequence requires sequence and must be boolean")
    maximum = expectation.get("max_steps")
    if maximum is not None and (
        not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0
    ):
        raise ValueError("max_steps must be a non-negative integer")
    if sequence is not None and not sequence:
        raise ValueError("sequence must contain at least one tool")

    if replay is None:
        return
    _calls(replay)
    for name in called:
        assert_tool_called(replay, name)
    for name in not_called:
        assert_tool_not_called(replay, name)
    for name, count in counts.items():
        assert_tool_call_count(replay, name, count)
    for item in arguments:
        assert_tool_arguments(
            replay, item["name"], item["value"], occurrence=item.get("occurrence")
        )
    for before, after in order:
        assert_tool_order(replay, before, after)
    if sequence is not None:
        assert_tool_sequence(replay, sequence, strict=strict)
    if maximum is not None:
        assert_max_steps(replay, maximum)


def validate_trajectory_expectation(expectation: Any) -> None:
    """Reject malformed declarative expectations before exporting tests."""
    _apply_trajectory(None, expectation)


def assert_trajectory(replay: ReplaySession, expectation: Any) -> None:
    """Apply a reviewed JSON trajectory expectation with no code evaluation."""
    _apply_trajectory(replay, expectation)
