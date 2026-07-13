import json
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from orchestrator.match import run_match


def run_bracket(
    agents: List[Dict[str, Any]],
    seed: int,
    logs_dir: Path,
    results_path: Path,
    match_runner: Callable[..., Dict[str, Any]] = run_match,
    max_workers: Optional[int] = None,
) -> Dict[str, Any]:
    """Run a single-elimination, best-of-1 bracket over `agents` (each
    `{"name": str, "command": list[str]}`). Matchups within a round run
    concurrently in separate OS processes, capped by CPU count by
    default; rounds are sequential because each round needs the previous
    round's winners. An odd number of agents remaining in a round gives
    the last one a bye. A drawn match (`winner` is None) advances the
    first-listed agent by convention — a real tournament would need an
    explicit tiebreak rule; this is a known thin-slice limitation, not a
    hidden bug."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    rounds: List[List[Dict[str, Any]]] = []
    remaining = list(agents)
    round_num = 1

    # Spawn avoids inheriting caller state from live threads or global RNG use.
    with ProcessPoolExecutor(
        max_workers=max_workers or os.cpu_count() or 1,
        mp_context=multiprocessing.get_context("spawn"),
    ) as executor:
        while len(remaining) > 1:
            this_round: List[Dict[str, Any]] = []
            next_remaining: List[Dict[str, Any]] = []
            matchups: List[Dict[str, Any]] = []

            for i in range(0, len(remaining) - 1, 2):
                agent_a, agent_b = remaining[i], remaining[i + 1]
                log_path = logs_dir / f"round{round_num}_match{i // 2 + 1}.jsonl"
                future = executor.submit(
                    match_runner,
                    agent_a["command"],
                    agent_b["command"],
                    seed=seed,
                    log_path=log_path,
                )
                matchups.append({
                    "agent_a": agent_a,
                    "agent_b": agent_b,
                    "log_path": log_path,
                    "future": future,
                })

            for matchup in matchups:
                agent_a = matchup["agent_a"]
                agent_b = matchup["agent_b"]
                log_path = matchup["log_path"]
                result = matchup["future"].result()
                winner = agent_b if result["winner"] == 1 else agent_a
                this_round.append({
                    "a": agent_a["name"],
                    "b": agent_b["name"],
                    "winner": winner["name"],
                    "log": str(log_path),
                })
                next_remaining.append(winner)

            if len(remaining) % 2 == 1:
                bye_agent = remaining[-1]
                this_round.append({"a": bye_agent["name"], "b": None, "winner": bye_agent["name"], "log": None})
                next_remaining.append(bye_agent)

            rounds.append(this_round)
            remaining = next_remaining
            round_num += 1

    results = {"rounds": rounds}
    results_path.write_text(json.dumps(results, indent=2))
    return results
