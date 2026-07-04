import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "baseline_random"))

from agent import choose_action


def test_no_action_when_hand_empty():
    state = {"request_id": 1, "hand": [], "elixir": 10.0}
    action = choose_action(state, player_id=0)
    assert action == {"request_id": 1, "action": "none"}


def test_no_action_when_elixir_too_low():
    state = {"request_id": 2, "hand": ["Knight"], "elixir": 0.5}
    action = choose_action(state, player_id=0)
    assert action == {"request_id": 2, "action": "none"}


def test_deploys_on_own_half_for_player_0():
    state = {"request_id": 3, "hand": ["Knight"], "elixir": 5.0}
    action = choose_action(state, player_id=0)
    assert action["action"] == "deploy"
    assert action["card"] == "Knight"
    assert 2.0 <= action["y"] <= 13.0


def test_deploys_on_own_half_for_player_1():
    state = {"request_id": 4, "hand": ["Knight"], "elixir": 5.0}
    action = choose_action(state, player_id=1)
    assert action["action"] == "deploy"
    assert action["card"] == "Knight"
    assert 18.0 <= action["y"] <= 29.0
