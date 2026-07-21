import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import GAMEDATA_PATH
from orchestrator.entity_view import is_projectile, iter_live_entities

from clasher.engine import BattleEngine
from clasher.arena import Position
from clasher.entities import Projectile


def _make_battle_with_projectile():
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
    return battle, projectile


def test_default_call_excludes_projectiles():
    battle, _ = _make_battle_with_projectile()

    cards = {card_name for _, card_name in iter_live_entities(battle)}

    assert "Knight" in cards
    assert "Musketeer" not in cards


def test_include_projectiles_true_yields_the_projectile():
    battle, projectile = _make_battle_with_projectile()

    results = list(iter_live_entities(battle, include_projectiles=True))
    entities_by_name = {card_name: entity for entity, card_name in results}

    assert "Knight" in entities_by_name
    assert "Musketeer" in entities_by_name
    assert entities_by_name["Musketeer"] is projectile


def test_is_projectile_true_for_projectile_false_for_troop():
    battle, projectile = _make_battle_with_projectile()
    knight = next(
        e for e in battle.entities.values()
        if getattr(e.card_stats, "name", None) == "Knight"
    )

    assert is_projectile(projectile) is True
    assert is_projectile(knight) is False
