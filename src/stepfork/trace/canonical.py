"""Deterministic JSON serialization for Stepfork hashes.

Stepfork v0.1 uses a documented Python JSON profile for canonicalization:
sorted object keys, compact separators, UTF-8 bytes, non-ASCII characters
preserved, and non-finite floats rejected. This is not full RFC 8785.
"""

from __future__ import annotations

import json
import math
from typing import Any

from stepfork.trace.models import JsonValue

CANONICAL_JSON_PROFILE = "stepfork-json-v0.1"


class CanonicalJsonError(TypeError):
    """Raised when a value cannot be canonically serialized as JSON."""


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Return deterministic UTF-8 JSON bytes for a JSON-compatible value."""
    _validate_json_value(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalJsonError("value is not canonical JSON serializable") from exc


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJsonError("non-finite floats are not supported")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError("JSON object keys must be strings")
            _validate_json_value(item)
        return
    raise CanonicalJsonError(f"unsupported JSON value type: {type(value).__name__}")
