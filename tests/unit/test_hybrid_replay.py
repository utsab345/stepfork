from __future__ import annotations

from pathlib import Path

import pytest

from stepfork import ReplaySession, llm_request, record, trace_tool
from stepfork.assertions import assert_tool_called, assert_tool_not_called
from stepfork.export.generator import generate_pytest_source
from stepfork.export.runtime import run_regression_case
from stepfork.replay import ReplayMismatchError

TOOL_BODIES: list[str] = []
LLM_BODIES: list[str] = []


@trace_tool(name="lookup")
def lookup(item: str) -> dict[str, str]:
    TOOL_BODIES.append(item)
    return {"item": item}


@trace_tool(name="charge_card")
def charge_card(item: str) -> dict[str, str]:
    TOOL_BODIES.append("charged")
    return {"item": item}


def agent(prompt: str, *, live_answer: str = "deny") -> dict[str, str]:
    def model_body() -> dict[str, str]:
        LLM_BODIES.append(prompt)
        return {"decision": live_answer}

    response = llm_request(
        provider="fake", model="model", input={"prompt": prompt}, call=model_body
    )
    result = lookup("A")
    return {"decision": response["decision"], "item": result["item"]}


def changed_agent() -> dict[str, str]:
    return agent("new", live_answer="approve")


def test_hybrid_runs_only_allowlisted_llm_and_checks_behavior(tmp_path: Path) -> None:
    path = tmp_path / "run.sftrace"
    TOOL_BODIES.clear()
    LLM_BODIES.clear()
    with record("agent", output=path):
        assert agent("old") == {"decision": "deny", "item": "A"}
    assert TOOL_BODIES == ["A"]
    assert LLM_BODIES == ["old"]
    TOOL_BODIES.clear()
    LLM_BODIES.clear()

    with ReplaySession.from_trace(
        path, mode="hybrid", live_llms={"fake/model"}
    ) as replay:
        result = agent("new", live_answer="approve")
        replay.verify_complete()
    assert result == {"decision": "approve", "item": "A"}
    assert TOOL_BODIES == []
    assert LLM_BODIES == ["new"]
    assert [call.action for call in replay.executed_calls] == [
        "executed",
        "substituted",
    ]
    assert_tool_called(replay, "lookup")
    assert_tool_not_called(replay, "charge_card")

    assert run_regression_case(
        trace_path=path,
        import_root=Path(__file__).parent,
        entrypoint="test_hybrid_replay:changed_agent",
        expectation={"decision": "approve", "item": "A"},
        trajectory_expectation={"called": ["lookup"], "not_called": ["charge_card"]},
        mode="hybrid",
        live_llms={"fake/model"},
    ) == {"decision": "approve", "item": "A"}

    source = generate_pytest_source(
        trace_path=path,
        output_path=tmp_path / "test_hybrid.py",
        entrypoint="test_hybrid_replay:changed_agent",
        expectation={"decision": "approve", "item": "A"},
        trajectory_expectation={"called": ["lookup"]},
        mode="hybrid",
        live_llms={"fake/model"},
        import_root=Path(__file__).parent,
    )
    compile(source, "<hybrid test>", "exec")
    assert "LIVE_LLMS = set(['fake/model'])" in source

    with (
        ReplaySession.from_trace(path) as frozen,
        pytest.raises(ReplayMismatchError, match="input diverged"),
    ):
        agent("new", live_answer="approve")
    assert frozen.pending == 2


def test_hybrid_rejects_new_tool_before_side_effect(tmp_path: Path) -> None:
    path = tmp_path / "run.sftrace"
    with record("agent", output=path):
        agent("old")
    TOOL_BODIES.clear()
    with ReplaySession.from_trace(
        path, mode="hybrid", live_llms={"fake/model"}
    ) as replay:
        llm_request(
            provider="fake",
            model="model",
            input={"prompt": "new"},
            call=lambda: {"decision": "approve"},
        )
        with pytest.raises(ReplayMismatchError, match="expected tool"):
            charge_card("A")
    assert TOOL_BODIES == []
    assert replay.pending == 1


def test_hybrid_requires_explicit_llm_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "run.sftrace"
    with record("agent", output=path):
        agent("old")
    with pytest.raises(ValueError, match="requires explicit live_llms"):
        ReplaySession.from_trace(path, mode="hybrid")
    with pytest.raises(ValueError, match="only valid"):
        ReplaySession.from_trace(path, mode="frozen", live_llms={"fake/model"})
