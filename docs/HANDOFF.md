# Handoff: AI Agent Battle Competition Platform

Status: week-1 build complete, handed off for ~7 weeks of hardening before the live event
Date: 2026-07-06
Original builder: Caden (solo)

This document is for the ACM members picking this project up. It assumes you've never seen the code. Read this once, top to bottom, before you touch anything — it'll save you from re-discovering decisions that were already made deliberately.

---

## 1. What this project actually is

Students write AI agents (any language, as long as they speak a simple JSON-over-stdin/stdout protocol) that battle each other in a real-time simulator based on a Clash-Royale-style game. Agents deploy units, defend towers, and manage an elixir economy in head-to-head matches. The event format is a single-elimination bracket across all submitted agents, with a live leaderboard.

**Timeline context:** this was built solo in one week (2026-06-29 to 2026-07-05) specifically so that every part of the system — engine, sandboxing, web UI, tournament tooling, and an end-to-end dry run — would have *something* working, rather than one piece being deep and the rest nonexistent. The event itself is roughly two months out from the original build date. The ~7 weeks between now and then are for hardening what's here, not building from zero.

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

# Launch the web UI (from the repo root — this matters, see §7)
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
A plain copy (not a git submodule — that was a deliberate call, see the original spec §3) of the forked battle simulator. `src/clasher/` has the actual simulation: `battle.py` (tick loop, combat, tower destruction), `entities.py` (troops/buildings/spells), `player.py` (elixir, hand/deck cycling), `arena.py` (the 18×32 tile grid, deploy-zone legality).

Two things worth knowing if you ever need to touch this:
- **The engine's own `random` usage is global, not seeded per-battle.** Troop-spread and death-spawn positions use Python's global `random` module. Seeding before a match makes the *engine's* randomness reproducible, but an agent subprocess's own decisions are separate — see §8.
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

**Important:** it uses Python's own unseeded `random`, not a seeded RNG. See §8 for what this means for reproducibility.

### `tournament/bracket.py` — the tournament runner
`run_bracket(agents, seed, logs_dir, results_path)` takes a list of `{"name": str, "command": list[str]}` entries, builds a single-elimination bracket (best-of-1, byes for odd counts), and calls `run_match()` once per matchup with a distinct `log_path`. Writes `results.json` shaped as `{"rounds": [[{"a", "b", "winner", "log"}, ...], ...]}`.

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
| Vendored engine, not a git submodule | Avoids double-commit bookkeeping on a solo one-week timeline | `engine/` — re-vendor from the fork if upstream changes |
| Plain JS/HTML, no framework | No build pipeline for a one-week build; a future team can migrate deliberately | `web/static/*` |
| HTTP polling, not WebSockets | The orchestrator already writes a JSONL log every tick — polling `/snapshot/latest` avoids bridging a synchronous tick loop into an async push channel, for ~250ms of latency nobody watching a replay notices | `web/server.py`, `viewer.js` |
| Docker sandboxing is opt-in | Every agent running this week was our own script, not real student code — per-submission custom images and enforcement are real Phase 2 work for your team | `docker/agent.Dockerfile`, wherever the tournament runner constructs agent commands |
| Best-of-1 bracket, no series | Tripling match count and tracking series state wasn't worth the time this week | `tournament/bracket.py` |
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
- `--seed` makes the battle engine deterministic, but `agents/baseline_random/agent.py` (and any agent using its own unseeded RNG) is not — re-running the same seed with stochastic agents will not reproduce the same match. This is inherent to the protocol (agents are independent processes the orchestrator can't seed), not something week-1 was expected to solve.
- The bracket page shows rounds separated by spacing, not literal connector lines linking a match to its winner's slot in the next round — a full connector-line bracket tree was judged too much CSS complexity for the time available. It reads as a tournament; it isn't pixel-perfect.
- No leaderboard/standings aggregation exists yet — the bracket page shows match-by-match results, not a computed win-count ranking. Nothing in `results.json`'s shape currently tracks cumulative wins across a larger event.
- `web/server.py`'s `/snapshot/latest` re-reads and re-parses the entire log file on every poll (every 250ms in live mode) just to get the last line. Fine at demo scale (a few thousand ticks); would need optimizing (e.g., seek-from-end) for very long-running live matches.

**Full detail, if you need it:** every task in both builds went through an individual code review and each build got a final whole-repo review; the complete finding-by-finding history (including things fixed along the way, not just what's still open) lives in `.superpowers/sdd/progress.md` and `.superpowers/sdd/progress-ui-redesign.md`. Those are gitignored working notes, not polished docs, but they're the ground truth if you want to trace *why* a specific line of code looks the way it does.

---

## 8. Explicitly deferred to your team

Straight from the original spec (§12), still accurate:

| Area | What's here now | What's deferred |
|---|---|---|
| Engine & protocol | Full: audited engine, fog-of-war, timeout/forfeit handling, real end-to-end tests | Tuning the ~100ms deadline against real (not baseline) student agents |
| Sandboxing & logging | One shared Docker base image; per-tick JSONL log | Per-submission custom images; log compaction/rotation for a long-running tournament; **enforcing** the sandbox (see §4) |
| Web UI | Now a real visual product (icons, health/elixir bars, bracket tree) — but still HTTP polling, no manual/drag-to-deploy play mode | WebSocket push; manual play controls; possible React migration if the team wants it |
| Tournament tooling | Single-elimination, best-of-1, reuses `run_match` | Best-of-3 series; a qualifying/seeding run against a benchmark agent; running at full 32-agent scale |
| Scale | Verified end-to-end with 4-8 agents | A full 32-agent (~300-game) dry run before the live event |

**Not started at all, flagged as a different document for a different audience:** participant-facing documentation — a guide for students on how to write, locally test, and submit an agent. This needs the Docker submission format locked down first so it doesn't go stale mid-way through when students are actively using it.

---

## 9. A note on process (why you can trust this codebase)

This was built using an AI-assisted TDD workflow: every task was implemented against a written spec, covered by a failing-test-first cycle where a test suite made sense, and reviewed by a separate pass before being marked done. Both the original 13-task build and the follow-on 7-task UI redesign each got a dedicated final whole-repository review at the end, independent of the per-task reviews, specifically looking for integration issues that only show up once everything is assembled — and both rounds found real cross-task bugs (things like a log-file overwrite race, an unrestricted file-read security gap, a CSS layout bug) that got fixed before being called done. This isn't a guarantee of zero remaining bugs, but it means the "obvious in hindsight" category of integration bug got a dedicated pass, not just per-file review.

If you want the full commit-by-commit history of what was built when and why, `git log` on this repo is complete and readable — every commit message describes intent, not just "fix stuff."
