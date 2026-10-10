"""Run the offline LangGraph prompt-decision demonstration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = Path(__file__).resolve().parent
ARTIFACTS = EXAMPLE / ".artifacts"
TRACE = ARTIFACTS / "refund_failure.sftrace"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.model_decision import agent  # noqa: E402
from stepfork import ReplaySession, record  # noqa: E402
from stepfork.assertions import assert_tool_sequence  # noqa: E402
from stepfork.export.generator import export_pytest_test  # noqa: E402
from stepfork.replay import ReplayMismatchError  # noqa: E402


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    agent.MODEL_CALLS.clear()
    agent.TOOL_CALLS.clear()
    with record("refund-decision", output=TRACE, overwrite=True) as session:
        failure = agent.run_buggy()
        session.set_output(failure)
    assert failure == {"approved": False}
    print(f"Recorded model decision: {failure}")

    agent.MODEL_CALLS.clear()
    agent.TOOL_CALLS.clear()
    with ReplaySession.from_trace(TRACE) as replay:
        frozen = agent.run_buggy()
        replay.verify_complete()
    assert frozen == failure
    assert not agent.MODEL_CALLS and not agent.TOOL_CALLS
    print("Frozen replay repeated the failure; model/tool bodies ran 0 times")

    try:
        with ReplaySession.from_trace(TRACE):
            agent.run_fixed()
    except ReplayMismatchError:
        print("Frozen replay rejected the changed prompt")
    else:
        raise AssertionError("frozen replay accepted a changed prompt")

    agent.MODEL_CALLS.clear()
    agent.TOOL_CALLS.clear()
    with ReplaySession.from_trace(
        TRACE, mode="hybrid", live_llms={agent.MODEL_LABEL}
    ) as replay:
        corrected = agent.run_fixed()
        replay.verify_complete()
    assert corrected == {"approved": True}
    assert len(agent.MODEL_CALLS) == 3
    assert agent.TOOL_CALLS == []
    assert_tool_sequence(replay, ["lookup_customer", "get_refund_policy"])
    print(
        f"Hybrid fake-provider decision: {corrected}; "
        "live model calls: 3; live tools: 0"
    )

    expectations = {
        "called": ["lookup_customer", "get_refund_policy"],
        "not_called": ["charge_card"],
        "sequence": ["lookup_customer", "get_refund_policy"],
        "max_steps": 5,
    }
    for variant in ("buggy", "fixed"):
        destination = ARTIFACTS / f"test_refund_{variant}.py"
        export_pytest_test(
            trace_path=TRACE,
            output_path=destination,
            entrypoint=f"examples.model_decision.agent:run_{variant}",
            expectation={"approved": True},
            trajectory_expectation=expectations,
            mode="hybrid",
            live_llms={agent.MODEL_LABEL},
            import_root=ROOT,
            overwrite=True,
        )
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(destination)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        expected_code = 1 if variant == "buggy" else 0
        if result.returncode != expected_code:
            print(result.stdout)
            print(result.stderr)
            raise AssertionError(
                f"{variant} generated test exited {result.returncode}, "
                f"expected {expected_code}"
            )
        outcome = "FAIL" if variant == "buggy" else "PASS"
        print(f"Exported {variant} pytest test: {outcome}")
    print("Offline fake-provider demonstration complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
