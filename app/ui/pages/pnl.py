"""GuV / Budget — read-only Deckungsbeitragsrechnung, computed from source rows.

This replaces the #REF!-broken Excel sheet: it is always derived, never linked.
"""
from __future__ import annotations

from nicegui import ui

from ...db import get_session
from ...engine.pnl import pnl_view
from ...engine.scenarios import list_scenarios
from ..components.scenario_ui import scenario_select
from ..formatting import MONTHS_DE, YEARS, eur


def render() -> None:
    state = {"year": YEARS[0], "scenario": 1}

    ui.label("GuV / Budget (Deckungsbeitragsrechnung)").classes("text-xl font-bold")
    ui.label("Automatisch aus Einnahmen, Ausgaben und Mitarbeitern berechnet — keine "
             "Verknüpfungen, kein #REF!.").classes("text-sm text-gray-500")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.select(YEARS, value=state["year"], label="Jahr",
                  on_change=lambda e: _change_year(e.value)).props("outlined dense").classes("w-28")
        scenario_select(state["scenario"], lambda v: _change_scenario(v))

    @ui.refreshable
    def comparison() -> None:
        year = state["year"]
        with get_session() as s:
            scs = list_scenarios(s)
            if len(scs) < 2:
                return
            per_scenario = {sc.id: pnl_view(s, year, sc.id) for sc in scs}
            sc_names = {sc.id: sc.name for sc in scs}
        # Compare the subtotal positions (annual) across scenarios.
        keys = [r.label for r in next(iter(per_scenario.values())) if r.kind == "subtotal"]
        col_defs = [{"headerName": "Kennzahl (Jahr)", "field": "label", "pinned": "left", "width": 240}]
        for sc in scs:
            col_defs.append({"headerName": sc_names[sc.id], "field": f"s{sc.id}",
                             "type": "numericColumn", "width": 150,
                             ":valueFormatter": "p => Math.round(p.value||0).toLocaleString('de-DE')+' €'"})
        row_data = []
        for label in keys:
            d = {"label": label.replace("=", "").strip()}
            for sc in scs:
                match = next((r for r in per_scenario[sc.id] if r.label == label), None)
                d[f"s{sc.id}"] = round(match.annual) if match else 0
            row_data.append(d)
        ui.label("Szenarienvergleich (Jahreswerte)").classes("text-base font-semibold mt-4")
        ui.aggrid({
            "columnDefs": col_defs, "rowData": row_data,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            "rowHeight": 30, "headerHeight": 34,
        }).classes("w-full max-w-4xl").style(f"height: {34 + max(1, len(row_data)) * 30 + 20}px")

    @ui.refreshable
    def table() -> None:
        with get_session() as s:
            rows_model = pnl_view(s, state["year"], state["scenario"])

        col_defs = [{"headerName": "Position", "field": "label", "pinned": "left", "width": 270}]
        for m in range(1, 13):
            col_defs.append({"headerName": MONTHS_DE[m - 1], "field": f"m{m}",
                             "type": "numericColumn", "width": 90,
                             ":valueFormatter":
                             "p => (p.value? Math.round(p.value).toLocaleString('de-DE'):'')"})
        col_defs.append({"headerName": "Gesamt", "field": "jahr", "pinned": "right", "width": 130,
                         "type": "numericColumn", "cellClass": "font-bold",
                         ":valueFormatter":
                         "p => p.value? Math.round(p.value).toLocaleString('de-DE')+' €':''"})

        row_data = []
        for r in rows_model:
            d = {"label": r.label, "jahr": round(r.annual), "_kind": r.kind}
            for m in range(1, 13):
                d[f"m{m}"] = round(r.values[m - 1])
            row_data.append(d)

        # Bold the subtotal/section rows via a rowClassRules on the hidden _kind field.
        ui.aggrid({
            "columnDefs": col_defs,
            "rowData": row_data,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            ":rowClassRules": "{'font-bold bg-blue-50': p => p.data._kind === 'subtotal',"
                              " 'font-semibold': p => p.data._kind === 'section'}",
        }).classes("w-full").style("height: calc(100vh - 300px); min-height: 360px")

    def _change_year(value: int) -> None:
        state["year"] = int(value)
        table.refresh()
        comparison.refresh()

    def _change_scenario(value: int) -> None:
        state["scenario"] = int(value)
        table.refresh()

    table()
    comparison()

    def _on_show() -> None:
        # GuV reads source rows directly — re-run so it reflects the latest edits.
        table.refresh()
        comparison.refresh()

    return _on_show
