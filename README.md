# AI Agent Battle Simulator

This project is an ACM club AI-agent battle simulator. It wraps a vendored Clash-style Python battle engine with an orchestrator that runs two student agents as subprocesses, records per-tick JSONL replays, runs simple single-elimination brackets, and serves a lightweight FastAPI web viewer for match replays and bracket results.

## Setup

Create and activate a virtual environment, then install the project dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run A Single Match

Run two agents through the orchestrator CLI:

```bash
.venv/bin/python -m orchestrator.cli \
  --agent-a ".venv/bin/python agents/baseline_random/agent.py" \
  --agent-b ".venv/bin/python agents/baseline_random/agent.py" \
  --seed 123 \
  --log-path logs/example_match.jsonl
```

The CLI prints a JSON match result. When `--log-path` is provided, the replay is written as one JSON snapshot per line.

Note on `--seed`: it makes the battle engine itself deterministic, but `agents/baseline_random/agent.py` uses Python's own unseeded `random` module in its own subprocess — so re-running the same seed with a stochastic agent like the baseline will not necessarily reproduce the same match outcome.

## Run A Bracket

Use `tournament.bracket.run_bracket` with agent entries shaped as `{"name": str, "command": list[str]}`:

Save this as `run_bracket_example.py` in the repo root:

```python
from pathlib import Path
from tournament.bracket import run_bracket

if __name__ == "__main__":
    agents = [
        {"name": f"agent{i}", "command": [".venv/bin/python", "agents/baseline_random/agent.py"]}
        for i in range(4)
    ]

    results = run_bracket(
        agents,
        seed=123,
        logs_dir=Path("logs"),
        results_path=Path("tournament/results.json"),
    )
    print(results)
```

Then run it from the repo root:

```bash
.venv/bin/python run_bracket_example.py
```

Use a saved `.py` file, not a heredoc, `python -c`, or stdin-piped snippet: matches within a round run in separate worker processes, and Python's multiprocessing needs a real file on disk to hand those workers.

## Running Multiple Simulations Concurrently

Matchups within a single bracket round already run concurrently; there is no extra flag to turn on. By default, the number of concurrent worker processes is capped at the machine's CPU count (`os.cpu_count()`).

Pass `max_workers` to `run_bracket()` if you want to override that cap:

```python
run_bracket(
    agents,
    seed=123,
    logs_dir=Path("logs"),
    results_path=Path("tournament/results.json"),
    max_workers=4,
)
```

To see the concurrency in practice, run a bracket with enough agents that the first round takes a few real seconds. Eight or more baseline agents is usually enough; use the saved-file pattern from "Run A Bracket" and expand the `range(4)` to `range(8)` or higher.

While that bracket is running, start the web viewer in another terminal from the repo root:

```bash
uvicorn web.server:app --reload
```

Open multiple browser tabs, each pointed at a different round-1 match log in live mode:

```text
http://localhost:8000/viewer?log=logs/round1_match1.jsonl&mode=live
http://localhost:8000/viewer?log=logs/round1_match2.jsonl&mode=live
```

Seeing several matches animate at once, in separate tabs, at the same time, is the concurrency made visible. A full bracket run also finishes well below the wall-clock time of running every match one-by-one, especially at larger agent counts such as a 32-agent bracket.

## Launch The Web Viewer

Start the FastAPI app:

```bash
uvicorn web.server:app --reload
```

Open `http://localhost:8000/` — the home page lists every match log under `logs/` and any bracket results under `tournament/` as clickable cards; click one to open its replay or bracket view. To jump straight to a specific match, open `http://localhost:8000/viewer?log=logs/example_match.jsonl&mode=replay` directly (use `mode=live` while a match with `--log-path` is still running). Replay links load JSONL files from the allowed `logs/` directory, and bracket results load from `tournament/`.

## Docker Sandboxing Note

A Docker image definition exists at `docker/agent.Dockerfile` for future agent sandboxing work. Today, agent commands are opaque `list[str]` values passed to subprocesses, and the tournament runner does not enforce containerization. Treat student-submitted commands as trusted-LAN-only until the club decides and implements the sandbox policy.

## Rebuilding The Theme

If you change any Tailwind utility classes in `web/static/*.html`, regenerate `web/static/theme.css`:

```bash
curl -sLo /tmp/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64
chmod +x /tmp/tailwindcss
/tmp/tailwindcss -i web/tailwind-input.css -o web/static/theme.css --minify
```

Replace `tailwindcss-macos-arm64` with your platform's binary name (`tailwindcss-linux-x64`, `tailwindcss-windows-x64.exe`, etc. — see the [releases page](https://github.com/tailwindlabs/tailwindcss/releases/latest)) if you're not on Apple Silicon. This is the only build step in the project — everything else is plain HTML/CSS/JS served directly by FastAPI.
