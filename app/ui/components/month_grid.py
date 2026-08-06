"""Reusable editable 12-month matrix grid (ui.aggrid) with a live 'Jahr' total.

Each row is a dict with `m1`..`m12` numeric fields plus whatever lead columns
the caller supplies. On any cell edit the whole row dict is handed to
`on_row_change` — robust and simple (no need to know which column changed).
"""
from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from ..formatting import MONTHS_DE
from ..grid import DE_NUM_PARSER, fit_grid

_MONEY_FMT = ("params => (params.value==null||params.value==='') ? '' : "
              "Number(params.value).toLocaleString('de-DE',{maximumFractionDigits:0})+' €'")
_NUM_PARSER = DE_NUM_PARSER

# Fixed grid metrics so the host height can be computed deterministically.
_ROW_H = 30
_HEADER_H = 34
_GRID_CHROME = 20   # header border + horizontal scrollbar allowance


def editable_month_grid(rows: list[dict], lead_cols: list[dict],
                        on_row_change: Callable[[dict], None],
                        fill_height: bool = False):
    col_defs: list[dict] = list(lead_cols)
    for m in range(1, 13):
        col_defs.append({
            "headerName": MONTHS_DE[m - 1], "field": f"m{m}", "editable": True,
            "width": 84, "type": "numericColumn", ":valueParser": _NUM_PARSER,
        })
    year_getter = "params => " + "+".join(f"(Number(params.data.m{m})||0)" for m in range(1, 13))
    col_defs.append({
        "headerName": "Jahr", "field": "jahr", "width": 120, "pinned": "right",
        "type": "numericColumn", ":valueGetter": year_getter, ":valueFormatter": _MONEY_FMT,
        "cellClass": "font-bold",
    })

    options = fit_grid({
        "columnDefs": col_defs,
        "rowData": rows,
        "defaultColDef": {"resizable": True, "sortable": False, "suppressMovable": True},
        "singleClickEdit": True,
        "stopEditingWhenCellsLoseFocus": True,
        "rowHeight": _ROW_H,
        "headerHeight": _HEADER_H,
    })
    if fill_height:
        # Fill the remaining viewport height down to the bottom, scroll inside the grid.
        grid = ui.aggrid(options).classes("w-full").style("height: calc(100vh - 300px); min-height: 320px")
    else:
        # Deterministic height from the row count — avoids ag-Grid autoHeight
        # mis-measuring at high-DPI/4K (which collapsed the host and overlapped the
        # element below it).
        height = _HEADER_H + max(1, len(rows)) * _ROW_H + _GRID_CHROME
        grid = ui.aggrid(options).classes("w-full").style(f"height: {height}px")
    grid.on("cellValueChanged", lambda e: on_row_change(e.args["data"]))
    return grid
