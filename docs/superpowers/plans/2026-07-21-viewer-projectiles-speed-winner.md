# Viewer Projectiles, Faster Playback, Early Winner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project-specific execution note:** this repo's established pattern (see `.superpowers/sdd/progress*.md`) is Codex CLI as the task implementer (`codex exec --sandbox workspace-write --output-last-message ...`) with a Claude subagent as reviewer — Codex cannot `git commit`, so the controller verifies tests and commits. Follow that pattern here rather than having a Claude subagent hand-write the code directly.

**Goal:** Make the spectator match viewer show in-flight projectiles, offer playback speeds beyond 8x, and reveal the winner of a finished replay immediately instead of requiring a full watch-through.

**Architecture:** Projectile-family entities (`Projectile`, `SpawnProjectile`, `RollingProjectile`, `TimedExplosive`) already exist in `BattleState.entities` every tick; they're filtered out before `orchestrator/entity_view.py`'s `iter_live_entities` yields anything. Add an opt-in `include_projectiles` flag to that function (default `False`, so the agent-facing `state_projection.py` is byte-for-byte unaffected), turn it on only in `orchestrator/match_log.py`'s `build_snapshot`, and tag each entity with a `kind` field plus optional `target_x`/`target_y` so `web/static/viewer.js` can render projectiles distinctly. Playback speed and the winner reveal are pure `viewer.html`/`viewer.js` changes — no backend or schema work needed there, since replay mode already downloads the full match before playback starts.

**Tech Stack:** Python 3.11+ (pytest), vanilla JS/HTML/Canvas (no build step, no npm) — matches the rest of `web/static/`.

## Global Constraints

- `orchestrator/state_projection.py` (the fog-of-war payload sent to competing agents) and its test suite (`tests/test_state_projection.py`) must not change behavior — projectiles are a spectator-only detail agents were never meant to see. This is enforced by keeping `include_projectiles` opt-in with a `False` default.
- No changes to `web/server.py` or its tests — `/replay` and `/snapshot/latest` already pass whatever JSON is in the log through unchanged; the new snapshot fields ride along automatically.
- Snapshot schema changes must be additive only (new keys), so existing log files and any other consumer keep working.
- Python: type hints on all new/modified function signatures (project convention).
- No new frontend build tooling — plain `<script>` files, consistent with the rest of `web/static/`.

---

### Task 1: Opt-in projectile support in `entity_view.py`

**Files:**
- Modify: `orchestrator/entity_view.py`
- Test: `tests/test_entity_view.py` (new)

**Interfaces:**
- Produces: `is_projectile(entity) -> bool`; `iter_live_entities(battle: BattleState, include_projectiles: bool = False) -> Iterator[Tuple[entity, str]]` — same default behavior as today when `include_projectiles` is omitted.
- Consumes: nothing new (uses `clasher.entities.{Building,Projectile,RollingProjectile,TimedExplosive,Troop}`, all existing classes).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_entity_view.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_entity_view.py -v` (from the repo root — `orchestrator/__init__.py` adds `engine/src` to `sys.path` on import, so no `cd` or extra `PYTHONPATH` is needed)
Expected: FAIL — `ImportError: cannot import name 'is_projectile' from 'orchestrator.entity_view'` (and `include_projectiles` isn't a valid keyword yet).

- [ ] **Step 3: Implement the widened `entity_view.py`**

Replace the full contents of `orchestrator/entity_view.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_entity_view.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the existing agent-facing regression suite**

Run: `.venv/bin/python -m pytest tests/test_state_projection.py -v`
Expected: PASS, unchanged — confirms the `include_projectiles=False` default preserved old behavior exactly.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/entity_view.py tests/test_entity_view.py
git commit -m "Add opt-in projectile visibility to entity_view.iter_live_entities"
```

---

### Task 2: Wire projectiles into the spectator snapshot

**Files:**
- Modify: `orchestrator/match_log.py`
- Test: `tests/test_match_log.py`

**Interfaces:**
- Consumes: Task 1's `is_projectile(entity)` and `iter_live_entities(battle, include_projectiles=True)`.
- Produces: `build_snapshot(battle)` entity dicts now always include `"kind"` (`"unit"` or `"projectile"`), and include `"target_x"`/`"target_y"` (floats) when the entity has a `target_position` (true for `Projectile`/`SpawnProjectile`, not for `RollingProjectile`/`TimedExplosive`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_match_log.py` (add `from clasher.entities import Projectile` to the existing imports at the top):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_match_log.py::test_build_snapshot_includes_projectiles_with_kind_and_target -v`
Expected: FAIL — `KeyError: 'Musketeer'` (projectile isn't in the snapshot's entities yet).

- [ ] **Step 3: Implement the snapshot change**

Replace the full contents of `orchestrator/match_log.py`:

```python
import json
from pathlib import Path
from typing import Any, Dict

