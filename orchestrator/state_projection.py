from typing import Any, Dict

from clasher.battle import BattleState
from clasher.entities import Building, Troop

_TOWER_CARD_NAMES = {"Tower", "KingTower"}


def project_state(battle: BattleState, player_id: int, request_id: int) -> Dict[str, Any]:
    """Build the fog-of-war-filtered payload sent to one player's agent.

    Only the receiving player's own hand/cycle are included; the
    opponent's hand and cycle queue never appear anywhere in the result.
    """
    enemy_id = 1 - player_id
    player = battle.players[player_id]
    enemy = battle.players[enemy_id]

    own_troops = []
    enemy_troops = []
    for entity in battle.entities.values():
        if not entity.is_alive or not isinstance(entity, (Troop, Building)):
            continue
        card_name = getattr(entity.card_stats, "name", "Unknown")
        if card_name in _TOWER_CARD_NAMES:
            continue
        troop_info = {
            "card": card_name,
            "x": entity.position.x,
            "y": entity.position.y,
            "hp": entity.hitpoints,
        }
        if entity.player_id == player_id:
            own_troops.append(troop_info)
        else:
            enemy_troops.append(troop_info)

    return {
        "request_id": request_id,
        "tick": battle.tick,
        "elixir": player.elixir,
        "hand": list(player.hand),
        "next_card": player.get_next_card(),
        "own_troops": own_troops,
        "enemy_troops": enemy_troops,
        "towers": {
            "own": {
                "king": player.king_tower_hp,
                "left": player.left_tower_hp,
                "right": player.right_tower_hp,
            },
            "enemy": {
                "king": enemy.king_tower_hp,
                "left": enemy.left_tower_hp,
                "right": enemy.right_tower_hp,
            },
        },
    }
