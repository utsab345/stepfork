"""Deterministic customer-support refund agent used to demonstrate Stepfork.

The example is intentionally tiny and fully offline. It has one LLM-like
dependency (a fake, deterministic provider) and one tool dependency
(``check_refund_policy``). Both are instrumented with Stepfork boundaries so a
recorded run can be replayed without touching the network.

The example ships two implementations of the same agent:

- :func:`run_agent` is buggy: it denies the refund even though the claim is
  eligible under the refund policy.
- :func:`run_agent_fixed` approves the refund when the policy check passes.

The dependency calls made by both implementations are identical, which is
what makes the same recording replayable against either one.
"""

from __future__ import annotations

from typing import Any

from stepfork import llm_request, trace_tool

CLAIM: dict[str, Any] = {
    "order_id": "ORD-2024-7717",
    "customer": "Arya Tamang",
    "product": "ACME Wireless Mouse",
    "amount": 59.99,
    "days_since_purchase": 12,
}

SYSTEM_PROMPT = "You are a careful customer-support refund specialist."

REFUND_POLICY: dict[str, Any] = {
    "window_days": 30,
    "max_amount": 100.0,
}

#: Every order id that reached the real ``check_refund_policy`` body. Frozen
#: replay must leave this list untouched, which proves the external dependency
#: was not executed.
TOOL_EXECUTIONS: list[str] = []


@trace_tool(name="refund_policy_check")
def check_refund_policy(
    order_id: str,
    days_since_purchase: int,
    amount: float,
) -> dict[str, Any]:
    """Return the refund decision the policy requires for a claim.

    In a real agent this would call a refund-policy service. Under frozen
    replay Stepfork returns the captured response and this body never runs.
    """
    TOOL_EXECUTIONS.append(order_id)
    approved = (
        days_since_purchase <= REFUND_POLICY["window_days"]
        and amount <= REFUND_POLICY["max_amount"]
    )
    if approved:
        reason = (
            f"Approved: within {REFUND_POLICY['window_days']}-day window and "
            f"under the {REFUND_POLICY['max_amount']} refund cap."
        )
    else:
        reason = "Denied: outside return window or over the refund cap."
    return {
        "approved": approved,
        "window_days": REFUND_POLICY["window_days"],
        "max_amount": REFUND_POLICY["max_amount"],
        "reason": reason,
    }


def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
    """A deterministic, offline stand-in for an LLM provider."""
    return {
        "model": "demo-model",
        "content": "Decide refund eligibility from the policy, then approve or deny.",
        "usage": {
            "prompt_tokens": 47,
            "completion_tokens": 13,
            "total_tokens": 60,
        },
    }


def _messages(claim: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Assess whether order {claim['order_id']} "
                f"({claim['product']}, {claim['amount']} USD, "
                f"{claim['days_since_purchase']} days ago) is refundable."
            ),
        },
    ]


def _run(claim: dict[str, Any], decide: Any) -> dict[str, Any]:
    messages = _messages(claim)
    plan = llm_request(
        provider="fake",
        model="demo-model",
        input={"messages": messages},
        call=lambda: fake_llm(messages),
    )
    policy = check_refund_policy(
        claim["order_id"],
        claim["days_since_purchase"],
        claim["amount"],
    )
    outcome = decide(claim, policy)
    return {**outcome, "plan": plan["content"]}


def _deny(claim: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": "deny",
        "order_id": claim["order_id"],
        "refund_amount": 0.0,
        "reason": "Denied by policy.",
    }


def _decide(claim: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if policy["approved"]:
        return {
            "decision": "approve",
            "order_id": claim["order_id"],
            "refund_amount": claim["amount"],
            "reason": "Refund approved.",
        }
    return {
        "decision": "deny",
        "order_id": claim["order_id"],
        "refund_amount": 0.0,
        "reason": policy["reason"],
    }


def run_agent(claim: dict[str, Any] = CLAIM) -> dict[str, Any]:
    """Buggy implementation: denies every refund regardless of policy."""
    return _run(claim, _deny)


def run_agent_fixed(claim: dict[str, Any] = CLAIM) -> dict[str, Any]:
    """Corrected implementation: approves eligible refunds."""
    return _run(claim, _decide)


EXPECTED_OUTPUT: dict[str, Any] = {
    "decision": "approve",
    "order_id": CLAIM["order_id"],
    "refund_amount": CLAIM["amount"],
    "reason": "Refund approved.",
    "plan": "Decide refund eligibility from the policy, then approve or deny.",
}
