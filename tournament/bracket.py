import json
from pathlib import Path
from typing import Any, Dict, List

from orchestrator.match import run_match


def run_bracket(
    agents: List[Dict[str, Any]],
    seed: int,
    logs_dir: Path,
    results_path: Path,
) -> Dict[str, Any]:
    """Run a single-elimination, best-of-1 bracket over `agents` (each
    `{"name": str, "command": list[str]}`). An odd number of agents
    remaining in a round gives the last one a bye. A drawn match
    (`winner` is None) advances the first-listed agent by convention —
    a real tournament would need an explicit tiebreak rule; this is a
    known thin-slice limitation, not a hidden bug."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    rounds: List[List[Dict[str, Any]]] = []
    remaining = list(agents)
    round_num = 1

    while len(remaining) > 1:
        this_round: List[Dict[str, Any]] = []
        next_remaining: List[Dict[str, Any]] = []

        for i in range(0, len(remaining) - 1, 2):
            agent_a, agent_b = remaining[i], remaining[i + 1]
            log_path = logs_dir / f"round{round_num}_match{i // 2 + 1}.jsonl"
            result = run_match(
                agent_a["command"],
                agent_b["command"],
                seed=seed,
                log_path=log_path,
            )
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
