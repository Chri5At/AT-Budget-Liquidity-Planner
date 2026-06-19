"""Central configuration: paths, DB url, constants."""
from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

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
