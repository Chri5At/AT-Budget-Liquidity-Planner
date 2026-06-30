"""Ausgaben — cost categories with grouping, an editable monthly matrix, an
advanced per-cell breakdown (notes/colour/copy), and a recurring auto-fill.

Mirrors the Einnahmen page; categories here are a UI grouping only — every cost
row is an ordinary CostCategory, so the GuV/liquidity engines sum each once.
"""
from __future__ import annotations

from nicegui import ui
from sqlmodel import select

from ...db import get_session
from ...models import (
    CostCategory,
    CostCellEntry,
    CostPlanMonth,
    OpexCategory,
    PaymentTerm,
    PnlLine,
    ScenarioDisable,
)
from ...models.enums import PNL_LINE_DE, TERM_DAYS
from ...services.recompute import recompute_all
from ..formatting import MONTHS_DE, eur, page_title, years
from ..grid import fit_grid
from ..components.scenario_ui import base_toggle_panel, scenario_select

CELL_COLORS = {"": "keine", "#fff3cd": "Gelb", "#d1e7dd": "Grün",
               "#f8d7da": "Rot", "#cfe2ff": "Blau", "#ffe5d0": "Orange", "#e2e3e5": "Grau"}

_CELL_PARSER = 'params => (params.newValue===""||params.newValue==null)?0:Number(params.newValue)'
_CELL_STYLE = (
    'params => { if (params.data.kind === "category") return {fontWeight:"bold"};'
    ' if (params.data.kind === "grandtotal") return {fontWeight:"bold", backgroundColor:"#e2e8f0"};'
    ' var c = params.data["color"+params.colDef.field.substring(1)];'
    ' return c?{backgroundColor:c}:null; }')
_CELL_RENDER = (
    'params => { var f=params.colDef.field.substring(1);'
    ' var v=(params.value!=null&&params.value!=="")?Math.round(params.value).toLocaleString("de-DE")+" €":"";'
    ' return params.data["mark"+f] ? v+" <span style=\'color:#1976d2;font-weight:bold\''
    ' title=\'Detail/Notiz – Doppelklick\'>•</span>" : v; }')
_NAME_RENDER = (
    'params => { var k=params.data.kind, nm=params.data.name||"";'
    ' if (k==="category"){ var ic=params.data.expanded?"▼":"▶";'
    '   return "<span style=\'cursor:pointer;font-weight:bold\'>"+ic+" "+nm+"</span>"; }'
    ' if (k==="grandtotal") return "<b>"+nm+"</b>";'
    ' if (k==="child"||k==="direct"){'
    '   return "<span style=\'padding-left:16px;color:#374151\'>"+nm+"</span>"; }'
    ' return nm; }')
_ROW_STYLE = ('params => params.data.kind === "category" '
              '? {backgroundColor: params.data.row_color || "#fdecec"} : null')


def _cat_days(c: CostCategory) -> int:
    return c.payment_days if c.payment_days is not None else TERM_DAYS[c.payment_term]


def _bereich(c: CostCategory) -> str:
    if c.pnl_line == PnlLine.OPEX and c.opex_category:
        return c.opex_category.value
    return PNL_LINE_DE[c.pnl_line]


def _cell_pm(s, cat_id: int, year: int, month: int) -> CostPlanMonth:
    pm = s.exec(select(CostPlanMonth).where(
        CostPlanMonth.category_id == cat_id, CostPlanMonth.year == year,
        CostPlanMonth.month == month)).first()
    if pm is None:
        pm = CostPlanMonth(category_id=cat_id, year=year, month=month)
        s.add(pm)
    return pm


def _recompute_cell(s, cat_id: int, year: int, month: int) -> None:
    entries = s.exec(select(CostCellEntry).where(
        CostCellEntry.category_id == cat_id, CostCellEntry.year == year,
        CostCellEntry.month == month)).all()
    pm = _cell_pm(s, cat_id, year, month)
    pm.amount = sum(e.amount for e in entries)
    s.commit()


