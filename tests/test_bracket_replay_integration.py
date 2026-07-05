import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tournament.bracket import run_bracket
import web.server as web_server

BASELINE = [sys.executable, str(Path(__file__).resolve().parent.parent / "agents" / "baseline_random" / "agent.py")]


def test_bracket_produced_log_is_replayable(tmp_path, monkeypatch):
    agents = [{"name": f"agent{i}", "command": BASELINE} for i in range(2)]
    results_path = tmp_path / "results.json"

    run_bracket(
        agents,
        seed=7,
        logs_dir=tmp_path / "logs",
        results_path=results_path,
    )

    results = json.loads(results_path.read_text())
    log_path = Path(results["rounds"][0][0]["log"])
    monkeypatch.setattr(web_server, "ALLOWED_ROOTS", [tmp_path.resolve()])

    client = TestClient(web_server.app)
    response = client.get("/replay", params={"log": str(log_path)})

    assert response.status_code == 200
    snapshots = response.json()
    assert snapshots
    assert all({"tick", "entities", "players"} <= snapshot.keys() for snapshot in snapshots)
