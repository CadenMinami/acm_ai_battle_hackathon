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

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _is_allowed(candidate: Path) -> bool:
    candidate = candidate.resolve()
    for root in ALLOWED_ROOTS:
        allowed_root = Path(root).resolve()
        if candidate == allowed_root or candidate.is_relative_to(allowed_root):
            return True
    return False


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/bracket")
def bracket_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "bracket.html")


@app.get("/snapshot/latest")
def snapshot_latest(log: str) -> JSONResponse:
    log_path = Path(log).resolve()
    if not _is_allowed(log_path):
        return JSONResponse({"error": "path not allowed"}, status_code=403)
    if not log_path.exists():
        return JSONResponse({"error": "log not found"}, status_code=404)
    with open(log_path, "rb") as f:
        lines = f.read().splitlines()
    if not lines:
        return JSONResponse({"error": "log is empty"}, status_code=404)
    try:
        return JSONResponse(json.loads(lines[-1]))
    except json.JSONDecodeError:
        return JSONResponse({"error": "malformed json"}, status_code=400)


@app.get("/replay")
def replay(log: str) -> JSONResponse:
    log_path = Path(log).resolve()
    if not _is_allowed(log_path):
        return JSONResponse({"error": "path not allowed"}, status_code=403)
    if not log_path.exists():
        return JSONResponse({"error": "log not found"}, status_code=404)
    try:
        with open(log_path) as f:
            snapshots = [json.loads(line) for line in f if line.strip()]
    except json.JSONDecodeError:
        return JSONResponse({"error": "malformed json"}, status_code=400)
    return JSONResponse(snapshots)


@app.get("/results")
def results(path: str) -> JSONResponse:
    results_path = Path(path).resolve()
    if not _is_allowed(results_path):
        return JSONResponse({"error": "path not allowed"}, status_code=403)
    if not results_path.exists():
        return JSONResponse({"error": "results not found"}, status_code=404)
    try:
        return JSONResponse(json.loads(results_path.read_text()))
    except json.JSONDecodeError:
        return JSONResponse({"error": "malformed json"}, status_code=400)
