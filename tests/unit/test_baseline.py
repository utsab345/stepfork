from __future__ import annotations

import json
from pathlib import Path

import pytest

from stepfork import (
    BaselineCompatibilityError,
    BaselineError,
    BaselineExistsError,
    BaselineNotFoundError,
    compare_baseline,
    list_baselines,
    load_baseline,
    record,
    save_baseline,
    trace_tool,
)
from stepfork.trace import RunStart, Trace


@trace_tool(name="baseline_echo")
def _echo(value: str) -> dict[str, str]:
    return {"value": value}


def _record(path: Path, value: str) -> None:
    with record("baseline-test", output=path) as session:
        result = _echo(value)
        session.set_output(result)


def test_save_load_and_list_baselines(tmp_path: Path) -> None:
    trace = tmp_path / "source.sftrace"
    store = tmp_path / "baselines"
    _record(trace, "stable")

    saved = save_baseline("stable-v1", trace, directory=store)
    save_baseline("stable-v2", trace, directory=store)
    loaded = load_baseline("stable-v1", directory=store)

    assert saved == store / "stable-v1.sftrace"
    assert loaded.name == "stable-v1"
    assert loaded.trace.run_id
    assert [baseline.name for baseline in list_baselines(directory=store)] == [
        "stable-v1",
        "stable-v2",
    ]


def test_saving_existing_baseline_never_overwrites(tmp_path: Path) -> None:
    first = tmp_path / "first.sftrace"
    second = tmp_path / "second.sftrace"
    store = tmp_path / "baselines"
    _record(first, "first")
    _record(second, "second")

    save_baseline("release-1", first, directory=store)
    original = (store / "release-1.sftrace" / "events.jsonl").read_bytes()

    with pytest.raises(BaselineExistsError, match="already exists"):
        save_baseline("release-1", second, directory=store)

    assert (store / "release-1.sftrace" / "events.jsonl").read_bytes() == original


@pytest.mark.parametrize(
    "name",
    ["../outside", "Upper", "", "a/b", "-invalid", "nul", "com1.trace"],
)
def test_baseline_names_cannot_escape_store(tmp_path: Path, name: str) -> None:
    trace = tmp_path / "trace.sftrace"
    _record(trace, "stable")

    with pytest.raises(BaselineError, match="baseline name"):
        save_baseline(name, trace, directory=tmp_path / "baselines")


def test_symlinked_trace_and_store_paths_are_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "source.sftrace"
    store = tmp_path / "baselines"
    _record(trace, "stable")
    store.mkdir()
    try:
        trace_link = tmp_path / "trace-link.sftrace"
        trace_link.symlink_to(trace, target_is_directory=True)
        store_link = tmp_path / "store-link"
        store_link.symlink_to(store, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(BaselineError, match="must not be a symlink"):
        save_baseline("linked-trace", trace_link, directory=tmp_path / "new-store")
    with pytest.raises(BaselineError, match="must not be a symlink"):
        list_baselines(directory=store_link)


def test_symlinked_baseline_entry_is_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "source.sftrace"
    store = tmp_path / "baselines"
    _record(trace, "stable")
    store.mkdir()
    try:
        (store / "linked.sftrace").symlink_to(trace, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(BaselineError, match="must not be a symlink"):
        load_baseline("linked", directory=store)


def test_missing_baseline_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(BaselineNotFoundError, match="was not found"):
        load_baseline("missing", directory=tmp_path / "baselines")


def test_unsupported_trace_schema_is_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "source.sftrace"
    _record(trace, "stable")
    save_baseline("stable", trace, directory=tmp_path / "baselines")
    manifest_path = tmp_path / "baselines" / "stable.sftrace" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "9.9"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BaselineCompatibilityError, match="unsupported format"):
        load_baseline("stable", directory=tmp_path / "baselines")


def test_corrupt_baseline_is_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "source.sftrace"
    _record(trace, "stable")
    save_baseline("stable", trace, directory=tmp_path / "baselines")
    events_path = tmp_path / "baselines" / "stable.sftrace" / "events.jsonl"
    events_path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(BaselineError, match="invalid"):
        load_baseline("stable", directory=tmp_path / "baselines")


def test_candidate_must_be_integrity_verified(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.sftrace"
    candidate = tmp_path / "candidate.sftrace"
    _record(baseline, "stable")
    _record(candidate, "stable")
    save_baseline("stable", baseline, directory=tmp_path / "baselines")
    (candidate / "events.jsonl").write_text("corrupt\n", encoding="utf-8")

    with pytest.raises(BaselineError, match="invalid"):
        compare_baseline("stable", candidate, directory=tmp_path / "baselines")


def test_incomplete_trace_cannot_be_a_baseline_or_candidate(tmp_path: Path) -> None:
    complete = tmp_path / "complete.sftrace"
    incomplete = tmp_path / "incomplete.sftrace"
    store = tmp_path / "baselines"
    _record(complete, "stable")
    partial_trace = Trace(agent_name="partial-run")
    partial_trace.add(RunStart())
    partial_trace.save(incomplete)
    save_baseline("stable", complete, directory=store)

    with pytest.raises(BaselineError, match="terminal run_end"):
        save_baseline("incomplete", incomplete, directory=store)
    with pytest.raises(BaselineError, match="terminal run_end"):
        compare_baseline("stable", incomplete, directory=store)


def test_complete_failed_candidate_is_detected_as_changed_behavior(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.sftrace"
    candidate = tmp_path / "failed.sftrace"
    store = tmp_path / "baselines"
    _record(baseline, "stable")
    try:
        with record("baseline-test", output=candidate):
            raise RuntimeError("expected fixture failure")
    except RuntimeError:
        pass
    save_baseline("stable", baseline, directory=store)

    result = compare_baseline("stable", candidate, directory=store)

    assert not result.equivalent
    assert any(
        change.path == "run_status" for step in result.steps for change in step.changes
    )


def test_compare_uses_behavioral_diff_and_paths(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.sftrace"
    candidate = tmp_path / "candidate.sftrace"
    _record(baseline, "expected")
    _record(candidate, "actual")
    saved = save_baseline("stable", baseline, directory=tmp_path / "baselines")

    result = compare_baseline("stable", candidate, directory=tmp_path / "baselines")

    assert not result.equivalent
    assert result.changed > 0
    assert result.baseline.path == str(saved)
    assert result.candidate.path == str(candidate)
    assert any(
        change.path == "input.value" for step in result.steps for change in step.changes
    )


def test_empty_store_lists_no_baselines(tmp_path: Path) -> None:
    assert list_baselines(directory=tmp_path / "missing") == []
