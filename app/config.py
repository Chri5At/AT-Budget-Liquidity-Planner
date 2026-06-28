"""Central configuration: paths, DB url, constants.

The database location is resolved through a small bootstrap file, ``config.json``,
kept in a fixed per-user support directory. That file lets the user move their
data elsewhere (Settings → Daten) without losing the pointer to it — the support
directory is always findable, the data directory is whatever it records.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent

# Folder name used for the per-user support directory of a packaged build.
APP_FOLDER = "BudgetLiquidity"


def _support_dir() -> Path:
    """Fixed per-user directory holding config.json (and, by default, the data).

    A frozen build must not write next to the .exe (onefile runs from a temp dir
    Windows can purge; an installed exe may sit in read-only Program Files), so it
    uses %LOCALAPPDATA%. Running from source keeps everything in the repo.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / APP_FOLDER
    return ROOT


SUPPORT_DIR = _support_dir()
SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = SUPPORT_DIR / "config.json"


def read_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_data_dir() -> Path:
    # Packaged: the support dir itself; source: the in-repo ./data folder.
    return SUPPORT_DIR if getattr(sys, "frozen", False) else ROOT / "data"


def _resolve_data_dir() -> Path:
    configured = read_config().get("data_dir")
    if configured:
        try:
            p = Path(configured)
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass  # fall back to default if the recorded path is unusable
    return _default_data_dir()


def refresh_paths() -> str:
    """Recompute DATA_DIR / DB_PATH / DB_URL from config.json; return the DB url.

    Called at import and again after the data directory is changed at runtime.
    """
    global DATA_DIR, DB_PATH, DB_URL
    DATA_DIR = _resolve_data_dir()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Keep the SQLite filename ASCII even though the parent path may contain an umlaut.
    DB_PATH = DATA_DIR / "planung.sqlite"
    DB_URL = f"sqlite:///{DB_PATH}"
    return DB_URL


def set_data_dir(path: str | Path) -> Path:
    """Record a new data directory in config.json (does not move any files)."""
    cfg = read_config()
    cfg["data_dir"] = str(Path(path))
    write_config(cfg)
    return Path(path)


# Resolve the paths once at import.
DATA_DIR: Path
DB_PATH: Path
DB_URL: str
refresh_paths()

# Austrian standard VAT rate (Umsatzsteuer).
VAT_RATE = 0.20

# Default federal-state subdivision for the holidays library: "4" == Oberösterreich.
DEFAULT_SUBDIV = "4"

APP_TITLE = "Budget- & Liquiditätsplanung"
# Default local port. 8080 is commonly taken by other dev servers, so use a less
# common one; run.py also auto-falls back to the next free port if this is busy.
PORT = 8137