def _apply_cell_content(s, cat_id: int, year: int, month: int, *, use_list: bool,
                        items: list[dict], note: str, color: str, single_value) -> None:
    for e in s.exec(select(CostCellEntry).where(
            CostCellEntry.category_id == cat_id, CostCellEntry.year == year,
            CostCellEntry.month == month)).all():
        s.delete(e)
    pm = _cell_pm(s, cat_id, year, month)
    if use_list:
        kept = [it for it in items if (it["amount"] or it["note"])]
        for i, it in enumerate(kept):
            s.add(CostCellEntry(category_id=cat_id, year=year, month=month, sort_order=i,
                                amount=float(it["amount"] or 0), note=it["note"] or ""))
    else:
        pm.amount = float(single_value or 0)
    pm.note = note or ""
    pm.color = color or ""
    s.commit()
    if use_list:
        _recompute_cell(s, cat_id, year, month)


def _save_amount_cell(cat_id: int, year: int, month: int, amount: float) -> None:
    # No recompute here — the cashflow ledger rebuilds when Liquidität opens, so
    # rapid cell edits stay instant without a page refresh.
    with get_session() as s:
        for e in s.exec(select(CostCellEntry).where(
                CostCellEntry.category_id == cat_id, CostCellEntry.year == year,
                CostCellEntry.month == month)).all():
            s.delete(e)
        pm = _cell_pm(s, cat_id, year, month)
        pm.amount = float(amount or 0)
        s.commit()


def _cat_month_total(s, cat_id: int, year: int, month: int) -> int:
    ids = [cat_id] + [c.id for c in s.exec(select(CostCategory).where(
        CostCategory.parent_id == cat_id)).all()]
    total = 0.0
    for cid in ids:
        pm = s.exec(select(CostPlanMonth).where(
            CostPlanMonth.category_id == cid, CostPlanMonth.year == year,
            CostPlanMonth.month == month)).first()
        if pm:
            total += pm.amount
    return round(total)


def _month_grand_totals(s, year: int, scenario_id: int) -> list[int]:
    """Per-month total across all rows (each row's own value counts once, which
    equals Σ of the displayed top-level rows). Used for the pinned bottom row."""
    cat_ids = {c.id for c in s.exec(select(CostCategory)).all() if c.scenario_id == scenario_id}
    totals = [0.0] * 12
    for pm in s.exec(select(CostPlanMonth).where(CostPlanMonth.year == year)).all():
        if pm.category_id in cat_ids and 1 <= pm.month <= 12:
            totals[pm.month - 1] += pm.amount
    return [round(x) for x in totals]


def _grandtotal_row(totals: list[int]) -> dict:
    row = {"rid": "grandtotal", "kind": "grandtotal", "name": "Σ Gesamt / Monat"}
    for i, v in enumerate(totals):
        row[f"m{i + 1}"] = v
    return row


def _save_name_cell(cat_id: int, name: str) -> None:
    with get_session() as s:
        c = s.get(CostCategory, cat_id)
        if c is not None:
            c.name = name
            s.add(c)
            s.commit()


def _data_row(s, c: CostCategory, year: int, kind: str, *, name: str | None = None,
              cat_id: int | None = None) -> dict:
    months = {p.month: p for p in s.exec(select(CostPlanMonth).where(
        CostPlanMonth.category_id == c.id, CostPlanMonth.year == year)).all()}
    ent_months = {e.month for e in s.exec(select(CostCellEntry).where(
        CostCellEntry.category_id == c.id, CostCellEntry.year == year)).all()}
    row = {"rid": f"{kind}-{c.id}", "id": c.id, "kind": kind, "cat_id": cat_id,
           "name": name if name is not None else c.name, "bereich": _bereich(c)}
    for m in range(1, 13):
        pm = months.get(m)
        row[f"m{m}"] = round(pm.amount) if pm else 0
        row[f"color{m}"] = pm.color if pm else ""
        row[f"mark{m}"] = bool((pm and pm.note) or m in ent_months)
        row[f"detail{m}"] = m in ent_months
    return row


def _own_amounts(s, cat_id: int, year: int) -> list[float]:
    months = {p.month: p.amount for p in s.exec(select(CostPlanMonth).where(
        CostPlanMonth.category_id == cat_id, CostPlanMonth.year == year)).all()}
    return [round(months.get(m, 0.0)) for m in range(1, 13)]


