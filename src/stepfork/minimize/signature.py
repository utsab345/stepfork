"""Failure signature detection for replay outcomes.

A failure signature captures what makes a trace fail during replay, enabling
verification that a minimized trace preserves the same failure as the original.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stepfork.export.entrypoint import resolve_entrypoint
from stepfork.minimize.models import FailureSignature
from stepfork.replay import (
    RecordedDependencyError,
    ReplayError,
    ReplayExhaustedError,
    ReplayMismatchError,
    ReplaySession,
)
from stepfork.trace.canonical import canonical_json_bytes
from stepfork.trace.models import JsonValue, Trace


class FailureDetectionError(Exception):
    """Raised when failure signature cannot be determined."""


def detect_failure_signature(
    trace: Trace,
    entrypoint: str,
    *,
    expected_output: JsonValue | None = None,
    mode: str = "frozen",
    timeout_seconds: float = 30.0,
) -> FailureSignature:
    """Detect the failure signature by replaying the trace.

    Args:
        trace: The trace to replay
        entrypoint: MODULE:FUNCTION entrypoint specification
        expected_output: Expected output for comparison (optional)
        mode: Replay mode (frozen, live, hybrid)
        timeout_seconds: Maximum time to wait for replay

    Returns:
        FailureSignature describing how the trace fails

    Raises:
        FailureDetectionError: If the trace does not fail or signature is ambiguous
    """
    # Resolve the entrypoint function
    try:
        entrypoint_fn = resolve_entrypoint(entrypoint, import_root=Path.cwd())
    except Exception as exc:
        raise FailureDetectionError(
            f"cannot resolve entrypoint {entrypoint!r}: {exc}"
        ) from exc

    # Attempt replay and capture the failure
    exception: BaseException | None = None
    actual_output: Any = None
    divergence_error: ReplayError | None = None

    try:
        with ReplaySession.from_trace(trace, mode=mode) as replay:
            actual_output = entrypoint_fn()
            divergence_error = replay.divergence
    except RecordedDependencyError as exc:
        exception = exc
    except ReplayMismatchError as exc:
        exception = exc
    except ReplayExhaustedError as exc:
        exception = exc
    except ReplayError as exc:
        exception = exc
    except Exception as exc:
        # Application exception during replay
        exception = exc

    # Determine the failure signature based on what happened
    if exception is not None:
        return _signature_from_exception(exception, divergence_error)

    if divergence_error is not None:
        return _signature_from_divergence(
            divergence_error, actual_output, expected_output
        )

    if expected_output is not None:
        return _signature_from_output_mismatch(actual_output, expected_output)

    # No failure detected
    raise FailureDetectionError(
        "trace replay completed successfully; no failure to minimize"
    )


def _signature_from_exception(
    exception: BaseException,
    divergence: ReplayError | None,
) -> FailureSignature:
    """Create signature from an exception during replay."""
    exception_type = type(exception).__name__
    exception_message = str(exception)

    # Check if there was also a divergence
    if divergence is not None:
        divergence_type = type(divergence).__name__
        divergence_pattern = str(divergence)
        return FailureSignature(
            kind="output_and_divergence",
            exception_type=exception_type,
            exception_message_pattern=exception_message[:200],
            divergence_type=divergence_type,
            divergence_pattern=divergence_pattern[:200],
        )

    # Pure exception-based failure
    return FailureSignature(
        kind="exception",
        exception_type=exception_type,
        exception_message_pattern=exception_message[:200],
    )


def _signature_from_divergence(
    divergence: ReplayError,
    actual_output: JsonValue,
    expected_output: JsonValue | None,
) -> FailureSignature:
    """Create signature from replay divergence."""
    divergence_type = type(divergence).__name__
    divergence_pattern = str(divergence)

    # If we also have output mismatch, include both
    if expected_output is not None and not _outputs_match(
        actual_output, expected_output
    ):
        diff_hash = _compute_output_diff_hash(actual_output, expected_output)
        return FailureSignature(
            kind="output_and_divergence",
            divergence_type=divergence_type,
            divergence_pattern=divergence_pattern[:200],
            expected_output=expected_output,
            actual_output=actual_output,
            output_diff_hash=diff_hash,
        )

    return FailureSignature(
        kind="replay_divergence",
        divergence_type=divergence_type,
        divergence_pattern=divergence_pattern[:200],
    )


def _signature_from_output_mismatch(
    actual_output: JsonValue,
    expected_output: JsonValue,
) -> FailureSignature:
    """Create signature from output mismatch."""
    if _outputs_match(actual_output, expected_output):
        raise FailureDetectionError(
            "actual output matches expected output; no failure to minimize"
        )

    diff_hash = _compute_output_diff_hash(actual_output, expected_output)
    return FailureSignature(
        kind="output_mismatch",
        expected_output=expected_output,
        actual_output=actual_output,
        output_diff_hash=diff_hash,
    )


def _outputs_match(actual: JsonValue, expected: JsonValue) -> bool:
    """Check if two outputs are equivalent."""
    try:
        return canonical_json_bytes(actual) == canonical_json_bytes(expected)
    except (TypeError, ValueError):
        return actual == expected


def _compute_output_diff_hash(actual: JsonValue, expected: JsonValue) -> str:
    """Compute a stable hash of the difference between two outputs."""
    # Serialize both outputs canonically
    try:
        actual_bytes = canonical_json_bytes(actual)
        expected_bytes = canonical_json_bytes(expected)
    except (TypeError, ValueError):
        actual_bytes = json.dumps(actual, sort_keys=True).encode("utf-8")
        expected_bytes = json.dumps(expected, sort_keys=True).encode("utf-8")

    # Hash the concatenation
    hasher = hashlib.sha256()
    hasher.update(b"expected:")
    hasher.update(expected_bytes)
    hasher.update(b"|actual:")
    hasher.update(actual_bytes)
    return hasher.hexdigest()[:16]


def format_signature(signature: FailureSignature) -> str:
    """Format a failure signature for human-readable display."""
    if signature.kind == "exception":
        return f"Exception: {signature.exception_type}"
    elif signature.kind == "replay_divergence":
        return f"Replay Divergence: {signature.divergence_type}"
    elif signature.kind == "output_mismatch":
        return "Output Mismatch"
    elif signature.kind == "output_and_divergence":
        parts = []
        if signature.exception_type:
            parts.append(f"Exception: {signature.exception_type}")
        if signature.divergence_type:
            parts.append(f"Divergence: {signature.divergence_type}")
        if signature.output_diff_hash:
            parts.append("Output Mismatch")
        return " + ".join(parts)
    return "Unknown Failure"
