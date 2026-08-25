"""Open a folder (or a file's folder) in the operating system's file manager.

Used by Verträge & Abos to jump to a contract's Ablage. This is a local desktop
app, so handing the path to the shell is the whole job — Windows Explorer,
Finder and the freedesktop handler each take it directly.

`file_dialogs` covers picking and saving paths; opening one is the missing piece
and lives here so that module stays about dialogs.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def resolve_folder(raw: str) -> Path | None:
    """The folder to reveal for a stored path: the path itself, or its parent."""
    text = (raw or "").strip().strip('"')
    if not text:
        return None
    path = Path(text)
    if path.is_dir():
        return path
    if path.exists():
        return path.parent
    return None


def open_folder(raw: str) -> str:
    """Open the path in the file manager. Returns "" on success, else a message."""
    folder = resolve_folder(raw)
    if folder is None:
        return f"Pfad nicht gefunden: {raw}" if (raw or "").strip() else "Kein Pfad hinterlegt."
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(folder))                    # noqa: S606 — desktop app
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])      # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603,S607
    except Exception as exc:                             # noqa: BLE001 — never kill the app
        return f"Konnte den Ordner nicht öffnen: {exc}"
    return ""
