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

**Timeline:** the live event is ~2 months out (early September 2026). A
working local prototype — engine + one baseline agent + orchestrator running
a full match, no UI required — is due within one week of this doc
(by 2026-07-11). That prototype is the subject of this design; the rest of
the roadmap (section 6) is sequenced for the remaining ~7 weeks.

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

## 8. Explicitly out of scope for week 1

Deferred to later phases (see roadmap below), not built now: Docker
sandboxing of agent subprocesses, tick-by-tick replay logging, the web
UI, tournament/bracket/leaderboard tooling, cloud deployment, the
Gymnasium RL wrapper, and a heuristic (non-random) reference agent.

## 9. Roadmap beyond week 1

| Phase | Focus | Deliverables |
|---|---|---|
| 1 (this doc) | Engine audit & agent interface | Correctness pass on the engine; documented `decide()` protocol; baseline agent |
| 2 | Orchestrator & sandboxing | Docker isolation added around the existing subprocess protocol (no protocol rework); tick-by-tick JSONL logger |
| 3 | Web UI — live view | Board renderer (React + Canvas/SVG); manual play mode |
| 4 | Replay & tournament tooling | Speed-adjustable replay viewer; bracket/leaderboard; match scheduling |
| 5 | Polish & dry run | Full dry-run tournament with placeholder agents before the live event |

Rough match volume at 32 agents: ~200–250 seeding games (each agent vs. a
benchmark) plus ~90 bracket games (best-of-3 across a 31-series bracket)
≈ 300 total games for a full event run-through. At that scale, raw
compute is not the bottleneck — the value of the cloud stretch goal
(Fargate/ECS, S3 for logs, DynamoDB for leaderboard) is isolation and
portfolio story, not throughput necessity.

## 10. Open items carried forward (not blocking week 1)

- Exact wall-clock deadline (100ms target) to be tuned once real
  student agents are being tested, per the original team doc.
- Whether the qualifying/seeding run against a benchmark agent needs its
  own scheduling tooling before Phase 4, or can reuse the week-1
  orchestrator as-is (likely yes, since the protocol doesn't change).
- GitHub account/org to fork the engine into (personal account assumed
  above; revisit if this becomes an ACM-org-owned project).
