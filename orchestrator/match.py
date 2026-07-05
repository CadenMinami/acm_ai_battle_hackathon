import contextlib
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator import GAMEDATA_PATH
from orchestrator.agent_process import AgentProcess
from orchestrator.match_log import append_snapshot, build_snapshot
from orchestrator.state_projection import project_state

from clasher.engine import BattleEngine
from clasher.arena import Position

POLL_EVERY_N_TICKS = 5
MAX_CONSECUTIVE_MISSES = 5
DEFAULT_DEADLINE_SECONDS = 0.1
DEFAULT_STARTUP_GRACE_SECONDS = 2.0
# tiebreaker_time in the engine is 360.0s at 0.033s/tick (~10,909 ticks);
# BattleEngine.run_battle()'s own default of 9090 cuts off before that
# point resolves, so this orchestrator drives step() itself with a
# max_ticks set comfortably past the tiebreaker.
DEFAULT_MAX_TICKS = 12000


def run_match(
    agent_a_command: List[str],
    agent_b_command: List[str],
    seed: int,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    max_ticks: int = DEFAULT_MAX_TICKS,
    startup_grace_seconds: float = DEFAULT_STARTUP_GRACE_SECONDS,
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        random.seed(seed)

        engine = BattleEngine(data_file=str(GAMEDATA_PATH))
        battle = engine.create_battle()

        agents: List[AgentProcess] = []
        miss_counts = [0, 0]
        forfeited_by: Optional[int] = None
        request_id = 0

        try:
            if log_path is not None:
                log_path.unlink(missing_ok=True)

            agents.append(AgentProcess(agent_a_command + [str(0)]))
            agents.append(AgentProcess(agent_b_command + [str(1)]))
            start_time = time.monotonic()

            for _tick in range(1, max_ticks + 1):
                battle.step()

                if log_path is not None:
                    append_snapshot(log_path, build_snapshot(battle))

                if battle.tick % POLL_EVERY_N_TICKS == 0:
                    request_id += 1
                    grace_active = (time.monotonic() - start_time) < startup_grace_seconds
                    payloads = [project_state(battle, player_id, request_id) for player_id in (0, 1)]

                    # Send both requests before collecting either response, so
                    # both agents' deadline windows open at the same moment and
                    # neither decision can be influenced by the other's.
                    sent = [
                        agents[player_id].send_request(payloads[player_id])
                        for player_id in (0, 1)
                    ]
                    deadline = time.monotonic() + deadline_seconds
                    responses = [
                        agents[player_id].await_response(request_id, deadline) if sent[player_id] else None
                        for player_id in (0, 1)
                    ]

                    for player_id, response in enumerate(responses):
                        if response is None:
                            if not grace_active:
                                miss_counts[player_id] += 1
                                if miss_counts[player_id] >= MAX_CONSECUTIVE_MISSES:
                                    forfeited_by = player_id
                            continue

                        # Any well-formed, on-time response — a deploy OR an
                        # explicit "none" — is a successful poll and resets the
                        # consecutive-miss count. Declining to act is a legal
                        # play, not a miss.
                        miss_counts[player_id] = 0
                        if response.get("action") != "deploy":
                            continue
                        card = response.get("card")
                        x = response.get("x")
                        y = response.get("y")
                        if card is not None and x is not None and y is not None:
                            try:
                                battle.deploy_card(player_id, card, Position(float(x), float(y)))
                            except (TypeError, ValueError):
                                pass

                    if forfeited_by is not None:
                        break

                if battle.game_over:
                    break

            completed = battle.game_over or forfeited_by is not None
            winner = (1 - forfeited_by) if forfeited_by is not None else battle.winner

            return {
                "winner": winner,
                "forfeited_by": forfeited_by,
                "ticks": battle.tick,
                "completed": completed,
                "seed": seed,
            }
        finally:
            for agent in agents:
                agent.close()
