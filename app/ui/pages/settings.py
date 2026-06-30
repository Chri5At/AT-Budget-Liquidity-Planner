"""Einstellungen — global planning parameters (split model, %, opening balance…)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from nicegui import ui
from sqlalchemy import delete as sa_delete

from ... import config
from ...db import get_session, get_settings
from ...services import data_io
from ...version import __version__
from ...models import (
    CashflowEntry,
    CostCategory,
    CostPlanMonth,
    Depreciation,
    Employee,
    Investment,
    Loan,
    LoanSchedule,
    RevenuePlanMonth,
    RevenueStream,
    SalaryMonth,
    SplitModel,
)
from ...models.enums import SPLIT_MODEL_DE
from ...services.recompute import recompute_all
from ..formatting import eur

# Source tables wiped by "Alle Daten löschen" (Settings is kept, flagged seeded).
_RESET_TABLES = (
    SalaryMonth, Employee, RevenuePlanMonth, RevenueStream,
    CostPlanMonth, CostCategory, Depreciation, LoanSchedule, Loan,
    Investment, CashflowEntry,
)


def render() -> None:
    ui.label("Einstellungen").classes("text-xl font-bold")
    ui.label("Globale Parameter. Mitarbeiter können einzeln abweichen "
             "(siehe Mitarbeiter-Einstellungen).").classes("text-sm text-gray-500")

    with get_session() as s:
        st = get_settings(s)
        data = {
            "company_name": st.company_name,
            "split_model": st.split_model,
            "abgaben_pct": st.abgaben_pct * 100,
            "employer_burden_pct": st.employer_burden_pct * 100,
            "salary_net_pct": st.salary_net_pct * 100,
            "abgaben_pay_day": st.abgaben_pay_day,
            "opening_balance": st.opening_balance,
            "opening_balance_date": st.opening_balance_date.isoformat(),
            "horizon_start": st.horizon_start.isoformat(),
            "horizon_end": st.horizon_end.isoformat(),
        }

    with ui.card().classes("w-full max-w-3xl"):
        with ui.grid(columns=2).classes("gap-3 w-full"):
            name = ui.input("Firmenname", value=data["company_name"])
            model = ui.select({m: SPLIT_MODEL_DE[m] for m in SplitModel},
                              value=data["split_model"], label="Gehalts-Aufteilungsmodell")
            abg = ui.number("Abgaben % (Modell A)", value=data["abgaben_pct"], step=1, min=0, max=100)
            burden = ui.number("Lohnnebenkosten % (LNK)", value=data["employer_burden_pct"], step=1, min=0, max=100)
            netpct = ui.number("Netto % vom Brutto (Modell B)", value=data["salary_net_pct"], step=1, min=0, max=100)
            payday = ui.number("Abgaben-Zahltag (Folgemonat)", value=data["abgaben_pay_day"], step=1, min=1, max=28)
            opening = ui.number("Anfangskontostand (€)", value=data["opening_balance"], step=1000)
            opening_date = ui.input("Anfangsdatum (YYYY-MM-DD)", value=data["opening_balance_date"])
            hstart = ui.input("Planungsbeginn (YYYY-MM-DD)", value=data["horizon_start"])
            hend = ui.input("Planungsende (YYYY-MM-DD)", value=data["horizon_end"])
            ui.label("Planungsende auf z. B. 2028-12-31 setzen, um das Jahr 2028 überall "
                     "(Tabellen, Auswahl, Export) hinzuzufügen.").classes("text-xs text-gray-500")

        def save() -> None:
            horizon_changed = False
            with get_session() as s:
                st = get_settings(s)
                old_span = (st.horizon_start.year, st.horizon_end.year)
                st.company_name = name.value
                st.split_model = SplitModel(model.value)
                st.abgaben_pct = float(abg.value or 0) / 100
                st.employer_burden_pct = float(burden.value or 0) / 100
                st.salary_net_pct = float(netpct.value or 0) / 100
                st.abgaben_pay_day = int(payday.value or 15)
                st.opening_balance = float(opening.value or 0)
                try:
                    st.opening_balance_date = date.fromisoformat(opening_date.value)
                    st.horizon_start = date.fromisoformat(hstart.value)
                    st.horizon_end = date.fromisoformat(hend.value)
                except ValueError:
                    ui.notify("Datumsformat: YYYY-MM-DD", type="warning")
                    return
                horizon_changed = (st.horizon_start.year, st.horizon_end.year) != old_span
                s.add(st)
                s.commit()
            recompute_all()
            if horizon_changed:
                ui.notify("Planungszeitraum geändert — Seite wird neu geladen", type="positive")
                ui.navigate.reload()
            else:
                ui.notify("Gespeichert und neu berechnet", type="positive")

        ui.button("Speichern", icon="save", on_click=save).classes("mt-2")

    ui.label(f"Aktueller Anfangskontostand: {eur(data['opening_balance'])}").classes("text-sm mt-2")

    _data_section()

    # --- Danger zone: wipe all data to start from scratch ----------------------
    with ui.card().classes("w-full max-w-3xl mt-4 border border-red-300"):
        ui.label("Gefahrenzone").classes("text-base font-semibold text-red-700")
        ui.label("Löscht alle Mitarbeiter, Einnahmen, Ausgaben, Investitionen, Darlehen und "
                 "Abschreibungen. Die Demodaten werden nicht erneut geladen — du startest mit "
                 "einer leeren Planung.").classes("text-sm text-gray-600")
        ui.button("Alle Daten löschen (leere Planung)", icon="delete_forever",
                  color="negative", on_click=_confirm_reset).props("outline")


def _open_folder(path: Path) -> None:
    try:
        os.startfile(str(path))     # noqa: S606 — Windows Explorer on a known local path
    except Exception:
        pass


def _export() -> None:
    try:
        path = data_io.export_zip()
    except Exception as exc:        # noqa: BLE001 — surface any failure to the user
        ui.notify(f"Export fehlgeschlagen: {exc}", type="negative")
        return
    ui.notify(f"Exportiert: {path.name}", type="positive")
    _open_folder(path.parent)


def _on_upload(e) -> None:
    try:
        raw = e.content.read()
        manifest, payload = data_io.read_import(raw)
    except ValueError as exc:
        ui.notify(str(exc), type="negative")
        return
    except Exception as exc:        # noqa: BLE001
        ui.notify(f"Datei konnte nicht gelesen werden: {exc}", type="negative")
        return
    _confirm_import(e.name, manifest, payload)


def _confirm_import(fname: str, manifest: dict, payload: str) -> None:
    rel = data_io.version_relation(manifest)
    ver = manifest.get("app_version", "?")
    with ui.dialog() as dlg, ui.card().classes("min-w-[380px]"):
        ui.label("Daten importieren?").classes("text-lg font-bold")
        ui.label(f"Datei: {fname}").classes("text-sm break-all")
        ui.label(f"Erstellt mit App-Version {ver} · diese App: {__version__}").classes("text-sm")
        if rel == "newer":
            ui.label("Achtung: Die Datei stammt aus einer NEUEREN App-Version. Unbekannte "
                     "Felder werden beim Import verworfen.").classes("text-sm text-red-700")
        ui.label("Die aktuellen Daten werden ersetzt. Vorher wird automatisch eine "
                 "Sicherung (Snapshot) erstellt.").classes("text-sm text-gray-600")
        with ui.row().classes("justify-end w-full"):
            ui.button("Abbrechen", on_click=dlg.close).props("flat")

            def _do() -> None:
                try:
                    data_io.apply_import(payload)
                except Exception as exc:    # noqa: BLE001
                    ui.notify(f"Import fehlgeschlagen: {exc}", type="negative")
                    dlg.close()
                    return
                dlg.close()
                ui.notify("Daten importiert (Auto-Sicherung erstellt)", type="positive")
                ui.navigate.reload()

            ui.button("Importieren", icon="upload", color="primary", on_click=_do)
    dlg.open()


async def _browse(target) -> None:
    """Best-effort native folder picker; falls back to manual entry in the browser."""
    from nicegui import app, run
    win = getattr(getattr(app, "native", None), "main_window", None)
    if win is None:
        ui.notify("Dateidialog nur in der App verfügbar — bitte Pfad eingeben.", type="info")
        return
    try:
        import webview
        res = await run.io_bound(win.create_file_dialog, webview.FOLDER_DIALOG)
    except Exception:               # noqa: BLE001
        ui.notify("Dateidialog nicht verfügbar — bitte Pfad eingeben.", type="info")
        return
    if res:
        target.value = str(res[0] if isinstance(res, (list, tuple)) else res)


def _change_dir(new_dir: str) -> None:
    new_dir = (new_dir or "").strip()
    if not new_dir:
        ui.notify("Bitte ein Verzeichnis angeben", type="warning")
        return
    try:
        _dst, copied = data_io.change_data_dir(new_dir)
    except Exception as exc:        # noqa: BLE001
        ui.notify(f"Konnte Speicherort nicht ändern: {exc}", type="negative")
        return
    msg = ("Datenbank in den neuen Ordner kopiert (Original bleibt als Sicherung)."
           if copied else "Auf die vorhandene Datenbank im Zielordner umgestellt.")
    ui.notify(f"Speicherort geändert. {msg}", type="positive")
    ui.navigate.reload()


def _data_section() -> None:
    with ui.card().classes("w-full max-w-3xl mt-4"):
        ui.label("Daten & Speicherort").classes("text-base font-semibold")
        ui.label("Aktueller Speicherort der Datenbank:").classes("text-sm text-gray-600")
        ui.label(str(config.DB_PATH)).classes("text-xs text-gray-700 break-all")

        loc = ui.input("Datenverzeichnis", value=str(config.DATA_DIR)).props(
            "outlined dense").classes("w-full")
        with ui.row().classes("items-center gap-2"):
            ui.button("Durchsuchen…", icon="folder_open",
                      on_click=lambda: _browse(loc)).props("outline")
            ui.button("Speicherort übernehmen", icon="drive_file_move",
                      on_click=lambda: _change_dir(loc.value)).props("outline")
        ui.label("Beim Wechsel wird die Datenbank in den neuen Ordner kopiert (sofern dort "
                 "noch keine existiert); das Original bleibt als Sicherung erhalten."
                 ).classes("text-xs text-gray-500")

        ui.separator().classes("my-2")
        ui.label("Sicherung & Übertragung").classes("text-sm font-medium")
        with ui.row().classes("items-center gap-3"):
            ui.button("Daten exportieren (ZIP)", icon="download", on_click=_export)
            ui.upload(label="ZIP importieren", auto_upload=True, on_upload=_on_upload).props(
                'accept=".zip" flat').classes("max-w-xs")
        ui.label("Export legt eine ZIP-Sicherung im Ordner „exports“ ab (mit App-Version). "
                 "Import ersetzt die aktuellen Daten — vorher wird automatisch ein Snapshot "
                 "angelegt.").classes("text-xs text-gray-500")


def _confirm_reset() -> None:
    with ui.dialog() as dlg, ui.card():
        ui.label("Wirklich ALLE Plandaten löschen?").classes("text-lg font-bold")
        ui.label("Dies kann nicht rückgängig gemacht werden. Die Einstellungen "
                 "(Prozentsätze etc.) bleiben erhalten, der Anfangskontostand wird auf 0 gesetzt."
                 ).classes("text-sm text-gray-500")
        with ui.row():
            ui.button("Abbrechen", on_click=dlg.close).props("flat")

            def _do() -> None:
                from ...services.snapshots import create_snapshot
                with get_session() as s:
                    # Safety net: capture the current state so a reset can be undone.
                    create_snapshot(s, "Auto-Sicherung vor Zurücksetzen",
                                    "automatisch vor „Alle Daten löschen“")
                    for table in _RESET_TABLES:
                        s.execute(sa_delete(table))
                    st = get_settings(s)
                    st.opening_balance = 0.0
                    st.seeded = True            # prevent demo data from being re-seeded
                    s.add(st)
                    s.commit()
                dlg.close()
                ui.notify("Alle Daten gelöscht (Auto-Sicherung erstellt)", type="positive")
                ui.navigate.reload()

            ui.button("Alles löschen", icon="delete_forever", color="negative", on_click=_do)
    dlg.open()
