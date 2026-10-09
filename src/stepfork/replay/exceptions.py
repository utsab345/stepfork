"""Structured exceptions raised while replaying a recorded trace."""

from __future__ import annotations


class ReplayError(Exception):
    """Base class for every replay failure."""


class ReplayMismatchError(ReplayError):
    """The live execution diverged from the recorded dependency sequence."""


class ReplayExhaustedError(ReplayMismatchError):
    """A dependency call was made after every recorded call was consumed."""


class ReplayPolicyError(ReplayError):
    """A replay policy forbids handling the dependency call automatically."""


class RecordedDependencyError(ReplayError):
    """Replay reproduced a dependency failure captured in the trace.

    The original exception type cannot be reconstructed safely, so replay
    raises this dedicated exception carrying the recorded error type and
    sanitized message.
    """

    def __init__(self, *, kind: str, name: str, error_type: str, message: str):
        self.kind = kind
        self.name = name
        self.error_type = error_type
        self.message = message
        super().__init__(
            f"recorded {kind} failure for {name!r}: {error_type}: {message}"
        )
