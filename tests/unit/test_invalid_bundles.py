from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from stepfork import Trace
from stepfork.trace import ToolCall, validate_bundle


def partial_bundle(tmp_path: Path) -> Path:
    trace = Trace(agent_name="invalid-agent")
    trace.add(ToolCall(name="search", input={"query": "Kathmandu flights"}))
    return trace.save(tmp_path / "invalid.sftrace")


def read_events(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (path / "events.jsonl").read_text().splitlines()
        if line
    ]


def write_events(path: Path, events: list[dict[str, object]]) -> None:
    (path / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda events: events.append({**events[0], "step": 1}),
            "duplicate_event_id",
        ),
        (
            lambda events: events[0].update({"parent_id": "evt_missing"}),
            "invalid_parent",
        ),
        (
            lambda events: events.extend(
                [
                    {
                        **events[0],
                        "id": "evt_later",
                        "step": 5,
                        "parent_id": None,
                    },
                    {
                        **events[0],
                        "id": "evt_earlier",
                        "step": 3,
                        "parent_id": None,
                    },
                ]
            ),
            "step_order",
        ),
        (
            lambda events: events[0].update({"run_id": "run_other"}),
            "run_id_mismatch",
        ),
    ],
)
def test_invalid_event_structure_cases(
    tmp_path: Path,
    mutate: Callable[[list[dict[str, object]]], None],
    expected_code: str,
) -> None:
    path = partial_bundle(tmp_path)
    events = read_events(path)
    mutate(events)
    write_events(path, events)

    result = validate_bundle(path, strict=False)

    assert expected_code in {issue.code for issue in result.issues}


def test_invalid_jsonl_reports_invalid_json(tmp_path: Path) -> None:
    path = partial_bundle(tmp_path)
    (path / "events.jsonl").write_text("{")

    result = validate_bundle(path)

    assert result.issues[0].code == "invalid_json"


def test_missing_manifest_reports_missing_file(tmp_path: Path) -> None:
    path = partial_bundle(tmp_path)
    (path / "manifest.json").unlink()

    result = validate_bundle(path)

    assert result.issues[0].code == "missing_file"


def test_wrong_schema_version_reports_unsupported(tmp_path: Path) -> None:
    path = partial_bundle(tmp_path)
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["schema_version"] = "9.9"
    (path / "manifest.json").write_text(json.dumps(manifest))

    result = validate_bundle(path)

    assert result.issues[0].code == "unsupported_schema"


def test_invalid_redaction_metadata_reports_invalid_manifest(tmp_path: Path) -> None:
    path = partial_bundle(tmp_path)
    (path / "redactions.json").write_text(
        json.dumps({"schema_version": "0.1", "entries": "bad"})
    )

    result = validate_bundle(path)

    assert result.issues[0].code == "invalid_manifest"