from clasher.battle import BattleState

from orchestrator.entity_view import TOWER_CARD_NAMES, is_projectile, iter_live_entities


def build_snapshot(battle: BattleState) -> Dict[str, Any]:
    """Build one spectator-facing snapshot of the battle. Unlike
    project_state, this has no fog-of-war restriction: it's written to a
    log for a human to watch after the fact, not sent to a competing
    agent, so both sides are shown in full — including in-flight
    projectiles, which agents never see (see entity_view.iter_live_entities)."""
    entities = []
    for entity, card_name in iter_live_entities(battle, include_projectiles=True):
        entry = {
            "card": card_name,
            "x": entity.position.x,
            "y": entity.position.y,
            "hp": entity.hitpoints,
            "max_hp": entity.max_hitpoints,
            "player_id": entity.player_id,
            "is_tower": card_name in TOWER_CARD_NAMES,
            "kind": "projectile" if is_projectile(entity) else "unit",
        }
        target_position = getattr(entity, "target_position", None)
        if target_position is not None:
            entry["target_x"] = target_position.x
            entry["target_y"] = target_position.y
        entities.append(entry)

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

- [ ] **Step 4: Run all match_log tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_match_log.py -v`
Expected: PASS (all tests, including the pre-existing `test_build_snapshot_includes_both_sides_in_full` — it doesn't check for `kind`, so the new field doesn't break it).

- [ ] **Step 5: Run the full backend test suite as a regression check**

Run: `.venv/bin/python -m pytest -q` (from the repo root — this picks up both `tests/` and `engine/tests/`)
Expected: PASS — everything (92 tests as of this plan), confirming Tasks 1 and 2 together haven't broken `test_web_server.py`, `test_state_projection.py`, `test_bracket*.py`, etc.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/match_log.py tests/test_match_log.py
git commit -m "Include projectiles in the spectator match snapshot"
```

---

### Task 3: Render projectiles distinctly in the viewer

**Files:**
- Modify: `web/static/viewer.js`

**Interfaces:**
- Consumes: Task 2's snapshot entity shape — `entity.kind` (`"unit"|"projectile"`), optional `entity.target_x`/`entity.target_y`.
- Produces: `drawProjectile(entity, x, y, teamColor)` (module-local function, not exported — no other file calls it).

- [ ] **Step 1: Add the `drawProjectile` helper**

In `web/static/viewer.js`, add this above the `function draw(snapshot) {` definition (i.e. right after `drawHpBar`, around line 155):

```javascript
const PROJECTILE_RADIUS = 3;
const PROJECTILE_TRAIL_LENGTH = 14; // px

function drawProjectile(entity, x, y, teamColor) {
  if (entity.target_x !== undefined && entity.target_y !== undefined) {
    const targetX = entity.target_x * TILE;
    const targetY = (32 - entity.target_y) * TILE;
    const dx = targetX - x;
    const dy = targetY - y;
    const distance = Math.hypot(dx, dy) || 1;
    const dirX = dx / distance;
    const dirY = dy / distance;

    const trailX = x - dirX * PROJECTILE_TRAIL_LENGTH;
    const trailY = y - dirY * PROJECTILE_TRAIL_LENGTH;

    const gradient = ctx.createLinearGradient(trailX, trailY, x, y);
    gradient.addColorStop(0, "rgba(255, 255, 255, 0)");
    gradient.addColorStop(1, teamColor);
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(trailX, trailY);
    ctx.lineTo(x, y);
    ctx.stroke();
  }

  ctx.fillStyle = teamColor;
  ctx.beginPath();
  ctx.arc(x, y, PROJECTILE_RADIUS, 0, Math.PI * 2);
  ctx.fill();
}
```

- [ ] **Step 2: Branch on `entity.kind` in the main render loop**

In the same file, inside `function draw(snapshot)`, find this loop:

```javascript
  for (const entity of snapshot.entities) {
    const x = entity.x * TILE;
    const y = (32 - entity.y) * TILE; // flip so player 0 renders at the bottom
    const teamColor = entity.player_id === 0 ? "#4a90d9" : "#d94a4a";
    const radius = entity.is_tower ? 12 : 8;
```

Replace those four lines with:

```javascript
  for (const entity of snapshot.entities) {
    const x = entity.x * TILE;
    const y = (32 - entity.y) * TILE; // flip so player 0 renders at the bottom
    const teamColor = entity.player_id === 0 ? "#4a90d9" : "#d94a4a";

    if (entity.kind === "projectile") {
      drawProjectile(entity, x, y, teamColor);
      continue;
    }

    const radius = entity.is_tower ? 12 : 8;
```

