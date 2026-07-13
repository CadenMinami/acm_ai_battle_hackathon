"""Test double for bracket concurrency tests.

Command tuples encode (delay_seconds, should_raise, sentinel_path).
"""
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def fake_match_runner(
    agent_a_command: List[Any],
    agent_b_command: List[Any],
    seed: int,
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    delay_seconds, should_raise, sentinel_path = agent_a_command
    time.sleep(delay_seconds)
    if should_raise:
        raise OSError("simulated bad agent command")
    if sentinel_path:
        Path(sentinel_path).write_text("done")
    return {"winner": 0, "forfeited_by": None, "ticks": 1, "completed": True, "seed": seed}
