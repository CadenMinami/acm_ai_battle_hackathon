import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import GAMEDATA_PATH
from orchestrator.match_log import append_snapshot, build_snapshot

from clasher.engine import BattleEngine
from clasher.arena import Position
from clasher.entities import Projectile, RollingProjectile, TimedExplosive


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
    assert all(e["max_hp"] > 0 for e in snapshot["entities"])


def test_build_snapshot_includes_projectiles_with_kind_and_target():
    engine = BattleEngine(data_file=str(GAMEDATA_PATH))
    battle = engine.create_battle()
    battle.deploy_card(0, "Knight", Position(9.0, 10.0))

    projectile = Projectile(
        id=battle.next_entity_id,
        position=Position(9.0, 16.0),
        player_id=0,
        card_stats=None,
        hitpoints=1,
        max_hitpoints=1,
        damage=50.0,
        range=0,
        sight_range=0,
        target_position=Position(9.0, 20.0),
        travel_speed=6.0,
        source_name="Musketeer",
    )
    battle.entities[projectile.id] = projectile
    battle.next_entity_id += 1

    snapshot = build_snapshot(battle)
    entities_by_card = {e["card"]: e for e in snapshot["entities"]}

    assert entities_by_card["Knight"]["kind"] == "unit"
    assert "target_x" not in entities_by_card["Knight"]

    assert entities_by_card["Musketeer"]["kind"] == "projectile"
    assert entities_by_card["Musketeer"]["target_x"] == 9.0
    assert entities_by_card["Musketeer"]["target_y"] == 20.0


def test_build_snapshot_targetless_projectiles_have_kind_but_no_target():
    engine = BattleEngine(data_file=str(GAMEDATA_PATH))
    battle = engine.create_battle()

    rolling = RollingProjectile(
        id=battle.next_entity_id,
        position=Position(9.0, 12.0),
        player_id=0,
        card_stats=None,
        hitpoints=1,
        max_hitpoints=1,
        damage=100.0,
        range=1.0,
        sight_range=0,
    )
    rolling.spell_name = "Log"
    battle.entities[rolling.id] = rolling
    battle.next_entity_id += 1

    explosive = TimedExplosive(
        id=battle.next_entity_id,
        position=Position(9.0, 14.0),
        player_id=1,
        card_stats=None,
        hitpoints=1,
        max_hitpoints=1,
        damage=0,
        range=0,
        sight_range=0,
    )
    battle.entities[explosive.id] = explosive
    battle.next_entity_id += 1

    snapshot = build_snapshot(battle)

    targetless_projectiles = [
        e
        for e in snapshot["entities"]
        if e["kind"] == "projectile" and e["card"] in ("Log", "Unknown")
    ]
    assert len(targetless_projectiles) >= 2
    for entity in targetless_projectiles:
        assert "target_x" not in entity
        assert "target_y" not in entity


def test_append_snapshot_writes_one_json_line_per_call(tmp_path):
    log_path = tmp_path / "match.jsonl"
    append_snapshot(log_path, {"tick": 1})
    append_snapshot(log_path, {"tick": 2})

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["tick"] == 1
    assert json.loads(lines[1])["tick"] == 2