(Everything below — the shadowed circle, `drawHpBar`, card icon, and name label — is unchanged and now only runs for non-projectile entities.)

- [ ] **Step 3: Syntax-check the file**

Run: `node --check web/static/viewer.js`
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add web/static/viewer.js
git commit -m "Render projectiles as team-colored streaks in the match viewer"
```

---

### Task 4: Playback speeds beyond 8x

**Files:**
- Modify: `web/static/viewer.html`
- Modify: `web/static/viewer.js`

**Interfaces:**
- Consumes: nothing new.
- Produces: the `#speed` `<select>`'s `value` format changes from a bare millisecond number (e.g. `"25"`) to `"intervalMs,ticksPerStep"` (e.g. `"25,2"`) — this is purely internal to `viewer.js`'s replay controls, nothing else in the codebase reads that value.

- [ ] **Step 1: Add the 16x/32x options and repoint existing values**

In `web/static/viewer.html`, replace the `<select id="speed">` block:

```html
    <select id="speed" class="bg-arena border border-arena-line rounded px-2 py-1">
      <option value="200">1x</option>
      <option value="100">2x</option>
      <option value="50">4x</option>
      <option value="25">8x</option>
    </select>
```

with:

```html
    <select id="speed" class="bg-arena border border-arena-line rounded px-2 py-1">
      <option value="200,1">1x</option>
      <option value="100,1">2x</option>
      <option value="50,1">4x</option>
      <option value="25,1">8x</option>
      <option value="25,2">16x</option>
      <option value="25,4">32x</option>
    </select>
```

- [ ] **Step 2: Advance multiple ticks per timer fire in `viewer.js`**

In `web/static/viewer.js`, find:

```javascript
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
```

Replace with:

```javascript
      function parseSpeed() {
        const [intervalMs, ticksPerStep] = speed.value.split(",").map(Number);
        return { intervalMs, ticksPerStep };
      }

      function tick() {
        if (index >= snapshots.length - 1) {
          playing = false;
          playPause.textContent = "Play";
          clearInterval(timer);
          return;
        }
        const { ticksPerStep } = parseSpeed();
        index = Math.min(index + ticksPerStep, snapshots.length - 1);
        render();
      }

      function restartTimer() {
        clearInterval(timer);
        if (playing) {
          const { intervalMs } = parseSpeed();
          timer = setInterval(tick, intervalMs);
        }
      }
```

- [ ] **Step 3: Syntax-check the file**

Run: `node --check web/static/viewer.js`
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add web/static/viewer.html web/static/viewer.js
git commit -m "Add 16x and 32x playback speeds to the match viewer"
```

---

### Task 5: See the winner without watching the replay

**Files:**
- Modify: `web/static/viewer.html`
- Modify: `web/static/viewer.js`

**Interfaces:**
- Consumes: the `snapshots` array and `playerName()` function already defined in `viewer.js`'s replay-loading flow.
- Produces: `renderResultBadge(snapshot)` (module-local function).

- [ ] **Step 1: Add the badge container and Skip to End button**

In `web/static/viewer.html`, replace:

```html
  <div class="max-w-md mx-auto py-4 flex items-center justify-center gap-3">
    <button id="playPause" class="border border-arena-line px-3 py-1 rounded hover:border-gold hover:text-gold transition-colors">Play</button>
    <input id="scrub" type="range" min="0" max="0" value="0" class="flex-1 accent-gold">
    <select id="speed" class="bg-arena border border-arena-line rounded px-2 py-1">
      <option value="200,1">1x</option>
      <option value="100,1">2x</option>
      <option value="50,1">4x</option>
      <option value="25,1">8x</option>
      <option value="25,2">16x</option>
      <option value="25,4">32x</option>
    </select>
  </div>
  <div id="match-header" class="max-w-md mx-auto mb-2 flex items-center justify-center gap-3 text-sm text-ink-muted"></div>
```

with:

```html
  <div class="max-w-md mx-auto py-4 flex items-center justify-center gap-3">
    <button id="playPause" class="border border-arena-line px-3 py-1 rounded hover:border-gold hover:text-gold transition-colors">Play</button>
    <button id="skipToEnd" class="border border-arena-line px-3 py-1 rounded hover:border-gold hover:text-gold transition-colors">Skip to End</button>
    <input id="scrub" type="range" min="0" max="0" value="0" class="flex-1 accent-gold">
    <select id="speed" class="bg-arena border border-arena-line rounded px-2 py-1">
      <option value="200,1">1x</option>
      <option value="100,1">2x</option>
      <option value="50,1">4x</option>
      <option value="25,1">8x</option>
      <option value="25,2">16x</option>
      <option value="25,4">32x</option>
    </select>
  </div>
  <div id="match-header" class="max-w-md mx-auto mb-2 flex items-center justify-center gap-3 text-sm text-ink-muted"></div>
  <div id="result-badge" class="max-w-md mx-auto mb-2 flex items-center justify-center gap-2 text-sm"></div>
