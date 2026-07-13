# Handoff: AI Agent Battle Competition Platform

Date: 2026-07-07

This document is for the ACM members picking this project up. It assumes you've never seen the code. Read this once, top to bottom, before you touch anything — it'll save you from re-discovering decisions that were already made deliberately.

---

## 1. What this project actually is

Students write AI agents (any language, as long as they speak a simple JSON-over-stdin/stdout protocol) that battle each other in a real-time simulator based on a Clash-Royale-style game. Agents deploy units, defend towers, and manage an elixir economy in head-to-head matches. The event format is a single-elimination bracket across all submitted agents, with a live leaderboard.

**Timeline context:** the live event is roughly two months out. Every part of the system — engine, orchestration, web UI, tournament tooling — already works end-to-end; the weeks between now and the event are for hardening and extending what's here, not building from zero.

**IP note, worth remembering:** the underlying engine is a fan-built simulation of a commercial mobile game using scraped card data (forked from `samdickson22/clash-simulator` on GitHub). Avoid using the real game's branding, art, or name in any event marketing or public-facing materials.

---

## 2. Five-minute orientation: get it running

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run one match between the reference agent and itself
.venv/bin/python -m orchestrator.cli \
  --agent-a ".venv/bin/python agents/baseline_random/agent.py" \
  --agent-b ".venv/bin/python agents/baseline_random/agent.py" \
  --seed 123 \
  --log-path logs/example_match.jsonl

# Launch the web UI (from the repo root — this matters, see §4)
uvicorn web.server:app --reload
```

Open `http://localhost:8000/` — you'll see a home page listing any match logs and bracket results found on disk. Click one to watch a replay, or run a small bracket yourself:

```python
from pathlib import Path
from tournament.bracket import run_bracket

agents = [{"name": f"agent{i}", "command": [".venv/bin/python", "agents/baseline_random/agent.py"]} for i in range(8)]
run_bracket(agents, seed=7, logs_dir=Path("logs"), results_path=Path("tournament/results.json"))
```

Refresh the home page and you'll see the bracket show up too, with a proper bracket-tree view and "watch" links into each match's replay.

Run the test suite any time you make a change: `.venv/bin/python -m pytest -q` — currently 87 tests, all passing, no warnings.

---

## 3. Architecture — how the five pieces connect

```
                    ┌─────────────────────────────────────┐
                    │         engine/  (vendored)           │
                    │   clasher battle simulation — deploy  │
                    │   legality, elixir, combat, towers    │
                    └───────────────┬───────────────────────┘
                                    │ BattleState.step()
                    ┌───────────────▼───────────────────────┐
                    │      orchestrator/  (the referee)      │
                    │  match.py    — tick loop, timeouts,    │
                    │                forfeits                │
                    │  agent_process.py — subprocess mgmt    │
                    │  state_projection.py — fog-of-war      │
                    │  match_log.py — spectator JSONL log    │
                    └───┬───────────────────────┬────────────┘
                        │ stdin/stdout JSON      │ writes
             ┌──────────▼──────────┐   ┌─────────▼──────────┐
             │   agent subprocess    │   │   logs/*.jsonl      │
             │  (student's own code, │   │  (one snapshot      │
             │   or agents/baseline_ │   │   per tick, both    │
             │   random for testing) │   │   sides visible)    │
             └───────────────────────┘   └─────────┬───────────┘
                                                    │
                    ┌───────────────────────────────▼───────────┐
                    │            tournament/bracket.py            │
                    │   runs many matches via the SAME run_match, │
                    │   writes tournament/results.json            │
                    └───────────────────────┬───────────────────┘
                                            │
                    ┌───────────────────────▼───────────────────┐
                    │                  web/                       │
                    │  server.py (FastAPI) + static/ (plain JS)   │
                    │  home page → viewer (canvas replay) →       │
                    │  bracket page — all read from logs/ and     │
                    │  tournament/ directly, no database           │
                    └─────────────────────────────────────────────┘
```

**The one thing to internalize:** `orchestrator/match.py`'s `run_match()` is the single source of truth for "how a match is played." The CLI calls it once. The bracket runner calls it once per matchup. Nothing else re-implements match logic — if you need to change how matches work, this is the only place.

---

