"""Snapshots — save the full plan, restore it, or compare it to the current plan."""
from __future__ import annotations

from nicegui import ui

from datetime import datetime

from ...db import get_session
from ...engine.scenarios import list_scenarios
from ...services.excel_export import export_scenario_comparison, export_single_scenario
from ...services.snapshots import (
    compute_kpis,
    create_snapshot,
    delete_snapshot,
    list_snapshots,
    restore_snapshot,
    snapshot_kpis,
)
from ..formatting import YEARS, eur


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "Export"


def render() -> None:
    state = {"compare_id": None, "year": YEARS[0], "scenario": 1}

    ui.label("Snapshots").classes("text-xl font-bold")
    ui.label("Speichere den vollständigen Planungsstand, um ihn später wieder zu laden oder "
             "mit dem aktuellen Stand zu vergleichen.").classes("text-sm text-gray-500")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.button("Snapshot erstellen", icon="photo_camera", on_click=lambda: _create_dialog())

    # --- Excel export ----------------------------------------------------------
    exp = {"scenario": 1, "year": YEARS[0]}

    def _export_scenario() -> None:
        with get_session() as s:
            scs = {sc.id: sc.name for sc in list_scenarios(s)}
            data = export_single_scenario(s, exp["scenario"])
        name = scs.get(exp["scenario"], "Szenario")
        fn = f"Budget_Liquiditaet_{_safe(name)}_{datetime.now():%Y-%m-%d}.xlsx"
        ui.download.content(data, fn)
        ui.notify(f"Export {name} erstellt", type="positive")

    def _export_comparison() -> None:
        with get_session() as s:
            data = export_scenario_comparison(s, exp["year"])
        ui.download.content(data, f"Szenarienvergleich_{exp['year']}_{datetime.now():%Y-%m-%d}.xlsx")
        ui.notify("Szenarienvergleich exportiert", type="positive")

    with ui.card().classes("w-full max-w-4xl"):
        ui.label("Excel-Export").classes("text-base font-semibold")
        ui.label("Ein Dokument je Szenario (Budget, Liquidität, Personal, Einnahmen, Ausgaben) "
                 "oder ein Szenarienvergleich mit Diagrammen.").classes("text-xs text-gray-500")
        with ui.row().classes("items-center gap-3 mt-1"):
            with get_session() as s:
                sc_opts = {sc.id: sc.name for sc in list_scenarios(s)}
            ui.select(sc_opts, value=exp["scenario"], label="Szenario",
                      on_change=lambda e: exp.update(scenario=int(e.value))
                      ).props("dense outlined").classes("w-48")
            ui.button("Szenario exportieren", icon="download", on_click=_export_scenario)
            ui.separator().props("vertical")
            ui.select(YEARS, value=exp["year"], label="Jahr (Vergleich)",
                      on_change=lambda e: exp.update(year=int(e.value))
                      ).props("dense outlined").classes("w-32")
            ui.button("Szenarienvergleich exportieren", icon="compare_arrows",
                      on_click=_export_comparison).props("outline")

    def _create_dialog() -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label("Neuer Snapshot").classes("text-lg font-bold")
            name = ui.input("Name", value="Planung").classes("w-80")
            note = ui.input("Notiz (optional)").classes("w-80")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    with get_session() as s:
                        create_snapshot(s, name.value or "Snapshot", note.value or "")
                    dlg.close()
                    ui.notify("Snapshot gespeichert", type="positive")
                    snap_list.refresh()

                ui.button("Speichern", icon="save", on_click=_do)
        dlg.open()

    @ui.refreshable
    def snap_list() -> None:
        with get_session() as s:
            snaps = [(sn.id, sn.name, sn.created_at, sn.note) for sn in list_snapshots(s)]
        if not snaps:
            ui.label("Noch keine Snapshots.").classes("text-sm text-gray-500")
            return
        with ui.card().classes("w-full max-w-4xl"):
            with ui.row().classes("items-center gap-3 text-xs text-gray-500 font-medium"):
                ui.label("Name").classes("w-56")
                ui.label("Erstellt").classes("w-44")
                ui.label("Notiz").classes("w-56")
            for sid, name, created, note in snaps:
                with ui.row().classes("items-center gap-3"):
                    ui.label(name).classes("w-56 font-medium")
                    ui.label((created or "").replace("T", " ")).classes("w-44 text-gray-600 text-sm")
                    ui.label(note or "—").classes("w-56 text-gray-500 text-sm")
                    ui.button("Vergleichen", icon="compare_arrows",
                              on_click=lambda sid=sid: _compare(sid)).props("flat dense")
                    ui.button("Laden", icon="restore",
                              on_click=lambda sid=sid, name=name: _restore_dialog(sid, name)
                              ).props("flat dense color=primary")
                    ui.button(icon="delete", on_click=lambda sid=sid: _delete(sid)
                              ).props("flat round dense color=negative").tooltip("löschen")

    def _delete(sid: int) -> None:
        with get_session() as s:
            delete_snapshot(s, sid)
        if state["compare_id"] == sid:
            state["compare_id"] = None
        ui.notify("Snapshot gelöscht", type="positive")
        snap_list.refresh()
        comparison.refresh()

    def _restore_dialog(sid: int, name: str) -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label(f'Snapshot „{name}“ laden?').classes("text-lg font-bold")
            ui.label("Der aktuelle Planungsstand wird durch den Snapshot ersetzt. Erstelle "
                     "vorher ggf. einen Snapshot des aktuellen Stands.").classes(
                "text-sm text-gray-500")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    with get_session() as s:
                        restore_snapshot(s, sid)
                    dlg.close()
                    ui.notify("Snapshot geladen — Stand ersetzt", type="positive")
                    ui.navigate.reload()

                ui.button("Laden", icon="restore", color="primary", on_click=_do)
        dlg.open()

    def _compare(sid: int) -> None:
        state["compare_id"] = sid
        comparison.refresh()

    @ui.refreshable
    def comparison() -> None:
        if not state["compare_id"]:
            return
        with get_session() as s:
            snap = next((sn for sn in list_snapshots(s) if sn.id == state["compare_id"]), None)
            if snap is None:
                return
            scs = {sc.id: sc.name for sc in list_scenarios(s)}
            cur = compute_kpis(s, state["year"], state["scenario"])
            snp = snapshot_kpis(snap, state["year"], state["scenario"])
        ui.separator().classes("my-3")
        with ui.row().classes("items-center gap-3"):
            ui.label(f"Vergleich: {snap.name} vs. aktuell").classes("text-base font-semibold")
            ui.select(YEARS, value=state["year"], label="Jahr",
                      on_change=lambda e: (_set("year", int(e.value)))
                      ).props("dense outlined").classes("w-28")
            ui.select(scs, value=state["scenario"], label="Szenario",
                      on_change=lambda e: (_set("scenario", int(e.value)))
                      ).props("dense outlined").classes("w-48")

        keys = list(cur.keys())
        col_defs = [
            {"headerName": "Kennzahl", "field": "k", "pinned": "left", "width": 220},
            {"headerName": "Snapshot", "field": "s", "type": "numericColumn", "width": 140,
             ":valueFormatter": "p=>Math.round(p.value||0).toLocaleString('de-DE')+' €'"},
            {"headerName": "Aktuell", "field": "c", "type": "numericColumn", "width": 140,
             ":valueFormatter": "p=>Math.round(p.value||0).toLocaleString('de-DE')+' €'"},
            {"headerName": "Differenz", "field": "d", "type": "numericColumn", "width": 150,
             "cellClass": "font-bold",
             ":valueFormatter": "p=>(p.value>0?'+':'')+Math.round(p.value||0).toLocaleString('de-DE')+' €'",
             ":cellStyle": "p=>({color: p.value>0?'#15803d':(p.value<0?'#b91c1c':'#374151')})"},
        ]
        row_data = [{"k": k, "s": snp.get(k, 0), "c": cur.get(k, 0),
                     "d": cur.get(k, 0) - snp.get(k, 0)} for k in keys]
        ui.aggrid({
            "columnDefs": col_defs, "rowData": row_data,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            "rowHeight": 30, "headerHeight": 34,
        }).classes("w-full max-w-3xl").style(f"height: {34 + len(row_data) * 30 + 20}px")

        # Bar chart of the differences.
        ui.echart({
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "value"},
            "yAxis": {"type": "category", "data": keys, "axisLabel": {"fontSize": 10}},
            "grid": {"left": 160, "right": 40, "top": 10, "bottom": 30},
            "series": [{"type": "bar", "data": [round(cur.get(k, 0) - snp.get(k, 0)) for k in keys],
                        "itemStyle": {"color": "#2563eb"}}],
        }).classes("w-full max-w-3xl").style("height: 280px")

    def _set(key: str, value) -> None:
        state[key] = value
        comparison.refresh()

    snap_list()
    comparison()
