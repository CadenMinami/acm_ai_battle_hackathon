from typing import Iterator, Tuple, Union

from clasher.battle import BattleState
from clasher.entities import Building, Troop

TOWER_CARD_NAMES = {"Tower", "KingTower"}


def iter_live_entities(battle: BattleState) -> Iterator[Tuple[Union[Troop, Building], str]]:
    """Yield alive troops/buildings with their card names."""
    for entity in battle.entities.values():
        if not entity.is_alive or not isinstance(entity, (Troop, Building)):
            continue
        card_name = getattr(entity.card_stats, "name", "Unknown")
        yield entity, card_name
