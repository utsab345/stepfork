from __future__ import annotations

from copy import deepcopy
from typing import cast

from hypothesis import given
from hypothesis import strategies as st

from stepfork.trace import JsonValue
from stepfork.trace.redaction import REDACTION_REPLACEMENT, redact_json

SYNTHETIC_BEARER = "Bearer synthetic_token_123456"
SYNTHETIC_OPENAI = "sk-synthetic1234567890"
SYNTHETIC_GHP = "ghp_synthetic1234567890"
SYNTHETIC_GHO = "gho_synthetic1234567890"
SYNTHETIC_PAT = "github_pat_synthetic1234567890"


def redacted(value: object) -> object:
    return redact_json(cast(JsonValue, value)).value


def test_sensitive_key_variants_are_redacted() -> None:
    payload = {
        "api_key": "synthetic-value",
        "API_KEY": "synthetic-value",
        "api-key": "synthetic-value",
        "accessToken": "synthetic-value",
        "clientSecret": "synthetic-value",
        "password": "synthetic-value",
        "authorization": SYNTHETIC_BEARER,
    }

    assert redacted(payload) == {key: REDACTION_REPLACEMENT for key in payload}


def test_non_sensitive_key_names_are_not_redacted() -> None:
    payload = {
        "keyboard": "mechanical",
        "monkey": "banana",
        "primary_key": "user_id",
    }

    assert redacted(payload) == payload


def test_nested_dictionaries_and_lists_are_redacted() -> None:
    payload = {
        "tool": "search",
        "args": [
            {"query": "Kathmandu flights"},
            {"authorization": SYNTHETIC_BEARER},
        ],
    }

    assert redacted(payload) == {
        "tool": "search",
        "args": [
            {"query": "Kathmandu flights"},
            {"authorization": REDACTION_REPLACEMENT},
        ],
    }


def test_string_credential_patterns_are_redacted_in_place() -> None:
    payload = {
        "message": (
            f"use {SYNTHETIC_OPENAI} and {SYNTHETIC_GHP} and "
            f"{SYNTHETIC_GHO} and {SYNTHETIC_PAT}"
        )
    }

    result = redact_json(payload)
    value = cast(dict[str, str], result.value)
    text = value["message"]

    assert SYNTHETIC_OPENAI not in text
    assert SYNTHETIC_GHP not in text
    assert SYNTHETIC_GHO not in text
    assert SYNTHETIC_PAT not in text
    assert text.count(REDACTION_REPLACEMENT) == 4


def test_json_pointer_paths_are_escaped() -> None:
    result = redact_json({"a/b": {"c~d": {"api_key": "synthetic"}}})

    assert result.findings[0].path == "/a~1b/c~0d/api_key"


def test_redaction_metadata_does_not_contain_raw_secret() -> None:
    result = redact_json({"api_key": "synthetic-secret-value"})
    metadata = [
        finding.model_dump() if hasattr(finding, "model_dump") else vars(finding)
        for finding in result.findings
    ]

    assert "synthetic-secret-value" not in repr(metadata)


def test_unicode_and_empty_values_are_preserved_when_not_sensitive() -> None:
    payload = {"city": "काठमाडौँ", "empty": ""}

    assert redacted(payload) == payload


def test_already_redacted_values_are_not_duplicated() -> None:
    result = redact_json({"api_key": REDACTION_REPLACEMENT})

    assert result.value == {"api_key": REDACTION_REPLACEMENT}
    assert result.findings == []


def test_original_input_object_is_not_mutated() -> None:
    payload = {"nested": {"api_key": "synthetic"}}
    original = deepcopy(payload)

    redact_json(payload)

    assert payload == original


@given(st.dictionaries(st.text(), st.text(), max_size=5))
def test_redaction_is_idempotent_for_string_maps(payload: dict[str, str]) -> None:
    once = redact_json(payload).value
    twice = redact_json(once).value

    assert once == twice
