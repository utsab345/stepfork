"""Data models for failure minimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from stepfork.trace.models import JsonValue


@dataclass(frozen=True)
class FailureSignature:
    """Captures what makes a trace fail during replay.

    Used to verify that a minimized trace preserves the same failure as the
    original trace. Multiple signature components can be present.
    """

    kind: Literal[
        "exception",
        "output_mismatch",
        "replay_divergence",
        "output_and_divergence",
    ]

    # Exception-based failure
    exception_type: str | None = None
    exception_message_pattern: str | None = None

    # Output mismatch failure
    expected_output: JsonValue | None = None
    actual_output: JsonValue | None = None
    output_diff_hash: str | None = None

    # Replay divergence failure
    divergence_type: str | None = None
    divergence_pattern: str | None = None

    def matches(self, other: FailureSignature) -> bool:
        """Check if this signature matches another failure signature.

        Allows minor variations in messages but requires matching core failure types.
        """
        if self.kind != other.kind:
            return False

        # Check exception-based signatures
        if self.exception_type is not None:
            if self.exception_type != other.exception_type:
                return False
            # Message pattern matching - check if key parts are present
            if self.exception_message_pattern and other.exception_message_pattern:
                return self._message_pattern_matches(
                    self.exception_message_pattern,
                    other.exception_message_pattern,
                )

        # Check replay divergence signatures
        if self.divergence_type is not None:
            if self.divergence_type != other.divergence_type:
                return False
            if self.divergence_pattern and other.divergence_pattern:
                return self._message_pattern_matches(
                    self.divergence_pattern,
                    other.divergence_pattern,
                )

        # Check output mismatch signatures
        if self.output_diff_hash is not None:
            # Exact hash match for output differences
            return self.output_diff_hash == other.output_diff_hash

        return True

    def _message_pattern_matches(self, pattern1: str, pattern2: str) -> bool:
        """Check if two message patterns describe the same failure.

        Extracts key identifiers and checks for overlap rather than exact match.
        """
        # Extract meaningful tokens (words/identifiers) from both patterns
        tokens1 = set(self._extract_tokens(pattern1))
        tokens2 = set(self._extract_tokens(pattern2))

        # Require significant overlap in key tokens
        if not tokens1 or not tokens2:
            return pattern1 == pattern2

        overlap = tokens1 & tokens2
        min_size = min(len(tokens1), len(tokens2))

        # At least 60% of tokens should overlap for a match
        return len(overlap) >= max(1, int(min_size * 0.6))

    def _extract_tokens(self, text: str) -> list[str]:
        """Extract meaningful tokens from an error message."""
        import re

        # Extract words, identifiers, and quoted strings
        tokens = re.findall(r"\b\w+\b", text.lower())
        # Filter out common words that don't help identify the failure
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "was",
            "were",
            "be",
            "been",
            "at",
            "by",
            "for",
            "from",
            "in",
            "of",
            "on",
            "to",
            "with",
        }
        return [token for token in tokens if token not in stopwords and len(token) > 2]


@dataclass(frozen=True)
class MinimizationResult:
    """Result of a minimization attempt."""

    success: bool
    original_event_count: int
    minimized_event_count: int | None
    replay_attempts: int
    preserved_failure: bool
    is_minimal: bool
    failure_signature: FailureSignature | None = None
    error_message: str | None = None
    nondeterministic: bool = False


@dataclass(frozen=True)
class MinimizationReport:
    """Human-readable report of minimization results."""

    original_trace_path: str
    minimized_trace_path: str | None
    original_event_count: int
    minimized_event_count: int | None
    reduction_percentage: float | None
    replay_attempts: int
    failure_signature: str
    is_minimal: bool
    nondeterministic: bool
    warnings: list[str]
