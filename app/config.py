"""Central configuration: paths, DB url, constants."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent


def _data_dir() -> Path:
    """Where the SQLite DB and runtime files live.

    A frozen (PyInstaller) build must not write next to the .exe — onefile runs
    from a temporary extraction dir that Windows can purge (data loss), and an
    installed exe may sit in a read-only Program Files folder. So a packaged app
    stores everything in a stable per-user location instead. Running from source
    keeps the in-repo ./data folder for convenience.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "BudgetLiquidity"
    return ROOT / "data"


DATA_DIR = _data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Keep the SQLite filename ASCII even though the parent path contains an umlaut.
DB_PATH = DATA_DIR / "planung.sqlite"
DB_URL = f"sqlite:///{DB_PATH}"

# Austrian standard VAT rate (Umsatzsteuer).
VAT_RATE = 0.20

# Default federal-state subdivision for the holidays library: "4" == Oberösterreich.
DEFAULT_SUBDIV = "4"

APP_TITLE = "Budget- & Liquiditätsplanung"
# Default local port. 8080 is commonly taken by other dev servers, so use a less
# common one; run.py also auto-falls back to the next free port if this is busy.
PORT = 8137
