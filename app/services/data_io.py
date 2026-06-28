"""User-facing data management: portable backup export/import and data relocation.

Export writes a ZIP (manifest.json + data.json) holding every source table. The
manifest records the app version the file was created with, so a later import can
warn on a version mismatch. Import always snapshots the current plan first as a
safety net before replacing it (back-up-before-migrate).
"""
from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .. import config
from ..version import __version__, APP_NAME
from ..db import get_session, reload_engine
from .snapshots import create_snapshot, dump_all, replace_all_from_payload

EXPORT_FORMAT = "budget-liquidity-export/1"


def _version_tuple(v: str) -> tuple:
    out = []
    for part in (v or "").split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return tuple(out)


# --- export ---------------------------------------------------------------

def export_zip() -> Path:
    """Write a timestamped backup ZIP into <data>/exports and return its path."""
    with get_session() as s:
        payload = dump_all(s)
    manifest = {
        "format": EXPORT_FORMAT,
        "app": APP_NAME,
        "app_version": __version__,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }
    exports = config.DATA_DIR / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    path = exports / f"budget-export-{datetime.now():%Y%m%d-%H%M%S}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("data.json", payload)
    return path


# --- import ---------------------------------------------------------------

def read_import(raw: bytes) -> tuple[dict, str]:
    """Parse an export ZIP → (manifest, payload). Raises ValueError on bad input."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            payload = z.read("data.json").decode("utf-8")
    except Exception as exc:
        raise ValueError("Keine gültige Export-Datei "
                         "(ZIP mit manifest.json und data.json erwartet).") from exc
    if manifest.get("format") != EXPORT_FORMAT:
        raise ValueError("Unbekanntes Dateiformat.")
    return manifest, payload


def version_relation(manifest: dict) -> str:
    """How the file's app_version compares to this app: 'older' | 'same' | 'newer'."""
    other = _version_tuple(manifest.get("app_version", "0"))
    current = _version_tuple(__version__)
    if other > current:
        return "newer"
    return "older" if other < current else "same"


def apply_import(payload: str) -> None:
    """Snapshot the current plan (safety net), then replace it with the payload."""
    with get_session() as s:
        create_snapshot(s, "Auto-Sicherung vor Import",
                        f"automatisch vor Datenimport (App {__version__})")
        replace_all_from_payload(s, payload)


# --- relocate -------------------------------------------------------------

def change_data_dir(new_dir: str | Path) -> tuple[Path, bool]:
    """Point the app at a new data directory and rebuild the engine.

    If the target already holds a database, switch to it as-is. Otherwise copy the
    current database there (the original is left behind, untouched, as a backup).
    Returns (new_db_path, copied_current_db).
    """
    target = Path(new_dir)
    target.mkdir(parents=True, exist_ok=True)
    src = config.DB_PATH

    # Record the new location and recompute paths, then release the file lock.
    config.set_data_dir(target)
    config.refresh_paths()
    dst = config.DB_PATH

    from .. import db
    try:
        db.engine.dispose()
    except Exception:
        pass

    copied = False
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
        copied = True

    reload_engine()
    return dst, copied
