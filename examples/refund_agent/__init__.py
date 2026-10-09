"""Deterministic customer-support refund agent example for Stepfork.

Run the full failure-to-test demonstration with::

    uv run python examples/refund_agent/demo.py
"""

from .agent import (
    CLAIM,
    EXPECTED_OUTPUT,
    REFUND_POLICY,
    SYSTEM_PROMPT,
    TOOL_EXECUTIONS,
    check_refund_policy,
    fake_llm,
    run_agent,
    run_agent_fixed,
)

__all__ = [
    "CLAIM",
    "EXPECTED_OUTPUT",
    "REFUND_POLICY",
    "SYSTEM_PROMPT",
    "TOOL_EXECUTIONS",
    "check_refund_policy",
    "fake_llm",
    "run_agent",
    "run_agent_fixed",
]
