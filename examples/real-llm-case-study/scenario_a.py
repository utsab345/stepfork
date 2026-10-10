"""Scenario A: a harmless internal refactor.

The refactor changes *how* evidence is gathered (a shared helper instead of two
inline comprehensions) but keeps every instrumented dependency call, its
arguments, its order, the LLM request payload, and the final result identical.

Expected: the frozen regression test still passes.
"""

from __future__ import annotations

from typing import Any, Callable

import agent


def _gather(
    services: list[str], tool: Callable[[str], dict[str, Any]]
) -> dict[str, Any]:
    return {service: tool(service) for service in services}


def run_incident_agent_refactored() -> dict[str, Any]:
    services = [agent.INCIDENT["primary_service"], *agent.INCIDENT["related_services"]]
    evidence = {
        "health": _gather(services, agent.lookup_service_health),
        "deployments": _gather(services, agent.get_recent_deployments),
        "runbook": agent.fetch_incident_runbook(agent.INCIDENT["incident_type"]),
    }
    facts = agent._facts(evidence)
    raw = agent._llm_triage(evidence)
    return agent._finalize_decision(raw, evidence, facts)
