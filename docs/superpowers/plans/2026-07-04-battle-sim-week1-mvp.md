# Battle Sim Week 1 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a thin, working slice of all 5 project phases within one week (engine + fair protocol + orchestrator + baseline agent; Docker sandboxing + match logging; a live/replay web viewer; a tournament bracket + leaderboard; a small dry run tying it together) so the project can hand off to other team members for hardening, rather than a deep Phase 1 followed by 7 more weeks of Caden's own time on Phases 2-5.

**Architecture:** A vendored copy of `samdickson22/clash-simulator` lives in `engine/`. An `orchestrator` package drives the engine's own tick loop directly (not its `run_battle()` helper, which has a tick-count bug — see Task 1), polls two agent subprocesses over stdin/stdout every 5 ticks using a background-thread-plus-queue timeout mechanism, applies legal actions via the engine's own `deploy_card`, and optionally logs a per-tick spectator snapshot to JSONL. Agent subprocesses are launched via an opaque command list, so wrapping them in `docker run` (Task 9) requires no changes to the orchestrator itself. A small FastAPI app polls those same JSONL logs to drive one shared canvas renderer for both a live view and a scrubbable replay (Task 10). A tournament bracket runner (Task 11) reuses `run_match` directly, and a flat leaderboard page (Task 12) ties bracket results back to the replay viewer.

**Tech Stack:** Python 3.11 (engine requires >=3.10), stdlib only for the core orchestrator (`subprocess`, `threading`, `queue`, `json`, `argparse`), `pytest` for tests, `fastapi`+`uvicorn` for the web viewer, plain HTML/JS/`<canvas>` for the frontend (no build step), Docker for agent sandboxing.

## Global Constraints

- Vendor the engine as plain copied files, not a git submodule (spec section 3) — no double-commit bookkeeping on a solo timeline.
- Import the vendored engine via `sys.path` manipulation, not an editable `pip install -e`, matching the upstream project's own `sys.path.append('src')` pattern seen in its `random_battle.py` — the vendored `pyproject.toml` has no `[tool.setuptools.packages.find]` section, so an editable install is unverified territory.
- No `numba`, `msgspec`, or `pygame` install needed — confirmed via GitHub code search that neither is imported anywhere in `src/clasher` or `tests/`, only listed in `pyproject.toml`/`requirements.txt`. Only `pytest` (plus `fastapi`/`uvicorn` from Task 10 onward) is required.
- The orchestrator must drive `battle.step()` itself in its own loop, never call `BattleEngine.run_battle()` — its default `max_ticks=9090` (~300s) cuts off before `BattleState.tiebreaker_time=360.0`s, so a match tied into sudden death could end with `game_over` still `False`. Use `max_ticks=12000` (~396s) instead.
- Deadlines (`deadline_seconds`) and the startup grace period (`startup_grace_seconds`) must be parameters, never hardcoded constants — tests need tiny values (e.g. `0.05`, `0.0`) to stay fast and deterministic regardless of host machine speed.
- Measure deadlines with `time.monotonic()`, never `time.time()`.
- Every request the orchestrator sends carries a `request_id`; a response is only accepted if its `request_id` matches the outstanding request, so a late/stale response from a prior tick is dropped instead of misapplied.
- An explicit, on-time `{"action": "none"}` response is a successful poll that resets the consecutive-miss counter — declining to act is a legal play. Only a missing/late/malformed response (or dead process) counts as a miss.
- Both agents' responses are collected against one shared absolute deadline opened after both requests are sent (`AgentProcess.send_request` then `await_response`), so neither player's deadline window depends on how long the other took.
- The opponent's `hand`, `deck`, and `cycle_queue` must never appear anywhere in a state payload sent to an agent — only currently-visible troops/buildings and tower HP. This restriction does **not** apply to the spectator log (Task 8) or web viewer (Task 10) — those show both sides in full, on purpose, since they're for humans watching after the fact, not competing agents.
- Every player-facing agent subprocess (baseline or student-submitted) is spawned with its assigned player ID (`0` or `1`) appended as a single CLI argument — this is the wire convention for orientation, since the JSON payload itself is player-relative and doesn't restate which side is "home."
- Docker sandboxing (Task 9) requires no changes to `AgentProcess` or `run_match` — both already treat the agent launch command as an opaque `list[str]`; wrapping it in `docker run` is purely a different command list constructed by the caller.
- This week's tournament bracket (Task 11) is best-of-1 and gives a bye to an odd agent out; best-of-3 series and full 32-agent scale are explicitly deferred to the handoff team (spec section 12).
- The web viewer (Task 10) uses HTTP polling, not a WebSocket push, and plain JS instead of React — a deliberate, flagged time-boxed tradeoff (spec section 9), not an oversight.

---

### Task 1: Fork and vendor the clash-simulator engine

**Files:**
- Create: `engine/src/clasher/` (copied from the fork)
- Create: `engine/gamedata.json`, `engine/hitboxes.json`
- Create: `engine/tests/` (copied from the fork)
- Create: `engine/pyproject.toml`
- Create: `.venv/` (local virtualenv, not committed)

**Interfaces:**
- Produces: an importable `clasher` package at `engine/src/clasher`, used by every later task via the `orchestrator` package's `sys.path` bootstrap (Task 2).

This task has no new application code to TDD — it vendors an existing, already-tested engine. Verification is running its existing test suite against the vendored copy, not writing new tests.

- [ ] **Step 1: Fork the engine repo**

This creates a new public repository under your GitHub account — confirm before running.

