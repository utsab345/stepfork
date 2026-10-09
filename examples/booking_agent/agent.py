"""Deterministic booking agent used to demonstrate Stepfork end to end.

The example is intentionally tiny and fully offline. It has one LLM-like
dependency (a fake, deterministic provider) and one tool dependency
(``search_flights``). Both are instrumented with Stepfork boundaries so a
recorded run can be replayed without touching the network.

The example ships two implementations of the same agent:

- :func:`run_agent` is buggy: it books the *first* flight returned.
- :func:`run_agent_fixed` books the *cheapest* flight.

The dependency calls made by both implementations are identical, which is
what makes the same recording replayable against either one.
"""

from __future__ import annotations

from typing import Any

from stepfork import llm_request, trace_tool

DESTINATION = "Lisbon"

SYSTEM_PROMPT = "You are a careful travel booking assistant."

FLIGHTS: dict[str, list[dict[str, Any]]] = {
    "Lisbon": [
        {"id": "A", "airline": "Nimbus Air", "price": 450},
        {"id": "B", "airline": "Coastal Jets", "price": 320},
        {"id": "C", "airline": "Skyline", "price": 390},
    ],
}

#: Every destination that reached the real ``search_flights`` body. Frozen
#: replay must leave this list untouched, which proves the external dependency
#: was not executed.
TOOL_EXECUTIONS: list[str] = []


@trace_tool(name="flight_search")
def search_flights(destination: str) -> dict[str, Any]:
    """Return deterministic flight options for ``destination``.

    In a real agent this would call a flights API. Under frozen replay Stepfork
    returns the captured response and this body never runs.
    """
    TOOL_EXECUTIONS.append(destination)
    return {"destination": destination, "flights": list(FLIGHTS.get(destination, []))}


def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
    """A deterministic, offline stand-in for an LLM provider."""
    return {
        "model": "demo-model",
        "content": "Search flights, then choose the cheapest option.",
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 11,
            "total_tokens": 53,
        },
    }


def _messages(destination: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Book the cheapest flight to {destination}."},
    ]


def _run(destination: str, choose: Any) -> dict[str, Any]:
    messages = _messages(destination)
    plan = llm_request(
        provider="fake",
        model="demo-model",
        input={"messages": messages},
        call=lambda: fake_llm(messages),
    )
    search_result = search_flights(destination)
    selected = choose(search_result["flights"])
    return {
        "destination": destination,
        "selected_flight": selected,
        "plan": plan["content"],
    }


def _choose_first(flights: list[dict[str, Any]]) -> str:
    return str(flights[0]["id"])


def _choose_cheapest(flights: list[dict[str, Any]]) -> str:
    return str(min(flights, key=lambda flight: flight["price"])["id"])


def run_agent(destination: str = DESTINATION) -> dict[str, Any]:
    """Buggy implementation: selects the first flight instead of the cheapest."""
    return _run(destination, _choose_first)


def run_agent_fixed(destination: str = DESTINATION) -> dict[str, Any]:
    """Corrected implementation: selects the cheapest flight."""
    return _run(destination, _choose_cheapest)


EXPECTED_OUTPUT: dict[str, Any] = {
    "destination": DESTINATION,
    "selected_flight": "B",
    "plan": "Search flights, then choose the cheapest option.",
}
