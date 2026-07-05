import argparse
import contextlib
import json
import os
from pathlib import Path

from orchestrator.match import run_match


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one battle between two agent subprocesses.")
    parser.add_argument("--agent-a", required=True, help="Command to launch agent A, e.g. 'python3 agents/baseline_random/agent.py'")
    parser.add_argument("--agent-b", required=True, help="Command to launch agent B")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--deadline-seconds", type=float, default=0.1)
    parser.add_argument("--max-ticks", type=int, default=12000)
    parser.add_argument("--log-path", type=Path, default=None, help="If set, append a per-tick JSONL snapshot log here")
    args = parser.parse_args()

    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        result = run_match(
            agent_a_command=args.agent_a.split(),
            agent_b_command=args.agent_b.split(),
            seed=args.seed,
            deadline_seconds=args.deadline_seconds,
            max_ticks=args.max_ticks,
            log_path=args.log_path,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
