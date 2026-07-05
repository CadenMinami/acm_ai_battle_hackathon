import json
from pathlib import Path
from typing import Any, Dict

from clasher.battle import BattleState

from orchestrator.entity_view import TOWER_CARD_NAMES, iter_live_entities


def build_snapshot(battle: BattleState) -> Dict[str, Any]:
    """Build one spectator-facing snapshot of the battle. Unlike
    project_state, this has no fog-of-war restriction: it's written to a
    log for a human to watch after the fact, not sent to a competing
    agent, so both sides are shown in full."""
    entities = []
    for entity, card_name in iter_live_entities(battle):
        entities.append({
            "card": card_name,
            "x": entity.position.x,
            "y": entity.position.y,
            "hp": entity.hitpoints,
            "player_id": entity.player_id,
            "is_tower": card_name in TOWER_CARD_NAMES,
        })

    return {
        "tick": battle.tick,
        "entities": entities,
        "players": [
            {
                "elixir": p.elixir,
                "king_hp": p.king_tower_hp,
                "left_hp": p.left_tower_hp,
                "right_hp": p.right_tower_hp,
            }
            for p in battle.players
        ],
        "game_over": battle.game_over,
        "winner": battle.winner,
    }


def append_snapshot(log_path: Path, snapshot: Dict[str, Any]) -> None:
    with open(log_path, "a") as f:
        f.write(json.dumps(snapshot) + "\n")