## 4. Directory-by-directory walkthrough

### `engine/` — vendored, do not casually edit
A plain copy (not a git submodule — a deliberate call, see §6) of the forked battle simulator. `src/clasher/` has the actual simulation: `battle.py` (tick loop, combat, tower destruction), `entities.py` (troops/buildings/spells), `player.py` (elixir, hand/deck cycling), `arena.py` (the 18×32 tile grid, deploy-zone legality).

Two things worth knowing if you ever need to touch this:
- **The engine's own `random` usage is global, not seeded per-battle.** Troop-spread and death-spawn positions use Python's global `random` module. Seeding before a match makes the *engine's* randomness reproducible, but an agent subprocess's own decisions are separate — see §7.
- **`BattleEngine.run_battle()` is never called anywhere in this codebase.** Its default `max_ticks=9090` cuts off before the engine's own sudden-death tiebreaker (`tiebreaker_time=360.0s`, ~10,900 ticks) can resolve. `orchestrator/match.py` drives `battle.step()` itself in its own loop with `max_ticks=12000` instead. If you ever see code calling `run_battle()`, that's a red flag — it will silently truncate close matches.

### `orchestrator/` — the referee
- **`match.py`** — `run_match(agent_a_command, agent_b_command, seed, ...)`. Spawns both agents, drives the tick loop, polls each agent every 5 ticks, applies actions, tracks misses/forfeits, returns a result dict. Wraps the whole body in `redirect_stdout(devnull)` because the vendored engine prints debug noise (`[Detect]`, `[Lifecycle]`) that would otherwise pollute every caller's stdout.
- **`agent_process.py`** — `AgentProcess` wraps one subprocess. Deadlines are measured with `time.monotonic()` (never `time.time()`, which can jump). Every request carries a `request_id`; a response is only accepted if the ID matches, so a late response from a previous tick can't be misapplied. `send_request()`/`await_response()` are split so both agents' requests go out before either response is collected — neither player's timing can be influenced by how fast the other responded.
- **`state_projection.py`** — builds the JSON payload sent to an agent. **This is the fairness boundary.** The opponent's `hand`, `deck`, and `cycle_queue` never appear here — only currently-visible troops/buildings and tower HP. If you're ever debugging "why can't my agent see X," check here first; it's very likely deliberate.
- **`match_log.py`** — `build_snapshot()`/`append_snapshot()`. Unlike the agent-facing payload, this has **no fog-of-war restriction** — both sides shown in full, because it's a spectator log for humans, not sent to a competing agent. Also includes `max_hp` per entity (added for the health-bar UI feature) — the engine tracks this internally (`entity.max_hitpoints`), it's just exposed here now.
- **`entity_view.py`** — a small shared helper (`iter_live_entities`, `TOWER_CARD_NAMES`) used by both `state_projection.py` and `match_log.py` so the entity-filtering logic isn't duplicated.
- **`cli.py`** — the `orchestrator.cli` module. Prints clean JSON to stdout on success; on a bad `--agent-a`/`--agent-b` command (e.g., pointing at a non-existent executable), prints a clean error to stderr and exits non-zero instead of a raw Python traceback.

### `agents/baseline_random/agent.py` — the reference implementation
This is what every "vs. itself" match in this doc uses, and it's the model for what a real submission looks like: read one JSON line from stdin, decide, write one JSON line to stdout, repeat. It deliberately does **not** import anything from `clasher` or `orchestrator` — real student agents will eventually run in an isolated container with no access to this repo's internals, only the JSON arriving over stdin. It plays a uniformly random legal-ish move and relies on the engine's own `deploy_card()` to silently reject anything it can't actually afford yet.

**Important:** it uses Python's own unseeded `random`, not a seeded RNG. See §7 for what this means for reproducibility.

### `tournament/bracket.py` — the tournament runner
`run_bracket(agents, seed, logs_dir, results_path)` takes a list of `{"name": str, "command": list[str]}` entries, builds a single-elimination bracket (best-of-1, byes for odd counts), and calls `run_match()` once per matchup with a distinct `log_path`. Writes `results.json` shaped as `{"rounds": [[{"a", "b", "winner", "log"}, ...], ...]}`.

