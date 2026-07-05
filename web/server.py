import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/bracket")
def bracket_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "bracket.html")


@app.get("/snapshot/latest")
def snapshot_latest(log: str) -> JSONResponse:
    log_path = Path(log)
    if not log_path.exists():
        return JSONResponse({"error": "log not found"}, status_code=404)
    with open(log_path, "rb") as f:
        lines = f.read().splitlines()
    if not lines:
        return JSONResponse({"error": "log is empty"}, status_code=404)
    return JSONResponse(json.loads(lines[-1]))


@app.get("/replay")
def replay(log: str) -> JSONResponse:
    log_path = Path(log)
    if not log_path.exists():
        return JSONResponse({"error": "log not found"}, status_code=404)
    with open(log_path) as f:
        snapshots = [json.loads(line) for line in f if line.strip()]
    return JSONResponse(snapshots)


@app.get("/results")
def results(path: str) -> JSONResponse:
    results_path = Path(path)
    if not results_path.exists():
        return JSONResponse({"error": "results not found"}, status_code=404)
    return JSONResponse(json.loads(results_path.read_text()))
