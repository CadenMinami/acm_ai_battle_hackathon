import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

from fake_match_runner import fake_match_runner
from tournament.bracket import run_bracket

BASELINE = [sys.executable, str(Path(__file__).resolve().parent.parent / "agents" / "baseline_random" / "agent.py")]


def test_matchups_in_a_round_run_concurrently(tmp_path):
    agents = [{"name": f"agent{i}", "command": (0.4, False, None)} for i in range(8)]

    start = time.monotonic()
    results = run_bracket(
        agents,
        seed=7,
        logs_dir=tmp_path / "logs",
        results_path=tmp_path / "results.json",
        match_runner=fake_match_runner,
        max_workers=4,
    )
    elapsed = time.monotonic() - start

    assert 1.0 < elapsed < 2.5
    assert len(results["rounds"]) == 3
    assert len(results["rounds"][0]) == 4
    assert len(results["rounds"][1]) == 2
    assert len(results["rounds"][2]) == 1


def test_round_results_preserve_submission_order_not_completion_order(tmp_path):
    agents = [
        {"name": "agent0", "command": (0.5, False, None)},
        {"name": "agent1", "command": (0.05, False, None)},
        {"name": "agent2", "command": (0.05, False, None)},
        {"name": "agent3", "command": (0.05, False, None)},
    ]

    results = run_bracket(
        agents,
        seed=7,
        logs_dir=tmp_path / "logs",
        results_path=tmp_path / "results.json",
        match_runner=fake_match_runner,
        max_workers=2,
    )

    assert results["rounds"][0][0]["a"] == "agent0"
    assert results["rounds"][0][1]["a"] == "agent2"


def test_bad_agent_command_propagates_and_sibling_still_completes(tmp_path):
    sentinel_path = tmp_path / "sibling_done.txt"
    results_path = tmp_path / "results.json"
    agents = [
        {"name": "agent0", "command": (0.05, True, None)},
        {"name": "agent1", "command": (0.05, False, None)},
        {"name": "agent2", "command": (0.3, False, str(sentinel_path))},
        {"name": "agent3", "command": (0.05, False, None)},
    ]

    with pytest.raises(OSError):
        run_bracket(
            agents,
            seed=7,
            logs_dir=tmp_path / "logs",
            results_path=results_path,
            match_runner=fake_match_runner,
            max_workers=2,
        )

    assert sentinel_path.exists()
    assert not results_path.exists()


def test_real_agents_run_through_the_parallel_path(tmp_path):
    agents = [{"name": f"agent{i}", "command": BASELINE} for i in range(8)]
    results_path = tmp_path / "results.json"

    results = run_bracket(
        agents,
        seed=7,
        logs_dir=tmp_path / "logs",
        results_path=results_path,
    )

    assert len(results["rounds"]) == 3
    assert len(results["rounds"][0]) == 4
    assert len(results["rounds"][1]) == 2
    assert len(results["rounds"][2]) == 1
    assert results["rounds"][2][0]["winner"] in {a["name"] for a in agents}
    for round_results in results["rounds"]:
        for matchup in round_results:
            if matchup["b"] is not None:
                log_path = Path(matchup["log"])
                assert log_path.exists()
                assert log_path.stat().st_size > 0
    assert results_path.exists()