Run: `gh repo fork samdickson22/clash-simulator --clone=false`
Expected: output confirming `CadenMinami/clash-simulator` created as a fork.

- [ ] **Step 2: Clone the fork to a scratch location**

Run:
```bash
git clone https://github.com/CadenMinami/clash-simulator.git /tmp/clash-simulator-fork
```
Expected: clone completes with no errors.

- [ ] **Step 3: Copy the runtime engine and its tests into `engine/`**

Run (from the repo root, `acm_ai_battle_hackathon/`):
```bash
mkdir -p engine
cp -r /tmp/clash-simulator-fork/src engine/src
cp /tmp/clash-simulator-fork/gamedata.json engine/gamedata.json
cp /tmp/clash-simulator-fork/hitboxes.json engine/hitboxes.json
cp -r /tmp/clash-simulator-fork/tests engine/tests
cp /tmp/clash-simulator-fork/pyproject.toml engine/pyproject.toml
```
Expected: `engine/src/clasher/`, `engine/gamedata.json`, `engine/hitboxes.json`, `engine/tests/`, and `engine/pyproject.toml` all exist.

- [ ] **Step 4: Create a virtualenv and install the only dependency the engine's tests actually need**

Run:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install pytest
```
Expected: `pytest` installs with no errors.

- [ ] **Step 5: Run the vendored engine's own test suite**

Run:
```bash
cd engine && python3 -m pytest tests/ -v && cd ..
```
Expected: every test passes, zero failures. If any test fails, stop and investigate before proceeding — later tasks assume this engine is correct as-is.

- [ ] **Step 6: Commit**

```bash
git add engine/
git commit -m "Vendor clash-simulator engine from fork"
```

---

### Task 2: Scaffold the orchestrator package and verify the engine import path

**Files:**
- Create: `orchestrator/__init__.py`
- Test: `tests/test_engine_import.py`

**Interfaces:**
- Consumes: `engine/src/clasher` (Task 1).
- Produces: `orchestrator.REPO_ROOT` (`pathlib.Path`), `orchestrator.ENGINE_SRC` (`pathlib.Path`), `orchestrator.GAMEDATA_PATH` (`pathlib.Path`) — every later task that needs to `import clasher...` relies on importing the `orchestrator` package first, which inserts `ENGINE_SRC` onto `sys.path` as an import-time side effect.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_import.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_clasher_package_is_importable_after_bootstrap():
    import orchestrator  # noqa: F401 (side effect: puts engine/src on sys.path)
    from clasher.battle import BattleState
    from clasher.engine import BattleEngine

    assert hasattr(BattleState, "step")
    assert hasattr(BattleEngine, "create_battle")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_engine_import.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator'`

- [ ] **Step 3: Write the bootstrap**

```python
# orchestrator/__init__.py
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_SRC = REPO_ROOT / "engine" / "src"
GAMEDATA_PATH = REPO_ROOT / "engine" / "gamedata.json"

if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_engine_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/__init__.py tests/test_engine_import.py
git commit -m "Add orchestrator package with engine import bootstrap"
```

---

### Task 3: Build the fog-of-war state projector

**Files:**
- Create: `orchestrator/state_projection.py`
- Test: `tests/test_state_projection.py`

**Interfaces:**
- Consumes: `clasher.battle.BattleState`, `clasher.entities.Troop`/`Building` (Task 1); `orchestrator.GAMEDATA_PATH` (Task 2).
- Produces: `project_state(battle: BattleState, player_id: int, request_id: int) -> dict`, used by `orchestrator/match.py` (Task 6).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state_projection.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import GAMEDATA_PATH
from orchestrator.state_projection import project_state

from clasher.engine import BattleEngine
from clasher.arena import Position


def _make_battle():
    engine = BattleEngine(data_file=str(GAMEDATA_PATH))
    battle = engine.create_battle()
    battle.deploy_card(0, "Knight", Position(9.0, 10.0))
    battle.deploy_card(1, "Giant", Position(9.0, 22.0))
    return battle


def test_project_state_never_leaks_enemy_hand():
    battle = _make_battle()
    payload = project_state(battle, player_id=0, request_id=1)

    assert "enemy_hand" not in payload
    assert payload["hand"] == list(battle.players[0].hand)
    assert all("hand" not in troop for troop in payload["enemy_troops"])


def test_project_state_shows_deployed_troops_on_each_side():
    battle = _make_battle()
    payload = project_state(battle, player_id=0, request_id=2)

    own_cards = {t["card"] for t in payload["own_troops"]}
    enemy_cards = {t["card"] for t in payload["enemy_troops"]}
    assert "Knight" in own_cards
    assert "Giant" in enemy_cards
    assert "Knight" not in enemy_cards
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_projection.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.state_projection'`

- [ ] **Step 3: Write the implementation**

```python
# orchestrator/state_projection.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_state_projection.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/state_projection.py tests/test_state_projection.py
git commit -m "Add fog-of-war state projector"
```

---

### Task 4: Build the baseline random-legal-move agent

**Files:**
- Create: `agents/baseline_random/agent.py`
- Test: `tests/test_baseline_agent.py`

**Interfaces:**
- Consumes: nothing from the engine or orchestrator packages — deliberately self-contained, since real student agents will eventually run isolated in a container with no access to orchestrator internals.
- Produces: a subprocess entry point invoked as `python3 agents/baseline_random/agent.py <player_id>`, consumed by Task 6's end-to-end test and the Task 7 CLI.

- [ ] **Step 1: Write the failing test**

This test drives `choose_action` directly (no subprocess) to keep it fast.

