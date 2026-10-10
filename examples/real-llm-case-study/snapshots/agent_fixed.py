"""IT incident-triage agent for the Stepfork real-LLM case study.

The agent:

1. reads a short incident report (a fixed, synthetic scenario),
2. consults internal operational data through three instrumented tools backed
   by local JSON fixtures (no real infrastructure),
3. makes one real LLM triage call through the supported Stepfork OpenAI SDK
   adapter (``stepfork.integrations.openai.chat_completions_create``), and
4. post-processes the model output against an independently defined severity
   policy.

The severity policy lives here, not in the model prompt, and is enforced with
a deterministic floor. A genuine application bug then lowers a policy-mandated
P0 to P1 whenever a recent deployment is present. That bug is application
logic, not a fabricated model response.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from stepfork import trace_tool
from stepfork.integrations.openai import chat_completions_create

from counters import TOOL_BODY_EXECUTIONS
from provider import build_client

HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "fixtures"

# The recorded model. Overridable for re-recording, but the default must match
# the committed trace so that offline replay resolves identically.
MODEL = os.environ.get("CASE_STUDY_MODEL", "gemini-2.5-flash")

SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

INCIDENT: dict[str, Any] = {
    "incident_id": "INC-2026-1010-001",
    "report": (
        "A production API is returning HTTP 500 errors for most customers. "
        "Error rates increased sharply after a deployment, and the payment "
        "checkout endpoint is failing."
    ),
    "primary_service": "checkout-api",
    "related_services": ["payments-api"],
    "incident_type": "api_5xx_checkout",
}

# Set to the timestamp-free values observed by the LLM call; used only to
# report token usage in RESULTS.md.
LAST_LLM_USAGE: dict[str, Any] = {}
# Raw (pre-policy) parsed model decision, for the optional hybrid comparison.
LAST_RAW_DECISION: dict[str, Any] = {}


def _load(name: str) -> dict[str, Any]:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Instrumented tools (safe, deterministic, local fixtures only)
# ---------------------------------------------------------------------------


@trace_tool(name="lookup_service_health")
def lookup_service_health(service: str) -> dict[str, Any]:
    """Return the current health record for a service."""
    TOOL_BODY_EXECUTIONS["count"] += 1
    services = _load("services.json")["services"]
    return services.get(
        service,
        {"service": service, "status": "unknown", "customer_facing": False},
    )


@trace_tool(name="get_recent_deployments")
def get_recent_deployments(service: str, window_minutes: int = 60) -> dict[str, Any]:
    """Return deployments for a service and whether any is inside the window."""
    TOOL_BODY_EXECUTIONS["count"] += 1
    deployments = _load("deployments.json")["deployments"].get(service, [])
    recent = [d for d in deployments if d.get("minutes_ago", 10**9) <= window_minutes]
    return {
        "service": service,
        "window_minutes": window_minutes,
        "recent_deployment": bool(recent),
        "deployments": deployments,
    }


@trace_tool(name="fetch_incident_runbook")
def fetch_incident_runbook(incident_type: str) -> dict[str, Any]:
    """Return the runbook for an incident type."""
    TOOL_BODY_EXECUTIONS["count"] += 1
    runbooks = _load("runbooks.json")["runbooks"]
    return runbooks.get(
        incident_type,
        {"runbook_id": incident_type, "steps": [], "severity_guidance": ""},
    )


# ---------------------------------------------------------------------------
# Deterministic severity policy (independent of the model)
# ---------------------------------------------------------------------------


def _facts(evidence: dict[str, Any]) -> dict[str, Any]:
    health = evidence["health"]
    customer_facing = [h for h in health.values() if h.get("customer_facing")]
    widespread = any(h.get("error_rate", 0.0) >= 0.5 for h in customer_facing)
    checkout_failing = health.get("checkout-api", {}).get("error_rate", 0.0) >= 0.5
    return {
        "widespread_customer_impact": widespread,
        "checkout_failing": checkout_failing,
    }


def policy_severity(facts: dict[str, Any]) -> str:
    """Return the minimum acceptable severity required by policy."""
    if facts["widespread_customer_impact"] and facts["checkout_failing"]:
        return "P0"
    if facts["widespread_customer_impact"]:
        return "P1"
    return "P2"


# ---------------------------------------------------------------------------
# LLM boundary (recorded/replayed through the Stepfork OpenAI adapter)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an IT incident triage assistant. Given operational evidence, "
    "return ONLY a JSON object with exactly these keys: "
    "summary (string), severity (one of P0, P1, P2, P3), "
    "affected_services (array of service name strings), "
    "recommended_next_action (string), "
    "supporting_evidence (array of short strings). "
    "Do not wrap the JSON in markdown."
)

# Used only by the optional hybrid prompt comparison (Section 9). The default
# is "baseline"; frozen replay always uses the recorded baseline prompt.
REVISED_SYSTEM_PROMPT = (
    SYSTEM_PROMPT
    + " Apply this severity policy explicitly: widespread production checkout "
    "failure is P0 and requires escalation; a recent deployment is rollback "
    "context and must not lower the severity."
)
_PROMPT_VARIANT = os.environ.get("CASE_STUDY_PROMPT_VARIANT", "baseline")


def _build_messages(evidence: dict[str, Any]) -> list[dict[str, str]]:
    system = REVISED_SYSTEM_PROMPT if _PROMPT_VARIANT == "revised" else SYSTEM_PROMPT
    evidence_json = json.dumps(evidence, sort_keys=True, indent=2)
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Incident report: {INCIDENT['report']}\n\n"
                f"Operational evidence (JSON):\n{evidence_json}"
            ),
        },
    ]


def _parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1]
        candidate = candidate.rsplit("```", 1)[0]
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {
            "summary": text.strip()[:200],
            "severity": "P3",
            "affected_services": [],
            "recommended_next_action": "",
            "supporting_evidence": ["unparseable model output"],
        }
    return parsed if isinstance(parsed, dict) else {}


def _llm_triage(evidence: dict[str, Any]) -> dict[str, Any]:
    messages = _build_messages(evidence)
    client = build_client()
    response = chat_completions_create(
        client,
        model=MODEL,
        messages=messages,
        temperature=0,
        # Gemini 2.5 Flash spends output tokens on internal "thinking"; keep a
        # generous cap so the JSON answer is not truncated.
        max_tokens=2000,
    )
    usage = response.get("usage") if isinstance(response, dict) else None
    if isinstance(usage, dict):
        LAST_LLM_USAGE.clear()
        LAST_LLM_USAGE.update(usage)
    content = response["choices"][0]["message"]["content"]
    parsed = _parse_json_object(content)
    LAST_RAW_DECISION.clear()
    LAST_RAW_DECISION.update(parsed)
    return parsed


# ---------------------------------------------------------------------------
# Deterministic post-processing
# ---------------------------------------------------------------------------


def _normalize(raw: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    severity = str(raw.get("severity", "")).strip().upper()
    if severity not in SEVERITY_RANK:
        severity = "P3"
    affected = [str(s).strip() for s in (raw.get("affected_services") or []) if str(s).strip()]
    evidence = [str(e).strip() for e in (raw.get("supporting_evidence") or []) if str(e).strip()]
    return {
        "incident_id": INCIDENT["incident_id"],
        "summary": str(raw.get("summary", "")).strip(),
        "severity": severity,
        "affected_services": affected,
        "recommended_next_action": str(raw.get("recommended_next_action", "")).strip(),
        "escalation_required": severity in {"P0", "P1"},
        "supporting_evidence": evidence,
    }


def _apply_policy_floor(
    decision: dict[str, Any], facts: dict[str, Any]
) -> dict[str, Any]:
    floor = policy_severity(facts)
    if SEVERITY_RANK[decision["severity"]] > SEVERITY_RANK[floor]:
        decision["severity"] = floor
    decision["escalation_required"] = decision["severity"] in {"P0", "P1"}
    return decision


def _correlate_recent_deployment(
    decision: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    """Record deployment correlation without overriding the severity policy.

    FIX: a recent deployment is useful rollback context, but it must never
    lower the severity enforced by the independent policy floor. The earlier
    version of this function overwrote a P0 decision with P1 and disabled
    escalation whenever a deployment fell inside the correlation window; the
    recorded trace was produced by that buggy version.
    """
    return decision


def _finalize_decision(
    raw: dict[str, Any], evidence: dict[str, Any], facts: dict[str, Any]
) -> dict[str, Any]:
    decision = _normalize(raw, facts)
    decision = _apply_policy_floor(decision, facts)
    decision = _correlate_recent_deployment(decision, evidence)
    return decision


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _collect_evidence() -> dict[str, Any]:
    services = [INCIDENT["primary_service"], *INCIDENT["related_services"]]
    health = {service: lookup_service_health(service) for service in services}
    deployments = {service: get_recent_deployments(service) for service in services}
    runbook = fetch_incident_runbook(INCIDENT["incident_type"])
    return {"health": health, "deployments": deployments, "runbook": runbook}


def run_incident_agent() -> dict[str, Any]:
    """Zero-argument entrypoint used for recording, replay, and pytest export."""
    evidence = _collect_evidence()
    facts = _facts(evidence)
    raw = _llm_triage(evidence)
    return _finalize_decision(raw, evidence, facts)


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    print(json.dumps(run_incident_agent(), indent=2, sort_keys=True))
