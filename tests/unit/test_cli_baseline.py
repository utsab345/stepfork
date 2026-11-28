from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from stepfork import record, trace_tool
from stepfork.cli.main import app

runner = CliRunner()


@trace_tool(name="cli_baseline_echo")
def _echo(value: str) -> dict[str, str]:
    return {"value": value}


@trace_tool(name="cli_baseline_secret")
def _secret(value: str) -> dict[str, str]:
    return {"value": value}


def _record(path: Path, value: str) -> None:
    with record("cli-baseline-agent", output=path) as session:
        result = _echo(value)
        session.set_output(result)


def _record_secret(path: Path, value: str) -> None:
    with record("cli-baseline-agent", output=path) as session:
        result = _secret(value)
        session.set_output(result)


def _save(name: str, trace: Path, directory: Path) -> None:
    result = runner.invoke(
        app,
        ["baseline", "save", name, str(trace), "--directory", str(directory)],
    )
    assert result.exit_code == 0, result.stdout


def test_baseline_save_list_and_show(tmp_path: Path) -> None:
    trace = tmp_path / "stable.sftrace"
    store = tmp_path / "baselines"
    _record(trace, "stable")

    saved = runner.invoke(
        app,
        ["baseline", "save", "stable-v1", str(trace), "--directory", str(store)],
    )
    listed = runner.invoke(
        app, ["baseline", "list", "--json", "--directory", str(store)]
    )
    shown = runner.invoke(
        app,
        ["baseline", "show", "stable-v1", "--json", "--directory", str(store)],
    )

    assert saved.exit_code == 0
    assert "Saved baseline" in saved.stdout
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)[0]["name"] == "stable-v1"
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["schema_version"] == "0.1"


def test_baseline_compare_exit_codes_and_threshold(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.sftrace"
    same = tmp_path / "same.sftrace"
    changed = tmp_path / "changed.sftrace"
    store = tmp_path / "baselines"
    _record(baseline, "same")
    _record(same, "same")
    _record(changed, "different")
    _save("stable", baseline, store)

    match = runner.invoke(
        app,
        [
            "baseline",
            "compare",
            "stable",
            str(same),
            "--directory",
            str(store),
        ],
    )
    regression = runner.invoke(
        app,
        [
            "baseline",
            "compare",
            "stable",
            str(changed),
            "--directory",
            str(store),
        ],
    )
    threshold = runner.invoke(
        app,
        [
            "baseline",
            "compare",
            "stable",
            str(changed),
            "--max-changes",
            "10",
            "--directory",
            str(store),
        ],
    )

    assert match.exit_code == 0
    assert "BASELINE MATCH" in match.stdout
    assert regression.exit_code == 1
    assert "BEHAVIOR CHANGED" in regression.stdout
    assert "expected:" in regression.stdout
    assert "actual:" in regression.stdout
    assert threshold.exit_code == 0
    assert "within configured threshold" in threshold.stdout


def test_baseline_compare_json_reports_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.sftrace"
    changed = tmp_path / "changed.sftrace"
    store = tmp_path / "baselines"
    _record(baseline, "same")
    _record(changed, "different")
    _save("stable", baseline, store)

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare",
            "stable",
            str(changed),
            "--json",
            "--directory",
            str(store),
        ],
    )

    payload = json.loads(result.stdout)
    assert result.exit_code == 1
    assert payload["regression"] is True
    assert payload["change_count"] > 0


def test_baseline_compare_output_redacts_secret_values(tmp_path: Path) -> None:
    secret = "sk-abcdefgh12345"
    baseline = tmp_path / "baseline.sftrace"
    candidate = tmp_path / "candidate.sftrace"
    store = tmp_path / "baselines"
    _record_secret(baseline, secret)
    _record_secret(candidate, "different")
    _save("stable", baseline, store)

    result = runner.invoke(
        app,
        [
            "baseline",
            "compare",
            "stable",
            str(candidate),
            "--directory",
            str(store),
        ],
    )

    assert result.exit_code == 1
    assert secret not in result.stdout
    assert "[REDACTED]" in result.stdout


def test_missing_or_corrupt_baseline_exits_two(tmp_path: Path) -> None:
    trace = tmp_path / "trace.sftrace"
    store = tmp_path / "baselines"
    _record(trace, "stable")
    missing = runner.invoke(
        app,
        [
            "baseline",
            "compare",
            "missing",
            str(trace),
            "--directory",
            str(store),
        ],
    )
    _save("broken", trace, store)
    (store / "broken.sftrace" / "events.jsonl").write_text(
        "invalid\n", encoding="utf-8"
    )
    corrupt = runner.invoke(
        app,
        [
            "baseline",
            "show",
            "broken",
            "--directory",
            str(store),
        ],
    )

    assert missing.exit_code == 2
    assert "was not found" in missing.stdout
    assert corrupt.exit_code == 2
    assert "invalid" in corrupt.stdout


def test_duplicate_baseline_cli_does_not_replace(tmp_path: Path) -> None:
    first = tmp_path / "first.sftrace"
    second = tmp_path / "second.sftrace"
    store = tmp_path / "baselines"
    _record(first, "first")
    _record(second, "second")
    _save("stable", first, store)

    duplicate = runner.invoke(
        app,
        ["baseline", "save", "stable", str(second), "--directory", str(store)],
    )

    assert duplicate.exit_code == 2
    assert "already exists" in duplicate.stdout


def test_invalid_baseline_threshold_is_rejected(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "baseline",
            "compare",
            "stable",
            str(tmp_path / "candidate.sftrace"),
            "--max-changes",
            "-1",
        ],
    )

    assert result.exit_code == 2
