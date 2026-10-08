from __future__ import annotations

import math
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from stepfork.trace import JsonValue
from stepfork.trace.canonical import CanonicalJsonError, canonical_json_bytes

json_scalars = st.none() | st.booleans() | st.integers() | st.text()
json_values = st.recursive(
    json_scalars,
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(), children, max_size=4)
    ),
    max_leaves=12,
)


def test_canonical_json_sorts_object_keys() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_canonical_json_preserves_array_order() -> None:
    assert canonical_json_bytes([2, 1]) != canonical_json_bytes([1, 2])


def test_canonical_json_preserves_unicode_as_utf8() -> None:
    assert canonical_json_bytes({"city": "काठमाडौँ"}) == ('{"city":"काठमाडौँ"}'.encode())


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_floats(value: float) -> None:
    with pytest.raises(CanonicalJsonError):
        canonical_json_bytes(value)


@pytest.mark.parametrize("value", [object(), {"bad": object()}, {1: "bad"}])
def test_canonical_json_rejects_unsupported_python_objects(value: object) -> None:
    with pytest.raises(CanonicalJsonError):
        canonical_json_bytes(cast(JsonValue, value))


@given(json_values)
def test_canonical_json_is_deterministic(value: object) -> None:
    json_value = cast(JsonValue, value)

    assert canonical_json_bytes(json_value) == canonical_json_bytes(json_value)


@given(st.dictionaries(st.text(min_size=1), json_scalars, min_size=1, max_size=6))
def test_canonical_json_is_independent_of_dict_insertion_order(
    value: dict[str, object],
) -> None:
    reversed_value = dict(reversed(list(value.items())))

    assert canonical_json_bytes(value) == canonical_json_bytes(reversed_value)
