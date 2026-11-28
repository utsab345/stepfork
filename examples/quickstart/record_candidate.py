"""Record the deterministic fixed quickstart agent for baseline comparison."""

from __future__ import annotations

import argparse
from pathlib import Path

from examples.quickstart.agent import run_agent_fixed
from stepfork import record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with record("order-agent", output=args.output) as session:
        result = run_agent_fixed()
        session.set_output(result)
    print(f"Recorded candidate trace at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
