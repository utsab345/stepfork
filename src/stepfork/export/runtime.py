"""Runtime helper executed by Stepfork-generated pytest regression tests.

This module is deliberately small, fixed, and reviewed. Generated tests only
assemble literals and call :func:`run_regression_case`; no generated code is
ever derived from trace payloads.
"""

from __future__ import annotations

from pathlib import Path

from stepfork.diff.compare import first_difference
from stepfork.export.entrypoint import EntrypointError, resolve_entrypoint
from stepfork.replay import (
    ReplayError,
    ReplayMismatchError,
    ReplayPolicyError,
    ReplaySession,
)
from stepfork.trace import (
    JsonValue,
    Trace,
    TraceSerializationError,
    TraceStorageError,
    canonical_json_bytes,
    to_json_value,
)

PREVIEW_LIMIT = 300


def run_regression_case(
    *,
    trace_path: Path,
    import_root: Path | None,
    entrypoint: str,
    expectation: JsonValue | None = None,
    has_expectation: bool = True,
    mode: str = "frozen",
) -> JsonValue:
    """Replay a trusted entrypoint and assert the expected behavior.

    Fails with an actionable ``AssertionError`` when the trace is missing, the
    entrypoint cannot load, replay diverges from the recorded dependency
    sequence, or the returned value differs from ``expectation``.
    """
    bundle = Path(trace_path)
    if not bundle.exists():
        raise AssertionError(f"stepfork: trace bundle not found: {bundle}")
    try:
        recorded = Trace.load(bundle)
    except TraceStorageError as exc:
        raise AssertionError(f"stepfork: trace bundle unreadable: {exc}") from exc

    try:
        entry = resolve_entrypoint(entrypoint, import_root=import_root)
    except EntrypointError as exc:
        raise AssertionError(f"stepfork: entrypoint failed: {exc}") from exc

    with ReplaySession.from_trace(recorded, mode=mode) as replay:
        try:
            actual = entry()
        except ReplayMismatchError as exc:
            raise AssertionError(f"stepfork replay divergence: {exc}") from exc
        except ReplayPolicyError as exc:
            raise AssertionError(f"stepfork replay policy violation: {exc}") from exc
        try:
            replay.verify_complete()
        except ReplayError as exc:
            raise AssertionError(f"stepfork replay divergence: {exc}") from exc

    try:
        actual_json = to_json_value(actual)
    except TraceSerializationError as exc:
        raise AssertionError(
            f"stepfork: entrypoint returned a non-serializable value: {exc}"
        ) from exc

    if has_expectation:
        difference = first_difference(expectation, actual_json)
        if difference is not None:
            path, expected_value, actual_value = difference
            raise AssertionError(
                f"behavior mismatch at '{path}': "
                f"expected {_preview(expected_value)}, "
                f"got {_preview(actual_value)}"
            )

    return actual_json


def _preview(value: JsonValue | None) -> str:
    if value is None:
        return "None"
    try:
        text = canonical_json_bytes(value).decode("utf-8", errors="replace")
    except TypeError:
        return "<unserializable>"
    if len(text) > PREVIEW_LIMIT:
        return f"{text[: PREVIEW_LIMIT - 1]}…"
    return text