```python
# tests/test_baseline_agent.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "baseline_random"))

from agent import choose_action


def test_no_action_when_hand_empty():
    state = {"request_id": 1, "hand": [], "elixir": 10.0}
    action = choose_action(state, player_id=0)
    assert action == {"request_id": 1, "action": "none"}


def test_no_action_when_elixir_too_low():
    state = {"request_id": 2, "hand": ["Knight"], "elixir": 0.5}
    action = choose_action(state, player_id=0)
    assert action == {"request_id": 2, "action": "none"}


def test_deploys_on_own_half_for_player_0():
    state = {"request_id": 3, "hand": ["Knight"], "elixir": 5.0}
    action = choose_action(state, player_id=0)
    assert action["action"] == "deploy"
    assert action["card"] == "Knight"
    assert 2.0 <= action["y"] <= 13.0


def test_deploys_on_own_half_for_player_1():
    state = {"request_id": 4, "hand": ["Knight"], "elixir": 5.0}
    action = choose_action(state, player_id=1)
    assert action["action"] == "deploy"
    assert 18.0 <= action["y"] <= 29.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_baseline_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent'`

- [ ] **Step 3: Write the implementation**

```python
# agents/baseline_random/agent.py
#!/usr/bin/env python3
"""Reference agent: deploys a random card from hand at a random position
within a generous bounding box on the agent's own side of the arena, once
elixir clears a low floor. It relies on the orchestrator/engine's own
legality check (deploy_card) to silently reject anything it can't
actually afford or place yet, rather than tracking exact card costs or
occupied tiles itself.

Deliberately self-contained: it does not import the `clasher` engine
package, since real student agents will eventually run isolated in a
container with no access to orchestrator internals — only the JSON
state arriving over stdin.
"""
import json
import random
import sys

OWN_HALF_Y_RANGES = {
    0: (2.0, 13.0),   # bottom/blue player's side, clear of the river and king tower
    1: (18.0, 29.0),  # top/red player's side
}


def choose_action(state: dict, player_id: int) -> dict:
    hand = state.get("hand", [])
    elixir = state.get("elixir", 0.0)

    if not hand or elixir < 1.0:
        return {"request_id": state["request_id"], "action": "none"}

    card = random.choice(hand)
    y_min, y_max = OWN_HALF_Y_RANGES[player_id]
    x = round(random.uniform(1.0, 17.0), 1)
    y = round(random.uniform(y_min, y_max), 1)

    return {
        "request_id": state["request_id"],
        "action": "deploy",
        "card": card,
        "x": x,
        "y": y,
    }


def main() -> None:
    player_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        state = json.loads(line)
        action = choose_action(state, player_id)
        print(json.dumps(action), flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_baseline_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/baseline_random/agent.py tests/test_baseline_agent.py
git commit -m "Add baseline random-legal-move reference agent"
```

---

### Task 5: Build the agent subprocess wrapper (protocol, timeout, crash handling)

**Files:**
- Create: `orchestrator/agent_process.py`
- Create: `tests/fixtures/fixture_agent.py`
- Test: `tests/test_agent_process.py`

**Interfaces:**
- Produces: `AgentProcess(command: list[str])` with `.send_request(payload: dict) -> bool`, `.await_response(request_id, deadline: float) -> dict | None` (deadline is an absolute `time.monotonic()` value), a `.request(payload: dict, deadline_seconds: float) -> dict | None` convenience wrapper combining the two, and `.close() -> None`. Task 6's orchestrator uses the split send/await pair so both players share one deadline window; the tests here use `.request(...)`. A `None` return means timeout, a crashed process, or unparseable output — all three are indistinguishable to the caller by design (see Global Constraints).

- [ ] **Step 1: Write the controllable fixture agent**

```python
# tests/fixtures/fixture_agent.py
#!/usr/bin/env python3
"""Controllable test double for AgentProcess tests. Mode is picked via
argv[1]: 'echo' (well-behaved), 'sleep' (misses every deadline),
'garbage' (sends invalid JSON), 'crash' (exits immediately)."""
import json
import sys
import time


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "echo"

    if mode == "crash":
        sys.exit(1)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)

        if mode == "sleep":
            time.sleep(5.0)
        elif mode == "garbage":
            print("not json", flush=True)
            continue

        response = {"request_id": request["request_id"], "action": "none"}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_agent_process.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.agent_process import AgentProcess

FIXTURE = [sys.executable, str(Path(__file__).resolve().parent / "fixtures" / "fixture_agent.py")]


def test_normal_response_is_returned():
    agent = AgentProcess(FIXTURE + ["echo"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=1.0)
        assert response == {"request_id": 1, "action": "none"}
    finally:
        agent.close()


def test_slow_agent_times_out():
    agent = AgentProcess(FIXTURE + ["sleep"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=0.05)
        assert response is None
    finally:
        agent.close()


def test_garbage_output_is_treated_as_miss():
    agent = AgentProcess(FIXTURE + ["garbage"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=0.2)
        assert response is None
    finally:
        agent.close()


def test_crashed_process_is_treated_as_miss():
    agent = AgentProcess(FIXTURE + ["crash"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=0.2)
        assert response is None
    finally:
        agent.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_agent_process.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.agent_process'`

- [ ] **Step 4: Write the implementation**

