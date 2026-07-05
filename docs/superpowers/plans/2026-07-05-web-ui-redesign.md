# Web UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a discoverable home page and restyle the viewer/bracket pages with a game-inspired Tailwind theme, fixing the URL-discoverability gap that caused a real bug and replacing the current bare/plain visual design.

**Architecture:** A new `GET /api/browse` endpoint lists real match logs and bracket results from disk; a new home page at `/` renders them as clickable cards linking into the existing viewer (moved to `/viewer`) and bracket page. All three pages share one precompiled Tailwind CSS file and a shared card-icon JS module.

**Tech Stack:** FastAPI (existing), plain HTML/CSS/JS (no framework, no bundler), Tailwind CSS v4 standalone CLI (build-time only, not a runtime dependency), pytest + FastAPI TestClient for the one new backend endpoint.

Spec: `docs/specs/2026-07-05-web-ui-redesign-design.md`

## Global Constraints

- Stay plain HTML/CSS/JS with no JS framework and no Node/npm build pipeline — Tailwind is precompiled once via its standalone CLI binary (downloaded directly, never installed via npm, never loaded from a CDN at runtime), so the site works fully offline at demo time.
- `/` is fully repurposed as the new home page; the existing match viewer moves to `/viewer` with no redirect kept at the old location — a deliberate one-time breaking change made before this project has real external users.
- The card-icon map in `cards.js` covers exactly the 10 names that can appear in a default-deck match — `Knight, Archer, Giant, Minions, Musketeer, BabyDragon, Balloon, Wizard, Tower, KingTower` — each mapped to a specific emoji (exact table in Task 2), with a `❔` fallback for anything unmapped.
- Team-colored circles (`#4a90d9` player 0 / `#d94a4a` player 1) stay as the primary way to distinguish sides on the canvas — icons and glow are layered on top, they never replace team coloring.
- The home page refreshes only via a manual "Refresh" button — no auto-polling.
- `GET /api/browse` is the only new backend endpoint; it reads from `LOGS_DIR`/`TOURNAMENT_DIR` (refactored out of the existing `ALLOWED_ROOTS` list in `web/server.py`) and gets real pytest coverage. Every other visual change in this plan is frontend-only and manually verified in a browser, matching this codebase's existing precedent for `index.html`/`bracket.html` (no test framework exists for pure frontend rendering in this repo).
- Use the project venv for every test run: `.venv/bin/python -m pytest`, never bare `pytest`.
- The full suite must pass with zero new failures or warnings after every task.
- The Tailwind CLI binary for this machine (macOS arm64) downloads from `https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64` — confirmed working (v4.3.2) by directly running the download-and-build pipeline before writing this plan. It is never committed to the repo (platform-specific binary); only the input CSS (`web/tailwind-input.css`) and the generated output (`web/static/theme.css`) are checked in.

---

### Task 1: Precompile the Tailwind design system

**Files:**
- Create: `web/tailwind-input.css`
- Create: `web/static/theme.css` (generated build output, committed)
- Modify: `README.md` (add a "Rebuilding the theme" note)

**Interfaces:**
- Produces: `web/static/theme.css`, linked via `<link rel="stylesheet" href="/static/theme.css">` by every page from Task 4 onward. Custom color utilities available to every page: `bg-arena`, `bg-arena-dark`, `border-arena-line`, `text-gold`, `bg-gold`, `text-team-blue`, `text-team-red`, `text-ink`, `text-ink-muted` (Tailwind auto-generates the full utility set — `bg-*`, `text-*`, `border-*`, `accent-*` etc. — for every `--color-*` variable declared in `@theme`).

- [ ] **Step 1: Write the Tailwind input CSS**

```css
/* web/tailwind-input.css */
@import "tailwindcss" source("./static");

@theme {
  --color-arena: #142914;
  --color-arena-dark: #0c1a0c;
  --color-arena-line: #2a4a2a;
  --color-gold: #d4af37;
  --color-team-blue: #4a90d9;
  --color-team-red: #d94a4a;
  --color-ink: #f5f5f0;
  --color-ink-muted: #9aa89a;
}

body {
  background-color: var(--color-arena-dark);
  color: var(--color-ink);
  font-family: "JetBrains Mono", ui-monospace, monospace;
}
```

