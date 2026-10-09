"""Deep comparison helpers for JSON trace payloads.

Comparisons use Stepfork's canonical JSON profile so ``1`` and ``1.0`` are
never treated as equal and dictionary key order never matters.
"""

from __future__ import annotations

from stepfork.diff.models import FieldChange
from stepfork.trace.canonical import canonical_json_bytes
from stepfork.trace.models import JsonValue


def values_equal(expected: JsonValue, actual: JsonValue) -> bool:
    """Return True when both values are canonically identical."""
    try:
        return canonical_json_bytes(expected) == canonical_json_bytes(actual)
    except TypeError:
        return False


def first_difference(
    expected: JsonValue,
    actual: JsonValue,
    *,
    path: str = "",
) -> tuple[str, JsonValue, JsonValue] | None:
    """Return the first differing leaf as ``(path, expected, actual)``."""
    if values_equal(expected, actual):
        return None

    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            child_path = f"{path}.{key}" if path else key
            if key not in expected:
                return child_path, None, actual[key]
            if key not in actual:
                return child_path, expected[key], None
            nested = first_difference(
                expected[key],
                actual[key],
                path=child_path,
            )
            if nested is not None:
                return nested
        return path, expected, actual

    if isinstance(expected, list) and isinstance(actual, list):
        shared = min(len(expected), len(actual))
        for index in range(shared):
            nested = first_difference(
                expected[index],
                actual[index],
                path=f"{path}[{index}]",
            )
            if nested is not None:
                return nested
        if len(expected) > len(actual):
            return f"{path}[{shared}]", expected[shared], None
        if len(actual) > len(expected):
            return f"{path}[{shared}]", None, actual[shared]
        return path, expected, actual

    return path or "$", expected, actual


def collect_field_changes(
    expected: JsonValue,
    actual: JsonValue,
    *,
    path: str,
    output: list[FieldChange],
) -> None:
    """Append every differing leaf between two payloads to ``output``."""
    if values_equal(expected, actual):
        return

    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            child_path = f"{path}.{key}" if path else key
            if key not in expected:
                output.append(
                    FieldChange(
                        path=child_path,
                        kind="added",
                        expected=None,
                        actual=actual[key],
                    )
                )
            elif key not in actual:
                output.append(
                    FieldChange(
                        path=child_path,
                        kind="removed",
                        expected=expected[key],
                        actual=None,
                    )
                )
            else:
                collect_field_changes(
                    expected[key],
                    actual[key],
                    path=child_path,
                    output=output,
                )
        return

    if isinstance(expected, list) and isinstance(actual, list):
        shared = min(len(expected), len(actual))
        for index in range(shared):
            collect_field_changes(
                expected[index],
                actual[index],
                path=f"{path}[{index}]",
                output=output,
            )
        for index in range(shared, len(expected)):
            output.append(
                FieldChange(
                    path=f"{path}[{index}]",
                    kind="removed",
                    expected=expected[index],
                    actual=None,
                )
            )
        for index in range(shared, len(actual)):
            output.append(
                FieldChange(
                    path=f"{path}[{index}]",
                    kind="added",
                    expected=None,
                    actual=actual[index],
                )
            )
        return

    output.append(
        FieldChange(
            path=path,
            kind="changed",
            expected=expected,
            actual=actual,
        )
    )
