"""Replay policy values for recorded trace dependencies."""

from enum import StrEnum


class ReplayPolicy(StrEnum):
    """Describe how a dependency should behave during replay.

    `frozen` returns captured output, `live` re-executes the dependency,
    `manual` requires explicit user approval, `forbidden` prevents automatic
    execution, and `derived` recomputes locally from deterministic inputs.
    """

    FROZEN = "frozen"
    LIVE = "live"
    MANUAL = "manual"
    FORBIDDEN = "forbidden"
    DERIVED = "derived"
