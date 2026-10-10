"""Scenario B: changes that alter the instrumented dependency trajectory.

Two variants are provided:

* ``run_incident_agent_divergent``: reorders two tool calls.
* ``run_incident_agent_divergent_argument``: changes a tool argument.

Expected: strict frozen replay detects divergence with a
``ReplayMismatchError`` before the divergent tool body executes.
"""

from __future__ import annotations

from typing import Any

import agent


def run_incident_agent_divergent() -> dict[str, Any]:
    """Reorder calls: deployments before health."""
    services = [agent.INCIDENT["primary_service"], *agent.INCIDENT["related_services"]]
    evidence = {
        "deployments": {s: agent.get_recent_deployments(s) for s in services},
        "health": {s: agent.lookup_service_health(s) for s in services},
        "runbook": agent.fetch_incident_runbook(agent.INCIDENT["incident_type"]),
    }
    facts = agent._facts(evidence)
    raw = agent._llm_triage(evidence)
    return agent._finalize_decision(raw, evidence, facts)


def run_incident_agent_divergent_argument() -> dict[str, Any]:
    """Change a tool argument: widen the deployment window to 120 minutes."""
    services = [agent.INCIDENT["primary_service"], *agent.INCIDENT["related_services"]]
    health = {s: agent.lookup_service_health(s) for s in services}
    deployments = {s: agent.get_recent_deployments(s, window_minutes=120) for s in services}
    runbook = agent.fetch_incident_runbook(agent.INCIDENT["incident_type"])
    evidence = {"health": health, "deployments": deployments, "runbook": runbook}
    facts = agent._facts(evidence)
    raw = agent._llm_triage(evidence)
    return agent._finalize_decision(raw, evidence, facts)