- [ ] **Step 2: Download the standalone Tailwind CLI and build**

```bash
curl -sLo /tmp/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
chmod +x /tmp/tailwindcss
/tmp/tailwindcss -i web/tailwind-input.css -o web/static/theme.css --minify
```
Expected: prints `Done in <N>ms`, creates `web/static/theme.css`.

- [ ] **Step 3: Verify the output contains the expected theme**

```bash
grep -o "color-arena-dark:#0c1a0c" web/static/theme.css
grep -o "background-color:var(--color-arena-dark)" web/static/theme.css
```
Expected: both greps print a match. (Only `--color-arena-dark` and `--color-ink` appear in `:root` at this point — Tailwind v4 only emits `@theme` variables that are actually referenced somewhere, and no HTML file uses the other colors yet. The rest appear once Tasks 4/5/6 add HTML that uses them — each of those tasks reruns this exact build command.)

- [ ] **Step 4: Document the rebuild command in the README**

In `README.md`, after the "Docker Sandboxing Note" section, add:

`````markdown

## Rebuilding The Theme

If you change any Tailwind utility classes in `web/static/*.html`, regenerate `web/static/theme.css`:

```bash
curl -sLo /tmp/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
chmod +x /tmp/tailwindcss
/tmp/tailwindcss -i web/tailwind-input.css -o web/static/theme.css --minify
```

Replace `tailwindcss-macos-arm64` with your platform's binary name (`tailwindcss-linux-x64`, `tailwindcss-windows-x64.exe`, etc. — see the [releases page](https://github.com/tailwindlabs/tailwindcss/releases/latest)) if you're not on Apple Silicon. This is the only build step in the project — everything else is plain HTML/CSS/JS served directly by FastAPI.
`````

- [ ] **Step 5: Commit**

```bash
git add web/tailwind-input.css web/static/theme.css README.md
git commit -m "Add precompiled Tailwind design system"
```

---

### Task 2: Build the shared card-icon module

**Files:**
- Create: `web/static/cards.js`

**Interfaces:**
- Produces: a global `getCardIcon(cardName: string) -> string` function (plain script, no ES module — loaded via `<script src="/static/cards.js">` before `viewer.js`, matching this repo's existing non-module script pattern). Consumed by Task 5's canvas redesign.

- [ ] **Step 1: Write the module**

```javascript
// web/static/cards.js
// Shared card-name -> icon map for the canvas renderer (viewer.js). These
// are the 10 names that can appear in a default-deck match (confirmed
// against engine/src/clasher/player.py's default deck, plus the two tower
// entity types). Anything not in this map falls back to a generic icon
// instead of breaking the renderer, in case the deck ever changes.
const CARD_ICONS = {
  Knight: "⚔️",
  Archer: "🏹",
  Giant: "👹",
  Minions: "🦇",
  Musketeer: "🔫",
  BabyDragon: "🐉",
  Balloon: "🎈",
  Wizard: "🧙",
  Tower: "🗼",
  KingTower: "👑",
};

const CARD_ICON_FALLBACK = "❔";

function getCardIcon(cardName) {
  return CARD_ICONS[cardName] || CARD_ICON_FALLBACK;
}
```

(The values are escaped Unicode for the emoji — this avoids any editor/encoding ambiguity. They decode to: Knight ⚔️, Archer 🏹, Giant 👹, Minions 🦇, Musketeer 🔫, BabyDragon 🐉, Balloon 🎈, Wizard 🧙, Tower 🗼, KingTower 👑, fallback ❔.)

- [ ] **Step 2: Verify in a browser console**

```bash
.venv/bin/python -m uvicorn web.server:app --port 8000 &
```
Open `http://localhost:8000/` in a browser, open dev tools, and in the console load the script and check it:
```javascript
const s = document.createElement("script"); s.src = "/static/cards.js"; document.head.appendChild(s);
```
Then, after it loads:
```javascript
getCardIcon("Knight")   // "⚔️"
getCardIcon("Unicorn")  // "❔"
```
Expected: matches the values above. Stop the server (`kill %1` or find the process on port 8000).

- [ ] **Step 3: Commit**

```bash
git add web/static/cards.js
git commit -m "Add shared card-icon module"
```

---

### Task 3: Add `GET /api/browse`

**Files:**
- Modify: `web/server.py:8-9` (refactor `ALLOWED_ROOTS` into two named constants)
- Modify: `web/server.py` (add the new route)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Produces: `GET /api/browse -> {"logs": [{"path": str, "mtime": float, "size": int}, ...], "results": [{"path": str, "mtime": float, "size": int}, ...]}`, both lists sorted newest-first by `mtime`, empty lists if the directories don't exist. Consumed by Task 4's home page.
- Also produces (renamed from existing code): `LOGS_DIR: Path` and `TOURNAMENT_DIR: Path` module-level constants in `web/server.py`, replacing the inline paths inside the existing `ALLOWED_ROOTS` list. `ALLOWED_ROOTS = [LOGS_DIR, TOURNAMENT_DIR]` — same value as before, same behavior for `_is_allowed()`, just named.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_server.py`, add `import os` to the top imports (alongside the existing `import json`, `import sys`), then add:

```python
def test_browse_lists_logs_and_results_sorted_newest_first(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    tournament_dir = tmp_path / "tournament"
    tournament_dir.mkdir()
    monkeypatch.setattr(web_server, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(web_server, "TOURNAMENT_DIR", tournament_dir)

    old_log = logs_dir / "old.jsonl"
    old_log.write_text('{"tick": 1}\n')
    new_log = logs_dir / "new.jsonl"
    new_log.write_text('{"tick": 1}\n')
    os.utime(old_log, (1_000_000, 1_000_000))
    os.utime(new_log, (2_000_000, 2_000_000))

    results_file = tournament_dir / "results.json"
    results_file.write_text('{"rounds": []}')

    response = client.get("/api/browse")

    assert response.status_code == 200
    data = response.json()
    assert [entry["path"] for entry in data["logs"]] == [str(new_log), str(old_log)]
    assert len(data["results"]) == 1
    assert data["results"][0]["path"] == str(results_file)


def test_browse_returns_empty_lists_when_directories_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(web_server, "LOGS_DIR", tmp_path / "nonexistent_logs")
    monkeypatch.setattr(web_server, "TOURNAMENT_DIR", tmp_path / "nonexistent_tournament")

    response = client.get("/api/browse")

    assert response.status_code == 200
    assert response.json() == {"logs": [], "results": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -v -k browse`
Expected: FAIL — `AttributeError: <module 'web.server' ...> does not have the attribute 'LOGS_DIR'` (from the `monkeypatch.setattr` call).

- [ ] **Step 3: Refactor `ALLOWED_ROOTS` into named constants**

In `web/server.py`, this repo's existing convention (`orchestrator/match.py`, `orchestrator/match_log.py`, `tournament/bracket.py`) uses `typing.List`/`Dict` rather than bare built-in generics, so add that import too. Replace:
```python
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"
ALLOWED_ROOTS = [Path("logs").resolve(), Path("tournament").resolve()]
```
with:
```python
import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGS_DIR = Path("logs").resolve()
TOURNAMENT_DIR = Path("tournament").resolve()
ALLOWED_ROOTS = [LOGS_DIR, TOURNAMENT_DIR]
```

- [ ] **Step 4: Add the endpoint**

In `web/server.py`, add this function and route (after `_is_allowed`, before `@app.get("/")`):

```python
def _list_directory(directory: Path, pattern: str) -> List[Dict[str, Any]]:
    if not directory.exists():
        return []
    entries = []
    for path in directory.glob(pattern):
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append({"path": str(path), "mtime": stat.st_mtime, "size": stat.st_size})
    entries.sort(key=lambda entry: entry["mtime"], reverse=True)
    return entries


@app.get("/api/browse")
def browse() -> JSONResponse:
    return JSONResponse({
        "logs": _list_directory(LOGS_DIR, "*.jsonl"),
        "results": _list_directory(TOURNAMENT_DIR, "*.json"),
    })
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -v -k browse`
Expected: `2 passed`

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (83 + 2 new = 85), no warnings.

- [ ] **Step 7: Commit**

```bash
git add web/server.py tests/test_web_server.py
git commit -m "Add GET /api/browse endpoint"
```

---

### Task 4: Build the home page and move the viewer to `/viewer`

**Files:**
- Rename: `web/static/index.html` → `web/static/viewer.html` (no content change)
- Create: `web/static/index.html` (new home page)
- Create: `web/static/home.js`
- Modify: `web/server.py` (add `/viewer` route)
- Modify: `web/static/bracket.html:47` (fix the now-broken replay link)
- Modify: `tests/test_web_server.py` (replace the test that asserted `/` served viewer markup)

**Interfaces:**
- Consumes: `GET /api/browse` (Task 3).
- Produces: `GET /` now serves the home page; `GET /viewer` serves the (content-unchanged) match viewer. Both consumed by a human clicking around, and by `bracket.html`'s "watch" links, which must point at `/viewer` from now on.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_server.py`, replace this existing test:

```python
def test_index_returns_viewer_markup():
    response = client.get("/")

    assert response.status_code == 200
    assert "Battle Sim Viewer" in response.text
    assert '<canvas id="board"' in response.text
    assert "/static/viewer.js" in response.text
```

with these two:

```python
def test_index_returns_home_page_markup():
    response = client.get("/")

    assert response.status_code == 200
    assert "Battle Sim" in response.text
    assert "/static/home.js" in response.text


def test_viewer_route_returns_viewer_markup():
    response = client.get("/viewer")

    assert response.status_code == 200
    assert "Battle Sim Viewer" in response.text
    assert '<canvas id="board"' in response.text
    assert "/static/viewer.js" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -v -k "home_page or viewer_route"`
Expected: FAIL — `test_index_returns_home_page_markup` fails on its second assertion (`/` still serves the old viewer, which has no `/static/home.js` reference); `test_viewer_route_returns_viewer_markup` fails with a 404 (no `/viewer` route yet).

- [ ] **Step 3: Move the existing viewer**

```bash
git mv web/static/index.html web/static/viewer.html
```

- [ ] **Step 4: Add the `/viewer` route**

In `web/server.py`, add (near the existing `@app.get("/")` route):

```python
@app.get("/viewer")
def viewer_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "viewer.html")
```

- [ ] **Step 5: Write the new home page**

```html
<!-- web/static/index.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Battle Sim</title>
  <link rel="stylesheet" href="/static/theme.css">
</head>
<body class="min-h-screen bg-arena-dark text-ink font-mono p-8">
  <header class="max-w-4xl mx-auto mb-8 flex items-center justify-between">
    <h1 class="text-2xl font-bold text-gold">Battle Sim</h1>
    <button id="refresh" class="border border-arena-line px-3 py-1 rounded hover:border-gold hover:text-gold transition-colors">Refresh</button>
  </header>

  <main class="max-w-4xl mx-auto">
    <section id="bracket-section" class="mb-10 hidden">
      <h2 class="text-lg text-ink-muted mb-3">Brackets</h2>
      <div id="bracket-list" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4"></div>
    </section>

    <section id="matches-section">
      <h2 class="text-lg text-ink-muted mb-3">Recent Matches</h2>
      <div id="matches-list" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4"></div>
    </section>

    <p id="empty-state" class="hidden text-ink-muted mt-10">
      No matches yet — run one via the CLI, then hit Refresh:
      <br>
      <code class="block mt-2 bg-arena p-3 rounded text-sm">python -m orchestrator.cli --agent-a "python agents/baseline_random/agent.py" --agent-b "python agents/baseline_random/agent.py" --seed 1 --log-path logs/example_match.jsonl</code>
    </p>
  </main>

  <script src="/static/home.js"></script>
</body>
</html>
```

- [ ] **Step 6: Write `home.js`**

```javascript
// web/static/home.js
const matchesList = document.getElementById("matches-list");
const bracketList = document.getElementById("bracket-list");
const bracketSection = document.getElementById("bracket-section");
const matchesSection = document.getElementById("matches-section");
const emptyState = document.getElementById("empty-state");
const refreshButton = document.getElementById("refresh");

function formatTime(mtime) {
  return new Date(mtime * 1000).toLocaleString();
}

function makeCard(title, subtitle, href) {
  const a = document.createElement("a");
  a.href = href;
  a.className = "block border border-arena-line rounded p-4 hover:border-gold hover:text-gold transition-colors";
  a.innerHTML = "";
  const titleDiv = document.createElement("div");
  titleDiv.className = "font-bold";
  titleDiv.textContent = title;
  const subtitleDiv = document.createElement("div");
  subtitleDiv.className = "text-sm text-ink-muted mt-1";
  subtitleDiv.textContent = subtitle;
  a.appendChild(titleDiv);
  a.appendChild(subtitleDiv);
  return a;
}

async function loadBrowse() {
  matchesList.innerHTML = "";
  bracketList.innerHTML = "";

  const response = await fetch("/api/browse");
  const data = await response.json();

  if (data.logs.length === 0 && data.results.length === 0) {
    emptyState.classList.remove("hidden");
    matchesSection.classList.add("hidden");
    bracketSection.classList.add("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  if (data.results.length > 0) {
    bracketSection.classList.remove("hidden");
    for (const result of data.results) {
      const href = `/bracket?results=${encodeURIComponent(result.path)}`;
      bracketList.appendChild(makeCard(result.path, formatTime(result.mtime), href));
    }
  } else {
    bracketSection.classList.add("hidden");
  }

  matchesSection.classList.remove("hidden");
  for (const log of data.logs) {
    const href = `/viewer?log=${encodeURIComponent(log.path)}&mode=replay`;
    matchesList.appendChild(makeCard(log.path, formatTime(log.mtime), href));
  }
}

refreshButton.addEventListener("click", loadBrowse);
loadBrowse();
```

(Uses `textContent`, not `innerHTML`, for the user-visible file path/timestamp text — avoids the unescaped-`innerHTML` pattern flagged as a Minor finding on `bracket.html` during the original build.)

- [ ] **Step 7: Fix the now-broken replay link in `bracket.html`**

In `web/static/bracket.html`, change:
```javascript
              ? `<a href="/?log=${encodeURIComponent(match.log)}&mode=replay">watch</a>`
```
to:
```javascript
              ? `<a href="/viewer?log=${encodeURIComponent(match.log)}&mode=replay">watch</a>`
```
(This is the only change to `bracket.html` in this task — the full visual redesign happens in Task 6. Without this fix, "watch" links would open the new home page instead of a replay.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -v`
Expected: all pass, including the two new/replaced tests.

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass, no warnings.

- [ ] **Step 10: Rebuild the theme**

```bash
curl -sLo /tmp/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
chmod +x /tmp/tailwindcss
/tmp/tailwindcss -i web/tailwind-input.css -o web/static/theme.css --minify
```

- [ ] **Step 11: Manually verify in a browser**

```bash
.venv/bin/python -m uvicorn web.server:app --port 8000
```
Open `http://localhost:8000/`. Expected: styled home page (dark arena background, gold accents), listing real entries from `logs/` and `tournament/` if any exist on disk, or the empty-state message if not. Click "Refresh" — list re-fetches. If logs exist, click a match card — opens `/viewer?log=...&mode=replay` and plays back correctly (still using the old, not-yet-redesigned canvas from Task 5). Stop the server.

- [ ] **Step 12: Commit**

```bash
git add web/static/index.html web/static/viewer.html web/static/home.js web/static/bracket.html web/server.py tests/test_web_server.py web/static/theme.css
git commit -m "Add home page, move viewer to /viewer"
```

---

### Task 5: Redesign the viewer (chrome + canvas)

**Files:**
- Modify: `web/static/viewer.html` (Tailwind chrome, add `cards.js` script tag)
- Modify: `web/static/viewer.js` (canvas redesign: icons, glow, arena texture, HUD)

**Interfaces:**
- Consumes: `getCardIcon(cardName)` from `cards.js` (Task 2).

- [ ] **Step 1: Rewrite `viewer.html`**

```html
<!-- web/static/viewer.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Battle Sim Viewer</title>
  <link rel="stylesheet" href="/static/theme.css">
</head>
<body class="bg-arena-dark text-ink font-mono min-h-screen">
  <div class="max-w-md mx-auto py-4 flex items-center justify-center gap-3">
    <button id="playPause" class="border border-arena-line px-3 py-1 rounded hover:border-gold hover:text-gold transition-colors">Play</button>
    <input id="scrub" type="range" min="0" max="0" value="0" class="flex-1 accent-gold">
    <select id="speed" class="bg-arena border border-arena-line rounded px-2 py-1">
      <option value="200">1x</option>
      <option value="100">2x</option>
      <option value="50">4x</option>
      <option value="25">8x</option>
    </select>
  </div>
  <canvas id="board" width="360" height="640" class="block mx-auto border-2 border-arena-line rounded"></canvas>
  <script src="/static/cards.js"></script>
  <script src="/static/viewer.js"></script>
</body>
</html>
```

- [ ] **Step 2: Rewrite the `draw` function and add the arena background in `viewer.js`**

Replace the existing `draw(snapshot)` function (and everything above it starting from `const TILE = ...`) with:

```javascript
const TILE = 20; // pixels per arena tile (18 wide x 32 tall -> 360x640)
const ARENA_WIDTH = 360;
const ARENA_HEIGHT = 640;

function drawArenaBackground() {
  const bgGradient = ctx.createLinearGradient(0, 0, 0, ARENA_HEIGHT);
  bgGradient.addColorStop(0, "#1b3a2e");
  bgGradient.addColorStop(0.5, "#173322");
  bgGradient.addColorStop(1, "#1b3a2e");
  ctx.fillStyle = bgGradient;
  ctx.fillRect(0, 0, ARENA_WIDTH, ARENA_HEIGHT);

  const riverGradient = ctx.createLinearGradient(0, ARENA_HEIGHT / 2 - 18, 0, ARENA_HEIGHT / 2 + 18);
  riverGradient.addColorStop(0, "rgba(74, 144, 217, 0.15)");
  riverGradient.addColorStop(0.5, "rgba(74, 144, 217, 0.35)");
  riverGradient.addColorStop(1, "rgba(74, 144, 217, 0.15)");
  ctx.fillStyle = riverGradient;
  ctx.fillRect(0, ARENA_HEIGHT / 2 - 18, ARENA_WIDTH, 36);

  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
  ctx.lineWidth = 1;
  [ARENA_WIDTH * 0.3, ARENA_WIDTH * 0.7].forEach((x) => {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, ARENA_HEIGHT);
    ctx.stroke();
  });
}

function draw(snapshot) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawArenaBackground();
  if (!snapshot) return;

  for (const entity of snapshot.entities) {
    const x = entity.x * TILE;
    const y = (32 - entity.y) * TILE; // flip so player 0 renders at the bottom
    const teamColor = entity.player_id === 0 ? "#4a90d9" : "#d94a4a";
    const radius = entity.is_tower ? 12 : 8;

    ctx.save();
    ctx.shadowColor = teamColor;
    ctx.shadowBlur = entity.is_tower ? 14 : 8;
    ctx.fillStyle = teamColor;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `${entity.is_tower ? 14 : 11}px sans-serif`;
    ctx.fillText(getCardIcon(entity.card), x, y);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";

    ctx.fillStyle = "#fff";
    ctx.font = "9px monospace";
    ctx.fillText(entity.card, x + radius + 3, y + 3);
  }

  ctx.fillStyle = "#f5f5f0";
  ctx.font = "bold 13px monospace";
  ctx.fillText(`tick ${snapshot.tick}`, 10, 18);

  snapshot.players.forEach((p, i) => {
    const color = i === 0 ? "#4a90d9" : "#d94a4a";
    const y = 36 + i * 16;
    ctx.fillStyle = color;
    ctx.font = "11px sans-serif";
    ctx.fillText("💧", 10, y);
    ctx.fillStyle = "#f5f5f0";
    ctx.font = "11px monospace";
    ctx.fillText(`${p.elixir.toFixed(1)}  king ${Math.round(p.king_hp)}`, 26, y);
  });
}
```

(`💧` is the escaped droplet emoji 💧, used as a small elixir indicator per player.) Leave everything below this (the `if (!logPath) { ... } else if (mode === "live") { ... } else { ... }` block) unchanged — only `draw` and the constants above it change.

- [ ] **Step 3: Rebuild the theme**

```bash
curl -sLo /tmp/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
chmod +x /tmp/tailwindcss
/tmp/tailwindcss -i web/tailwind-input.css -o web/static/theme.css --minify
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (no test covers canvas rendering — this is a frontend-only change). No new failures or warnings.

- [ ] **Step 5: Manually verify in a browser**

```bash
mkdir -p logs
.venv/bin/python -c "
from pathlib import Path
from orchestrator.match import run_match
run_match(['.venv/bin/python', 'agents/baseline_random/agent.py'], ['.venv/bin/python', 'agents/baseline_random/agent.py'], seed=1, log_path=Path('logs/theme_check.jsonl'))
"
.venv/bin/python -m uvicorn web.server:app --port 8000
```
Open `http://localhost:8000/viewer?log=logs/theme_check.jsonl&mode=replay`, click Play. Expected: styled controls (dark theme, gold hover states), a textured arena background with a visible river band across the middle, team-colored circles with a matching colored glow, an icon on each entity distinguishing card type, and a restyled HUD with a droplet icon next to each player's elixir. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add web/static/viewer.html web/static/viewer.js web/static/theme.css
git commit -m "Redesign the viewer with card icons and an arena background"
```

---

### Task 6: Redesign the bracket page as a bracket tree

**Files:**
- Modify: `web/static/bracket.html` (full rewrite)

**Interfaces:**
- Consumes: `GET /results` (existing, unchanged).

- [ ] **Step 1: Rewrite `bracket.html`**

```html
<!-- web/static/bracket.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Battle Sim Bracket</title>
  <link rel="stylesheet" href="/static/theme.css">
</head>
<body class="bg-arena-dark text-ink font-mono min-h-screen p-8">
  <h1 class="text-xl text-gold mb-6 text-center">Tournament Bracket</h1>
  <div id="bracket" class="flex gap-10 overflow-x-auto justify-center"></div>

  <script>
    const params = new URLSearchParams(window.location.search);
    const resultsPath = params.get("results") || "tournament/results.json";
    const bracketEl = document.getElementById("bracket");

    function renderLoadError(err) {
      bracketEl.innerHTML = "";
      const p = document.createElement("p");
      p.className = "text-team-red";
      p.textContent = `Could not load results file: ${resultsPath}` + (err && err.message ? ` (${err.message})` : "");
      bracketEl.appendChild(p);
    }

    function matchCard(match) {
      const div = document.createElement("div");
      div.className = "border border-arena-line rounded p-3 bg-arena min-w-[180px] mb-4";

      const rowA = document.createElement("div");
      rowA.className = match.winner === match.a ? "text-gold font-bold" : "text-ink-muted";
      rowA.textContent = match.a;

      const rowB = document.createElement("div");
      rowB.className = match.winner === match.b ? "text-gold font-bold" : "text-ink-muted";
      rowB.textContent = match.b ?? "—";

      const linkRow = document.createElement("div");
      linkRow.className = "mt-2";
      if (match.log) {
        const a = document.createElement("a");
        a.href = `/viewer?log=${encodeURIComponent(match.log)}&mode=replay`;
        a.className = "text-team-blue hover:text-gold text-xs";
        a.textContent = "watch";
        linkRow.appendChild(a);
      } else {
        const span = document.createElement("span");
        span.className = "text-ink-muted text-xs";
        span.textContent = "(bye)";
        linkRow.appendChild(span);
      }

      div.appendChild(rowA);
      div.appendChild(rowB);
      div.appendChild(linkRow);
      return div;
    }

    fetch(`/results?path=${encodeURIComponent(resultsPath)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!Array.isArray(data.rounds) || data.rounds.length === 0) {
          throw new Error("no rounds in results");
        }
        bracketEl.innerHTML = "";
        data.rounds.forEach((round, roundIndex) => {
          const wrapper = document.createElement("div");
          wrapper.className = "flex flex-col justify-around";
          wrapper.style.gap = `${16 * Math.pow(2, roundIndex)}px`;

          const label = document.createElement("div");
          label.className = "text-ink-muted text-xs text-center mb-2";
          label.textContent = roundIndex + 1 === data.rounds.length ? "Final" : `Round ${roundIndex + 1}`;
          wrapper.appendChild(label);

          round.forEach((match) => wrapper.appendChild(matchCard(match)));
          bracketEl.appendChild(wrapper);
        });
      })
      .catch(renderLoadError);
  </script>
</body>
</html>
```

- [ ] **Step 2: Rebuild the theme**

```bash
curl -sLo /tmp/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
chmod +x /tmp/tailwindcss
/tmp/tailwindcss -i web/tailwind-input.css -o web/static/theme.css --minify
```

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass, no new failures or warnings (bracket page rendering has no automated coverage, matching existing precedent).

- [ ] **Step 4: Manually verify in a browser**

```bash
mkdir -p logs
.venv/bin/python -c "
from pathlib import Path
from tournament.bracket import run_bracket
agents = [{'name': f'agent{i}', 'command': ['.venv/bin/python', 'agents/baseline_random/agent.py']} for i in range(4)]
run_bracket(agents, seed=1, logs_dir=Path('logs'), results_path=Path('tournament/results.json'))
"
.venv/bin/python -m uvicorn web.server:app --port 8000
```
Open `http://localhost:8000/bracket?results=tournament/results.json`. Expected: a styled bracket-tree layout (one column per round, "Round 1"/"Final" labels, gold-highlighted winners, increasing vertical spacing toward the final), with working "watch" links opening `/viewer?log=...` replays. Test the error path too: open `http://localhost:8000/bracket?results=nonexistent.json` — expect a visible red error message, not a blank page. Stop the server.

- [ ] **Step 5: Commit**

```bash
git add web/static/bracket.html web/static/theme.css
git commit -m "Redesign the bracket page as a bracket tree"
```

---

### Task 7: Update the README for the new routes

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update the "Launch The Web Viewer" section**

In `README.md`, replace:

```markdown
The replay viewer needs a `log` and `mode` query param — it doesn't work at the bare `/` URL. Open `http://localhost:8000/?log=logs/example_match.jsonl&mode=replay` to replay the match from the CLI example above (use `mode=live` while a match with `--log-path` is still running). For the bracket page, open `http://localhost:8000/bracket?results=tournament/results.json`. Replay links load JSONL files from the allowed `logs/` directory, and bracket results load from `tournament/`.
```

with:

```markdown
Open `http://localhost:8000/` — the home page lists every match log under `logs/` and any bracket results under `tournament/` as clickable cards; click one to open its replay or bracket view. To jump straight to a specific match, open `http://localhost:8000/viewer?log=logs/example_match.jsonl&mode=replay` directly (use `mode=live` while a match with `--log-path` is still running). Replay links load JSONL files from the allowed `logs/` directory, and bracket results load from `tournament/`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Update README for the new home page route"
```

---