```python
# orchestrator/agent_process.py
import json
import queue
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional


class AgentProcess:
    """Wraps one persistent agent subprocess: sends JSON-line requests,
    collects JSON-line responses on a background thread, and enforces a
    per-request wall-clock deadline measured with a monotonic clock."""

    def __init__(self, command: List[str]):
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._responses: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._responses.put(message)

    def send_request(self, payload: Dict[str, Any]) -> bool:
        """Write one request without waiting. Split from await_response
        so the orchestrator can open both players' deadline windows at
        the same moment: send to both agents first, then collect both."""
        if self._proc.poll() is not None or self._proc.stdin is None:
            return False
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def await_response(self, request_id: Any, deadline: float) -> Optional[Dict[str, Any]]:
        """Wait until `deadline` (an absolute time.monotonic() value) for
        the response matching request_id. Returns None on timeout, a dead
        process, or malformed output — all three are treated identically
        by the caller (a missed poll), so this method doesn't distinguish
        them. Uses max(0, remaining) rather than returning early on
        remaining <= 0, so a response that arrived in time but hasn't been
        drained from the queue yet is still accepted."""
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                message = self._responses.get(timeout=remaining)
            except queue.Empty:
                return None
            if message.get("request_id") == request_id:
                return message
            # Stale response from a prior tick — discard and keep waiting.

    def request(self, payload: Dict[str, Any], deadline_seconds: float) -> Optional[Dict[str, Any]]:
        """Convenience wrapper: send one request and wait up to
        deadline_seconds for its response."""
        if not self.send_request(payload):
            return None
        return self.await_response(payload.get("request_id"), time.monotonic() + deadline_seconds)

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_agent_process.py -v`
Expected: PASS (the `sleep`/`garbage`/`crash` cases each take up to their test's `deadline_seconds` to resolve, so this file takes a bit under a second total — that's expected, not a hang.)

- [ ] **Step 6: Commit**

```bash
git add orchestrator/agent_process.py tests/fixtures/fixture_agent.py tests/test_agent_process.py
git commit -m "Add agent subprocess wrapper with timeout and crash handling"
```

---

### Task 6: Build the match orchestrator (tick loop, forfeit accounting, end-to-end test)

**Files:**
- Create: `orchestrator/match.py`
- Test: `tests/test_match.py`

**Interfaces:**
- Consumes: `orchestrator.GAMEDATA_PATH` (Task 2), `project_state` (Task 3), `AgentProcess` (Task 5), `agents/baseline_random/agent.py` (Task 4), `clasher.engine.BattleEngine`, `clasher.arena.Position`.
- Produces: `run_match(agent_a_command: list[str], agent_b_command: list[str], seed: int, deadline_seconds: float = 0.1, max_ticks: int = 12000, startup_grace_seconds: float = 2.0) -> dict` with keys `winner` (`int | None`), `forfeited_by` (`int | None`), `ticks` (`int`), `completed` (`bool`), `seed` (`int`). Used by the Task 7 CLI.

- [ ] **Step 1: Write the failing tests**

The second test here is the end-to-end test: two real subprocess agents playing a full match through the real engine, no mocks.

```python
# tests/test_match.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.match import run_match

FIXTURE = [sys.executable, str(Path(__file__).resolve().parent / "fixtures" / "fixture_agent.py")]
BASELINE = [sys.executable, str(Path(__file__).resolve().parent.parent / "agents" / "baseline_random" / "agent.py")]


def test_forfeit_after_five_consecutive_misses():
    result = run_match(
        agent_a_command=FIXTURE + ["echo"],
        agent_b_command=FIXTURE + ["sleep"],
        seed=1,
        deadline_seconds=0.05,
        max_ticks=200,
        startup_grace_seconds=0.0,
    )
    assert result["forfeited_by"] == 1
    assert result["winner"] == 0


def test_full_match_between_baseline_agents_reaches_conclusion():
    result = run_match(
        agent_a_command=BASELINE,
        agent_b_command=BASELINE,
        seed=42,
    )
    assert result["completed"] is True
    assert result["forfeited_by"] is None
    assert result["winner"] in (0, 1, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_match.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.match'`

- [ ] **Step 3: Write the implementation**

```python
# orchestrator/match.py
import random
import time
from typing import Any, Dict, List, Optional

from orchestrator import GAMEDATA_PATH
from orchestrator.agent_process import AgentProcess
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
) -> Dict[str, Any]:
    random.seed(seed)

    engine = BattleEngine(data_file=str(GAMEDATA_PATH))
    battle = engine.create_battle()

    agents = [
        AgentProcess(agent_a_command + [str(0)]),
        AgentProcess(agent_b_command + [str(1)]),
    ]
    miss_counts = [0, 0]
    forfeited_by: Optional[int] = None
    request_id = 0
    start_time = time.monotonic()

    try:
        for _tick in range(1, max_ticks + 1):
            battle.step()

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
                        battle.deploy_card(player_id, card, Position(float(x), float(y)))

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_match.py -v`
Expected: PASS. The second test runs a full ~5-6 minute simulated match (compressed to real seconds since nothing throttles `battle.step()` to wall-clock speed) between two baseline agents and asserts it actually concludes — this is the end-to-end proof for week 1, not a mock.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/match.py tests/test_match.py
git commit -m "Add match orchestrator with tick loop and forfeit accounting"
```

---

### Task 7: Add a CLI entry point to run a match

**Files:**
- Create: `orchestrator/cli.py`

**Interfaces:**
- Consumes: `run_match` (Task 6).
- Produces: a runnable `python3 -m orchestrator.cli` command — this is the deliverable that lets you (or anyone reviewing the prototype) actually run a match by hand.

- [ ] **Step 1: Write the implementation**

There's no new behavior to unit-test here — `run_match` is already covered end-to-end in Task 6. This step wires it to argv.

```python
# orchestrator/cli.py
import argparse
import json

