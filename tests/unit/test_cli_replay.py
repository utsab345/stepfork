from __future__ import annotations

import random
import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stepfork import FailureInfo, ReplaySession, Trace, record, trace_tool
from stepfork.cli.main import app
from stepfork.trace import ErrorEvent, RunEnd, RunStatus

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = "examples.booking_agent:run_agent"


@trace_tool(name="step")
def step(value: str) -> dict[str, str]:
    return {"value": value}


def _record_step(destination: Path) -> None:
    with record("demo-agent", output=destination):
        step("a")


def _record_booking(destination: Path) -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from examples.booking_agent import agent

    with record("booking-agent", output=destination) as session:
        session.set_output(agent.run_agent())


def test_replay_cli_frozen_success(tmp_path: Path) -> None:
    trace = tmp_path / "booking.sftrace"
    _record_booking(trace)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", ENTRYPOINT, "--mode", "frozen"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "COMPLETED" in result.stdout


def test_replay_cli_rejects_invalid_mode(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_step(trace)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", ENTRYPOINT, "--mode", "banana"],
    )

    assert result.exit_code == 2
    assert "Invalid replay mode" in result.stdout


def test_replay_cli_missing_trace_exits_two(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["replay", str(tmp_path / "missing.sftrace"), "--entrypoint", ENTRYPOINT],
    )

    assert result.exit_code == 2


def test_replay_cli_invalid_entrypoint_exits_two(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_step(trace)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", "not_a_module:func"],
    )

    assert result.exit_code == 2
    assert "entrypoint" in result.stdout.lower()


def test_replay_api_is_importable() -> None:
    assert ReplaySession is not None


_TARGETS = """
from stepfork import trace_tool

@trace_tool(name="step")
def step(value: str) -> dict[str, str]:
    return {"value": value}

def call_step_b(value: str = "b") -> dict[str, str]:
    return step(value)

def noop() -> dict[str, object]:
    return {"blob": "x" * 1000}

def raise_value_error() -> dict[str, object]:
    raise ValueError("boom")

def raise_type_error() -> dict[str, object]:
    raise TypeError("bad")

def random_value() -> dict[str, float]:
    import random
    return {"value": random.random()}

def call_step_a() -> dict[str, str]:
    return step("a")

@trace_tool(name="failing_step")
def failing_step() -> None:
    raise ValueError("dependency failed")

def call_failing_step() -> None:
    failing_step()
"""


def _write_targets(directory: Path) -> None:
    package = directory / "targetpkg"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "targets.py").write_text(
        textwrap.dedent(_TARGETS),
        encoding="utf-8",
    )


def _record_failed(destination: Path) -> None:
    trace = Trace(agent_name="fail-agent")
    trace.add(ErrorEvent(error_type="ValueError", message="boom"))
    trace.add(RunEnd(run_status=RunStatus.FAILED))
    trace.status = RunStatus.FAILED
    trace.failure = FailureInfo(type="ValueError", message="boom", step=0)
    trace.save(destination)


def test_replay_cli_reports_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace = tmp_path / "run.sftrace"
    _record_step(trace)
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", "targetpkg.targets:call_step_b"],
    )

    assert result.exit_code == 1
    assert "DIVERGED" in result.stdout


def test_replay_cli_success_with_no_tool_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "plain.sftrace"
    with record("plain-agent", output=trace):
        pass
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", "targetpkg.targets:noop"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "COMPLETED" in result.stdout
    assert "no dependency calls matched" in result.stdout
    assert "blob" in result.stdout
    assert "Recorded behavior: NOT RECORDED" in result.stdout


def test_replay_cli_detects_untraced_random_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    from targetpkg.targets import random_value

    trace = tmp_path / "random.sftrace"
    monkeypatch.setattr(random, "random", lambda: 0.25)
    with record("random-agent", output=trace) as session:
        session.set_output(random_value())
    monkeypatch.setattr(random, "random", lambda: 0.75)

    result = runner.invoke(
        app, ["replay", str(trace), "--entrypoint", "targetpkg.targets:random_value"]
    )

    assert result.exit_code == 1
    assert "Execution: COMPLETED" in result.stdout
    assert "Dependency matching: COMPLETE" in result.stdout
    assert "Recorded behavior: DIFFERENT" in result.stdout
    assert "final result differs" in result.stdout


def test_replay_cli_matching_final_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)
    trace = tmp_path / "step.sftrace"
    with record("step-agent", output=trace) as session:
        session.set_output(step("a"))

    result = runner.invoke(
        app, ["replay", str(trace), "--entrypoint", "targetpkg.targets:call_step_a"]
    )

    assert result.exit_code == 0
    assert "Recorded behavior: MATCHED" in result.stdout


def test_replay_cli_short_fingerprints_with_verbose_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "step.sftrace"
    _record_step(trace)
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)
    args = ["replay", str(trace), "--entrypoint", "targetpkg.targets:call_step_b"]

    short = runner.invoke(app, args)
    verbose = runner.invoke(app, [*args, "--verbose"])

    assert short.exit_code == verbose.exit_code == 1
    assert "input fingerprint" in short.stdout
    assert "…" in short.stdout
    assert "input fingerprint" in verbose.stdout
    assert any(len(word) == 64 for word in verbose.stdout.split())


def test_replay_cli_reproduces_recorded_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "fail.sftrace"
    _record_failed(trace)
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "replay",
            str(trace),
            "--entrypoint",
            "targetpkg.targets:raise_value_error",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "REPRODUCED FAILURE" in result.stdout
    assert "ValueError" in result.stdout


def test_replay_cli_reproduces_recorded_dependency_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    from targetpkg.targets import call_failing_step

    trace = tmp_path / "dependency_failure.sftrace"
    with (
        pytest.raises(ValueError, match="dependency failed"),
        record("fail-agent", output=trace),
    ):
        call_failing_step()

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", "targetpkg.targets:call_failing_step"],
    )

    assert result.exit_code == 0
    assert "Execution: RAISED" in result.stdout
    assert "Dependency matching: COMPLETE" in result.stdout
    assert "Recorded behavior: FAILURE TYPE MATCHED" in result.stdout
    assert "REPRODUCED FAILURE" in result.stdout


def test_replay_cli_reports_failed_run_without_raise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "fail.sftrace"
    _record_failed(trace)
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", "targetpkg.targets:noop"],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "DIVERGED" in result.stdout
    assert "recorded a failed run" in result.stdout


def test_replay_cli_reports_unexpected_exception_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = tmp_path / "fail.sftrace"
    _record_failed(trace)
    _write_targets(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["replay", str(trace), "--entrypoint", "targetpkg.targets:raise_type_error"],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "TypeError" in result.stdout
    assert "DIVERGED" in result.stdout
