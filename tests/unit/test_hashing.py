from __future__ import annotations

import re
from typing import cast

import pytest

from stepfork.trace import (
    ErrorEvent,
    Event,
    JsonValue,
    LLMRequest,
    LLMResponse,
    RunEnd,
    RunStart,
    RunStatus,
    StateChange,
    ToolCall,
    ToolResult,
)
from stepfork.trace.canonical import CanonicalJsonError
from stepfork.trace.hashing import hash_event_payloads, hash_json


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"),
        (True, "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"),
        (42, "73475cb40a568e8da8a045ced110137e159f890ac4da883b6b17dc651b3a8049"),
        (1.5, "9f29a130438b81170b92a42650f9a94291ecad60bd47af2a3886e75f7f728725"),
        ({}, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
        ([], "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"),
        (
            {"a": 1, "b": 2},
            "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
        ),
        (
            {"nested": {"z": [1, "काठमाडौँ", None], "a": False}},
            "5e994630d09623b09ab0043b91b383a698f9effbebd1ab0271db0877ba6b4ac7",
        ),
    ],
)
def test_hash_json_known_answers(value: JsonValue, expected: str) -> None:
    assert hash_json(value) == expected


def test_hash_json_is_key_order_independent() -> None:
    assert hash_json({"a": 1, "b": 2}) == hash_json({"b": 2, "a": 1})


def test_hash_json_rejects_unsupported_values() -> None:
    with pytest.raises(CanonicalJsonError):
        hash_json(cast(JsonValue, {"bad": object()}))


def test_hash_json_is_lowercase_sha256_hex() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", hash_json({"ok": True}))


@pytest.mark.parametrize(
    "event",
    [
        RunStart(input=None),
        LLMRequest(model="gpt-test", input={"messages": []}),
        LLMResponse(output={"text": "hello"}),
        ToolCall(name="search", input={"query": "Kathmandu flights"}),
        ToolResult(name="search", output={"ok": True}),
        StateChange(before={"a": 1}, after={"a": 2}),
        ErrorEvent(error_type="ToolError", message="boom", details={"code": 500}),
        RunEnd(run_status=RunStatus.COMPLETED, output={"done": True}),
    ],
)
def test_hash_event_payloads_populates_applicable_hashes(event: Event) -> None:
    hashed = hash_event_payloads(event)

    assert hashed.input_hash is not None or hashed.output_hash is not None


def test_state_change_maps_before_to_input_and_after_to_output() -> None:
    event = hash_event_payloads(StateChange(before={"a": 1}, after={"a": 2}))

    assert event.input_hash == hash_json({"a": 1})
    assert event.output_hash == hash_json({"a": 2})
