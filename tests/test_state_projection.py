import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import GAMEDATA_PATH
from orchestrator.state_projection import project_state

from clasher.engine import BattleEngine
from clasher.arena import Position


def _make_battle():
    engine = BattleEngine(data_file=str(GAMEDATA_PATH))
    battle = engine.create_battle()
    battle.deploy_card(0, "Knight", Position(9.0, 10.0))
    battle.deploy_card(1, "Giant", Position(9.0, 22.0))
    return battle


def test_project_state_never_leaks_enemy_hand():
    battle = _make_battle()
    payload = project_state(battle, player_id=0, request_id=1)

    assert "enemy_hand" not in payload
    assert payload["hand"] == list(battle.players[0].hand)
    assert all("hand" not in troop for troop in payload["enemy_troops"])


def test_project_state_shows_deployed_troops_on_each_side():
    battle = _make_battle()
    payload = project_state(battle, player_id=0, request_id=2)

    own_cards = {t["card"] for t in payload["own_troops"]}
    enemy_cards = {t["card"] for t in payload["enemy_troops"]}
    assert "Knight" in own_cards
    assert "Giant" in enemy_cards
    assert "Knight" not in enemy_cards
