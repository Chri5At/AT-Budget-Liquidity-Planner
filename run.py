"""Entry point — initialise the DB and launch the local NiceGUI server.

Run with the project's virtual environment:
    .venv\\Scripts\\python run.py            (normal)
    .venv\\Scripts\\python run.py --debug    (auto-reload + verbose logging)
The chosen port is printed on startup (default 8137, auto-falls back if busy).

Configuration via environment variables (overrides defaults):
    BL_DEBUG=1      enable debug mode (same as --debug)
    BL_PORT=8137    port to listen on
    BL_RELOAD=1     enable auto-reload on file changes
    BL_SHOW=0       do not auto-open the browser
"""
from __future__ import annotations

import os
import socket
import sys

from app.config import APP_TITLE, PORT
from app.db import init_db
from app.ui import main  # noqa: F401  (registers the @ui.page route)

from nicegui import ui


def _flag(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _pick_free_port(preferred: int, span: int = 50) -> int:
    """Return the preferred port, or the next free one if it's already in use."""
    for p in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sk:
            try:
                sk.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    return preferred


# A packaged (PyInstaller) build runs frozen; default it to a native desktop
# window so the end user never sees a browser tab or a localhost URL.
FROZEN = getattr(sys, "frozen", False)

# --debug on the command line is shorthand for BL_DEBUG=1.
DEBUG = "--debug" in sys.argv or _flag("BL_DEBUG", False)

RELOAD = _flag("BL_RELOAD", DEBUG)        # debug implies auto-reload
NATIVE = _flag("BL_NATIVE", FROZEN)       # frozen → native window (needs pywebview)
SHOW = _flag("BL_SHOW", True) and not NATIVE
LOG_LEVEL = "debug" if DEBUG else "warning"

# Frozen onefile launches from a temp dir; make relative runtime files (NiceGUI's
# ".nicegui" storage) land in the writable per-user data folder, not %TEMP%.
if FROZEN:
    from app.config import DATA_DIR
    os.chdir(DATA_DIR)

# Pick a free port so a busy port never crashes the app. Auto-fallback is skipped
# under auto-reload (the reloader re-binds the exact port itself).
_wanted = int(os.environ.get("BL_PORT", PORT))
PORT = _wanted if RELOAD else _pick_free_port(_wanted)

init_db(seed=True)

if PORT != _wanted:
    print(f"[run] Port {_wanted} is in use — using {PORT} instead.")
if DEBUG:
    print(f"[run] DEBUG mode  port={PORT}  reload={RELOAD}  log={LOG_LEVEL}")
print(f"[run] Starting on http://localhost:{PORT}")

ui.run(
    title=APP_TITLE,
    port=PORT,
    reload=RELOAD,
    show=SHOW,
    native=NATIVE,
    storage_secret="budget-liquidity-local",
    uvicorn_logging_level=LOG_LEVEL,
)
