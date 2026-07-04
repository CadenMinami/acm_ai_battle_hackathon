# AI Agent Battle Competition — Project Spec & Week 1 MVP Design

Status: approved for implementation
Date: 2026-07-04
Owner: Caden (solo build)

## 1. Project vision

Students write Python-only AI agents that play a real-time battle simulator
based on [samdickson22/clash-simulator](https://github.com/samdickson22/clash-simulator).
Agents compete head-to-head in a 32-agent single-elimination bracket; matches
run automatically and feed a live leaderboard. A match can be watched three
ways: manual (human) play, live agent-vs-agent, or recorded replay with
adjustable playback speed.

**Timeline:** the live event is ~2 months out (early September 2026), but
Caden's personal build window is one week (by 2026-07-11), after which the
project hands off to other team members for the remaining ~7 weeks of
hardening before the event. Because of that, **every one of the 5 phases
gets a working, thin, unpolished slice this week** — not just Phase 1 in
depth followed by Phases 2-5 later. Section 12 lays out exactly what's thin
now vs. explicitly deferred to whoever inherits this, phase by phase, so the
handoff is honest about what's rough rather than silently incomplete.

**IP note:** the base engine is a fan-built simulation of a commercial mobile
game using scraped card data. Avoid Supercell branding/art and don't lean on
the "Clash Royale" name in event marketing.

## 2. Foundation — audit of the upstream engine

Verified directly against the `samdickson22/clash-simulator` source
(`main` branch, audited 2026-07-04):

- `BattleState.step(speed_factor)` advances one deterministic 33ms tick;
  `deploy_card(player_id, card_name, position)` already enforces elixir,
  hand membership, and arena-position legality internally and returns
  `bool` — the orchestrator does not need to reimplement legality checks.
- Hand/deck cycling is real and built into `PlayerState`
  (`hand`, `deck`, `cycle_queue`, auto-refill on `play_card`).
- The repo's own `README.md` is stale/aspirational: it documents
  `gym_env.py`, `replay.py`, and `visualizer.py`, none of which exist in the
  repo. Only `visualize_battle.py` (root-level pygame debug script) and
  `random_battle.py` (a subclass of it that deploys random legal moves)
  exist. This confirms the team's read: no replay logging, no Gymnasium
  env, and no web UI exist yet — all three need to be built.
- **Audit finding — tiebreaker cutoff bug:** `BattleEngine.run_battle()`
  defaults to `max_ticks=9090` (~300s), but `BattleState`'s own sudden-death
  tiebreaker doesn't resolve until `tiebreaker_time=360.0`s
  (~10,900 ticks). A match tied at 5:00 and heading into sudden death would
  hit `max_ticks` and stop with `game_over` still `False`, before the
  tiebreaker logic ever runs. **Consequence:** the orchestrator must drive
  `battle.step()` itself in its own loop rather than calling
  `run_battle()`, with `max_ticks` set comfortably past `tiebreaker_time`.
- **Audit finding — global RNG:** troop-spread and death-spawn positions
  are randomized via Python's global `random` module rather than a
  seeded instance owned by `BattleState`. Reproducing a match exactly
  requires seeding `random` before any engine call. Note this is a known
  limitation, not something to fix in week 1: an opponent's own agent
  process can introduce its own independent randomness that this seeding
  can't control, so "exact reproducibility" only covers the engine's
  internal randomness, not agent decisions.
- 54/54 existing engine tests pass on a clean checkout; a full sample
  battle (`random_battle.py`) runs end-to-end successfully.

## 3. Repo layout

```
acm_ai_battle_hackathon/
  engine/              # vendored from a fork of clash-simulator
  orchestrator/         # tick loop, subprocess management, state projection
  agents/
    baseline_random/    # reference agent: random legal move
  tests/                # orchestrator-level tests (separate from engine's own 54)
  docs/specs/           # design docs (this file)
  .gitignore
```

**Engine integration:** fork `samdickson22/clash-simulator` to a personal
GitHub account, then vendor (plain copy, not a submodule) `src/clasher/`,
`gamedata.json`, `hitboxes.json`, and `tests/` into `engine/`. Vendoring
(rather than a git submodule) avoids double-commit bookkeeping on a
one-week solo timeline; the fork exists so there's a place to push engine
changes (audit fixes, future replay-logging hooks) and, optionally, diff
against upstream later via a manually-added `upstream` remote inside the
fork itself.

## 4. Agent protocol

One JSON object per line over the agent subprocess's stdin/stdout. The
orchestrator polls each agent every 5 ticks (~165ms, ~6 decisions/sec).
Each agent runs as a single persistent subprocess for the whole match, not
re-spawned per decision.

**Orchestrator → agent request:**
```json
{
  "request_id": 42,
  "tick": 1230,
  "elixir": 6.3,
  "hand": ["Knight", "Archers", "Giant", "Minions"],
  "next_card": "Musketeer",
  "own_troops": [{"card": "Knight", "x": 8.5, "y": 12.0, "hp": 800}],
  "enemy_troops": [{"card": "Giant", "x": 9.0, "y": 20.0, "hp": 2000}],
  "towers": {
    "own": {"king": 4824, "left": 3631, "right": 3631},
    "enemy": {"king": 4824, "left": 0, "right": 3631}
  }
}
```

**Agent → orchestrator response:**
```json
{"request_id": 42, "action": "deploy", "card": "Knight", "x": 8.5, "y": 12.0}
```
or
```json
{"request_id": 42, "action": "none"}
```

**Fog of war:** the opponent's hand and cycle queue are never sent — only
troops/buildings currently visible on the board and the opponent's tower
HP. This is the fairness boundary that makes the protocol legitimate for
a competitive match rather than leaking hidden information.

**`request_id` and staleness:** every request carries a monotonically
increasing ID; a response is only accepted if its `request_id` matches
the outstanding request. If an agent's response arrives after its
deadline has already been treated as a miss, the orchestrator has moved
on — the ID lets it recognize and silently drop that late response
instead of misapplying a stale action.

## 5. Orchestrator design

**Tick loop**, per match:
1. Seed the engine's global RNG and record the seed in the match result.
2. Spawn both agent subprocesses; grant each a ~2s startup grace period
   before their first missed-deadline counts (so Python import/init time
   doesn't immediately burn a miss).
3. Loop: call `battle.step()` every tick. Every 5th tick:
   - Build one state snapshot from the *current* battle state.
   - Project it into two fog-of-war-filtered payloads (one per player)
     from that single shared snapshot.
   - Send both requests, then collect both responses (via the timeout
     mechanism below) *before* applying either action — this guarantees
     neither agent's decision is influenced by the other's action within
     the same decision point.
   - Apply accepted actions in a fixed order (player 0, then player 1)
     via `battle.deploy_card(...)`; a `False` return (illegal move) is
     logged and treated as a no-op, not a miss.
4. Stop when `battle.game_over` is `True`, or at a `max_ticks` set past
   `tiebreaker_time` (see audit finding above) as a hard backstop.

**Timeout mechanism:** subprocess pipes block in Python, so each agent
gets a background thread that continuously reads its stdout into a
queue; the main loop does `queue.get(timeout=deadline_seconds)` and
discards any response whose `request_id` doesn't match. The deadline is
measured with `time.monotonic()`, not `time.time()`, so it can't be
thrown off by a clock adjustment mid-match. The deadline itself is a
parameter (target 100ms in production; tests use a much smaller value —
see section 7) rather than a hardcoded constant.

**Miss/forfeit accounting:** a timeout, a malformed response, and a
crashed/dead subprocess all increment the *same* per-player miss
counter — there is deliberately no separate "instant forfeit on crash"
code path, since a dead process will keep missing every subsequent poll
anyway, and 5 consecutive misses is under a second of simulated time
regardless of which failure caused it. 5 consecutive misses forfeits the
match for that player.

## 6. Baseline agent

A reference implementation of the stdin/stdout protocol that plays a
random legal-ish move: if elixir covers the cheapest card in hand,
deploy a random hand card at a random position within a generous
own-half bounding box. It relies on the engine's own `deploy_card`
legality check to reject invalid spots (silently treated as a no-op
tick) rather than duplicating arena-half logic — acceptable for a
baseline, not for a competitive submission.

## 7. Testing plan

- Re-run the engine's existing 54 tests against the vendored copy
  (`pytest engine/tests`) to confirm the fork/vendor didn't break
  anything.
- New orchestrator tests, using a small fixture agent (under
  `tests/fixtures/`) that can be told via arguments to sleep past the
  deadline, send malformed JSON, or crash on command — this makes the
  timeout/forfeit logic deterministically testable instead of depending
  on real subprocess timing on a possibly-loaded machine. Tests use a
  tiny deadline (e.g. 10ms) against these fixtures rather than the
  production 100ms value.
  - State projector never includes the opponent's hand or cycle queue.
  - A timeout is treated as "no action" and doesn't crash the match.
  - 5 consecutive misses (any cause) triggers a forfeit.
  - A full match between two baseline agents reaches a winner or draw
    within a bounded tick count.

## 8. Phase 2 thin slice — Docker sandboxing + match logging

**Docker requires no changes to `AgentProcess` or `match.py`.** Both were
already designed around an opaque `command: list[str]` passed to
`subprocess.Popen` — swapping a raw `["python3", "agent.py", "0"]` for
`["docker", "run", "-i", "--rm", "battle-agent-base", "python3",
"/app/agents/baseline_random/agent.py", "0"]` is purely a change to what
command gets constructed by the caller (the CLI, or the bracket runner in
section 10). One shared base image (`python:3.11-slim`, the whole
`agents/` directory copied in) is enough for week 1, since every agent
running this week is our own script, not real student submissions —
per-submission custom images are a real Phase 2 concern for the handoff
team, not something week 1 needs to solve.

**Match logging** is a JSONL file of periodic full-state snapshots
(tick, every troop/building's card/position/HP for *both* sides, both
players' elixir and tower HP, `game_over`, `winner`) written once per
tick during `run_match`. Unlike the agent protocol, a spectator log has
no fog-of-war constraint — it's written after the fact for a human to
watch, not sent to a competing agent. `run_match` gains an optional
`log_path: Path | None` parameter; when set, it appends one JSON line
per tick. This is the same log format Phase 3's viewer and Phase 4's
bracket runner both consume, so it only needs to be built once.

## 9. Phase 3 thin slice — shared live/replay web viewer

**Deliberate stack deviation from the original doc:** the original doc
named React + Canvas/SVG and a live-push architecture. For a one-week
solo build, this plan uses plain HTML/JS + `<canvas>` (no build step,
no npm dependency to manage under time pressure) and **HTTP polling
instead of a WebSocket push** — the orchestrator already writes a JSONL
log every tick (section 8), so a page can just poll
`GET /snapshot/latest?log=<path>` every ~250ms and read the last line of
the file, instead of bridging `run_match`'s synchronous loop into an
async WebSocket broadcaster. The ~250ms latency is imperceptible to a
spectator; the async-bridging code it avoids is real complexity that
doesn't pay for itself this week. This is a named, flagged tradeoff, not
an oversight — migrating to React and a real push channel is reasonable
work for the handoff team once the core pipeline is proven.

**One renderer serves two modes**, since both need to draw the same
troop/tower data — only the data source differs:
- **Live**: poll `/snapshot/latest?log=<path>` every ~250ms while a
  match is running (or has just finished) and draw the latest snapshot.
- **Replay**: fetch `/replay?log=<path>` once (returns the whole file as
  a JSON array — match logs are a few MB at most), then step through it
  locally on a `setInterval` whose delay implements the speed slider
  (e.g. 200ms/tick = 1x, 25ms/tick = 8x), with play/pause and a scrub
  slider bound to the array index.

A small FastAPI app (`web/server.py`) serves the static page and the two
endpoints above. Rendering itself: an 18×32 grid scaled to the canvas,
troops as colored circles (blue vs. red) labeled with card name, towers
as HP bars at their fixed arena positions.

**Explicitly deferred to the handoff team:** manual play (drag-to-deploy
controls), the full React rewrite, WebSocket push, and the "should feel
like watching an actual match" visual polish bar from the original doc —
this week's viewer is legible, not polished.

## 10. Phase 4 thin slice — tournament bracket + leaderboard

`tournament/bracket.py` takes a list of `{"name": str, "command":
list[str]}` agent entries, builds a single-elimination bracket, and runs
each match via the *same* `run_match` from Phase 1 — no new
match-running code, just a loop that calls it once per bracket slot with
a distinct `log_path` per match (e.g. `logs/round1_match1.jsonl`).
Results accumulate in `tournament/results.json`:
```json
{"rounds": [[{"a": "agent1", "b": "agent2", "winner": "agent1", "log": "logs/round1_match1.jsonl"}]]}
```
A static `web/static/bracket.html` fetches that file and renders a flat
table (round, matchup, winner, a link to replay that match's log through
the Phase 3 viewer) — a real bracket-tree visualization is deferred.

**Explicitly deferred to the handoff team:** best-of-3 series (this
week's bracket is best-of-1 per matchup — tripling match count and
tracking series state isn't worth the time this week), the qualifying
run against a benchmark agent, and running at the full 32-agent scale.

## 11. Phase 5 thin slice — dry run

Run `tournament/bracket.py` against 4-8 copies of the baseline agent (or
simple hand-written variants, so matches aren't literally identical) —
not the full 32 — to prove logging, the bracket runner, and both web
pages hold together as one pipeline. This phase is verification and
bugfixing against the other four phases, not new code of its own.

## 12. What's thin now vs. deferred to the handoff team

| Phase | Built this week (thin) | Explicitly deferred |
|---|---|---|
| 1 — Engine & protocol | Full: audited engine, fog-of-war protocol, timeout/forfeit handling, real end-to-end test | Tuning the 100ms deadline against real student agents |
| 2 — Sandboxing & logging | One shared Docker base image; per-tick JSONL spectator log | Per-submission custom images; log compaction/rotation for long tournaments |
| 3 — Web UI | Plain HTML/JS/canvas viewer, HTTP polling, live + replay from one renderer | Manual play (drag-to-deploy); React migration; WebSocket push; visual polish |
| 4 — Tournament tooling | Single-elimination bracket runner reusing `run_match`; flat-table leaderboard page | Best-of-3 series; benchmark-agent qualifying/seeding run; 32-agent scale |
| 5 — Dry run | End-to-end pipeline check with 4-8 placeholder agents | Full 32-agent (~300 game) dry run before the live event |

## 13. Roadmap after handoff

Because every phase already has a thin, working slice, the ~7 weeks
before the event are about hardening each row of the table above to its
originally-scoped depth — not starting any of them from zero. Rough
match volume at the full 32-agent scale: ~200–250 seeding games (each
agent vs. a benchmark) plus ~90 bracket games (best-of-3 across a
31-series bracket) ≈ 300 total games for a full event run-through. At
that scale, raw compute is not the bottleneck — the value of the cloud
stretch goal (Fargate/ECS, S3 for logs, DynamoDB for leaderboard) is
isolation and portfolio story, not throughput necessity.

## 14. Open items carried forward (not blocking week 1)

- Exact wall-clock deadline (100ms target) to be tuned once real
  student agents are being tested, per the original team doc.
- Whether the qualifying/seeding run against a benchmark agent needs its
  own scheduling tooling, or can reuse this week's bracket runner as-is
  (likely yes, since the protocol doesn't change).
- GitHub account/org to fork the engine into (personal account assumed
  above; revisit if this becomes an ACM-org-owned project).
- **Participant-facing documentation** (flagged by Caden, explicitly not
  a week-1 requirement): a guide for students on how to write, locally
  test, and submit an agent against the baseline before the event. This
  is a different audience from this spec (participants, not the handoff
  engineering team) and a different document — likely written once the
  Docker submission format (section 8) is locked down enough that it
  won't change under participants mid-way through.