Within each round, those matchups run concurrently in separate OS processes, capped at `os.cpu_count()` by default unless callers pass `max_workers`; rounds still run sequentially because each round needs the previous winners. Results are collected back in matchup order, not completion order, so `results.json` keeps the same shape and ordering expectations.

A drawn match (`winner` is `None` from `run_match`) advances the first-listed agent — a real tournament needs an explicit tiebreak rule, and this is a known, documented thin-slice limitation.

**Every time you run this, it truncates and rewrites the log files at `logs_dir`.** This was a real bug (append-mode logs would double up across bracket re-runs) that got fixed — `run_match` now unlinks any existing file at `log_path` before writing. Don't rely on old match logs surviving a bracket re-run into the same directory.

### `web/` — the spectator-facing site
- **`server.py`** — FastAPI app. Routes: `/` (home page), `/viewer` (canvas replay — this used to be at `/`, moved during the UI redesign), `/bracket` (bracket-tree page), plus JSON endpoints `/api/browse`, `/replay`, `/snapshot/latest`, `/results`. All file-reading endpoints (`/replay`, `/snapshot/latest`, `/results`) validate the requested path against an allowlist (`LOGS_DIR`, `TOURNAMENT_DIR`) before touching the filesystem — this exists because the server will run on a LAN with students, and without it, `/replay?log=/etc/passwd` would happily read arbitrary files. **This allowlist is resolved relative to the server's working directory at import time — always start `uvicorn` from the repo root.**
- **`static/index.html` + `home.js`** — the home page. Fetches `/api/browse` and renders matches/brackets as clickable cards. Manual "Refresh" button, no auto-polling.
- **`static/viewer.html` + `viewer.js`** — the canvas replay. Renders team-colored circles (blue = player 0, red = player 1) with a per-card-type icon (`cards.js`) and colored glow, over a drawn arena background (river band, lane lines). Also draws a small HP bar over each unit (green/yellow/red by health percentage) and two 10-segment elixir bars flanking the canvas. Works in two modes: `mode=live` polls `/snapshot/latest` every 250ms; `mode=replay` (default) fetches the whole log once and steps through it locally with play/pause/scrub/speed controls.
- **`static/bracket.html`** — the bracket-tree page. One column per round, gold-highlighted winners, "watch" links into `/viewer`.
- **`static/cards.js`** — `getCardIcon(cardName)`, a hardcoded map of the 10 card names that can appear in a default-deck match to an emoji icon, with a `❔` fallback for anything unmapped (so a future deck change degrades gracefully instead of crashing the renderer).
- **`tailwind-input.css` + `theme.css`** — the design system. `theme.css` is a **generated build artifact** (compiled by the standalone Tailwind CLI, committed to git) — don't hand-edit it. If you change any Tailwind class in the HTML/JS, rebuild it: the exact command is in the README's "Rebuilding The Theme" section.

**No JS framework, no Node/npm, no CDN dependency at runtime.** This was a deliberate choice so the site works fully offline at demo time and any ACM member can open a `.html` file and understand it without a build pipeline. If a future contributor wants to migrate to React, that's reasonable — just know it wasn't an oversight that it isn't already.

### `docker/agent.Dockerfile` — optional sandboxing
A minimal `python:3.11-slim` image with `agents/` copied in. **This is opt-in, not enforced anywhere in the orchestrator.** `AgentProcess`/`run_match` treat the agent command as an opaque `list[str]` — wrapping it in `docker run ...` is purely a different command string constructed by whoever calls `run_match` (the CLI, the bracket runner). Nothing currently forces student submissions through this path. **This is the first real decision your team needs to make before accepting untrusted student code**: either make the tournament runner require containerized commands, or build out a submission pipeline that does it for them.

### `tests/` — 87 tests, all passing
Organized by what they cover, not by file-for-file mirroring of `orchestrator/`/`web/`. Notable ones:
- `fixtures/fixture_agent.py` — a controllable test double (modes: `echo`, `sleep`, `garbage`, `crash`) used to deterministically test timeout/forfeit logic without depending on real subprocess timing.
- `test_bracket_replay_integration.py` — a real end-to-end test proving a bracket-produced log actually plays through the real `/replay` endpoint, not two isolated unit tests that happen to both pass.
- `test_cli.py` — subprocess-level test that a bad agent command produces a clean error, not a traceback.

