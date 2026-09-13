"""Native Datei-Dialoge für die App, mit Browser-Fallback.

Im gepackten Build läuft die Oberfläche in einem pywebview-Fenster, und pywebview
**bricht Downloads grundsätzlich ab** (``webview.settings['ALLOW_DOWNLOADS']`` ist
standardmäßig ``False`` → ``on_download_starting`` setzt ``args.Cancel = True``).
Ein ``ui.download`` erzeugt dort also stillschweigend gar keine Datei. Jede Datei,
die die App an den Benutzer herausgibt, geht deshalb über einen echten
„Speichern unter"-Dialog; nur wenn die App aus dem Quellcode im Browser läuft
(kein natives Fenster), fällt sie auf den normalen Browser-Download zurück.

Das native Fenster läuft in einem eigenen Prozess — ``app.native.main_window`` ist
ein ``WindowProxy``, dessen ``create_file_dialog`` eine *Coroutine* ist. Es muss
awaited werden (nicht in ``run.io_bound`` gewickelt), sonst öffnet sich der Dialog
nie und der Aufrufer bekommt ein Coroutine-Objekt zurück.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

from nicegui import app, run, ui

from .. import config

# Dateifilter: pywebview akzeptiert nur „Beschreibung (*.endung)" mit einer
# Beschreibung aus Wortzeichen und Leerzeichen — ein Bindestrich („Excel-Datei")
# lässt create_file_dialog im Fensterprozess mit ValueError sterben.
XLSX_TYPES = ("Excel Arbeitsmappe (*.xlsx)",)
ZIP_TYPES = ("ZIP Sicherung (*.zip)",)

_OPEN, _FOLDER, _SAVE = 10, 20, 30      # webview.FileDialog-Werte (stabil seit pywebview 3)

# Dieselbe Prüfung wie in webview.util.parse_file_type. Wir filtern vorab selbst:
# im Fensterprozess wird die Exception nur geloggt, die Antwort bleibt aus — der
# Aufruf würde also nicht scheitern, sondern für immer hängen.
_FILTER_RE = re.compile(r"^([\w ]+)\((\*(?:\.(?:\w+|\*))*(?:;\*(?:\.(?:\w+|\*))*)*)\)$")


def valid_filters(file_types) -> tuple[str, ...]:
    """Nur Filter durchlassen, die pywebview akzeptiert (lieber keiner als ein Hänger)."""
    return tuple(f for f in file_types if _FILTER_RE.match(f))


def native_window():
    """Das pywebview-Fenster, wenn die App als Desktop-App läuft — sonst None."""
    return getattr(getattr(app, "native", None), "main_window", None)


def default_export_dir() -> Path:
    """Im Dialog vorgeschlagener Ordner: der zuletzt benutzte, sonst <Daten>/exports."""
    configured = config.read_config().get("export_dir")
    if configured:
        p = Path(configured)
        if p.is_dir():
            return p
    p = config.DATA_DIR / "exports"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        return config.DATA_DIR
    return p


def remember_export_dir(directory: Path) -> None:
    """Ordner merken, damit der nächste Export dort wieder startet."""
    cfg = config.read_config()
    cfg["export_dir"] = str(directory)
    config.write_config(cfg)


def ensure_suffix(path: Path, filename: str) -> Path:
    """Endung des Vorschlagsnamens erzwingen (Windows hängt sie nicht immer an)."""
    suffix = Path(filename).suffix
    if suffix and path.suffix.lower() != suffix.lower():
        return path.with_name(path.name + suffix)
    return path


def _first_path(result) -> Path | None:
    """Rückgabe von create_file_dialog (Tupel, str oder None) → Path | None."""
    if not result:
        return None
    if isinstance(result, (list, tuple)):
        return Path(result[0]) if result else None
    return Path(result)


async def _dialog(win, **kwargs):
    """create_file_dialog aufrufen — als Coroutine (WindowProxy) oder blockierend."""
    if inspect.iscoroutinefunction(win.create_file_dialog):
        return await win.create_file_dialog(**kwargs)
    return await run.io_bound(lambda: win.create_file_dialog(**kwargs))


async def pick_folder(start: Path | None = None) -> Path | None:
    """Ordner-Auswahl. None, wenn abgebrochen oder kein natives Fenster da ist."""
    win = native_window()
    if win is None:
        ui.notify("Ordnerauswahl nur in der App verfügbar — bitte Pfad eingeben.", type="info")
        return None
    try:
        res = await _dialog(win, dialog_type=_FOLDER,
                            directory=str(start or config.DATA_DIR))
    except Exception as exc:        # noqa: BLE001 — Dialog darf die App nie abschießen
        ui.notify(f"Dateidialog nicht verfügbar ({exc}) — bitte Pfad eingeben.", type="info")
        return None
    return _first_path(res)


async def save_bytes(data: bytes, filename: str, *, file_types: tuple[str, ...] = (),
                     what: str = "Datei") -> Path | None:
    """Den Benutzer fragen, wohin `data` gespeichert werden soll, und schreiben.

    Gibt den geschriebenen Pfad zurück — None, wenn abgebrochen wurde oder die
    Datei (Browser-Modus) als Download übergeben wurde.
    """
    win = native_window()
    if win is None:                     # Browser: dort funktioniert der Download
        ui.download.content(data, filename)
        ui.notify(f"{what} wird heruntergeladen: {filename}", type="positive")
        return None

    try:
        res = await _dialog(win, dialog_type=_SAVE, directory=str(default_export_dir()),
                            save_filename=filename, file_types=valid_filters(file_types))
    except Exception as exc:            # noqa: BLE001
        ui.notify(f"Speichern-Dialog nicht verfügbar: {exc}", type="negative")
        return None

    path = _first_path(res)
    if path is None:
        ui.notify("Export abgebrochen", type="info")
        return None
    path = ensure_suffix(path, filename)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        await run.io_bound(path.write_bytes, data)
    except Exception as exc:            # noqa: BLE001 — z.B. Datei in Excel offen
        ui.notify(f"Konnte nicht speichern: {exc}", type="negative")
        return None

    remember_export_dir(path.parent)
    ui.notify(f"{what} gespeichert: {path}", type="positive")
    return path
