from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from stepfork import record
from stepfork.export import (
    EntrypointError,
    ExportError,
    ExportExistsError,
    export_pytest_test,
    generate_pytest_source,
    resolve_entrypoint,
    run_regression_case,
)
from stepfork.export.runtime import _preview

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "destination": "Lisbon",
    "selected_flight": "B",
    "plan": "Search flights, then choose the cheapest option.",
}


def _record_buggy(destination: Path) -> None:
    from examples.booking_agent import agent

    with record("booking-agent", output=destination) as session:
        session.set_output(agent.run_agent())


def test_resolve_entrypoint_rejects_invalid_specs() -> None:
    with pytest.raises(EntrypointError, match="expected the form"):
        resolve_entrypoint("no_colon")

    with pytest.raises(EntrypointError, match="cannot import module"):
        resolve_entrypoint("not_a_real_module:func")

    with pytest.raises(EntrypointError, match="no attribute"):
        resolve_entrypoint(
            "examples.booking_agent:does_not_exist",
            import_root=REPO_ROOT,
        )


def test_resolve_entrypoint_finds_callable() -> None:
    entry = resolve_entrypoint(
        "examples.booking_agent:run_agent",
        import_root=REPO_ROOT,
    )
    assert callable(entry)


def test_generated_source_compiles(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_buggy(trace)

    source = generate_pytest_source(
        trace_path=trace,
        output_path=tmp_path / "test_regression.py",
        entrypoint="examples.booking_agent:run_agent",
        expectation=EXPECTED,
        has_expectation=True,
        import_root=REPO_ROOT,
    )

    compile(source, "<generated>", "exec")
    assert "assert True" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "run_regression_case" in source


def test_generated_source_does_not_embed_secrets(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    with record("agent", output=trace) as session:
        session.set_output({"token": "sk-supersecretvalue123", "ok": "yes"})

    source = generate_pytest_source(
        trace_path=trace,
        output_path=tmp_path / "test_regression.py",
        entrypoint="examples.booking_agent:run_agent",
        expectation={"token": "sk-supersecretvalue123", "ok": "yes"},
        has_expectation=True,
        import_root=REPO_ROOT,
    )

    assert "sk-supersecretvalue123" not in source
    assert "[REDACTED]" in source


def test_export_requires_overwrite(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_buggy(trace)
    output = tmp_path / "test_regression.py"
    output.write_text("# existing\n", encoding="utf-8")

    with pytest.raises(ExportExistsError, match="already exists"):
        export_pytest_test(
            trace_path=trace,
            output_path=output,
            entrypoint="examples.booking_agent:run_agent",
            expectation=EXPECTED,
            import_root=REPO_ROOT,
        )


def test_export_overwrite_replaces(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_buggy(trace)
    output = tmp_path / "test_regression.py"
    output.write_text("# existing\n", encoding="utf-8")

    export_pytest_test(
        trace_path=trace,
        output_path=output,
        entrypoint="examples.booking_agent:run_agent",
        expectation=EXPECTED,
        import_root=REPO_ROOT,
        overwrite=True,
    )

    assert "run_regression_case" in output.read_text(encoding="utf-8")


def test_export_rejects_directory_output(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_buggy(trace)
    output = tmp_path / "adir"
    output.mkdir()

    with pytest.raises(ExportError, match="directory"):
        export_pytest_test(
            trace_path=trace,
            output_path=output,
            entrypoint="examples.booking_agent:run_agent",
            expectation=EXPECTED,
            import_root=REPO_ROOT,
        )


def test_run_regression_case_fails_on_buggy_agent(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_buggy(trace)

    with pytest.raises(AssertionError, match="behavior mismatch"):
        run_regression_case(
            trace_path=trace,
            import_root=REPO_ROOT,
            entrypoint="examples.booking_agent:run_agent",
            expectation=EXPECTED,
            has_expectation=True,
            mode="frozen",
        )


def test_run_regression_case_passes_on_fixed_agent(tmp_path: Path) -> None:
    from examples.booking_agent import agent

    trace = tmp_path / "run.sftrace"
    _record_buggy(trace)

    agent.TOOL_EXECUTIONS.clear()
    result = run_regression_case(
        trace_path=trace,
        import_root=REPO_ROOT,
        entrypoint="examples.booking_agent:run_agent_fixed",
        expectation=EXPECTED,
        has_expectation=True,
        mode="frozen",
    )

    assert result == EXPECTED
    assert agent.TOOL_EXECUTIONS == []


def test_run_regression_case_missing_trace(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="trace bundle not found"):
        run_regression_case(
            trace_path=tmp_path / "missing.sftrace",
            import_root=REPO_ROOT,
            entrypoint="examples.booking_agent:run_agent",
            expectation=EXPECTED,
        )


def test_generated_module_executes(tmp_path: Path) -> None:
    trace = tmp_path / "run.sftrace"
    _record_buggy(trace)
    output = tmp_path / "test_generated_module.py"
    export_pytest_test(
        trace_path=trace,
        output_path=output,
        entrypoint="examples.booking_agent:run_agent_fixed",
        expectation=EXPECTED,
        import_root=REPO_ROOT,
    )

    spec = importlib.util.spec_from_file_location("test_generated_module", output)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_generated_module"] = module
    try:
        spec.loader.exec_module(module)
        module.test_stepfork_regression_run()
    finally:
        sys.modules.pop("test_generated_module", None)


def test_preview_truncates_large_values() -> None:
    preview = _preview({"blob": "x" * 1000})
    assert len(preview) <= 300
    assert preview.endswith("…")