Frontend rendering (canvas drawing, bracket-tree layout, home page cards) has **no automated test coverage** — this is a deliberate, documented gap, not an oversight. It's been verified manually in a real browser at each stage. If your team adds a browser-automation test harness later, this is the obvious place to point it.

---

## 5. The agent protocol, in full

One JSON object per line over stdin/stdout. The orchestrator polls every 5 ticks (~165ms of simulated time, ~6 decisions/sec at 1x speed). Each agent is a single persistent subprocess for the whole match — not re-spawned per decision.

**Orchestrator → agent:**
```json
{
  "request_id": 42,
  "tick": 1230,
  "elixir": 6.3,
  "hand": ["Knight", "Archer", "Giant", "Minions"],
  "next_card": "Musketeer",
  "own_troops": [{"card": "Knight", "x": 8.5, "y": 12.0, "hp": 800}],
  "enemy_troops": [{"card": "Giant", "x": 9.0, "y": 20.0, "hp": 2000}],
  "towers": {
    "own": {"king": 4824, "left": 3631, "right": 3631},
    "enemy": {"king": 4824, "left": 0, "right": 3631}
  }
}
```

**Agent → orchestrator:**
```json
{"request_id": 42, "action": "deploy", "card": "Knight", "x": 8.5, "y": 12.0}
```
or
```json
{"request_id": 42, "action": "none"}
```

**Rules that have teeth:**
- The opponent's `hand`/`deck`/`cycle_queue` never appear — fog of war is enforced server-side, not by agent trust.
- `request_id` must match the outstanding request, or the response is dropped as stale.
- An explicit, on-time `{"action": "none"}` is a **successful** poll — declining to act is legal and resets the miss counter. Only a missing, late, or malformed response (or a dead process) counts as a miss.
- **5 consecutive misses forfeits the match** for that player, regardless of cause (timeout, crash, garbage output — they all increment the same counter, because a dead process will keep missing every subsequent poll anyway).
- Both agents' requests are sent before either response is collected, so neither player's decision window depends on how long the other took to respond.

---

## 6. Why things were built this way (so you don't "fix" a deliberate choice)

| Decision | Why | Where to change it if needed |
|---|---|---|
| Vendored engine, not a git submodule | Avoids double-commit bookkeeping across two repos | `engine/` — re-vendor from the fork if upstream changes |
| Plain JS/HTML, no framework | No build pipeline to maintain; a future team can migrate deliberately | `web/static/*` |
| HTTP polling, not WebSockets | The orchestrator already writes a JSONL log every tick — polling `/snapshot/latest` avoids bridging a synchronous tick loop into an async push channel, for ~250ms of latency nobody watching a replay notices | `web/server.py`, `viewer.js` |
| Docker sandboxing is opt-in | Every agent run so far was our own script, not real student code — per-submission custom images and enforcement are real Phase 2 work for your team | `docker/agent.Dockerfile`, wherever the tournament runner constructs agent commands |
| Best-of-1 bracket, no series | Tripling match count and tracking series state wasn't worth it in the initial build | `tournament/bracket.py` |
| Within-round matches parallelized with OS processes, not threads | `run_match` mutates process-global state (`random.seed`, `redirect_stdout`); threads would corrupt each other, processes isolate it | `tournament/bracket.py` |
| Tailwind precompiled and committed, not CDN | Works fully offline at demo time; no CDN dependency if venue wifi is bad | `web/tailwind-input.css` → rebuild via the README's documented command |

---

## 7. Known limitations — read this before you file a bug

These are **documented, not accidental.** Some are genuinely worth fixing soon; none are silent gaps your team is discovering for the first time.

**Worth fixing relatively soon:**
- `orchestrator/cli.py` splits `--agent-a`/`--agent-b` with `.split()` — a command containing a path with a space in it will break. Low-effort fix with `shlex.split()` if it ever matters.
- The Tailwind CLI rebuild command in the README pulls `releases/latest` rather than a pinned version — if Tailwind ships a v5 with breaking changes, the documented rebuild command could produce incompatible output. Worth pinning to the version actually used (`v4.3.2` as of this writing).
- `tournament/bracket.py`'s `run_bracket` creates `logs_dir` but never `results_path.parent` — would raise `FileNotFoundError` if you ever point `results_path` at a directory that doesn't exist yet.
- If both players hit 5 consecutive misses on the exact same poll, `orchestrator/match.py` awards the "win" to whichever player's forfeit check runs second in the loop (currently player 1), rather than treating it as a draw. Edge case, but a real one.

