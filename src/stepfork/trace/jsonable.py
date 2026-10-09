"""Conversion of runtime values into JSON-compatible trace payloads.

Stepfork never falls back to ``repr()`` when recording payloads. Values must
already be JSON-compatible (``None``, ``str``, ``bool``, ``int``, finite
``float``, ``list``/``tuple``, ``dict`` with ``str`` keys) or the caller must
provide an explicit serializer hook.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, TypeAlias

from stepfork.trace.models import JsonValue

Serializer: TypeAlias = Callable[[Any], Any]

MAX_DEPTH = 100


class TraceSerializationError(TypeError):
    """Raised when a runtime value cannot be represented as JSON."""


def to_json_value(
    value: Any,
    *,
    serializer: Serializer | None = None,
    path: str = "$",
    depth: int = 0,
) -> JsonValue:
    """Convert ``value`` into a JSON-compatible value or raise a clear error.

    Non-JSON values are first passed through the optional ``serializer`` hook.
    The hook must return a JSON-compatible value; returning the input object
    unchanged (or another unsupported value) is an error.
    """
    if depth > MAX_DEPTH:
        raise TraceSerializationError(
            f"value at {path} exceeds the maximum nesting depth of {MAX_DEPTH}; "
            "this usually means a cyclic structure"
        )

    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TraceSerializationError(
                f"non-finite float at {path} cannot be recorded as JSON"
            )
        return value
    if isinstance(value, list | tuple):
        return [
            to_json_value(
                item,
                serializer=serializer,
                path=f"{path}[{index}]",
                depth=depth + 1,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        converted: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TraceSerializationError(
                    f"object key at {path} must be a string, got "
                    f"{type(key).__name__}: {key!r}"
                )
            converted[key] = to_json_value(
                item,
                serializer=serializer,
                path=f"{path}.{key}",
                depth=depth + 1,
            )
        return converted

    if serializer is not None:
        converted_value = serializer(value)
        if converted_value is value:
            raise TraceSerializationError(
                f"serializer returned the original {type(value).__name__} "
                f"unchanged at {path}"
            )
        return to_json_value(
            converted_value,
            serializer=serializer,
            path=path,
            depth=depth + 1,
        )

    raise TraceSerializationError(
        f"cannot serialize {type(value).__name__} at {path}; pass "
        "JSON-compatible values or provide a serializer hook via "
        "record(..., serializer=...) or trace_tool(..., serializer=...)"
    )