def _load_tree_rows(year: int, scenario_id: int, collapsed: set) -> list[dict]:
    with get_session() as s:
        scoped = [c for c in s.exec(select(CostCategory).order_by(
            CostCategory.sort_order, CostCategory.id)).all() if c.scenario_id == scenario_id]
        children_of: dict[int, list] = {}
        tops = []
        for c in scoped:
            (children_of.setdefault(c.parent_id, []).append(c) if c.parent_id else tops.append(c))
        rows: list[dict] = []
        for c in tops:
            if c.is_category:
                kids = children_of.get(c.id, [])
                expanded = c.id not in collapsed
                totals = _own_amounts(s, c.id, year)
                for kid in kids:
                    ka = _own_amounts(s, kid.id, year)
                    totals = [totals[i] + ka[i] for i in range(12)]
                cat = {"rid": f"cat-{c.id}", "id": c.id, "kind": "category", "name": c.name,
                       "bereich": f"Kategorie · {len(kids)}", "expanded": expanded,
                       "row_color": c.color or ""}
                for m in range(1, 13):
                    cat[f"m{m}"] = totals[m - 1]
                    cat[f"color{m}"] = ""
                    cat[f"mark{m}"] = False
                    cat[f"detail{m}"] = False
                rows.append(cat)
                if expanded:
                    rows.append(_data_row(s, c, year, "direct",
                                          name="↳ Allgemein (direkt)", cat_id=c.id))
                    for kid in kids:
                        rows.append(_data_row(s, kid, year, "child", cat_id=c.id))
            else:
                rows.append(_data_row(s, c, year, "leaf"))
        return rows


