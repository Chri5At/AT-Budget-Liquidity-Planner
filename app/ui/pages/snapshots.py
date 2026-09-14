"""Snapshots — save the full plan, restore it, or compare it to the current plan."""
from __future__ import annotations

from nicegui import ui

from datetime import datetime

from ...db import get_session
from ...engine.scenarios import list_scenarios
from ...services.excel_export import export_scenario_comparison, export_single_scenario
from ...services.snapshots import (
    GRANULARITIES,
    KPI_KEYS,
    compare_rows,
    create_snapshot,
    delete_snapshot,
    list_snapshots,
    period_ranges,
    plan_figures,
    restore_snapshot,
    snapshot_figures,
)
from ..file_dialogs import XLSX_TYPES, save_bytes
from ..formatting import MONTHS_DE, eur, years
from ..grid import fit_grid

def _period_opts() -> dict[str, str]:
    """(year, month) range options for the export, e.g. '2026-07' -> 'Jul 2026'."""
    return {f"{y}-{m:02d}": f"{MONTHS_DE[m - 1]} {y}" for y in years() for m in range(1, 13)}


def _parse_ym(s: str) -> tuple[int, int]:
    y, m = s.split("-")
    return int(y), int(m)


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "Export"


def render() -> None:
    state = {"compare_id": None, "year": years()[0], "scenario": 1,
             "granularity": "year", "diff_only": False,
             "chart_kpi": "Endsaldo Liquidität"}

    ui.label("Snapshots").classes("text-xl font-bold")
    ui.label("Speichere den vollständigen Planungsstand, um ihn später wieder zu laden oder "
             "mit dem aktuellen Stand zu vergleichen.").classes("text-sm text-gray-500")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.button("Snapshot erstellen", icon="photo_camera", on_click=lambda: _create_dialog())

    # --- Excel export ----------------------------------------------------------
    exp = {"scenario": 1, "year": years()[0],
           "start": f"{years()[0]}-01", "end": f"{years()[-1]}-12"}

    async def _export_scenario() -> None:
        start, end = _parse_ym(exp["start"]), _parse_ym(exp["end"])
        with get_session() as s:
            scs = {sc.id: sc.name for sc in list_scenarios(s)}
            data = export_single_scenario(s, exp["scenario"], start, end)
        name = scs.get(exp["scenario"], "Szenario")
        fn = (f"Budget_Liquiditaet_{_safe(name)}_{exp['start']}_bis_{exp['end']}"
              f"_{datetime.now():%Y-%m-%d}.xlsx")
        await save_bytes(data, fn, file_types=XLSX_TYPES,
                         what=f"Export {name} ({exp['start']}–{exp['end']})")

    async def _export_comparison() -> None:
        with get_session() as s:
            data = export_scenario_comparison(s, exp["year"])
        fn = f"Szenarienvergleich_{exp['year']}_{datetime.now():%Y-%m-%d}.xlsx"
        await save_bytes(data, fn, file_types=XLSX_TYPES, what="Szenarienvergleich")

    with ui.card().classes("w-full max-w-4xl"):
        ui.label("Excel-Export").classes("text-base font-semibold")
        ui.label("Ein Dokument je Szenario (Budget, Liquidität, Personal, Einnahmen, Ausgaben) "
                 "oder ein Szenarienvergleich mit Diagrammen. Der Zeitraum (Von/Bis) begrenzt "
                 "den Szenario-Export. Der Speicherort wird beim Export abgefragt."
                 ).classes("text-xs text-gray-500")
        with ui.row().classes("items-center gap-3 mt-1 flex-wrap"):
            with get_session() as s:
                sc_opts = {sc.id: sc.name for sc in list_scenarios(s)}
            ui.select(sc_opts, value=exp["scenario"], label="Szenario",
                      on_change=lambda e: exp.update(scenario=int(e.value))
                      ).props("dense outlined").classes("w-44")
            _popts = _period_opts()
            ui.select(_popts, value=exp["start"], label="Von",
                      on_change=lambda e: exp.update(start=e.value)
                      ).props("dense outlined").classes("w-36")
            ui.select(_popts, value=exp["end"], label="Bis",
                      on_change=lambda e: exp.update(end=e.value)
                      ).props("dense outlined").classes("w-36")
            ui.button("Szenario exportieren", icon="download", on_click=_export_scenario)
            ui.separator().props("vertical")
            ui.select(years(), value=exp["year"], label="Jahr (Vergleich)",
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
            ui.label("Der aktuelle Planungsstand wird durch den Snapshot ersetzt. Es wird "
                     "automatisch vorher eine Sicherung des aktuellen Stands erstellt.").classes(
                "text-sm text-gray-500")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    with get_session() as s:
                        # Safety net: snapshot the current state before it is replaced.
                        create_snapshot(s, "Auto-Sicherung vor Laden",
                                        f"automatisch vor Laden von „{name}“")
                        restore_snapshot(s, sid)
                    dlg.close()
                    ui.notify("Snapshot geladen — Auto-Sicherung erstellt", type="positive")
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
        year, gran = state["year"], state["granularity"]
        with get_session() as s:
            snap = next((sn for sn in list_snapshots(s) if sn.id == state["compare_id"]), None)
            if snap is None:
                return
            scs = {sc.id: sc.name for sc in list_scenarios(s)}
            cur = plan_figures(s, year, state["scenario"])
            snp = snapshot_figures(snap, year, state["scenario"])

        # Periods of the chosen resolution; finer views get a "Gesamt" (= whole year)
        # column at the end so the annual figure is never lost.
        periods = period_ranges(gran, year)
        if gran != "year":
            periods = periods + [(f"Gesamt {year}", (1, 12))]
        rows = compare_rows(cur, snp, [r for _, r in periods])

        ui.separator().classes("my-3")
        with ui.row().classes("items-center gap-3 flex-wrap"):
            ui.label(f"Vergleich: {snap.name} vs. aktuell").classes("text-base font-semibold")
            ui.select(years(), value=year, label="Jahr",
                      on_change=lambda e: (_set("year", int(e.value)))
                      ).props("dense outlined").classes("w-28")
            ui.select(scs, value=state["scenario"], label="Szenario",
                      on_change=lambda e: (_set("scenario", int(e.value)))
                      ).props("dense outlined").classes("w-48")
            ui.select(GRANULARITIES, value=gran, label="Auflösung",
                      on_change=lambda e: (_set("granularity", e.value))
                      ).props("dense outlined").classes("w-32")
            ui.checkbox("nur Differenz", value=state["diff_only"],
                        on_change=lambda e: _set("diff_only", bool(e.value))
                        ).props("dense").tooltip(
                "Nur die Differenz-Spalten anzeigen (kompakter bei Quartal/Monat)")
        ui.label("Liquiditätswerte beziehen sich auf den gewählten Zeitraum: Tiefststand = "
                 "niedrigster Kontostand innerhalb des Zeitraums, Endsaldo = Kontostand am "
                 "Ende des Zeitraums. Einnahmequellen werden über ihre ID zugeordnet, "
                 "umbenannte Quellen tragen den Snapshot-Namen als Hinweis."
                 ).classes("text-xs text-gray-500")

        fmt = "p=>Math.round(p.value||0).toLocaleString('de-DE')+' €'"
        fmt_diff = ("p=>(p.value>0?'+':'')+Math.round(p.value||0)"
                    ".toLocaleString('de-DE')+' €'")
        diff_style = "p=>({color: p.value>0?'#15803d':(p.value<0?'#b91c1c':'#374151')})"

        def _diff_col(i: int, header: str) -> dict:
            return {"headerName": header, "field": f"d{i}", "type": "numericColumn",
                    "width": 140, "cellClass": "font-bold",
                    ":valueFormatter": fmt_diff, ":cellStyle": diff_style}

        col_defs: list[dict] = [
            {"headerName": "Kennzahl", "field": "k", "pinned": "left", "width": 380,
             "tooltipField": "note",
             ":cellStyle": ("p=>p.data.indent?{paddingLeft:'28px',color:'#6b7280',"
                            "fontStyle:'italic'}:{fontWeight:600}")},
        ]
        for i, (label, _) in enumerate(periods):
            if state["diff_only"]:
                col_defs.append(_diff_col(i, label))
            else:
                col_defs.append({"headerName": label, "marryChildren": True, "children": [
                    {"headerName": "Snapshot", "field": f"s{i}", "type": "numericColumn",
                     "width": 130, ":valueFormatter": fmt},
                    {"headerName": "Aktuell", "field": f"c{i}", "type": "numericColumn",
                     "width": 130, ":valueFormatter": fmt},
                    _diff_col(i, "Differenz"),
                ]})

        row_data = []
        for r in rows:
            label = r.label if not r.note else f"{r.label}  ({r.note})"
            d = {"k": label, "note": r.note, "indent": r.indent}
            for i, (sv, cv, dv) in enumerate(zip(r.snap, r.cur, r.diff)):
                d[f"s{i}"], d[f"c{i}"], d[f"d{i}"] = sv, cv, dv
            row_data.append(d)

        header_h = 34 if state["diff_only"] else 68   # column groups add a header row
        # auto_size_columns=False: NiceGUI only sees "flex" on top-level columns, so with
        # column groups it would add its fitGridWidth strategy on top and the grid renders blank.
        ui.aggrid(fit_grid({
            "columnDefs": col_defs, "rowData": row_data,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            "rowHeight": 30, "headerHeight": 34, "tooltipShowDelay": 300,
        }), auto_size_columns=False).classes("w-full").style(f"height: {header_h + len(row_data) * 30 + 20}px")

        top = [r for r in rows if r.indent == 0]
        if gran == "year":
            # One bar per KPI: how far the current plan moved away from the snapshot.
            ui.echart({
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": [r.label for r in top],
                          "axisLabel": {"fontSize": 10}},
                "grid": {"left": 160, "right": 40, "top": 10, "bottom": 30},
                "series": [{"type": "bar", "data": [round(r.diff[0]) for r in top],
                            "itemStyle": {"color": "#2563eb"}}],
            }).classes("w-full max-w-3xl").style("height: 280px")
        else:
            # Snapshot vs. aktuell per period for one KPI (the Gesamt column is left out).
            with ui.row().classes("items-center gap-3 mt-2"):
                ui.label("Verlauf").classes("text-sm font-semibold")
                ui.select(KPI_KEYS, value=state["chart_kpi"], label="Kennzahl",
                          on_change=lambda e: _set("chart_kpi", e.value)
                          ).props("dense outlined").classes("w-56")
            sel = next((r for r in top if r.label == state["chart_kpi"]), top[0])
            n = len(periods) - 1
            ui.echart({
                "tooltip": {"trigger": "axis"},
                "legend": {"data": ["Snapshot", "Aktuell"], "top": 0},
                "xAxis": {"type": "category", "data": [lbl for lbl, _ in periods[:n]],
                          "axisLabel": {"fontSize": 10}},
                "yAxis": {"type": "value"},
                "grid": {"left": 80, "right": 30, "top": 30, "bottom": 30},
                "series": [
                    {"name": "Snapshot", "type": "bar", "data": [round(v) for v in sel.snap[:n]],
                     "itemStyle": {"color": "#9ca3af"}},
                    {"name": "Aktuell", "type": "bar", "data": [round(v) for v in sel.cur[:n]],
                     "itemStyle": {"color": "#2563eb"}},
                ],
            }).classes("w-full max-w-4xl").style("height: 300px")

    def _set(key: str, value) -> None:
        state[key] = value
        comparison.refresh()

    snap_list()
    comparison()