**Accepted tradeoffs, not bugs:**
- `--seed` makes the battle engine deterministic, but `agents/baseline_random/agent.py` (and any agent using its own unseeded RNG) is not — re-running the same seed with stochastic agents will not reproduce the same match. This is inherent to the protocol (agents are independent processes the orchestrator can't seed), not something the orchestrator can fix.
- The bracket page shows rounds separated by spacing, not literal connector lines linking a match to its winner's slot in the next round — a full connector-line bracket tree was judged too much CSS complexity for the time available. It reads as a tournament; it isn't pixel-perfect.
- No leaderboard/standings aggregation exists yet — the bracket page shows match-by-match results, not a computed win-count ranking. Nothing in `results.json`'s shape currently tracks cumulative wins across a larger event.
- `web/server.py`'s `/snapshot/latest` re-reads and re-parses the entire log file on every poll (every 250ms in live mode) just to get the last line. Fine at demo scale (a few thousand ticks); would need optimizing (e.g., seek-from-end) for very long-running live matches.

---

## 8. How students will build an agent

An agent is any program that speaks the §5 protocol: read one JSON line from stdin, decide, write one JSON action line to stdout, flush, repeat. Any language a student wants, as long as it can do line-buffered JSON over pipes. `agents/baseline_random/agent.py` is the model submission — under 60 lines, fully self-contained — and everything below is visible in it.

What a student needs to know to get a working agent:

- **Player id comes in as the last command-line argument** (`0` = bottom/blue, `1` = top/red) — the orchestrator appends it when it spawns the process (`orchestrator/match.py`). Use it to know which half of the arena is yours; deploys must land on your own side. The baseline uses y 2–13 for player 0 and y 18–29 for player 1, x 1–17, on the 18×32 tile grid.
- **Flush stdout after every response.** A response sitting in a buffer is a missed poll. This is the single most common way a first agent breaks.
- **Answer within the deadline (~100ms), even if the answer is "do nothing."** An on-time `{"action": "none"}` is a successful poll and resets the miss counter; 5 consecutive misses forfeits the match (§5).
- **Illegal deploys are silently rejected, not punished.** Not enough elixir, bad position — the engine's `deploy_card()` just ignores it. It's safe to try things; a smarter agent tracks its own elixir instead of relying on this.
- **No imports from this repo.** Submissions will eventually run in an isolated container where the only input is the JSON on stdin. Anything that reaches into `clasher` or `orchestrator` internals is doing something a real submission won't be able to do.

The local test loop to give students: run their agent against the baseline through the orchestrator CLI —

```bash
.venv/bin/python -m orchestrator.cli \
  --agent-a "python3 my_agent.py" \
  --agent-b ".venv/bin/python agents/baseline_random/agent.py" \
  --seed 1 --log-path logs/my_test.jsonl
```

— then watch the replay in the web viewer.

**Still to write: the participant-facing guide** (how to write, locally test, and submit an agent, as a standalone doc for students rather than this internal one). Hold off on writing it until the Docker submission format is locked down (§4's sandboxing decision), so it doesn't go stale while students are actively using it.

---

## 9. Building the benchmark agent

The benchmark agent is the house agent: meaningfully stronger than `baseline_random`, used for students to test against and for a qualifying/seeding run before the real bracket. It doesn't need to be brilliant — it needs to reliably beat random play so it's a meaningful bar.

**How to start:** create `agents/benchmark/agent.py` mirroring the baseline's structure — same stdin/stdout loop, same self-containment rule (no `clasher`/`orchestrator` imports). Only `choose_action()` should get smarter. Keeping it under the exact constraints students face guarantees anything it does is achievable by them too, and that it exercises the same protocol path.

A strategy ladder where each step should beat the one before it:

1. **Elixir discipline** — wait until elixir is near full before deploying, instead of the baseline's 1.0 floor, so pushes come in bursts instead of a trickle.
2. **Reactive defense** — parse `enemy_troops` each poll and deploy in whichever lane is under attack, between the attackers and your tower.
3. **Card roles** — hardcode a role map for the 10 default-deck cards (tank / ranged support / swarm / spell) and order deploys accordingly: tank first, support behind it.
4. **Tower targeting** — read `towers.enemy`; when one tower is damaged, keep pushing that lane to finish it.

**How to know it's actually better:** run it against the baseline over a batch of seeds and count wins — a quick loop over `orchestrator.cli` with `--seed 1..N`, or drop both into a 4-entry `run_bracket` and read the results. Aim for a decisive win rate (baseline is random, so anything near 50% means the "strategy" isn't doing anything). One caveat from §7: the orchestrator can't seed an agent's own RNG, so if you want reproducible benchmark matches, seed it yourself inside the agent (e.g. from the player-id argument).

---

## 10. Adjusting the UI

Everything frontend is in `web/static/` — plain HTML + JS, no framework, no npm, no build step for the JS (§4 has the full file-by-file walkthrough). Where to go for common changes:

- **Home page** (match/bracket cards): `index.html` + `home.js`, fed by `/api/browse`.
- **Replay/live viewer** (the canvas): `viewer.html` + `viewer.js` — arena background, unit circles, HP bars, elixir bars, playback controls all live here. Live mode polls `/snapshot/latest` every 250ms.
- **Bracket page**: `bracket.html`. The known cosmetic gap is connector lines between rounds (§7).
- **Card icons**: `cards.js` — a hardcoded name→emoji map for the 10 default-deck cards. If the deck ever changes, add entries here; unmapped cards degrade to `❔` rather than crashing.
- **Styling**: edit Tailwind classes in the HTML/JS and, if needed, `tailwind-input.css` — then rebuild `theme.css` with the command in the README's "Rebuilding The Theme" section. **Never hand-edit `theme.css`** — it's a generated artifact that happens to be committed (so the site works offline).
- **Backend routes**: `web/server.py`. If you add any endpoint that reads files, keep the path-allowlist validation pattern the existing endpoints use — it's the only thing standing between a LAN full of students and arbitrary file reads. And always start `uvicorn` from the repo root (the allowlist resolves against the working directory at import time).

There are no automated frontend tests (§4) — the current bar is verifying changes in a real browser, so do at least that; adding a browser-automation harness would be a genuinely useful contribution.

Bigger deferred UI work, if someone wants a meatier project: WebSocket push instead of polling, a manual/drag-to-deploy play mode, or a deliberate React migration.

---

## 11. Working on the brackets

All tournament logic is `tournament/bracket.py`, and it gets match results only by calling the same `run_match()` everything else uses — keep it that way (§3). The real work items, roughly in priority order:

- **An explicit tiebreak for draws.** Today a drawn match advances the first-listed agent (§7) — indefensible in a real event. Reasonable options: tower-HP differential from the final snapshot, or an immediate rematch on a fresh seed.
- **Best-of-3 series.** Deliberately skipped in the initial build (§6). Needs series state in the loop and a `results.json` shape that records games within a matchup — decide the shape together with the leaderboard work below so you only migrate it once.
- **Qualifying/seeding round.** Run every submission against the benchmark agent (§9) and seed the bracket by result, instead of bracket order being whatever order the list came in.
- **A leaderboard.** `results.json` currently stores per-round matchups only — no cumulative win counts. A standings view needs a shape change (or a separate aggregation step) plus a page or section in `web/`.
- **A full 32-agent dry run** well before the event. Verified at 4–8 agents so far. Watch `logs/` disk usage, total wall-clock time, and anything that behaves differently at depth-5 bracket sizes. Matches within each round now run in parallel, capped by CPU count unless `max_workers` is set. Peak concurrent OS processes is roughly worker cap × 3: each matchup driver process spawns 2 agent subprocesses, so a 16-matchup first round on an 8-core machine means about 24 simultaneous processes, not 48.

Two operational sharp edges to remember while working here (both in §7/§4): re-running a bracket into the same `logs_dir` truncates the existing logs, and `run_bracket` doesn't create `results_path`'s parent directory if it's missing.
