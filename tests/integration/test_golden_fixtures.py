from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stepfork import Trace
from stepfork.inspect import inspect_bundle
from stepfork.trace import validate_bundle
from stepfork.trace.integrity import IntegrityStatus, verify_bundle_integrity

GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "golden"
COMPLETE_FIXTURES = [
    "successful_run.sftrace",
    "failed_tool_run.sftrace",
    "failed_llm_run.sftrace",
]
ALL_FIXTURES = [
    *COMPLETE_FIXTURES,
    "partial_run.sftrace",
    "legacy_v01.sftrace",
]


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_golden_fixture_loads(fixture_name: str) -> None:
    assert Trace.load(GOLDEN_ROOT / fixture_name).agent_name.startswith("golden-")


@pytest.mark.parametrize("fixture_name", COMPLETE_FIXTURES)
def test_complete_golden_fixtures_pass_strict_validation(fixture_name: str) -> None:
    assert validate_bundle(GOLDEN_ROOT / fixture_name, verify_integrity=True).valid


def test_partial_golden_fixture_passes_partial_and_fails_strict() -> None:
    path = GOLDEN_ROOT / "partial_run.sftrace"

    assert validate_bundle(path, strict=False, verify_integrity=True).valid
    result = validate_bundle(path, strict=True, verify_integrity=True)

    assert not result.valid
    assert "run_start_count" in {issue.code for issue in result.issues}


@pytest.mark.parametrize("fixture_name", [*COMPLETE_FIXTURES, "partial_run.sftrace"])
def test_new_golden_fixtures_verify_integrity(fixture_name: str) -> None:
    result = verify_bundle_integrity(GOLDEN_ROOT / fixture_name)

    assert result.status is IntegrityStatus.VERIFIED


def test_legacy_golden_fixture_is_unverified_legacy() -> None:
    result = verify_bundle_integrity(GOLDEN_ROOT / "legacy_v01.sftrace")

    assert result.status is IntegrityStatus.UNVERIFIED_LEGACY
    assert Trace.load(GOLDEN_ROOT / "legacy_v01.sftrace").run_id == "run_legacy_001"


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_inspect_works_for_every_golden_fixture(fixture_name: str) -> None:
    inspection = inspect_bundle(GOLDEN_ROOT / fixture_name)
    payload = json.loads(inspection.model_dump_json())

    assert payload["agent_name"].startswith("golden-")
    assert isinstance(payload["timeline"], list)


def test_golden_fixtures_contain_no_raw_synthetic_secret() -> None:
    for path in GOLDEN_ROOT.glob("*.sftrace/*"):
        if path.is_file():
            assert "goldentoolsecret" not in path.read_text()


def test_resaving_golden_preserves_logical_identity(tmp_path: Path) -> None:
    source = GOLDEN_ROOT / "successful_run.sftrace"
    trace = Trace.load(source)
    destination = tmp_path / "resaved.sftrace"

    trace.save(destination, status=trace.status)
    loaded = Trace.load(destination)

    assert loaded.run_id == trace.run_id
    assert [event.id for event in loaded.events] == [event.id for event in trace.events]
    assert [event.step for event in loaded.events] == [
        event.step for event in trace.events
    ]


def test_tampered_golden_copy_fails_integrity(tmp_path: Path) -> None:
    source = GOLDEN_ROOT / "successful_run.sftrace"
    tampered = tmp_path / "tampered.sftrace"
    shutil.copytree(source, tampered)
    manifest = json.loads((tampered / "manifest.json").read_text())
    manifest["agent_name"] = "changed"
    (tampered / "manifest.json").write_text(json.dumps(manifest))

    assert verify_bundle_integrity(tampered).status is IntegrityStatus.MISMATCH
