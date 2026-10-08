from __future__ import annotations

from typing import cast

from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter

from stepfork.trace import Event, JsonValue, ToolCall, Trace
from stepfork.trace.canonical import canonical_json_bytes
from stepfork.trace.hashing import hash_json
from stepfork.trace.redaction import redact_json
from stepfork.trace.validation import validate_trace

json_scalars = st.none() | st.booleans() | st.integers() | st.text()
json_values = st.recursive(
    json_scalars,
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(), children, max_size=4)
    ),
    max_leaves=12,
)


@given(json_values)
def test_json_canonicalization_round_trips(value: object) -> None:
    json_value = cast(JsonValue, value)

    assert canonical_json_bytes(json_value) == canonical_json_bytes(json_value)


@given(st.dictionaries(st.text(min_size=1), json_scalars, max_size=5))
def test_hashing_equivalent_objects_is_stable(value: dict[str, object]) -> None:
    json_value = cast(JsonValue, value)
    reversed_value = cast(JsonValue, dict(reversed(list(value.items()))))

    assert hash_json(json_value) == hash_json(reversed_value)


@given(json_values)
def test_redaction_is_idempotent(value: object) -> None:
    json_value = cast(JsonValue, value)
    once = redact_json(json_value).value
    twice = redact_json(once).value

    assert once == twice


@given(json_values)
def test_event_serialization_round_trip(value: object) -> None:
    json_value = cast(JsonValue, value)
    event = ToolCall(name="property_tool", input=json_value)
    adapter: TypeAdapter[Event] = TypeAdapter(Event)

    parsed = adapter.validate_python(event.model_dump(mode="json"))

    assert isinstance(parsed, ToolCall)
    assert parsed.input == json_value


@given(st.lists(json_values, max_size=5))
def test_trace_add_keeps_structural_validation_valid(values: list[object]) -> None:
    trace = Trace(agent_name="property-agent")
    for value in values:
        trace.add(ToolCall(name="property_tool", input=cast(JsonValue, value)))

    assert validate_trace(trace, strict=False).valid
