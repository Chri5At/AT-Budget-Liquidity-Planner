"""GuV / Budget — read-only Deckungsbeitragsrechnung, computed from source rows.

This replaces the #REF!-broken Excel sheet: it is always derived, never linked.
"""
from __future__ import annotations

from nicegui import ui

from sqlmodel import select

from ...db import get_session
from ...engine.pnl import pnl_view
from ...engine.scenarios import list_scenarios
from ...models import Depreciation
from ..components.scenario_ui import scenario_select
from ..formatting import MONTHS_DE, eur, years
from ..grid import fit_grid


def _save_depreciation(year: int, month: int, amount) -> None:
    """Upsert the depreciation for one month to a single row (stored positive)."""
    with get_session() as s:
        for dp in s.exec(select(Depreciation).where(
                Depreciation.year == year, Depreciation.month == month)).all():
            s.delete(dp)
        amt = abs(float(amount or 0))
        if amt:
            s.add(Depreciation(year=year, month=month, amount=amt))
        s.commit()


def render() -> None:
    state = {"year": years()[0], "scenario": 1}

    ui.label("GuV / Budget (Deckungsbeitragsrechnung)").classes("text-xl font-bold")
    ui.label("Automatisch aus Einnahmen, Ausgaben und Mitarbeitern berechnet. Hellgelbe Zellen "
             "(z. B. Abschreibungen) sind direkt editierbar — Klick in die Zelle, Wert eingeben."
             ).classes("text-sm text-gray-500")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.select(years(), value=state["year"], label="Jahr",
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
        ui.aggrid(fit_grid({
            "columnDefs": col_defs, "rowData": row_data,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            "rowHeight": 30, "headerHeight": 34,
        })).classes("w-full max-w-4xl").style(f"height: {34 + max(1, len(row_data)) * 30 + 20}px")

    @ui.refreshable
    def table() -> None:
        with get_session() as s:
            rows_model = pnl_view(s, state["year"], state["scenario"])

        editable_month = "params => !!params.data._editable_key"
        editable_style = ("params => params.data._editable_key "
                          "? {backgroundColor:'#fffbeb', cursor:'pointer'} : null")
        col_defs = [{"headerName": "Position", "field": "label", "pinned": "left", "width": 270,
                     "suppressSizeToFit": True}]
        for m in range(1, 13):
            col_defs.append({"headerName": MONTHS_DE[m - 1], "field": f"m{m}",
                             "type": "numericColumn", "width": 90, "minWidth": 70,
                             ":editable": editable_month, ":cellStyle": editable_style,
                             ":valueParser": "p => (p.newValue===''||p.newValue==null)?0:Number(p.newValue)",
                             ":valueFormatter":
                             "p => (p.value? Math.round(p.value).toLocaleString('de-DE'):'')"})
        col_defs.append({"headerName": "Gesamt", "field": "jahr", "pinned": "right", "width": 130,
                         "type": "numericColumn", "cellClass": "font-bold", "suppressSizeToFit": True,
                         ":valueFormatter":
                         "p => p.value? Math.round(p.value).toLocaleString('de-DE')+' €':''"})

        row_data = []
        for r in rows_model:
            d = {"label": r.label, "jahr": round(r.annual), "_kind": r.kind,
                 "_editable_key": r.editable_key}
            for m in range(1, 13):
                d[f"m{m}"] = round(r.values[m - 1])
            row_data.append(d)

        # Bold the subtotal/section rows via a rowClassRules on the hidden _kind field.
        grid = ui.aggrid(fit_grid({
            "columnDefs": col_defs,
            "rowData": row_data,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            "singleClickEdit": True, "stopEditingWhenCellsLoseFocus": True,
            ":getRowId": "params => params.data.label",
            ":rowClassRules": "{'font-bold bg-blue-50': p => p.data._kind === 'subtotal',"
                              " 'font-semibold': p => p.data._kind === 'section'}",
        })).classes("w-full").style("height: calc(100vh - 300px); min-height: 360px")
        state["grid"] = grid
        grid.on("cellValueChanged", _on_edit)

    def _on_edit(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        col = a.get("colId") or a.get("column") or ""
        if not (data.get("_editable_key") == "depreciation" and isinstance(col, str)
                and col.startswith("m") and col[1:].isdigit()):
            return
        month = int(col[1:])
        _save_depreciation(state["year"], month, data.get(col, 0))
        # Depreciation is non-cash (not in the cashflow ledger), so no recompute_all().
        # Surgically update only the affected rows so focus stays for fast editing.
        grid = state.get("grid")
        if grid is None:
            return
        with get_session() as s:
            rows = pnl_view(s, state["year"], state["scenario"])

        def find(pred):
            return next((r for r in rows if pred(r.label)), None)

        # Editing depreciation changes Abschreibungen, EBIT and EBT (NB: "= EBIT" is a
        # substring of "= EBITDA", so match EBIT/EBT precisely).
        affected = (find(lambda lab: "Abschreibungen" in lab),
                    find(lambda lab: "EBIT" in lab and "EBITDA" not in lab),
                    find(lambda lab: "EBT" in lab))
        for row in affected:
            if row is None:
                continue
            grid.run_row_method(row.label, "setDataValue", f"m{month}", round(row.values[month - 1]))
            grid.run_row_method(row.label, "setDataValue", "jahr", round(row.annual))

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
