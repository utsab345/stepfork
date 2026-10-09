from __future__ import annotations

import math

import pytest

from stepfork.trace.jsonable import (
    MAX_DEPTH,
    TraceSerializationError,
    to_json_value,
)


def test_to_json_value_rejects_non_finite_float() -> None:
    for value in (math.inf, -math.inf, math.nan):
        with pytest.raises(TraceSerializationError, match="non-finite"):
            to_json_value(value)


def test_to_json_value_rejects_non_string_dict_keys() -> None:
    with pytest.raises(TraceSerializationError, match="must be a string"):
        to_json_value({1: "x"})


def test_to_json_value_rejects_serializer_returning_original() -> None:
    with pytest.raises(TraceSerializationError, match="unchanged"):
        to_json_value(object(), serializer=lambda value: value)


def test_to_json_value_rejects_excessive_nesting() -> None:
    value: dict[str, object] = {"leaf": True}
    for _ in range(MAX_DEPTH + 2):
        value = {"child": value}

    with pytest.raises(TraceSerializationError, match="nesting depth"):
        to_json_value(value)


def test_to_json_value_serializer_converts_values() -> None:
    class Point:
        def __init__(self, x: int) -> None:
            self.x = x

    converted = to_json_value(
        {"point": Point(7)},
        serializer=lambda value: {"x": value.x} if isinstance(value, Point) else value,
    )

    assert converted == {"point": {"x": 7}}
