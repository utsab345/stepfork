from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import diff_traces, record, trace_tool
from stepfork.diff import first_difference, values_equal
from stepfork.diff.compare import collect_field_changes
from stepfork.diff.models import FieldChange
from stepfork.trace import Trace


@trace_tool(name="echo")
def echo(value: str) -> dict[str, str]:
    return {"value": value}


@trace_tool(name="alpha")
def alpha() -> dict[str, str]:
    return {"name": "alpha"}


@trace_tool(name="beta")
def beta() -> dict[str, str]:
    return {"name": "beta"}


@trace_tool(name="leaky")
def leaky(status: str) -> dict[str, str]:
    return {"log": f"credential sk-abcdefgh12345 status={status}"}


def _record(destination: Path, action: object) -> Trace:
    with record("demo-agent", output=destination):
        action()  # type: ignore[operator]
    return Trace.load(destination)


def test_identical_behavior_is_equivalent(tmp_path: Path) -> None:
    baseline = _record(tmp_path / "b.sftrace", lambda: echo("x"))
    candidate = _record(tmp_path / "c.sftrace", lambda: echo("x"))

    result = diff_traces(baseline, candidate)

    assert result.equivalent
    assert result.changed == 0
    assert result.added == 0
    assert result.removed == 0
    # Identity metadata differs (run IDs, timestamps, event IDs) but is ignored.
    assert baseline.run_id != candidate.run_id


def test_changed_output_is_detected(tmp_path: Path) -> None:
    baseline = _record(tmp_path / "b.sftrace", lambda: echo("expected"))
    candidate = _record(tmp_path / "c.sftrace", lambda: echo("actual"))

    result = diff_traces(baseline, candidate)

    assert not result.equivalent
    paths = {change.path for step in result.steps for change in step.changes}
    assert "output.value" in paths


def test_changed_input_is_detected(tmp_path: Path) -> None:
    baseline = _record(tmp_path / "b.sftrace", lambda: echo("one"))
    candidate = _record(tmp_path / "c.sftrace", lambda: echo("two"))

    result = diff_traces(baseline, candidate)

    assert not result.equivalent
    paths = {change.path for step in result.steps for change in step.changes}
    assert "input.value" in paths


def test_changed_call_order_is_detected(tmp_path: Path) -> None:
    def baseline_action() -> None:
        alpha()
        beta()

    def candidate_action() -> None:
        beta()
        alpha()

    baseline = _record(tmp_path / "b.sftrace", baseline_action)
    candidate = _record(tmp_path / "c.sftrace", candidate_action)

    result = diff_traces(baseline, candidate)

    assert not result.equivalent
    assert result.changed >= 1


def test_added_and_removed_calls_are_detected(tmp_path: Path) -> None:
    def baseline_action() -> None:
        alpha()

    def candidate_action() -> None:
        alpha()
        beta()

    baseline = _record(tmp_path / "b.sftrace", baseline_action)
    candidate = _record(tmp_path / "c.sftrace", candidate_action)

    result = diff_traces(baseline, candidate)

    assert not result.equivalent
    assert result.added == 1
    assert result.removed == 0


def test_error_difference_is_detected(tmp_path: Path) -> None:
    @trace_tool(name="sometimes")
    def sometimes(fail: bool) -> dict[str, bool]:
        if fail:
            raise RuntimeError("nope")
        return {"ok": True}

    def baseline_action() -> None:
        sometimes(False)

    def candidate_action() -> None:
        sometimes(True)

    baseline = _record(tmp_path / "b.sftrace", baseline_action)
    with pytest.raises(RuntimeError, match="nope"):
        _record(tmp_path / "c.sftrace", candidate_action)
    candidate = Trace.load(tmp_path / "c.sftrace")

    result = diff_traces(baseline, candidate)

    assert not result.equivalent
    assert any(
        change.path == "status" for step in result.steps for change in step.changes
    )


def test_diff_output_is_secret_safe(tmp_path: Path) -> None:
    baseline = _record(tmp_path / "b.sftrace", lambda: leaky("ok"))
    candidate = _record(tmp_path / "c.sftrace", lambda: leaky("fail"))

    result = diff_traces(baseline, candidate)

    dumped = result.model_dump_json()
    assert "sk-abcdefgh12345" not in dumped
    assert "[REDACTED]" in dumped


def test_first_difference_finds_leaf_path() -> None:
    difference = first_difference({"a": {"b": [1, 2]}}, {"a": {"b": [1, 3]}})

    assert difference is not None
    path, expected, actual = difference
    assert path == "a.b[1]"
    assert expected == 2
    assert actual == 3


def test_values_equal_canonical_profile() -> None:
    assert values_equal({"b": 1, "a": 2}, {"a": 2, "b": 1})
    assert not values_equal(1, 1.0)


def test_values_equal_returns_false_for_unsupported_values() -> None:
    assert not values_equal({"a": 1}, {"a": object()})
    assert not values_equal([1], {"a": 1})


def test_first_difference_missing_dict_keys() -> None:
    missing_actual = first_difference({"k": 1}, {})
    assert missing_actual == ("k", 1, None)

    missing_expected = first_difference({}, {"k": 1})
    assert missing_expected == ("k", None, 1)


def test_first_difference_list_length_mismatch() -> None:
    longer_actual = first_difference([1], [1, 2])
    assert longer_actual == ("[1]", None, 2)

    longer_expected = first_difference([1, 2], [1])
    assert longer_expected == ("[1]", 2, None)


def test_first_difference_root_scalar() -> None:
    assert first_difference(1, 2) == ("$", 1, 2)


def test_collect_field_changes_detects_list_differences() -> None:
    changed: list[FieldChange] = []
    collect_field_changes([1, 2], [1, 3, 4], path="", output=changed)

    assert [change.path for change in changed] == ["[1]", "[2]"]
    assert [change.kind for change in changed] == ["changed", "added"]

    removed: list[FieldChange] = []
    collect_field_changes([1, 3, 4], [1, 2], path="", output=removed)

    assert [change.path for change in removed] == ["[1]", "[2]"]
    assert [change.kind for change in removed] == ["changed", "removed"]


def test_collect_field_changes_nested_dict_add_and_remove() -> None:
    changed: list[FieldChange] = []
    collect_field_changes({"a": 1}, {"b": 2}, path="", output=changed)

    assert {change.path: change.kind for change in changed} == {
        "a": "removed",
        "b": "added",
    }