from orchestrator.match import run_match


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one battle between two agent subprocesses.")
    parser.add_argument("--agent-a", required=True, help="Command to launch agent A, e.g. 'python3 agents/baseline_random/agent.py'")
    parser.add_argument("--agent-b", required=True, help="Command to launch agent B")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--deadline-seconds", type=float, default=0.1)
    parser.add_argument("--max-ticks", type=int, default=12000)
    args = parser.parse_args()

    result = run_match(
        agent_a_command=args.agent_a.split(),
        agent_b_command=args.agent_b.split(),
        seed=args.seed,
        deadline_seconds=args.deadline_seconds,
        max_ticks=args.max_ticks,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it manually to confirm the prototype works end-to-end**

Run (from the repo root, with `.venv` activated):
```bash
python3 -m orchestrator.cli --agent-a "python3 agents/baseline_random/agent.py" --agent-b "python3 agents/baseline_random/agent.py" --seed 42
```
Expected: prints a JSON object with `"completed": true` and a `winner` of `0`, `1`, or `null`. This is the week 1 milestone — the whole loop running for real, start to finish.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/cli.py
git commit -m "Add CLI entry point for running a match"
```

---

### Task 8: Add per-tick spectator logging (JSONL)

**Files:**
- Create: `orchestrator/match_log.py`
- Modify: `orchestrator/match.py`
- Modify: `orchestrator/cli.py`
- Test: `tests/test_match_log.py`
- Modify: `tests/test_match.py`

**Interfaces:**
- Produces: `build_snapshot(battle: BattleState) -> dict` (both sides shown in full, no fog of war), `append_snapshot(log_path: Path, snapshot: dict) -> None`. Consumed by `run_match` (this task), the web viewer (Task 10), and the bracket runner (Task 11).
- Consumes: `clasher.battle.BattleState`, `clasher.entities.Troop`/`Building` (Task 1).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_match_log.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_match_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.match_log'`

- [ ] **Step 3: Write the implementation**

```python
# orchestrator/match_log.py
import json
from pathlib import Path
from typing import Any, Dict

from clasher.battle import BattleState
from clasher.entities import Building, Troop

_TOWER_CARD_NAMES = {"Tower", "KingTower"}


def build_snapshot(battle: BattleState) -> Dict[str, Any]:
    """Build one spectator-facing snapshot of the battle. Unlike
    project_state, this has no fog-of-war restriction: it's written to a
    log for a human to watch after the fact, not sent to a competing
    agent, so both sides are shown in full."""
    entities = []
    for entity in battle.entities.values():
        if not entity.is_alive or not isinstance(entity, (Troop, Building)):
            continue
        card_name = getattr(entity.card_stats, "name", "Unknown")
        entities.append({
            "card": card_name,
            "x": entity.position.x,
            "y": entity.position.y,
            "hp": entity.hitpoints,
            "player_id": entity.player_id,
            "is_tower": card_name in _TOWER_CARD_NAMES,
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_match_log.py -v`
Expected: PASS

- [ ] **Step 5: Wire logging into `run_match`**

Modify `orchestrator/match.py`: add the import and an optional `log_path` parameter, and append a snapshot every tick.

```python
# orchestrator/match.py — add to the imports at the top
from pathlib import Path

from orchestrator.match_log import append_snapshot, build_snapshot
```

```python
# orchestrator/match.py — change the run_match signature to add log_path
# (Optional is already imported from Task 6's `from typing import ... Optional`)
def run_match(
    agent_a_command: List[str],
    agent_b_command: List[str],
    seed: int,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    max_ticks: int = DEFAULT_MAX_TICKS,
    startup_grace_seconds: float = DEFAULT_STARTUP_GRACE_SECONDS,
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
```

```python
# orchestrator/match.py — inside the tick loop, immediately after battle.step()
            battle.step()

            if log_path is not None:
                append_snapshot(log_path, build_snapshot(battle))
```

- [ ] **Step 6: Extend the existing end-to-end test to assert a log gets written**

```python
# tests/test_match.py — replace test_full_match_between_baseline_agents_reaches_conclusion with:
def test_full_match_between_baseline_agents_reaches_conclusion(tmp_path):
    log_path = tmp_path / "match.jsonl"
    result = run_match(
        agent_a_command=BASELINE,
        agent_b_command=BASELINE,
        seed=42,
        log_path=log_path,
    )
    assert result["completed"] is True
    assert result["forfeited_by"] is None
    assert result["winner"] in (0, 1, None)
    assert log_path.exists()
    assert len(log_path.read_text().strip().split("\n")) == result["ticks"]
```

- [ ] **Step 7: Run the full test suite to verify everything still passes**

Run: `pytest tests/ -v`
Expected: all tests PASS, including the modified end-to-end test.

- [ ] **Step 8: Add a `--log-path` option to the CLI**

```python
# orchestrator/cli.py — add this import at the top, alongside the existing ones
from pathlib import Path
```

```python
# orchestrator/cli.py — add this argument alongside the existing ones
    parser.add_argument("--log-path", type=Path, default=None, help="If set, append a per-tick JSONL snapshot log here")
```

```python
# orchestrator/cli.py — pass it through to run_match
    result = run_match(
        agent_a_command=args.agent_a.split(),
        agent_b_command=args.agent_b.split(),
        seed=args.seed,
        deadline_seconds=args.deadline_seconds,
        max_ticks=args.max_ticks,
        log_path=args.log_path,
    )
```

- [ ] **Step 9: Commit**

```bash
git add orchestrator/match_log.py orchestrator/match.py orchestrator/cli.py tests/test_match_log.py tests/test_match.py
git commit -m "Add per-tick spectator logging to JSONL"
```

---

### Task 9: Add Docker sandboxing for agent subprocesses

**Files:**
- Create: `docker/agent.Dockerfile`

**Interfaces:**
- Consumes: `agents/baseline_random/agent.py` (Task 4). No changes to `AgentProcess` or `run_match` — see Global Constraints.

This task has no pytest-level test: the deliverable is a container image, verified by manually running a match through it and confirming the same result shape as the non-Docker run.

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# docker/agent.Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY agents/ /app/agents/
ENTRYPOINT ["python3"]
```

- [ ] **Step 2: Build the image**

Run (from the repo root):
```bash
docker build -f docker/agent.Dockerfile -t battle-agent-base .
```
Expected: image builds successfully; `docker images | grep battle-agent-base` shows it.

- [ ] **Step 3: Run a match with both agents containerized**

```bash
python3 -m orchestrator.cli \
  --agent-a "docker run -i --rm battle-agent-base /app/agents/baseline_random/agent.py" \
  --agent-b "docker run -i --rm battle-agent-base /app/agents/baseline_random/agent.py" \
  --seed 42
```
Expected: same JSON result shape as the non-Docker run in Task 7, `"completed": true`. Note: the first run after a fresh `docker build` can be slower to start than the 2-second `startup_grace_seconds` default while Docker's daemon warms up — if you see spurious forfeits only on the first run, re-run once; if it persists, increase `--deadline-seconds` for containerized agents rather than changing the default (the default stays tuned for plain subprocesses).

- [ ] **Step 4: Commit**

```bash
git add docker/agent.Dockerfile
git commit -m "Add Docker sandboxing for agent subprocesses"
```

---

### Task 10: Build the shared live/replay web viewer

**Files:**
- Create: `web/server.py`
- Create: `web/static/index.html`
- Create: `web/static/viewer.js`

**Interfaces:**
- Consumes: JSONL logs produced by `append_snapshot` (Task 8), in the `build_snapshot` shape (entities with `card`/`x`/`y`/`hp`/`player_id`/`is_tower`; `players` with `elixir`/`king_hp`/`left_hp`/`right_hp`; `tick`).
- Produces: a running web server at `http://localhost:8000/` with `?log=<path>&mode=live|replay` query params, and a `/results` endpoint reused by Task 12.

This task's frontend pieces (canvas rendering, play/pause/scrub) aren't practically unit-testable in this plan — verification is manual: open the page in a browser and confirm what you see.

- [ ] **Step 1: Install the new dependencies**

```bash
pip install fastapi uvicorn
```

- [ ] **Step 2: Write the server**

```python
# web/server.py
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/bracket")
def bracket_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "bracket.html")


@app.get("/snapshot/latest")
def snapshot_latest(log: str) -> JSONResponse:
    log_path = Path(log)
    if not log_path.exists():
        return JSONResponse({"error": "log not found"}, status_code=404)
    with open(log_path, "rb") as f:
        lines = f.read().splitlines()
    if not lines:
        return JSONResponse({"error": "log is empty"}, status_code=404)
    return JSONResponse(json.loads(lines[-1]))


@app.get("/replay")
def replay(log: str) -> JSONResponse:
    log_path = Path(log)
    if not log_path.exists():
        return JSONResponse({"error": "log not found"}, status_code=404)
    with open(log_path) as f:
        snapshots = [json.loads(line) for line in f if line.strip()]
    return JSONResponse(snapshots)


@app.get("/results")
def results(path: str) -> JSONResponse:
    results_path = Path(path)
    if not results_path.exists():
        return JSONResponse({"error": "results not found"}, status_code=404)
    return JSONResponse(json.loads(results_path.read_text()))
```

Note: `/bracket` and `/results` are used by Task 12, but are added here since they live in the same file — no reason to touch `web/server.py` twice.

- [ ] **Step 3: Write the page**

```html
<!-- web/static/index.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Battle Sim Viewer</title>
  <style>
    body { font-family: monospace; background: #111; color: #eee; }
    canvas { background: #1b3a1b; display: block; margin: 20px auto; border: 2px solid #444; }
    #controls { text-align: center; }
  </style>
</head>
<body>
  <div id="controls">
    <button id="playPause">Play</button>
    <input id="scrub" type="range" min="0" max="0" value="0" style="width: 400px;">
    <select id="speed">
      <option value="200">1x</option>
      <option value="100">2x</option>
      <option value="50">4x</option>
      <option value="25">8x</option>
    </select>
  </div>
  <canvas id="board" width="360" height="640"></canvas>
  <script src="/static/viewer.js"></script>
</body>
</html>
```

- [ ] **Step 4: Write the renderer, shared between live and replay modes**

```javascript
// web/static/viewer.js
const params = new URLSearchParams(window.location.search);
const logPath = params.get("log");
const mode = params.get("mode") || "replay"; // "live" or "replay"

const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const TILE = 20; // pixels per arena tile (18 wide x 32 tall -> 360x640)

function draw(snapshot) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!snapshot) return;

  for (const entity of snapshot.entities) {
    const x = entity.x * TILE;
    const y = (32 - entity.y) * TILE; // flip so player 0 renders at the bottom
    ctx.fillStyle = entity.player_id === 0 ? "#4a90d9" : "#d94a4a";
    ctx.beginPath();
    ctx.arc(x, y, entity.is_tower ? 10 : 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "9px monospace";
    ctx.fillText(entity.card, x + 8, y);
  }

  ctx.fillStyle = "#fff";
  ctx.font = "12px monospace";
  ctx.fillText(`tick ${snapshot.tick}`, 10, 16);
  snapshot.players.forEach((p, i) => {
    ctx.fillText(
      `p${i} elixir=${p.elixir.toFixed(1)} king=${Math.round(p.king_hp)}`,
      10,
      32 + i * 14
    );
  });
}

if (mode === "live") {
  setInterval(async () => {
    const res = await fetch(`/snapshot/latest?log=${encodeURIComponent(logPath)}`);
    if (res.ok) draw(await res.json());
  }, 250);
} else {
  fetch(`/replay?log=${encodeURIComponent(logPath)}`)
    .then((res) => res.json())
    .then((snapshots) => {
      const scrub = document.getElementById("scrub");
      const playPause = document.getElementById("playPause");
      const speed = document.getElementById("speed");
      scrub.max = snapshots.length - 1;

      let index = 0;
      let playing = false;
      let timer = null;

      function render() {
        draw(snapshots[index]);
        scrub.value = index;
      }

      function tick() {
        if (index >= snapshots.length - 1) {
          playing = false;
          playPause.textContent = "Play";
          clearInterval(timer);
          return;
        }
        index += 1;
        render();
      }

      function restartTimer() {
        clearInterval(timer);
        if (playing) timer = setInterval(tick, Number(speed.value));
      }

      playPause.addEventListener("click", () => {
        playing = !playing;
        playPause.textContent = playing ? "Pause" : "Play";
        restartTimer();
      });
      speed.addEventListener("change", restartTimer);
      scrub.addEventListener("input", () => {
        index = Number(scrub.value);
        render();
      });

      render();
    });
}
```

- [ ] **Step 5: Manually verify**

Run:
```bash
mkdir -p logs
python3 -c "
from orchestrator.match import run_match
run_match(['python3', 'agents/baseline_random/agent.py'], ['python3', 'agents/baseline_random/agent.py'], seed=1, log_path='logs/demo.jsonl')
"
uvicorn web.server:app --reload
```
Then open `http://localhost:8000/?log=logs/demo.jsonl&mode=replay`.
Expected: a canvas showing blue and red dots for troops/towers, a working scrub bar, and Play/Pause that steps through the match at the selected speed.

- [ ] **Step 6: Commit**

```bash
git add web/server.py web/static/index.html web/static/viewer.js
git commit -m "Add shared live/replay web viewer"
```

---

### Task 11: Build the tournament bracket runner

**Files:**
- Create: `tournament/__init__.py` (empty)
- Create: `tournament/bracket.py`
- Test: `tests/test_bracket.py`

**Interfaces:**
- Consumes: `run_match` (Tasks 6 and 8, with `log_path`).
- Produces: `run_bracket(agents: list[dict], seed: int, logs_dir: Path, results_path: Path) -> dict`, used by Task 12's leaderboard page and Task 13's dry run. Each agent entry is `{"name": str, "command": list[str]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bracket.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tournament.bracket import run_bracket

BASELINE = [sys.executable, str(Path(__file__).resolve().parent.parent / "agents" / "baseline_random" / "agent.py")]


def test_run_bracket_with_four_agents_produces_two_rounds(tmp_path):
    agents = [{"name": f"agent{i}", "command": BASELINE} for i in range(4)]

    results = run_bracket(
        agents,
        seed=7,
        logs_dir=tmp_path / "logs",
        results_path=tmp_path / "results.json",
    )

    assert len(results["rounds"]) == 2
    assert len(results["rounds"][0]) == 2
    assert len(results["rounds"][1]) == 1
    final_winner = results["rounds"][1][0]["winner"]
    assert final_winner in {a["name"] for a in agents}
    assert (tmp_path / "results.json").exists()


def test_run_bracket_gives_bye_to_odd_agent_out(tmp_path):
    agents = [{"name": f"agent{i}", "command": BASELINE} for i in range(3)]

    results = run_bracket(
        agents,
        seed=7,
        logs_dir=tmp_path / "logs",
        results_path=tmp_path / "results.json",
    )

    assert results["rounds"][0][-1]["b"] is None
    assert results["rounds"][0][-1]["winner"] == "agent2"
```

Note: these tests run 2-3 real full matches each (real subprocesses, real engine), so this file takes noticeably longer than the rest of the suite — that's expected, not a hang.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bracket.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tournament'`

- [ ] **Step 3: Write the implementation**

```python
# tournament/__init__.py
```

```python
# tournament/bracket.py
import json
from pathlib import Path
from typing import Any, Dict, List

from orchestrator.match import run_match


def run_bracket(
    agents: List[Dict[str, Any]],
    seed: int,
    logs_dir: Path,
    results_path: Path,
) -> Dict[str, Any]:
    """Run a single-elimination, best-of-1 bracket over `agents` (each
    `{"name": str, "command": list[str]}`). An odd number of agents
    remaining in a round gives the last one a bye. A drawn match
    (`winner` is None) advances the first-listed agent by convention —
    a real tournament would need an explicit tiebreak rule; this is a
    known thin-slice limitation, not a hidden bug."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    rounds: List[List[Dict[str, Any]]] = []
    remaining = list(agents)
    round_num = 1

    while len(remaining) > 1:
        this_round: List[Dict[str, Any]] = []
        next_remaining: List[Dict[str, Any]] = []

        for i in range(0, len(remaining) - 1, 2):
            agent_a, agent_b = remaining[i], remaining[i + 1]
            log_path = logs_dir / f"round{round_num}_match{i // 2 + 1}.jsonl"
            result = run_match(
                agent_a["command"],
                agent_b["command"],
                seed=seed,
                log_path=log_path,
            )
            winner = agent_b if result["winner"] == 1 else agent_a
            this_round.append({
                "a": agent_a["name"],
                "b": agent_b["name"],
                "winner": winner["name"],
                "log": str(log_path),
            })
            next_remaining.append(winner)

        if len(remaining) % 2 == 1:
            bye_agent = remaining[-1]
            this_round.append({"a": bye_agent["name"], "b": None, "winner": bye_agent["name"], "log": None})
            next_remaining.append(bye_agent)

        rounds.append(this_round)
        remaining = next_remaining
        round_num += 1

    results = {"rounds": rounds}
    results_path.write_text(json.dumps(results, indent=2))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bracket.py -v`
Expected: PASS (slower than other test files — see the note in Step 1).

- [ ] **Step 5: Commit**

```bash
git add tournament/__init__.py tournament/bracket.py tests/test_bracket.py
git commit -m "Add single-elimination bracket runner"
```

---

### Task 12: Build the bracket/leaderboard web page

**Files:**
- Create: `web/static/bracket.html`

**Interfaces:**
- Consumes: `results.json` (Task 11, via the `/results` endpoint already added in Task 10) and the `/` replay viewer (Task 10) for its "watch" links.

No new pytest-level test — verified manually, same as Task 10's viewer.

- [ ] **Step 1: Write the page**

```html
<!-- web/static/bracket.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Battle Sim Bracket</title>
  <style>
    body { font-family: monospace; background: #111; color: #eee; padding: 20px; }
    table { border-collapse: collapse; width: 100%; max-width: 700px; margin: 0 auto; }
    th, td { border: 1px solid #444; padding: 8px; text-align: left; }
    a { color: #4a90d9; }
  </style>
</head>
<body>
  <table id="bracket"><thead><tr><th>Round</th><th>A</th><th>B</th><th>Winner</th><th>Replay</th></tr></thead><tbody></tbody></table>
  <script>
    const params = new URLSearchParams(window.location.search);
    const resultsPath = params.get("results") || "tournament/results.json";

    fetch(`/results?path=${encodeURIComponent(resultsPath)}`)
      .then((res) => res.json())
      .then((data) => {
        const tbody = document.querySelector("#bracket tbody");
        data.rounds.forEach((round, roundIndex) => {
          round.forEach((match) => {
            const row = document.createElement("tr");
            const replayLink = match.log
              ? `<a href="/?log=${encodeURIComponent(match.log)}&mode=replay">watch</a>`
              : "(bye)";
            row.innerHTML = `<td>${roundIndex + 1}</td><td>${match.a}</td><td>${match.b ?? "-"}</td><td>${match.winner}</td><td>${replayLink}</td>`;
            tbody.appendChild(row);
          });
        });
      });
  </script>
</body>
</html>
```

- [ ] **Step 2: Manually verify**

Run:
```bash
python3 -c "
from pathlib import Path
from tournament.bracket import run_bracket
agents = [{'name': f'agent{i}', 'command': ['python3', 'agents/baseline_random/agent.py']} for i in range(4)]
run_bracket(agents, seed=1, logs_dir=Path('logs'), results_path=Path('tournament/results.json'))
"
uvicorn web.server:app --reload
```
Then open `http://localhost:8000/bracket?results=tournament/results.json`.
Expected: a table with 2 rounds, 3 total matches, each non-bye row's "watch" link opening a working replay of that match.

- [ ] **Step 3: Commit**

```bash
git add web/static/bracket.html
git commit -m "Add bracket/leaderboard web page"
```

---

### Task 13: Dry run — verify the full pipeline end-to-end

**Files:** none created — this task is verification and bugfixing against Tasks 1-12, not new code.

**Interfaces:** exercises every interface produced by Tasks 1-12 together.

- [ ] **Step 1: Run a small placeholder bracket**

```bash
mkdir -p tournament
python3 -c "
from pathlib import Path
from tournament.bracket import run_bracket
agents = [{'name': f'agent{i}', 'command': ['python3', 'agents/baseline_random/agent.py']} for i in range(8)]
results = run_bracket(agents, seed=123, logs_dir=Path('logs'), results_path=Path('tournament/results.json'))
print(results)
"
```
Expected: 3 rounds (8 -> 4 -> 2 -> 1), 7 total matches, `tournament/results.json` and 7 files under `logs/` all created, no exceptions.

- [ ] **Step 2: Browse the results through the web UI**

```bash
uvicorn web.server:app --reload
```
Open `http://localhost:8000/bracket?results=tournament/results.json`, click "watch" on at least one first-round and the final match.
Expected: both replay correctly — canvas renders, scrub bar spans the full match, Play/Pause works.

- [ ] **Step 3: Fix anything broken**

If a step above fails, the fix belongs in whichever task actually owns the broken piece (e.g. a bracket-scoring bug belongs in Task 11's `bracket.py`, not here) — this task doesn't introduce new files, it closes out whatever Tasks 1-12 got wrong when exercised together for the first time.

- [ ] **Step 4: Commit**

Only if Step 3 required code changes elsewhere:
```bash
git add -A
git commit -m "Fix issues found in end-to-end dry run"
```
