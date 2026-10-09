"""Deterministic booking agent example for Stepfork.

Run the full failure-to-test demonstration with::

    uv run python examples/booking_agent/demo.py
"""

from .agent import (
    DESTINATION,
    EXPECTED_OUTPUT,
    FLIGHTS,
    SYSTEM_PROMPT,
    TOOL_EXECUTIONS,
    fake_llm,
    run_agent,
    run_agent_fixed,
    search_flights,
)

__all__ = [
    "DESTINATION",
    "EXPECTED_OUTPUT",
    "FLIGHTS",
    "SYSTEM_PROMPT",
    "TOOL_EXECUTIONS",
    "fake_llm",
    "run_agent",
    "run_agent_fixed",
    "search_flights",
]