def render() -> None:
    state = {"year": years()[0], "scenario": 1, "collapsed": set()}

    page_title("Ausgaben",
               "Aufwände je Kategorie und Monat. Kategorien gruppieren Positionen; die "
               "Kategoriezeile zeigt die Summe. Die Bereich-Zuordnung steuert die GuV.")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.select(years(), value=state["year"], label="Jahr",
                  on_change=lambda e: _change_year(e.value)).props("outlined dense").classes("w-28")
        scenario_select(state["scenario"], lambda v: _change_scenario(v))
        ui.button("Ausgabe hinzufügen", icon="add", on_click=lambda: _add_dialog(False))
        ui.button("Kategorie hinzufügen", icon="create_new_folder",
                  on_click=lambda: _add_dialog(True)).props("outline")
        ui.button("Wiederkehrende Ausgabe", icon="repeat",
                  on_click=lambda: _recurring_dialog()).props("outline")

    @ui.refreshable
    def matrix() -> None:
        rows = _load_tree_rows(state["year"], state["scenario"], state["collapsed"])
        if not rows and state["scenario"] != 1:
            ui.label("Keine Ausgaben in diesem Szenario — füge Positionen hinzu.").classes(
                "text-sm text-gray-500")
        editable = "params => params.data.kind !== 'category'"
        editable_month = ("params => params.data.kind !== 'category' && "
                          "!params.data['detail'+params.colDef.field.substring(1)]")
        col_defs = [
            {"headerName": "", "width": 38, "pinned": "left", "sortable": False,
             "resizable": False, "suppressMenu": True, "suppressSizeToFit": True,
             ":valueGetter": "() => ''",
             ":rowDrag": "params => params.data.kind !== 'direct'"},
            {"headerName": "Ausgabe / Kategorie", "field": "name", "pinned": "left", "width": 230,
             "suppressSizeToFit": True, ":editable": editable, ":cellRenderer": _NAME_RENDER},
            {"headerName": "Bereich", "field": "bereich", "width": 150, "suppressSizeToFit": True},
        ]
        for m in range(1, 13):
            col_defs.append({"headerName": MONTHS_DE[m - 1], "field": f"m{m}", "width": 92,
                             "minWidth": 64, "type": "numericColumn", ":editable": editable_month,
                             ":valueParser": _CELL_PARSER, ":cellStyle": _CELL_STYLE,
                             ":cellRenderer": _CELL_RENDER})
        year_getter = "params => " + "+".join(f"(Number(params.data.m{m})||0)" for m in range(1, 13))
        col_defs.append({"headerName": "Jahr", "field": "jahr", "pinned": "right", "width": 110,
                         "type": "numericColumn", "cellClass": "font-bold", "suppressSizeToFit": True,
                         ":valueGetter": year_getter,
                         ":valueFormatter": "p=>Math.round(p.value||0).toLocaleString('de-DE')+' €'"})
        bottom = {"rid": "grandtotal", "kind": "grandtotal", "name": "Σ Gesamt / Monat"}
        for m in range(1, 13):
            bottom[f"m{m}"] = sum(r[f"m{m}"] for r in rows if r["kind"] in ("category", "leaf"))
        grid = ui.aggrid(fit_grid({
            "columnDefs": col_defs, "rowData": rows,
            "pinnedBottomRowData": [bottom],
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            "singleClickEdit": True, "stopEditingWhenCellsLoseFocus": True,
            "rowDragManaged": True, "animateRows": True, "rowHeight": 30, "headerHeight": 34,
            ":getRowId": "params => params.data.rid",
            ":getRowStyle": _ROW_STYLE,
        })).classes("w-full").style(f"height: {34 + (max(1, len(rows)) + 1) * 30 + 20}px")
        state["grid"] = grid
        grid.on("cellValueChanged", _on_cell_edit)
        grid.on("cellClicked", _on_cell_click)
        grid.on("cellDoubleClicked", _on_cell_dblclick)
        grid.on("rowDragEnd", _on_drag_end)
        total = sum(r[f"m{m}"] for r in rows for m in range(1, 13)
                    if r["kind"] in ("category", "leaf"))
        ui.label(f"Eigene Ausgaben {state['year']}: {eur(total)}").classes("text-sm font-semibold mt-1")
        ui.label("Einfachklick = Wert · Doppelklick = Detail/Notiz/Farbe · Klick auf ▶/▼ = "
                 "Kategorie auf/zu · Ziehen am Griff ⠿ = Reihenfolge / in Kategorie verschieben"
                 ).classes("text-xs text-gray-500")
        base_toggle_panel(state["scenario"], "cost", CostCategory, matrix.refresh)

    def _cell_col(args) -> str:
        return args.get("colId") or args.get("column") or ""

    def _on_cell_edit(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        col = _cell_col(a)
        if "id" not in data or data.get("kind") == "category":
            return
        cid = int(data["id"])
        if col == "name":
            _save_name_cell(cid, data.get("name", ""))
        elif isinstance(col, str) and col.startswith("m") and col[1:].isdigit():
            if data.get(f"detail{col[1:]}"):
                return
            month = int(col[1:])
            _save_amount_cell(cid, state["year"], month, data.get(col, 0))
            grid = state.get("grid")
            if grid is None:
                return
            cat_id = data.get("cat_id")
            with get_session() as s:
                if cat_id:  # update the parent category's month cell in place
                    grid.run_row_method(f"cat-{cat_id}", "setDataValue", col,
                                        _cat_month_total(s, int(cat_id), state["year"], month))
                totals = _month_grand_totals(s, state["year"], state["scenario"])
            # Refresh the pinned bottom Σ-row (its month total just changed).
            grid.run_grid_method("setGridOption", "pinnedBottomRowData", [_grandtotal_row(totals)])

    def _on_cell_click(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        if data.get("kind") == "category" and _cell_col(a) == "name":
            state["collapsed"] ^= {int(data["id"])}
            matrix.refresh()

    def _on_cell_dblclick(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        col = _cell_col(a)
        if (data.get("kind") != "category" and "id" in data
                and isinstance(col, str) and col.startswith("m") and col[1:].isdigit()):
            _open_cell_modal(int(data["id"]), state["year"], int(col[1:]))

    async def _on_drag_end(e) -> None:
        try:
            client_rows = await e.sender.get_client_data()
        except Exception:
            return
        seq = [(r.get("kind"), int(r["id"])) for r in client_rows
               if "id" in r and r.get("kind") in ("category", "child", "leaf")]
        with get_session() as s:
            scoped = {c.id: c for c in s.exec(select(CostCategory)).all()
                      if c.scenario_id == state["scenario"]}
            top_order: list[int] = []
            cat_children: dict[int, list[int]] = {}
            current_cat = None
            for kind, cid in seq:
                if cid not in scoped:
                    continue
                if kind == "category":
                    top_order.append(cid)
                    cat_children.setdefault(cid, [])
                    current_cat = cid
                elif current_cat is not None:
                    cat_children.setdefault(current_cat, []).append(cid)
                else:
                    top_order.append(cid)
            seen = set(top_order) | {c for kids in cat_children.values() for c in kids}
            for c in scoped.values():
                if c.id in seen or c.is_category:
                    continue
                if c.parent_id in cat_children:
                    cat_children[c.parent_id].append(c.id)
            counter = 0
            for cid in top_order:
                c = scoped[cid]
                c.parent_id = None
                c.sort_order = counter
                counter += 1
                for kid_id in cat_children.get(cid, []):
                    k = scoped[kid_id]
                    k.parent_id = cid
                    k.sort_order = counter
                    counter += 1
            s.commit()
        matrix.refresh()
        manage.refresh()

    def _open_cell_modal(cat_id: int, year: int, month: int) -> None:
        with get_session() as s:
            c = s.get(CostCategory, cat_id)
            if c is None:
                return
            cname = c.name
            pm = s.exec(select(CostPlanMonth).where(
                CostPlanMonth.category_id == cat_id, CostPlanMonth.year == year,
                CostPlanMonth.month == month)).first()
            note0 = pm.note if pm else ""
            color0 = pm.color if pm else ""
            amount0 = pm.amount if pm else 0.0
            items = [{"amount": e.amount, "note": e.note}
                     for e in s.exec(select(CostCellEntry).where(
                         CostCellEntry.category_id == cat_id, CostCellEntry.year == year,
                         CostCellEntry.month == month).order_by(
                         CostCellEntry.sort_order, CostCellEntry.id)).all()]
        if not items:
            items = [{"amount": 0.0, "note": ""}]
        modal = {"color": color0}
        has_list = any((it["amount"] or it["note"]) for it in items)
        modal["use_list"] = has_list

        def _total() -> float:
            return sum((it["amount"] or 0) for it in items)

        with ui.dialog() as dlg, ui.card().classes("min-w-[640px]"):
            ui.label(f"{cname} — {MONTHS_DE[month - 1]} {year}").classes("text-lg font-bold")
            with ui.row().classes("items-center gap-3"):
                single_in = ui.number("Einzelwert (€)", value=round(amount0), step=100
                                      ).props("dense outlined").classes("w-44")
                use_list_sw = ui.switch("Detail-Aufstellung verwenden", value=has_list)
            with ui.row().classes("items-center gap-3 mt-1"):
                note_in = ui.input("Allgemeine Notiz", value=note0).classes("w-80")
                ui.select(CELL_COLORS, value=color0, label="Zellenfarbe",
                          on_change=lambda e: modal.update(color=e.value)
                          ).props("dense outlined").classes("w-40")
            list_box = ui.column().classes("w-full mt-2")
            total_label = ui.label().classes("text-sm font-semibold")

            def _refresh_total() -> None:
                total_label.text = f"Summe Aufstellung: {eur(_total())}"

            @ui.refreshable
            def lines() -> None:
                for it in items:
                    with ui.row().classes("items-center gap-2"):
                        ui.number("Betrag", value=it["amount"], step=100,
                                  on_change=lambda e, it=it: (it.__setitem__("amount", e.value or 0),
                                                              _refresh_total())
                                  ).props("dense outlined").classes("w-32")
                        ui.input("Notiz", value=it["note"],
                                 on_change=lambda e, it=it: it.__setitem__("note", e.value or "")
                                 ).props("dense outlined").classes("w-80")

                        def _remove(it=it) -> None:
                            items.remove(it)
                            if not items:
                                items.append({"amount": 0.0, "note": ""})
                            lines.refresh()
                            _refresh_total()

                        ui.button(icon="close", on_click=_remove).props("flat round dense")

            with list_box:
                lines()

                def _add_line() -> None:
                    items.append({"amount": 0.0, "note": ""})
                    lines.refresh()

                with ui.row().classes("items-center gap-3 mt-1"):
                    ui.button("Zeile hinzufügen", icon="add", on_click=_add_line).props("flat")
                    total_label
            _refresh_total()

            def _toggle_list(e) -> None:
                modal["use_list"] = bool(e.value)
                list_box.set_visibility(bool(e.value))
                single_in.set_visibility(not bool(e.value))
            use_list_sw.on_value_change(_toggle_list)
            list_box.set_visibility(has_list)
            single_in.set_visibility(not has_list)

            copy_sel = ui.select({m: MONTHS_DE[m - 1] for m in range(1, 13) if m != month},
                                 multiple=True, label="Auch in diese Monate kopieren (optional)"
                                 ).props("dense outlined use-chips").classes("w-full mt-2")

            with ui.row().classes("mt-2"):
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _save() -> None:
                    use_list = modal["use_list"]
                    targets = sorted({month, *[int(m) for m in (copy_sel.value or [])]})
                    with get_session() as s:
                        for tm in targets:
                            _apply_cell_content(s, cat_id, year, tm, use_list=use_list, items=items,
                                                note=note_in.value, color=modal["color"],
                                                single_value=single_in.value)
                    recompute_all()
                    dlg.close()
                    matrix.refresh()
                    extra = len(targets) - 1
                    ui.notify("Zelle gespeichert" + (f" und in {extra} weitere Monate kopiert"
                                                     if extra else ""), type="positive")

                ui.button("Speichern", icon="save", on_click=_save)
        dlg.open()

    @ui.refreshable
    def manage() -> None:
        with get_session() as s:
            cats_all = [c for c in s.exec(select(CostCategory).order_by(
                CostCategory.sort_order, CostCategory.id)).all() if c.scenario_id == state["scenario"]]
            cat_opts = {c.id: c.name for c in cats_all if c.is_category}
            data = [(c.id, c.name, c.pnl_line, c.opex_category, _cat_days(c), c.is_vatable,
                     c.is_category, c.parent_id, c.color or "") for c in cats_all]
        with ui.expansion("Ausgaben & Kategorien bearbeiten (Bereich, Zahlungsziel, Kategorie, "
                          "löschen)", icon="tune").classes("w-full"):
            if not data:
                ui.label("Keine eigenen Ausgaben in diesem Szenario.").classes(
                    "text-sm text-gray-500")
            for cid, name, pl, opx, days, vat, is_cat, parent_id, color in data:
                with ui.row().classes("items-center gap-2"):
                    with ui.column().classes("gap-0"):
                        ui.button(icon="keyboard_arrow_up", on_click=lambda cid=cid: _move(cid, -1)
                                  ).props("flat dense").classes("w-6 h-4").tooltip("nach oben")
                        ui.button(icon="keyboard_arrow_down", on_click=lambda cid=cid: _move(cid, 1)
                                  ).props("flat dense").classes("w-6 h-4").tooltip("nach unten")
                    ui.icon("create_new_folder" if is_cat else "trending_down").classes("text-gray-400")
                    ui.input("Bezeichnung", value=name,
                             on_change=lambda e, cid=cid: _save_field(cid, name=e.value)
                             ).props("dense outlined").classes("w-44")
                    ui.select({l: PNL_LINE_DE[l] for l in PnlLine}, value=pl, label="Bereich",
                              on_change=lambda e, cid=cid: _save_field(cid, pnl_line=PnlLine(e.value))
                              ).props("dense outlined").classes("w-44")
                    ui.select({o: o.value for o in OpexCategory},
                              value=opx or OpexCategory.OTHER, label="OPEX-Kategorie",
                              on_change=lambda e, cid=cid: _save_field(
                                  cid, opex_category=OpexCategory(e.value))
                              ).props("dense outlined").classes("w-40")
                    if is_cat:
                        ui.select(CELL_COLORS, value=color, label="Farbe",
                                  on_change=lambda e, cid=cid: _save_field(cid, color=e.value)
                                  ).props("dense outlined").classes("w-28")
                    else:
                        parent_opts = {0: "— keine Kategorie —", **cat_opts}
                        ui.select(parent_opts, value=parent_id or 0, label="Kategorie",
                                  on_change=lambda e, cid=cid: _save_field(
                                      cid, parent_id=(int(e.value) or None))
                                  ).props("dense outlined").classes("w-40")
                    ui.number("Ziel (Tage)", value=days, min=0, max=365, step=1,
                              on_change=lambda e, cid=cid: _save_field(cid, payment_days=int(e.value or 0))
                              ).props("dense outlined").classes("w-24")
                    ui.checkbox("VSt", value=vat,
                                on_change=lambda e, cid=cid: _save_field(cid, is_vatable=bool(e.value)))
                    ui.button(icon="delete", on_click=lambda cid=cid, name=name, is_cat=is_cat:
                              _delete(cid, name, is_cat)
                              ).props("flat round dense color=negative").tooltip("löschen")

    def _move(cid: int, delta: int) -> None:
        with get_session() as s:
            target = s.get(CostCategory, cid)
            if target is None:
                return
            sibs = [c for c in s.exec(select(CostCategory).order_by(
                CostCategory.sort_order, CostCategory.id)).all()
                if c.scenario_id == state["scenario"] and c.parent_id == target.parent_id]
            ids = [c.id for c in sibs]
            i = ids.index(cid)
            j = i + delta
            if j < 0 or j >= len(ids):
                return
            sibs[i].sort_order, sibs[j].sort_order = sibs[j].sort_order, sibs[i].sort_order
            s.commit()
        matrix.refresh()
        manage.refresh()

    def _save_field(cid: int, **kw) -> None:
        with get_session() as s:
            c = s.get(CostCategory, cid)
            if c is None:
                return
            for k, v in kw.items():
                setattr(c, k, v)
            s.add(c)
            s.commit()
        recompute_all()
        matrix.refresh()

    def _delete(cid: int, name: str, is_cat: bool) -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label(f'„{name}" löschen?').classes("text-lg font-bold")
            ui.label("Kategorie löschen: enthaltene Positionen werden zu obersten Positionen "
                     "(nicht gelöscht)." if is_cat
                     else "Alle Monatswerte dieser Position werden entfernt.").classes(
                "text-sm text-gray-500")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    with get_session() as s:
                        if is_cat:
                            for kid in s.exec(select(CostCategory).where(
                                    CostCategory.parent_id == cid)).all():
                                kid.parent_id = None
                                s.add(kid)
                        for p in s.exec(select(CostPlanMonth).where(
                                CostPlanMonth.category_id == cid)).all():
                            s.delete(p)
                        for ce in s.exec(select(CostCellEntry).where(
                                CostCellEntry.category_id == cid)).all():
                            s.delete(ce)
                        for d in s.exec(select(ScenarioDisable).where(
                                ScenarioDisable.ref_kind == "cost",
                                ScenarioDisable.ref_id == cid)).all():
                            s.delete(d)
                        c = s.get(CostCategory, cid)
                        if c is not None:
                            s.delete(c)
                        s.commit()
                    recompute_all()
                    dlg.close()
                    ui.notify(f'„{name}" gelöscht', type="positive")
                    matrix.refresh()
                    manage.refresh()

                ui.button("Löschen", icon="delete", color="negative", on_click=_do)
        dlg.open()

    def _change_year(value: int) -> None:
        state["year"] = int(value)
        matrix.refresh()

    def _change_scenario(value: int) -> None:
        state["scenario"] = int(value)
        matrix.refresh()
        manage.refresh()

    def _add_dialog(as_category: bool) -> None:
        with get_session() as s:
            cat_opts = {c.id: c.name for c in s.exec(select(CostCategory)).all()
                        if c.scenario_id == state["scenario"] and c.is_category}
        with ui.dialog() as dialog, ui.card():
            ui.label("Neue Kategorie" if as_category else "Neue Ausgabe").classes("text-lg font-bold")
            name = ui.input("Bezeichnung").classes("w-72")
            line = ui.select({l: PNL_LINE_DE[l] for l in PnlLine}, value=PnlLine.OPEX,
                             label="Bereich (P&L-Zuordnung)").classes("w-72")
            opex = ui.select({o: o.value for o in OpexCategory}, value=OpexCategory.OTHER,
                             label="OPEX-Kategorie (falls Sonstige)").classes("w-72")
            if as_category:
                parent = days = None
            else:
                parent = ui.select({0: "— keine Kategorie —", **cat_opts}, value=0,
                                   label="Kategorie (optional)").classes("w-72")
                days = ui.number("Zahlungsziel (Tage)", value=30, min=0, max=365, step=1).classes("w-72")
            with ui.row():
                ui.button("Abbrechen", on_click=dialog.close).props("flat")

                def _create() -> None:
                    if not name.value:
                        ui.notify("Bezeichnung fehlt", type="warning")
                        return
                    with get_session() as s:
                        order = max([x.sort_order for x in s.exec(select(CostCategory)).all()],
                                    default=0) + 1
                        pl = PnlLine(line.value)
                        s.add(CostCategory(
                            name=name.value, pnl_line=pl,
                            opex_category=(OpexCategory(opex.value) if pl == PnlLine.OPEX else None),
                            is_category=as_category,
                            parent_id=(None if as_category else (int(parent.value) or None)),
                            payment_days=(None if as_category else int(days.value or 0)),
                            scenario_id=state["scenario"], sort_order=order))
                        s.commit()
                    dialog.close()
                    matrix.refresh()
                    manage.refresh()

                ui.button("Anlegen", icon="add", on_click=_create)
        dialog.open()

    def _recurring_dialog() -> None:
        with get_session() as s:
            existing = [(c.id, c.name) for c in s.exec(select(CostCategory)).all()
                        if c.scenario_id == state["scenario"] and not c.is_category]
        with ui.dialog() as dlg, ui.card().classes("min-w-[520px]"):
            ui.label("Wiederkehrende Ausgabe").classes("text-lg font-bold")
            ui.label("Füllt den monatlichen Betrag von Start- bis Endmonat. Einzelne Monate "
                     "bleiben danach editierbar.").classes("text-xs text-gray-500")
            target = ui.select({0: "— neue Position anlegen —", **{i: n for i, n in existing}},
                               value=0, label="Position").classes("w-full")
            new_name = ui.input("Name (falls neu)").classes("w-full")
            line = ui.select({l: PNL_LINE_DE[l] for l in PnlLine}, value=PnlLine.OPEX,
                             label="Bereich (falls neu)").classes("w-full")
            amount = ui.number("Betrag je Monat (€)", value=0, step=100, min=0).classes("w-48")
            with ui.row().classes("items-center gap-3"):
                start_m = ui.select({m: MONTHS_DE[m - 1] for m in range(1, 13)}, value=1,
                                    label="Startmonat").props("dense outlined").classes("w-40")
                end_m = ui.select({m: MONTHS_DE[m - 1] for m in range(1, 13)}, value=12,
                                  label="Endmonat").props("dense outlined").classes("w-40")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    a = float(amount.value or 0)
                    s_m, e_m = int(start_m.value), int(end_m.value)
                    if e_m < s_m:
                        ui.notify("Endmonat vor Startmonat", type="warning")
                        return
                    with get_session() as s:
                        cid = int(target.value)
                        if not cid:
                            if not new_name.value:
                                ui.notify("Name fehlt", type="warning")
                                return
                            order = max([x.sort_order for x in s.exec(select(CostCategory)).all()],
                                        default=0) + 1
                            pl = PnlLine(line.value)
                            c = CostCategory(name=new_name.value, pnl_line=pl,
                                             opex_category=(OpexCategory.OTHER if pl == PnlLine.OPEX else None),
                                             scenario_id=state["scenario"], sort_order=order)
                            s.add(c)
                            s.commit()
                            s.refresh(c)
                            cid = c.id
                        for m in range(s_m, e_m + 1):
                            for ce in s.exec(select(CostCellEntry).where(
                                    CostCellEntry.category_id == cid, CostCellEntry.year == state["year"],
                                    CostCellEntry.month == m)).all():
                                s.delete(ce)
                            pm = _cell_pm(s, cid, state["year"], m)
                            pm.amount = a
                        s.commit()
                    recompute_all()
                    dlg.close()
                    ui.notify(f"Wiederkehrende Ausgabe {MONTHS_DE[s_m-1]}–{MONTHS_DE[e_m-1]} gesetzt",
                              type="positive")
                    matrix.refresh()
                    manage.refresh()

                ui.button("Übernehmen", icon="repeat", on_click=_do)
        dlg.open()

    matrix()
    manage()
