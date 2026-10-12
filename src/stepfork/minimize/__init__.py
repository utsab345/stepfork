"""Failure minimization.

Automatic delta debugging to find minimal reproducible traces.
"""

from stepfork.minimize.engine import (
    MinimizationEngine,
    MinimizationError,
    generate_report,
)
from stepfork.minimize.models import (
    FailureSignature,
    MinimizationReport,
    MinimizationResult,
)
from stepfork.minimize.signature import detect_failure_signature, format_signature

__all__ = [
    "FailureSignature",
    "MinimizationEngine",
    "MinimizationError",
    "MinimizationReport",
    "MinimizationResult",
    "detect_failure_signature",
    "format_signature",
    "generate_report",
]
