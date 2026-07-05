import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.match import run_match

FIXTURE = [sys.executable, str(Path(__file__).resolve().parent / "fixtures" / "fixture_agent.py")]
BASELINE = [sys.executable, str(Path(__file__).resolve().parent.parent / "agents" / "baseline_random" / "agent.py")]


def test_forfeit_after_five_consecutive_misses():
    result = run_match(
        agent_a_command=FIXTURE + ["echo"],
        agent_b_command=FIXTURE + ["sleep"],
        seed=1,
        deadline_seconds=0.05,
        max_ticks=200,
        startup_grace_seconds=0.0,
    )
    assert result["forfeited_by"] == 1
    assert result["winner"] == 0


def test_bad_deploy_coordinates_are_noop_not_forfeit():
    result = run_match(
        agent_a_command=FIXTURE + ["echo"],
        agent_b_command=FIXTURE + ["baddeploy"],
        seed=1,
        deadline_seconds=1.0,
        max_ticks=200,
        startup_grace_seconds=0.0,
    )
    assert isinstance(result, dict)
    assert result["forfeited_by"] is None


def test_full_match_between_baseline_agents_reaches_conclusion(tmp_path):
    log_path = tmp_path / "match.jsonl"
    result = run_match(
        agent_a_command=BASELINE,
        agent_b_command=BASELINE,
        seed=42,
        log_path=log_path,
    )
    assert result["completed"] is True
    assert result["forfeited_by"] is None
    assert result["winner"] in (0, 1, None)
    assert log_path.exists()
    assert len(log_path.read_text().strip().split("\n")) == result["ticks"]
