import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tournament.bracket import run_bracket

BASELINE = [sys.executable, str(Path(__file__).resolve().parent.parent / "agents" / "baseline_random" / "agent.py")]


def test_run_bracket_with_four_agents_produces_two_rounds(tmp_path):
    agents = [{"name": f"agent{i}", "command": BASELINE} for i in range(4)]

    results = run_bracket(
        agents,
        seed=7,
        logs_dir=tmp_path / "logs",
        results_path=tmp_path / "results.json",
    )

    assert len(results["rounds"]) == 2
    assert len(results["rounds"][0]) == 2
    assert len(results["rounds"][1]) == 1
    final_winner = results["rounds"][1][0]["winner"]
    assert final_winner in {a["name"] for a in agents}
    assert (tmp_path / "results.json").exists()


def test_run_bracket_gives_bye_to_odd_agent_out(tmp_path):
    agents = [{"name": f"agent{i}", "command": BASELINE} for i in range(3)]

    results = run_bracket(
        agents,
        seed=7,
        logs_dir=tmp_path / "logs",
        results_path=tmp_path / "results.json",
    )

    assert results["rounds"][0][-1]["b"] is None
    assert results["rounds"][0][-1]["winner"] == "agent2"
