from typing import Iterator, Tuple, Union

from clasher.battle import BattleState
from clasher.entities import Building, Projectile, RollingProjectile, TimedExplosive, Troop

TOWER_CARD_NAMES = {"Tower", "KingTower"}
PROJECTILE_TYPES = (Projectile, RollingProjectile, TimedExplosive)

EntityLike = Union[Troop, Building, Projectile, RollingProjectile, TimedExplosive]


def is_projectile(entity: EntityLike) -> bool:
    """True for in-flight/rolling attack effects (arrows, fireballs, Log, bombs).

    SpawnProjectile (Goblin Barrel) is a Projectile subclass, so it's
    already covered by this isinstance check without listing it separately.
    """
    return isinstance(entity, PROJECTILE_TYPES)


def _display_name(entity: EntityLike) -> str:
    card_name = getattr(entity.card_stats, "name", None)
    if card_name:
        return card_name
    # Projectile/SpawnProjectile carry a source_name field; RollingProjectile
    # gets spell_name bolted on after construction in spells.py (not a
    # dataclass field). Neither exists on every type, hence the fallback chain.
    return getattr(entity, "source_name", None) or getattr(entity, "spell_name", None) or "Unknown"


def iter_live_entities(
    battle: BattleState, include_projectiles: bool = False
) -> Iterator[Tuple[EntityLike, str]]:
    """Yield alive troops/buildings with their display names.

    `include_projectiles=True` also yields in-flight attack effects. This is
    opt-in because this function backs both the spectator log
    (match_log.py, wants projectiles) and the agent-facing fog-of-war
    payload (state_projection.py, must NOT gain visibility into
    projectiles agents were never meant to see).
    """
    allowed_types = (Troop, Building) + (PROJECTILE_TYPES if include_projectiles else ())
    for entity in battle.entities.values():
        if not entity.is_alive or not isinstance(entity, allowed_types):
            continue
        yield entity, _display_name(entity)
