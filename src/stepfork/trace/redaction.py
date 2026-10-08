"""Best-effort secret redaction for trace persistence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from stepfork.trace.manifest import TraceManifest
from stepfork.trace.models import Event, JsonValue, Trace

REDACTION_REPLACEMENT = "[REDACTED]"
MANIFEST_REDACTION_ID = "__manifest__"

SENSITIVE_KEY_NORMALIZED = {
    "apikey",
    "accesstoken",
    "refreshtoken",
    "authtoken",
    "authorization",
    "password",
    "passwd",
    "secret",
    "clientsecret",
    "privatekey",
    "sessiontoken",
    "bearertoken",
}

PROTECTED_EVENT_FIELDS = {
    "id",
    "run_id",
    "parent_id",
    "step",
    "type",
    "timestamp",
    "duration_ms",
    "status",
    "replay_policy",
    "input_hash",
    "output_hash",
    "redactions",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
    "run_status",
}

PROTECTED_MANIFEST_FIELDS = {
    "format",
    "schema_version",
    "run_id",
    "created_at",
    "status",
    "totals",
}

_event_adapter: TypeAdapter[Event] = TypeAdapter(Event)

_CREDENTIAL_PATTERNS = [
    re.compile(r"(?i)(Authorization:\s*Bearer\s+)([A-Za-z0-9._~+/=-]{8,})"),
    re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9._~+/=-]{8,})"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"\b(ghp_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"\b(gho_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{8,})\b"),
]


class RedactionError(ValueError):
    """Raised when a value cannot be safely redacted for persistence."""


class RedactionEntry(BaseModel):
    """Persisted redaction metadata without raw secret values."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    replacement: Literal["[REDACTED]"] = "[REDACTED]"


class RedactionManifest(BaseModel):
    """Redactions recorded for a `.sftrace` bundle."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    entries: list[RedactionEntry] = Field(default_factory=list)


@dataclass(frozen=True)
class RedactionFinding:
    """Internal redaction finding before an event ID is attached."""

    path: str
    reason: str


@dataclass(frozen=True)
class RedactionResult:
    """Sanitized JSON value plus non-secret metadata."""

    value: JsonValue
    findings: list[RedactionFinding] = field(default_factory=list)


@dataclass(frozen=True)
class PreparedTrace:
    """Trace data prepared for persistence."""

    trace: Trace
    manifest: TraceManifest
    redactions: RedactionManifest


def redact_json(value: JsonValue) -> RedactionResult:
    """Recursively redact sensitive keys and credential-like string spans."""
    sanitized, findings = _redact_value(value, path="")
    return RedactionResult(value=cast(JsonValue, sanitized), findings=findings)


def prepare_trace_for_persistence(
    trace: Trace,
    manifest: TraceManifest,
) -> PreparedTrace:
    """Return sanitized trace data and redaction metadata for writing."""
    manifest_payload = manifest.model_dump(mode="json")
    sanitized_manifest_payload, manifest_findings = _redact_mapping(
        manifest_payload,
        path="",
        protected_fields=PROTECTED_MANIFEST_FIELDS,
    )
    sanitized_manifest = TraceManifest.model_validate(sanitized_manifest_payload)

    sanitized_events: list[Event] = []
    entries: list[RedactionEntry] = []
    for event in trace.events:
        event_payload = event.model_dump(mode="json")
        sanitized_event_payload, findings = _redact_mapping(
            event_payload,
            path="",
            protected_fields=PROTECTED_EVENT_FIELDS,
        )
        event_entries = [
            RedactionEntry(
                event_id=event.id,
                path=finding.path,
                reason=finding.reason,
            )
            for finding in findings
        ]
        if event_entries:
            existing = sanitized_event_payload.get("redactions", [])
            sanitized_event_payload["redactions"] = [
                *existing,
                *(entry.path for entry in event_entries),
            ]
        sanitized_events.append(_event_adapter.validate_python(sanitized_event_payload))
        entries.extend(event_entries)

    entries.extend(
        RedactionEntry(
            event_id=MANIFEST_REDACTION_ID,
            path=finding.path,
            reason=finding.reason,
        )
        for finding in manifest_findings
    )

    sanitized_trace = Trace(
        run_id=sanitized_manifest.run_id,
        agent_name=sanitized_manifest.agent_name,
        created_at=sanitized_manifest.created_at,
        status=sanitized_manifest.status,
        failure=sanitized_manifest.failure,
        environment=sanitized_manifest.environment,
        totals=sanitized_manifest.totals,
        events=sanitized_events,
    )
    return PreparedTrace(
        trace=sanitized_trace,
        manifest=sanitized_manifest,
        redactions=RedactionManifest(entries=_dedupe_entries(entries)),
    )


def _redact_value(value: Any, *, path: str) -> tuple[Any, list[RedactionFinding]]:
    if isinstance(value, dict):
        return _redact_mapping(value, path=path, protected_fields=set())
    if isinstance(value, list):
        findings: list[RedactionFinding] = []
        redacted_items: list[Any] = []
        for index, item in enumerate(value):
            redacted_item, item_findings = _redact_value(
                item,
                path=f"{path}/{index}",
            )
            redacted_items.append(redacted_item)
            findings.extend(item_findings)
        return redacted_items, findings
    if isinstance(value, str):
        return _redact_string(value, path=path)
    return value, []


def _redact_mapping(
    value: dict[str, Any],
    *,
    path: str,
    protected_fields: set[str],
) -> tuple[dict[str, Any], list[RedactionFinding]]:
    findings: list[RedactionFinding] = []
    redacted: dict[str, Any] = {}

    for key in sorted(value):
        item = value[key]
        item_path = f"{path}/{_escape_json_pointer(key)}"
        if key in protected_fields:
            _assert_protected_value_is_safe(item)
            redacted[key] = item
            continue

        if _is_sensitive_key(key):
            if item == REDACTION_REPLACEMENT:
                redacted[key] = item
            else:
                redacted[key] = REDACTION_REPLACEMENT
                findings.append(
                    RedactionFinding(path=item_path, reason="sensitive_key")
                )
            continue

        redacted_item, item_findings = _redact_value(item, path=item_path)
        redacted[key] = redacted_item
        findings.extend(item_findings)

    return redacted, findings


def _redact_string(value: str, *, path: str) -> tuple[str, list[RedactionFinding]]:
    if value == REDACTION_REPLACEMENT:
        return value, []

    redacted = value
    changed = False
    for pattern in _CREDENTIAL_PATTERNS:
        redacted, replacements = pattern.subn(_replace_credential_match, redacted)
        changed = changed or replacements > 0

    if not changed:
        return value, []
    return redacted, [RedactionFinding(path=path, reason="credential_pattern")]


def _replace_credential_match(match: re.Match[str]) -> str:
    if len(match.groups()) == 2:
        return f"{match.group(1)}{REDACTION_REPLACEMENT}"
    return REDACTION_REPLACEMENT


def _is_sensitive_key(key: str) -> bool:
    return _normalize_key(key) in SENSITIVE_KEY_NORMALIZED


def _normalize_key(key: str) -> str:
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    return re.sub(r"[^a-z0-9]", "", camel_split.lower())


def _escape_json_pointer(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _assert_protected_value_is_safe(value: Any) -> None:
    if isinstance(value, str) and _redact_string(value, path="")[0] != value:
        raise RedactionError("credential pattern found in protected structural field")


def _dedupe_entries(entries: list[RedactionEntry]) -> list[RedactionEntry]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[RedactionEntry] = []
    for entry in entries:
        key = (entry.event_id, entry.path, entry.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique
