import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import GAMEDATA_PATH
from orchestrator.match_log import append_snapshot, build_snapshot

from clasher.engine import BattleEngine
from clasher.arena import Position


def test_build_snapshot_includes_both_sides_in_full():
    engine = BattleEngine(data_file=str(GAMEDATA_PATH))
    battle = engine.create_battle()
    battle.deploy_card(0, "Knight", Position(9.0, 10.0))
    battle.deploy_card(1, "Giant", Position(9.0, 22.0))

    snapshot = build_snapshot(battle)

    cards = {e["card"] for e in snapshot["entities"]}
    assert "Knight" in cards
    assert "Giant" in cards
    assert len(snapshot["players"]) == 2


def test_append_snapshot_writes_one_json_line_per_call(tmp_path):
    log_path = tmp_path / "match.jsonl"
    append_snapshot(log_path, {"tick": 1})
    append_snapshot(log_path, {"tick": 2})

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["tick"] == 1
    assert json.loads(lines[1])["tick"] == 2
