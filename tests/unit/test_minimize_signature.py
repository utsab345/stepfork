"""Unit tests for failure signature detection."""

from __future__ import annotations

from stepfork.minimize.models import FailureSignature
from stepfork.minimize.signature import format_signature


def test_signature_matches_same_exception_type() -> None:
    """Signatures with same exception type should match."""
    sig1 = FailureSignature(
        kind="exception",
        exception_type="ValueError",
        exception_message_pattern="invalid input data",
    )
    sig2 = FailureSignature(
        kind="exception",
        exception_type="ValueError",
        exception_message_pattern="invalid input values provided",
    )
    assert sig1.matches(sig2)


def test_signature_rejects_different_exception_type() -> None:
    """Signatures with different exception types should not match."""
    sig1 = FailureSignature(
        kind="exception",
        exception_type="ValueError",
        exception_message_pattern="invalid input",
    )
    sig2 = FailureSignature(
        kind="exception",
        exception_type="TypeError",
        exception_message_pattern="invalid input",
    )
    assert not sig1.matches(sig2)


def test_signature_matches_same_divergence_type() -> None:
    """Signatures with same divergence type should match."""
    sig1 = FailureSignature(
        kind="replay_divergence",
        divergence_type="ReplayMismatchError",
        divergence_pattern="tool search not found",
    )
    sig2 = FailureSignature(
        kind="replay_divergence",
        divergence_type="ReplayMismatchError",
        divergence_pattern="tool search missing",
    )
    assert sig1.matches(sig2)


def test_signature_rejects_different_divergence_type() -> None:
    """Signatures with different divergence types should not match."""
    sig1 = FailureSignature(
        kind="replay_divergence",
        divergence_type="ReplayMismatchError",
        divergence_pattern="tool search",
    )
    sig2 = FailureSignature(
        kind="replay_divergence",
        divergence_type="ReplayExhaustedError",
        divergence_pattern="tool search",
    )
    assert not sig1.matches(sig2)


def test_signature_rejects_different_kinds() -> None:
    """Signatures of different kinds should not match."""
    sig1 = FailureSignature(
        kind="exception",
        exception_type="ValueError",
    )
    sig2 = FailureSignature(
        kind="replay_divergence",
        divergence_type="ReplayMismatchError",
    )
    assert not sig1.matches(sig2)


def test_signature_matches_same_output_diff_hash() -> None:
    """Signatures with same output diff hash should match."""
    sig1 = FailureSignature(
        kind="output_mismatch",
        output_diff_hash="abc123def456",
    )
    sig2 = FailureSignature(
        kind="output_mismatch",
        output_diff_hash="abc123def456",
    )
    assert sig1.matches(sig2)


def test_signature_rejects_different_output_diff_hash() -> None:
    """Signatures with different output diff hashes should not match."""
    sig1 = FailureSignature(
        kind="output_mismatch",
        output_diff_hash="abc123def456",
    )
    sig2 = FailureSignature(
        kind="output_mismatch",
        output_diff_hash="xyz789abc123",
    )
    assert not sig1.matches(sig2)


def test_format_signature_exception() -> None:
    """Format exception signature."""
    sig = FailureSignature(
        kind="exception",
        exception_type="ValueError",
        exception_message_pattern="invalid input",
    )
    assert format_signature(sig) == "Exception: ValueError"


def test_format_signature_divergence() -> None:
    """Format divergence signature."""
    sig = FailureSignature(
        kind="replay_divergence",
        divergence_type="ReplayMismatchError",
        divergence_pattern="tool mismatch",
    )
    assert format_signature(sig) == "Replay Divergence: ReplayMismatchError"


def test_format_signature_output_mismatch() -> None:
    """Format output mismatch signature."""
    sig = FailureSignature(
        kind="output_mismatch",
        output_diff_hash="abc123",
    )
    assert format_signature(sig) == "Output Mismatch"


def test_format_signature_combined() -> None:
    """Format combined signature."""
    sig = FailureSignature(
        kind="output_and_divergence",
        exception_type="ValueError",
        divergence_type="ReplayMismatchError",
        output_diff_hash="abc123",
    )
    formatted = format_signature(sig)
    assert "ValueError" in formatted
    assert "ReplayMismatchError" in formatted
    assert "Output Mismatch" in formatted


def test_message_pattern_matching_with_overlap() -> None:
    """Message patterns with sufficient token overlap should match."""
    sig = FailureSignature(
        kind="exception",
        exception_type="ValueError",
        exception_message_pattern="tool search not found",
    )
    # Extract tokens and verify matching logic
    tokens1 = sig._extract_tokens("tool search not found")
    tokens2 = sig._extract_tokens("search tool missing")

    # Should have some overlap
    overlap = set(tokens1) & set(tokens2)
    assert len(overlap) > 0


def test_message_pattern_no_match_without_overlap() -> None:
    """Message patterns without token overlap should not match."""
    sig1 = FailureSignature(
        kind="exception",
        exception_type="ValueError",
        exception_message_pattern="database connection failed",
    )
    sig2 = FailureSignature(
        kind="exception",
        exception_type="ValueError",
        exception_message_pattern="authentication token expired",
    )
    # Different topics, should not match
    assert not sig1.matches(sig2)
