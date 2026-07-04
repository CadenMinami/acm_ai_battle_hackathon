import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_clasher_package_is_importable_after_bootstrap():
    import orchestrator  # noqa: F401 (side effect: puts engine/src on sys.path)
    from clasher.battle import BattleState
    from clasher.engine import BattleEngine

    assert hasattr(BattleState, "step")
    assert hasattr(BattleEngine, "create_battle")
