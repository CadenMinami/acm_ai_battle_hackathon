import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import web.server as web_server


client = TestClient(web_server.app)


def write_jsonl(path, snapshots):
    path.write_text("\n".join(json.dumps(snapshot) for snapshot in snapshots) + "\n")


def allow_tmp_path(monkeypatch, tmp_path):
    monkeypatch.setattr(web_server, "ALLOWED_ROOTS", [tmp_path.resolve()])


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


def test_replay_returns_snapshots_in_order(tmp_path, monkeypatch):
    allow_tmp_path(monkeypatch, tmp_path)
    log_path = tmp_path / "match.jsonl"
    snapshots = [
        {"tick": 1, "entities": []},
        {"tick": 2, "entities": [{"id": "knight"}]},
        {"tick": 3, "entities": [{"id": "giant"}]},
    ]
    write_jsonl(log_path, snapshots)

    response = client.get("/replay", params={"log": str(log_path)})

    assert response.status_code == 200
    assert response.json() == snapshots


def test_snapshot_latest_returns_last_snapshot(tmp_path, monkeypatch):
    allow_tmp_path(monkeypatch, tmp_path)
    log_path = tmp_path / "match.jsonl"
    snapshots = [
        {"tick": 1, "winner": None},
        {"tick": 2, "winner": None},
        {"tick": 3, "winner": 0},
    ]
    write_jsonl(log_path, snapshots)

    response = client.get("/snapshot/latest", params={"log": str(log_path)})

    assert response.status_code == 200
    assert response.json() == snapshots[-1]


def test_snapshot_latest_empty_file_returns_404(tmp_path, monkeypatch):
    allow_tmp_path(monkeypatch, tmp_path)
    log_path = tmp_path / "empty.jsonl"
    log_path.write_text("")

    response = client.get("/snapshot/latest", params={"log": str(log_path)})

    assert response.status_code == 404
    assert response.json() == {"error": "log is empty"}


def test_missing_paths_return_404(tmp_path, monkeypatch):
    allow_tmp_path(monkeypatch, tmp_path)
    missing_log = tmp_path / "missing.jsonl"
    missing_results = tmp_path / "missing_results.json"

    replay_response = client.get("/replay", params={"log": str(missing_log)})
    latest_response = client.get("/snapshot/latest", params={"log": str(missing_log)})
    results_response = client.get("/results", params={"path": str(missing_results)})

    assert replay_response.status_code == 404
    assert replay_response.json() == {"error": "log not found"}
    assert latest_response.status_code == 404
    assert latest_response.json() == {"error": "log not found"}
    assert results_response.status_code == 404
    assert results_response.json() == {"error": "results not found"}


def test_results_returns_parsed_json(tmp_path, monkeypatch):
    allow_tmp_path(monkeypatch, tmp_path)
    results_path = tmp_path / "results.json"
    results = {
        "winner": "agent-a",
        "scores": {"agent-a": 3, "agent-b": 1},
        "matches": [{"id": "final", "duration": 120}],
    }
    results_path.write_text(json.dumps(results))

    response = client.get("/results", params={"path": str(results_path)})

    assert response.status_code == 200
    assert response.json() == results


def test_disallowed_path_returns_403_before_existence_check(tmp_path, monkeypatch):
    monkeypatch.setattr(web_server, "ALLOWED_ROOTS", [(tmp_path / "allowed").resolve()])
    outside_path = tmp_path / "outside.jsonl"

    response = client.get("/replay", params={"log": str(outside_path)})

    assert response.status_code == 403
    assert response.json() == {"error": "path not allowed"}


def test_results_malformed_json_returns_400(tmp_path, monkeypatch):
    allow_tmp_path(monkeypatch, tmp_path)
    results_path = tmp_path / "results.json"
    results_path.write_text("not json")

    response = client.get("/results", params={"path": str(results_path)})

    assert response.status_code == 400
    assert response.json() == {"error": "malformed json"}
