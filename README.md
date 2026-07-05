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
python -m orchestrator.cli \
  --agent-a "python agents/baseline_random/agent.py" \
  --agent-b "python agents/baseline_random/agent.py" \
  --seed 123 \
  --log-path logs/example_match.jsonl
```

The CLI prints a JSON match result. When `--log-path` is provided, the replay is written as one JSON snapshot per line.

## Run A Bracket

Use `tournament.bracket.run_bracket` with agent entries shaped as `{"name": str, "command": list[str]}`:

```bash
python - <<'PY'
from pathlib import Path
from tournament.bracket import run_bracket

agents = [
    {"name": f"agent{i}", "command": ["python", "agents/baseline_random/agent.py"]}
    for i in range(4)
]

results = run_bracket(
    agents,
    seed=123,
    logs_dir=Path("logs"),
    results_path=Path("tournament/results.json"),
)
print(results)
PY
```

## Launch The Web Viewer

Start the FastAPI app:

```bash
uvicorn web.server:app --reload
```

Open `http://localhost:8000/` for the replay viewer, or `http://localhost:8000/bracket?results=tournament/results.json` for the bracket page. Replay links load JSONL files from the allowed `logs/` directory, and bracket results load from `tournament/`.

## Docker Sandboxing Note

A Docker image definition exists at `docker/agent.Dockerfile` for future agent sandboxing work. Today, agent commands are opaque `list[str]` values passed to subprocesses, and the tournament runner does not enforce containerization. Treat student-submitted commands as trusted-LAN-only until the club decides and implements the sandbox policy.
