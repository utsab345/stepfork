"""Minimal order-shipment notification agent for the Stepfork quickstart.

The quickstart agent is deliberately tiny. It has a single external dependency
(an order-status lookup) and makes one decision from the result.

- :func:`run_agent` is buggy: it notifies the customer when an order is
  *delivered*, so a just-shipped order is silently skipped.
- :func:`run_agent_fixed` is the corrected implementation: it notifies when
  the order is *shipped*.

Both implementations make the exact same dependency call, which is what makes
the same recording replayable against either one.
"""

from __future__ import annotations

from typing import Any

from stepfork import trace_tool

ORDER: dict[str, Any] = {
    "order_id": "ORD-1001",
    "status": "shipped",
    "carrier": "FedEx",
}

#: Every order id that reached the real ``order_status`` body. Frozen replay
#: must leave this list untouched, which proves the external dependency was
#: not executed.
TOOL_EXECUTIONS: list[str] = []

NOTIFY_STATUS = "shipped"


@trace_tool(name="order_status")
def order_status(order_id: str) -> dict[str, Any]:
    """Return the current status of an order.

    In a real agent this would call a shipping service. Under frozen replay
    Stepfork returns the captured response and this body never runs.
    """
    TOOL_EXECUTIONS.append(order_id)
    return dict(ORDER)


def _run(order_id: str) -> dict[str, Any]:
    status = order_status(order_id)
    should_notify = status["status"] == NOTIFY_STATUS
    return {
        "order_id": order_id,
        "should_notify": should_notify,
        "carrier": status["carrier"],
    }


def run_agent(order_id: str = ORDER["order_id"]) -> dict[str, Any]:
    """Buggy implementation: notifies only once an order is delivered."""
    status = order_status(order_id)
    should_notify = status["status"] == "delivered"
    return {
        "order_id": order_id,
        "should_notify": should_notify,
        "carrier": status["carrier"],
    }


def run_agent_fixed(order_id: str = ORDER["order_id"]) -> dict[str, Any]:
    """Corrected implementation: notifies when the order ships."""
    return _run(order_id)


EXPECTED_OUTPUT: dict[str, Any] = {
    "order_id": ORDER["order_id"],
    "should_notify": True,
    "carrier": ORDER["carrier"],
}
