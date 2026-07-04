import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_SRC = REPO_ROOT / "engine" / "src"
GAMEDATA_PATH = REPO_ROOT / "engine" / "gamedata.json"

if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))