```

(Note: Task 4's edit already changed the `<option>` values to the `"ms,ticks"` format — this step's replacement block above assumes that's already in place.)

- [ ] **Step 2: Add `renderResultBadge` to `viewer.js`**

Add this function anywhere near `renderSnapshotHeader` (e.g. directly after it):

```javascript
function renderResultBadge(finalSnapshot) {
  const badge = document.getElementById("result-badge");
  if (!finalSnapshot || !finalSnapshot.game_over) return;
  const text =
    finalSnapshot.winner === null
      ? "Final result: Draw"
      : `Final result: ${playerName(finalSnapshot.winner) || `Player ${finalSnapshot.winner + 1}`} wins`;
  const el = document.createElement("span");
  el.className = "text-gold font-bold";
  el.textContent = text;
  badge.replaceChildren(el);
}
```

- [ ] **Step 3: Call it on load and wire up the Skip to End button**

In `web/static/viewer.js`, inside `startViewer()`'s replay-loading `.then((snapshots) => { ... })` callback, find:

```javascript
      const scrub = document.getElementById("scrub");
      const playPause = document.getElementById("playPause");
      const speed = document.getElementById("speed");
      scrub.max = snapshots.length - 1;
```

Replace with:

```javascript
      const scrub = document.getElementById("scrub");
      const playPause = document.getElementById("playPause");
      const speed = document.getElementById("speed");
      const skipToEnd = document.getElementById("skipToEnd");
      scrub.max = snapshots.length - 1;
      renderResultBadge(snapshots[snapshots.length - 1]);
```

Then find the existing event listener wiring:

```javascript
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
```

and add, right after it:

```javascript
      skipToEnd.addEventListener("click", () => {
        playing = false;
        playPause.textContent = "Play";
        clearInterval(timer);
        index = snapshots.length - 1;
        render();
      });
```

- [ ] **Step 4: Syntax-check the file**

Run: `node --check web/static/viewer.js`
Expected: no output, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add web/static/viewer.html web/static/viewer.js
git commit -m "Show the match result immediately and add a Skip to End control"
```

---

### Task 6: Verify live in the browser

**Files:** none (verification only).

**Interfaces:** none — this task consumes the finished feature from Tasks 1-5 and confirms it actually works, per this project's `verifying-intent` convention of exercising the real flow rather than trusting tests alone.

- [ ] **Step 1: Start the web server**

Run: `cd /Users/caden/Acm/acm_ai_battle_hackathon && uvicorn web.server:app --reload`
Expected: server starts on `http://127.0.0.1:8000`.

- [ ] **Step 2: Run a real match with ranged attackers**

Run a standalone match (via `orchestrator.cli` or however this project's existing README documents running a match) between agents that deploy ranged units — Musketeer, Wizard, Giant, etc. — so the log actually contains fired projectiles. Confirm the resulting `logs/*.jsonl` file exists.

- [ ] **Step 3: Open the replay in the browser and check all three features**

Using `claude-in-chrome`, navigate to `http://127.0.0.1:8000/viewer?log=<path-to-the-log>&mode=replay` and verify:
- The result badge under the header immediately shows "Final result: ... wins" (or Draw) as soon as the page loads, before pressing Play.
- Pressing "Skip to End" jumps the scrubber to the last tick and shows the same result.
- Scrubbing back to an earlier tick still correctly clears/updates the scrub-position-linked header (the existing `renderSnapshotHeader` behavior), while the new result badge stays showing the final result regardless.
- Selecting 16x and 32x in the speed dropdown and pressing Play visibly plays faster than 8x, without freezing or erroring (check the browser console via `read_console_messages`).
- During playback, projectiles are visible as small team-colored streaks flying from an attacker toward its target, distinct from full units (no HP bar, no card label).

- [ ] **Step 4: Fix anything that doesn't match, then re-verify**

If any check in Step 3 fails, fix it in the relevant task's files, re-run that task's tests (Tasks 1-2) or `node --check` (Tasks 3-5), and re-verify in the browser before moving on.

No commit for this task — it's a verification gate, not a code change. If Step 4 produced fixes, commit those under the original task's commit message convention (e.g. `git commit -m "Fix projectile trail direction on scrub"`).
