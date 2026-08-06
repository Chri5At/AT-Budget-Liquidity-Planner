"""Einnahmen — revenue streams (typed) with an editable monthly amount matrix."""
from __future__ import annotations

from nicegui import ui
from sqlmodel import select

from ...db import get_session
from ...models import (
    RevenueCellEntry,
    RevenuePayRoutine,
    RevenuePlanMonth,
    RevenueStream,
    RevenueType,
    ScenarioDisable,
)
from ...models.enums import REVENUE_PAY_ROUTINE_DE, REVENUE_TYPE_DE, TERM_DAYS
from ...services.recompute import recompute_all
from ..formatting import MONTHS_DE, eur, eur_exact, page_title, years
from ..grid import DE_NUM_PARSER, fit_grid
from ..components.amount_input import AmountInput
from ..components.scenario_ui import base_toggle_panel, scenario_select

# Routines that need a deposit field, and the one that needs Raten/Laufzeit.
_DEPOSIT_ROUTINES = (RevenuePayRoutine.DEPOSIT_REST, RevenuePayRoutine.INSTALLMENTS)

# Preset cell background colours (label → CSS).
CELL_COLORS = {"": "keine", "#fff3cd": "Gelb", "#d1e7dd": "Grün",
               "#f8d7da": "Rot", "#cfe2ff": "Blau", "#ffe5d0": "Orange", "#e2e3e5": "Grau"}

# ag-Grid cell JS: numeric parser, per-cell colour, value + marker dot renderer.
_CELL_PARSER = DE_NUM_PARSER
# Month cells: category rows are bold (row colour comes from getRowStyle);
# data cells get their own per-cell colour.
_CELL_STYLE = (
    'params => { if (params.data.kind === "category") return {fontWeight:"bold"};'
    ' if (params.data.kind === "grandtotal") return {fontWeight:"bold", backgroundColor:"#e2e8f0"};'
    ' var c = params.data["color"+params.colDef.field.substring(1)];'
    ' return c?{backgroundColor:c}:null; }')
# Whole-row background: a category's chosen colour (or a default tint) tints the row.
_ROW_STYLE = ('params => params.data.kind === "category" '
              '? {backgroundColor: params.data.row_color || "#eef2ff"} : null')
_CELL_RENDER = (
    'params => { var f=params.colDef.field.substring(1);'
    ' var v=(params.value!=null&&params.value!=="")?Math.round(params.value).toLocaleString("de-DE")+" €":"";'
    ' return params.data["mark"+f] ? v+" <span style=\'color:#1976d2;font-weight:bold\''
    ' title=\'Detail/Notiz – Doppelklick\'>•</span>" : v; }')
# Name cell: expand/collapse caret for categories, indent for child/direct lines.
_NAME_RENDER = (
    'params => { var k=params.data.kind, nm=params.data.name||"";'
    ' if (k==="category"){ var ic=params.data.expanded?"▼":"▶";'
    '   return "<span style=\'cursor:pointer;font-weight:bold\'>"+ic+" "+nm+"</span>"; }'
    ' if (k==="grandtotal") return "<b>"+nm+"</b>";'
    ' if (k==="child"||k==="direct"){'
    '   return "<span style=\'padding-left:16px;color:#374151\'>"+nm+"</span>"; }'
    ' return nm; }')


def _stream_days(st: RevenueStream) -> int:
    return st.payment_days if st.payment_days is not None else TERM_DAYS[st.payment_term]


# Types whose breakdown lines are entered as Menge × Preis (qty × price) rather
# than a plain Betrag. Recurring income often has a price per unit (e.g. per sync)
# with a different quantity each month; projects are turbines × price + fees.
_QTY_PRICE_TYPES = (RevenueType.PRODUCT, RevenueType.RECURRING, RevenueType.PROJECT)


def _uses_qty_price(rtype: RevenueType) -> bool:
    return rtype in _QTY_PRICE_TYPES


def _cell_pm(s, stream_id: int, year: int, month: int) -> RevenuePlanMonth:
    pm = s.exec(select(RevenuePlanMonth).where(
        RevenuePlanMonth.stream_id == stream_id, RevenuePlanMonth.year == year,
        RevenuePlanMonth.month == month)).first()
    if pm is None:
        pm = RevenuePlanMonth(stream_id=stream_id, year=year, month=month)
        s.add(pm)
    return pm


def _recompute_cell(s, stream: RevenueStream, year: int, month: int) -> None:
    """Set the cell amount from its line entries (Σ Menge×Preis for products)."""
    entries = s.exec(select(RevenueCellEntry).where(
        RevenueCellEntry.stream_id == stream.id, RevenueCellEntry.year == year,
        RevenueCellEntry.month == month)).all()
    if stream.rtype == RevenueType.PROJECT:
        # Project income = turbines × price + fixed fees (subcontractor is a cost).
        total = sum(e.qty * e.price + e.fixed_fee for e in entries)
        units = sum(e.qty for e in entries)
    elif _uses_qty_price(stream.rtype):
        total = sum(e.qty * e.price for e in entries)
        units = sum(e.qty for e in entries)
    else:
        total = sum(e.amount for e in entries)
        units = 0.0
    pm = _cell_pm(s, stream.id, year, month)
    pm.amount = total
    pm.units = units
    s.commit()


def _apply_cell_content(s, stream: RevenueStream, year: int, month: int, *,
                        use_list: bool, items: list[dict], note: str, color: str,
                        single_value) -> None:
    """Write a cell's full content (line breakdown or single value + note + colour).

    Used both when saving a cell and when copying it to other months.
    """
    for e in s.exec(select(RevenueCellEntry).where(
            RevenueCellEntry.stream_id == stream.id, RevenueCellEntry.year == year,
            RevenueCellEntry.month == month)).all():
        s.delete(e)
    pm = _cell_pm(s, stream.id, year, month)
    if use_list:
        kept = [it for it in items
                if (it["qty"] or it["price"] or it["amount"] or it["note"]
                    or it.get("fixed_fee") or it.get("sub_rate") or it.get("sub_fixed"))]
        for i, it in enumerate(kept):
            s.add(RevenueCellEntry(
                stream_id=stream.id, year=year, month=month, sort_order=i,
                qty=float(it["qty"] or 0), price=float(it["price"] or 0),
                amount=float(it["amount"] or 0), note=it["note"] or "",
                pay_routine=it["routine"], payment_days=int(it["pdays"] or 0),
                deposit_is_pct=bool(it["dep_pct"]), deposit_value=float(it["dep_val"] or 0),
                rate_count=int(it["rates"] or 0), rate_months=int(it["months"] or 0),
                fixed_fee=float(it.get("fixed_fee") or 0), sub_rate=float(it.get("sub_rate") or 0),
                sub_fixed=float(it.get("sub_fixed") or 0), sub_days=int(it.get("sdays") or 0)))
    else:
        pm.amount = float(single_value or 0)
        pm.units = 0.0
    pm.note = note or ""
    pm.color = color or ""
    s.commit()
    if use_list:
        _recompute_cell(s, stream, year, month)


def _save_amount_cell(stream_id: int, year: int, month: int, amount: float) -> None:
    """Direct (single-click) edit: set the value and drop any line breakdown.

    No recompute here — the cashflow ledger is rebuilt when the Liquidität page is
    opened, so rapid cell edits stay instant and don't trigger a page refresh.
    """
    with get_session() as s:
        for e in s.exec(select(RevenueCellEntry).where(
                RevenueCellEntry.stream_id == stream_id, RevenueCellEntry.year == year,
                RevenueCellEntry.month == month)).all():
            s.delete(e)
        pm = _cell_pm(s, stream_id, year, month)
        pm.amount = float(amount or 0)
        pm.units = 0.0
        s.commit()


def _cat_month_total(s, cat_id: int, year: int, month: int) -> int:
    """Category month sum = the category's own value + all its children's values."""
    ids = [cat_id] + [c.id for c in s.exec(select(RevenueStream).where(
        RevenueStream.parent_id == cat_id)).all()]
    total = 0.0
    for cid in ids:
        pm = s.exec(select(RevenuePlanMonth).where(
            RevenuePlanMonth.stream_id == cid, RevenuePlanMonth.year == year,
            RevenuePlanMonth.month == month)).first()
        if pm:
            total += pm.amount
    return round(total)


def _month_grand_totals(s, year: int, scenario_id: int) -> list[int]:
    """Per-month total across all rows (each row's own value counts once) for the
    pinned bottom Σ-row."""
    ids = {st.id for st in s.exec(select(RevenueStream)).all() if st.scenario_id == scenario_id}
    totals = [0.0] * 12
    for pm in s.exec(select(RevenuePlanMonth).where(RevenuePlanMonth.year == year)).all():
        if pm.stream_id in ids and 1 <= pm.month <= 12:
            totals[pm.month - 1] += pm.amount
    return [round(x) for x in totals]


def _grandtotal_row(totals: list[int]) -> dict:
    row = {"rid": "grandtotal", "kind": "grandtotal", "name": "Σ Gesamt / Monat"}
    for i, v in enumerate(totals):
        row[f"m{i + 1}"] = v
    return row


def _save_name_cell(stream_id: int, name: str) -> None:
    with get_session() as s:
        st = s.get(RevenueStream, stream_id)
        if st is not None:
            st.name = name
            s.add(st)
            s.commit()


def _data_row(s, st: RevenueStream, year: int, kind: str, *, name: str | None = None,
              cat_id: int | None = None) -> dict:
    """A normal editable data row (leaf / child / direct) for one stream."""
    months = {p.month: p for p in s.exec(select(RevenuePlanMonth).where(
        RevenuePlanMonth.stream_id == st.id, RevenuePlanMonth.year == year)).all()}
    ent_months = {e.month for e in s.exec(select(RevenueCellEntry).where(
        RevenueCellEntry.stream_id == st.id, RevenueCellEntry.year == year)).all()}
    row = {"rid": f"{kind}-{st.id}", "id": st.id, "kind": kind, "cat_id": cat_id,
           "name": name if name is not None else st.name,
           "typ": REVENUE_TYPE_DE[st.rtype]}
    for m in range(1, 13):
        pm = months.get(m)
        row[f"m{m}"] = round(pm.amount) if pm else 0
        row[f"color{m}"] = pm.color if pm else ""
        row[f"mark{m}"] = bool((pm and pm.note) or m in ent_months)
        # Cells with a line-item breakdown are locked against single-click edits
        # (editing would discard the breakdown) — edit them via double-click.
        row[f"detail{m}"] = m in ent_months
    return row


def _own_amounts(s, stream_id: int, year: int) -> list[float]:
    months = {p.month: p.amount for p in s.exec(select(RevenuePlanMonth).where(
        RevenuePlanMonth.stream_id == stream_id, RevenuePlanMonth.year == year)).all()}
    return [round(months.get(m, 0.0)) for m in range(1, 13)]


def _load_tree_rows(year: int, scenario_id: int, collapsed: set) -> list[dict]:
    """Flat, tree-ordered rows: categories (with summed children) then their lines."""
    with get_session() as s:
        scoped = [st for st in s.exec(select(RevenueStream).order_by(
            RevenueStream.sort_order, RevenueStream.id)).all() if st.scenario_id == scenario_id]
        children_of: dict[int, list] = {}
        tops = []
        for st in scoped:
            if st.parent_id:
                children_of.setdefault(st.parent_id, []).append(st)
            else:
                tops.append(st)

        rows: list[dict] = []
        for st in tops:
            if st.is_category:
                kids = children_of.get(st.id, [])
                expanded = st.id not in collapsed
                totals = _own_amounts(s, st.id, year)
                for kid in kids:
                    ka = _own_amounts(s, kid.id, year)
                    totals = [totals[i] + ka[i] for i in range(12)]
                cat = {"rid": f"cat-{st.id}", "id": st.id, "kind": "category",
                       "name": st.name, "typ": f"Kategorie · {len(kids)}",
                       "expanded": expanded, "row_color": st.color or ""}
                for m in range(1, 13):
                    cat[f"m{m}"] = totals[m - 1]
                    cat[f"color{m}"] = ""
                    cat[f"mark{m}"] = False
                    cat[f"detail{m}"] = False
                rows.append(cat)
                if expanded:
                    rows.append(_data_row(s, st, year, "direct",
                                          name="↳ Allgemein (direkt)", cat_id=st.id))
                    for kid in kids:
                        rows.append(_data_row(s, kid, year, "child", cat_id=st.id))
            else:
                rows.append(_data_row(s, st, year, "leaf"))
        return rows


def _save_row(year: int, data: dict) -> None:
    with get_session() as s:
        st = s.get(RevenueStream, int(data["id"]))
        if st is None:
            return
        st.name = data.get("name", st.name)
        s.add(st)
        for m in range(1, 13):
            try:
                val = float(data.get(f"m{m}", 0) or 0)
            except (TypeError, ValueError):
                val = 0.0
            p = s.exec(select(RevenuePlanMonth).where(
                RevenuePlanMonth.stream_id == st.id, RevenuePlanMonth.year == year,
                RevenuePlanMonth.month == m)).first()
            if p is None:
                s.add(RevenuePlanMonth(stream_id=st.id, year=year, month=m, amount=val))
            else:
                p.amount = val
        s.commit()


def render() -> None:
    state = {"year": years()[0], "scenario": 1, "collapsed": set()}

    page_title("Einnahmen",
               "Umsatz je Einnahmequelle und Monat. Kategorien gruppieren Quellen; die "
               "Kategoriezeile zeigt die Summe. Doppelklick auf eine Zelle öffnet die "
               "Detail-Aufstellung (Menge × Preis, Zahlungsweisen, Projekt/Subunternehmer).")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.select(years(), value=state["year"], label="Jahr",
                  on_change=lambda e: _change_year(e.value)).props("outlined dense").classes("w-28")
        scenario_select(state["scenario"], lambda v: _change_scenario(v))
        ui.button("Einnahmequelle hinzufügen", icon="add", on_click=lambda: _add_dialog(False))
        ui.button("Kategorie hinzufügen", icon="create_new_folder",
                  on_click=lambda: _add_dialog(True)).props("outline")

    @ui.refreshable
    def matrix() -> None:
        rows = _load_tree_rows(state["year"], state["scenario"], state["collapsed"])
        if not rows and state["scenario"] != 1:
            ui.label("Keine Einnahmen in diesem Szenario — füge Positionen hinzu.").classes(
                "text-sm text-gray-500")
        editable = "params => params.data.kind !== 'category'"
        # Month cells are NOT single-click editable when they carry a line-item
        # breakdown (editing would discard it) — those are edited via double-click.
        editable_month = ("params => params.data.kind !== 'category' && "
                          "!params.data['detail'+params.colDef.field.substring(1)]")
        col_defs = [
            {"headerName": "", "width": 38, "pinned": "left", "sortable": False,
             "resizable": False, "suppressMenu": True, "suppressSizeToFit": True,
             ":valueGetter": "() => ''",
             # Drag everything except the synthetic "direct" row (it belongs to its category).
             ":rowDrag": "params => params.data.kind !== 'direct'"},
            {"headerName": "Einnahmequelle / Kategorie", "field": "name", "suppressSizeToFit": True,
             "pinned": "left", "width": 240, ":editable": editable, ":cellRenderer": _NAME_RENDER},
            {"headerName": "Typ", "field": "typ", "width": 150, "suppressSizeToFit": True},
        ]
        for m in range(1, 13):
            col_defs.append({"headerName": MONTHS_DE[m - 1], "field": f"m{m}",
                             "width": 96, "minWidth": 64, "type": "numericColumn",
                             ":editable": editable_month,
                             ":valueParser": _CELL_PARSER, ":cellStyle": _CELL_STYLE,
                             ":cellRenderer": _CELL_RENDER})
        year_getter = "params => " + "+".join(f"(Number(params.data.m{m})||0)" for m in range(1, 13))
        col_defs.append({"headerName": "Jahr", "field": "jahr", "pinned": "right", "width": 110,
                         "type": "numericColumn", "cellClass": "font-bold", "suppressSizeToFit": True,
                         ":valueGetter": year_getter,
                         ":valueFormatter": "p=>Math.round(p.value||0).toLocaleString('de-DE')+' €'"})
        # Pinned bottom row: total per month across top-level rows (categories
        # already include their children; leaves count once).
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
        # Top-level total = leaf rows + category rows (children are already in the category sum).
        total = sum(r[f"m{m}"] for r in rows for m in range(1, 13)
                    if r["kind"] in ("category", "leaf"))
        ui.label(f"Eigene Einnahmen {state['year']}: {eur(total)}").classes("text-sm font-semibold mt-1")
        ui.label("Einfachklick = Wert · Doppelklick = Detail/Notiz/Farbe · Klick auf ▶/▼ = "
                 "Kategorie auf/zu · Ziehen am Griff ⠿ = Reihenfolge / in Kategorie verschieben"
                 ).classes("text-xs text-gray-500")
        base_toggle_panel(state["scenario"], "revenue", RevenueStream, matrix.refresh)

    def _cell_col(args) -> str:
        return args.get("colId") or args.get("column") or ""

    def _on_cell_edit(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        col = _cell_col(a)
        if "id" not in data or data.get("kind") == "category":
            return
        sid = int(data["id"])
        if col == "name":
            _save_name_cell(sid, data.get("name", ""))
        elif isinstance(col, str) and col.startswith("m") and col[1:].isdigit():
            # Never overwrite a cell that has a line-item breakdown (data protection).
            if data.get(f"detail{col[1:]}"):
                return
            month = int(col[1:])
            _save_amount_cell(sid, state["year"], month, data.get(col, 0))
            grid = state.get("grid")
            if grid is None:
                return
            # A child/direct edit changes its category total — update ONLY that
            # category's cell in place (no full refresh → keeps focus for fast editing).
            cat_id = data.get("cat_id")
            with get_session() as s:
                if cat_id:
                    grid.run_row_method(f"cat-{cat_id}", "setDataValue", col,
                                        _cat_month_total(s, int(cat_id), state["year"], month))
                totals = _month_grand_totals(s, state["year"], state["scenario"])
            # Refresh the pinned bottom Σ-row (its month total just changed).
            grid.run_grid_method("setGridOption", "pinnedBottomRowData", [_grandtotal_row(totals)])

    def _on_cell_click(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        if data.get("kind") == "category" and _cell_col(a) == "name":
            cid = int(data["id"])
            state["collapsed"] ^= {cid}  # toggle membership
            matrix.refresh()

    def _on_cell_dblclick(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        col = _cell_col(a)
        if (data.get("kind") != "category" and "id" in data
                and isinstance(col, str) and col.startswith("m") and col[1:].isdigit()):
            _open_cell_modal(int(data["id"]), state["year"], int(col[1:]))

    async def _on_drag_end(e) -> None:
        """Persist a drag: re-derive each row's category (parent) and order from the
        new on-screen position. A row dropped inside a category becomes its child;
        dropped above all categories it becomes a top-level source."""
        try:
            client_rows = await e.sender.get_client_data()
        except Exception:
            return
        seq = [(r.get("kind"), int(r["id"])) for r in client_rows
               if "id" in r and r.get("kind") in ("category", "child", "leaf")]
        with get_session() as s:
            scoped = {st.id: st for st in s.exec(select(RevenueStream)).all()
                      if st.scenario_id == state["scenario"]}
            top_order: list[int] = []
            cat_children: dict[int, list[int]] = {}
            current_cat = None
            for kind, sid in seq:
                if sid not in scoped:
                    continue
                if kind == "category":
                    top_order.append(sid)
                    cat_children.setdefault(sid, [])
                    current_cat = sid
                elif current_cat is not None:
                    cat_children.setdefault(current_cat, []).append(sid)
                else:
                    top_order.append(sid)
            # Re-attach children of collapsed categories that weren't on screen.
            seen = set(top_order) | {c for kids in cat_children.values() for c in kids}
            for st in scoped.values():
                if st.id in seen or st.is_category:
                    continue
                if st.parent_id in cat_children:
                    cat_children[st.parent_id].append(st.id)
            # Assign a single increasing order across the rebuilt tree.
            counter = 0
            for sid in top_order:
                st = scoped[sid]
                st.parent_id = None
                st.sort_order = counter
                counter += 1
                for cid in cat_children.get(sid, []):
                    c = scoped[cid]
                    c.parent_id = sid
                    c.sort_order = counter
                    counter += 1
            s.commit()
        matrix.refresh()
        manage.refresh()

    def _open_cell_modal(stream_id: int, year: int, month: int) -> None:
        with get_session() as s:
            stream = s.get(RevenueStream, stream_id)
            if stream is None:
                return
            is_product = stream.rtype == RevenueType.PRODUCT
            is_project = stream.rtype == RevenueType.PROJECT
            qty_mode = _uses_qty_price(stream.rtype)   # Menge × Preis lines
            sname = stream.name
            default_days = _stream_days(stream)
            pm = s.exec(select(RevenuePlanMonth).where(
                RevenuePlanMonth.stream_id == stream_id, RevenuePlanMonth.year == year,
                RevenuePlanMonth.month == month)).first()
            note0 = pm.note if pm else ""
            color0 = pm.color if pm else ""
            amount0 = pm.amount if pm else 0.0
            items = [{"qty": e.qty, "price": e.price, "amount": e.amount, "note": e.note,
                      "routine": e.pay_routine,
                      "pdays": e.payment_days if e.payment_days is not None else default_days,
                      "dep_pct": e.deposit_is_pct, "dep_val": e.deposit_value,
                      "rates": e.rate_count, "months": e.rate_months,
                      "fixed_fee": e.fixed_fee, "sub_rate": e.sub_rate, "sub_fixed": e.sub_fixed,
                      "sdays": e.sub_days if e.sub_days is not None else default_days}
                     for e in s.exec(select(RevenueCellEntry).where(
                         RevenueCellEntry.stream_id == stream_id, RevenueCellEntry.year == year,
                         RevenueCellEntry.month == month).order_by(
                         RevenueCellEntry.sort_order, RevenueCellEntry.id)).all()]

        def _new_item() -> dict:
            return {"qty": 0.0, "price": 0.0, "amount": 0.0, "note": "",
                    "routine": RevenuePayRoutine.ON_DELIVERY, "pdays": default_days,
                    "dep_pct": True, "dep_val": 0.0, "rates": 3, "months": 6,
                    "fixed_fee": 0.0, "sub_rate": 0.0, "sub_fixed": 0.0, "sdays": default_days}

        if not items:
            items = [_new_item()]
        modal = {"color": color0}

        def _line_rev(it: dict) -> float:
            base = (it["qty"] or 0) * (it["price"] or 0)
            return base + (it["fixed_fee"] or 0) if is_project else base

        def _line_sub(it: dict) -> float:
            return (it["qty"] or 0) * (it["sub_rate"] or 0) + (it["sub_fixed"] or 0)

        def _total() -> float:
            if qty_mode:
                return sum(_line_rev(it) for it in items)
            return sum((it["amount"] or 0) for it in items)

        def _sub_total() -> float:
            return sum(_line_sub(it) for it in items)

        has_list = any((it["qty"] or it["price"] or it["amount"] or it["note"]) for it in items)
        modal["use_list"] = has_list

        with ui.dialog() as dlg, ui.card().classes("min-w-[760px]"):
            ui.label(f"{sname} — {MONTHS_DE[month - 1]} {year}").classes("text-lg font-bold")

            # (1) Single cell value at the top — used when no detail list is active.
            with ui.row().classes("items-center gap-3"):
                single_in = AmountInput("Einzelwert (€)", value=amount0).classes("w-44")
                use_list_sw = ui.switch("Detail-Aufstellung verwenden", value=has_list)

            # (2) Allgemeine Notiz, (3) Zellenfarbe
            with ui.row().classes("items-center gap-3 mt-1"):
                note_in = ui.input("Allgemeine Notiz", value=note0).classes("w-80")
                ui.select(CELL_COLORS, value=color0, label="Zellenfarbe",
                          on_change=lambda e: modal.update(color=e.value)
                          ).props("dense outlined").classes("w-40")

            # (4) the detail list
            list_box = ui.column().classes("w-full mt-2")
            total_label = ui.label().classes("text-sm font-semibold")

            def _refresh_total() -> None:
                if is_project:
                    rev, sub = _total(), _sub_total()
                    total_label.text = (f"Umsatz {eur_exact(rev)}  ·  Subunternehmer −{eur_exact(sub)}"
                                        f"  ·  Netto-Marge {eur_exact(rev - sub)}")
                else:
                    total_label.text = f"Summe Aufstellung: {eur_exact(_total())}"

            @ui.refreshable
            def lines() -> None:
                for idx, it in enumerate(items):
                    with ui.card().classes("w-full p-2 gap-1"):
                        with ui.row().classes("items-center gap-2"):
                            if qty_mode:
                                ui.number("Menge" if is_project else "Menge", value=it["qty"], step=1,
                                          on_change=lambda e, it=it: (it.__setitem__("qty", e.value or 0),
                                                                      _refresh_total())
                                          ).props("dense outlined").classes("w-24")
                                AmountInput("Preis", value=it["price"],
                                            on_amount_change=lambda v, it=it: (
                                                it.__setitem__("price", v), _refresh_total())
                                            ).classes("w-28")
                                if is_project:
                                    AmountInput("Fixkosten (€)", value=it["fixed_fee"],
                                                on_amount_change=lambda v, it=it: (
                                                    it.__setitem__("fixed_fee", v), _refresh_total())
                                                ).classes("w-32").tooltip(
                                        "Projektgebühr / Mob-Demob / Standby (Summe)")
                                else:
                                    ui.label(f"= {eur((it['qty'] or 0) * (it['price'] or 0))}").classes(
                                        "text-xs text-gray-500 w-28")
                                ui.input("Notiz", value=it["note"],
                                         on_change=lambda e, it=it: it.__setitem__("note", e.value or "")
                                         ).props("dense outlined").classes("w-48" if is_project else "w-64")
                            else:
                                AmountInput("Betrag", value=it["amount"],
                                            on_amount_change=lambda v, it=it: (
                                                it.__setitem__("amount", v), _refresh_total())
                                            ).classes("w-32")
                                ui.input("Notiz", value=it["note"],
                                         on_change=lambda e, it=it: it.__setitem__("note", e.value or "")
                                         ).props("dense outlined").classes("w-80")

                            def _remove(it=it) -> None:
                                items.remove(it)
                                if not items:
                                    items.append(_new_item())
                                lines.refresh()
                                _refresh_total()

                            ui.button(icon="close", on_click=_remove).props("flat round dense")

                        if is_product:
                            _product_payment_row(it)
                        if is_project:
                            _project_row(it)

            def _project_row(it: dict) -> None:
                with ui.row().classes("items-center gap-2"):
                    ui.number("Kunden-Ziel (Tage)", value=it["pdays"], min=0, max=365, step=1,
                              on_change=lambda e, it=it: it.__setitem__("pdays", int(e.value or 0))
                              ).props("dense outlined").classes("w-36").tooltip("Wann der Kunde zahlt")
                    ui.label("Subunternehmer:").classes("text-xs text-gray-500")
                    AmountInput("Satz/Turbine (€)", value=it["sub_rate"],
                                on_amount_change=lambda v, it=it: (
                                    it.__setitem__("sub_rate", v), _refresh_total())
                                ).classes("w-32")
                    AmountInput("Sub-Fix (€)", value=it["sub_fixed"],
                                on_amount_change=lambda v, it=it: (
                                    it.__setitem__("sub_fixed", v), _refresh_total())
                                ).classes("w-28").tooltip(
                        "Fixe Subunternehmer-Kosten (Standby, Mob-Demob, Setup)")
                    ui.number("Sub-Ziel (Tage)", value=it["sdays"], min=0, max=365, step=1,
                              on_change=lambda e, it=it: it.__setitem__("sdays", int(e.value or 0))
                              ).props("dense outlined").classes("w-32").tooltip(
                        "Wann wir den Subunternehmer zahlen (ab Monatsende)")
                    ui.label(f"Netto {eur(_line_rev(it) - _line_sub(it))}").classes(
                        "text-xs font-medium text-gray-600")

            def _product_payment_row(it: dict) -> None:
                with ui.row().classes("items-center gap-2"):
                    ui.select({r: REVENUE_PAY_ROUTINE_DE[r] for r in RevenuePayRoutine},
                              value=it["routine"], label="Zahlungsweise",
                              on_change=lambda e, it=it: (it.__setitem__("routine", RevenuePayRoutine(e.value)),
                                                          lines.refresh())
                              ).props("dense outlined").classes("w-72")
                    if it["routine"] != RevenuePayRoutine.ON_ORDER:
                        ui.number("Zahlungsziel (Tage)", value=it["pdays"], min=0, max=365, step=1,
                                  on_change=lambda e, it=it: it.__setitem__("pdays", int(e.value or 0))
                                  ).props("dense outlined").classes("w-36")
                    if it["routine"] in _DEPOSIT_ROUTINES:
                        AmountInput("Anzahlung", value=it["dep_val"],
                                    on_amount_change=lambda v, it=it: it.__setitem__("dep_val", v)
                                    ).classes("w-28")
                        ui.toggle({True: "%", False: "€"}, value=it["dep_pct"],
                                  on_change=lambda e, it=it: it.__setitem__("dep_pct", bool(e.value))
                                  ).props("dense")
                    if it["routine"] == RevenuePayRoutine.INSTALLMENTS:
                        ui.number("Raten", value=it["rates"], min=1, max=60, step=1,
                                  on_change=lambda e, it=it: it.__setitem__("rates", int(e.value or 1))
                                  ).props("dense outlined").classes("w-24")
                        ui.number("Laufzeit (Mon.)", value=it["months"], min=1, max=120, step=1,
                                  on_change=lambda e, it=it: it.__setitem__("months", int(e.value or 1))
                                  ).props("dense outlined").classes("w-32")

            with list_box:
                lines()

                def _add_line() -> None:
                    items.append(_new_item())
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

            # Copy this cell (incl. the whole breakdown) to other months of the same row.
            copy_sel = ui.select({m: MONTHS_DE[m - 1] for m in range(1, 13) if m != month},
                                 multiple=True, label="Auch in diese Monate kopieren (optional)"
                                 ).props("dense outlined use-chips").classes("w-full mt-2")

            with ui.row().classes("mt-2"):
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _save() -> None:
                    use_list = modal["use_list"]
                    targets = sorted({month, *[int(m) for m in (copy_sel.value or [])]})
                    with get_session() as s:
                        stream2 = s.get(RevenueStream, stream_id)
                        for tm in targets:
                            _apply_cell_content(
                                s, stream2, year, tm, use_list=use_list, items=items,
                                note=note_in.value, color=modal["color"],
                                single_value=single_in.amount)
                    recompute_all()
                    dlg.close()
                    matrix.refresh()
                    extra = len(targets) - 1
                    msg = ("Zelle gespeichert" if not extra
                           else f"Zelle gespeichert und in {extra} weitere Monate kopiert")
                    ui.notify(msg, type="positive")

                ui.button("Speichern", icon="save", on_click=_save)
        dlg.open()

    @ui.refreshable
    def manage() -> None:
        with get_session() as s:
            streams = [st for st in s.exec(select(RevenueStream).order_by(
                RevenueStream.sort_order, RevenueStream.id)).all()
                if st.scenario_id == state["scenario"]]
            cats = {st.id: st.name for st in streams if st.is_category}
            data = [(st.id, st.name, st.rtype, _stream_days(st), st.is_vatable,
                     st.is_category, st.parent_id, st.color or "") for st in streams]
        # Parent options: "no category" + every category (a category can't be its own parent).
        with ui.expansion("Einnahmequellen & Kategorien bearbeiten (Typ, Zahlungsziel, "
                          "Kategorie, löschen)", icon="tune").classes("w-full"):
            if not data:
                ui.label("Keine eigenen Einnahmequellen in diesem Szenario.").classes(
                    "text-sm text-gray-500")
            for sid, name, rtype, days, vat, is_cat, parent_id, color in data:
                with ui.row().classes("items-center gap-2"):
                    with ui.column().classes("gap-0"):
                        ui.button(icon="keyboard_arrow_up", on_click=lambda sid=sid: _move(sid, -1)
                                  ).props("flat dense").classes("w-6 h-4").tooltip("nach oben")
                        ui.button(icon="keyboard_arrow_down", on_click=lambda sid=sid: _move(sid, 1)
                                  ).props("flat dense").classes("w-6 h-4").tooltip("nach unten")
                    icon = "create_new_folder" if is_cat else "trending_up"
                    ui.icon(icon).classes("text-gray-400")
                    ui.input("Bezeichnung", value=name,
                             on_change=lambda e, sid=sid: _save_field(sid, name=e.value)
                             ).props("dense outlined").classes("w-48")
                    type_label = "Typ (Direkt-Einnahme)" if is_cat else "Typ"
                    ui.select({t: REVENUE_TYPE_DE[t] for t in RevenueType}, value=rtype,
                              label=type_label,
                              on_change=lambda e, sid=sid: _save_field(sid, rtype=RevenueType(e.value))
                              ).props("dense outlined").classes("w-48")
                    if is_cat:
                        ui.select(CELL_COLORS, value=color, label="Farbe",
                                  on_change=lambda e, sid=sid: _save_field(sid, color=e.value)
                                  ).props("dense outlined").classes("w-32")
                    else:
                        parent_opts = {0: "— keine Kategorie —", **{cid: nm for cid, nm in cats.items()}}
                        ui.select(parent_opts, value=parent_id or 0, label="Kategorie",
                                  on_change=lambda e, sid=sid: _save_field(
                                      sid, parent_id=(int(e.value) or None))
                                  ).props("dense outlined").classes("w-44")
                    ui.number("Ziel (Tage)", value=days, min=0, max=365, step=1,
                              on_change=lambda e, sid=sid: _save_field(sid, payment_days=int(e.value or 0))
                              ).props("dense outlined").classes("w-28")
                    ui.checkbox("USt", value=vat,
                                on_change=lambda e, sid=sid: _save_field(sid, is_vatable=bool(e.value)))
                    ui.button(icon="delete", on_click=lambda sid=sid, name=name, is_cat=is_cat:
                              _delete_stream(sid, name, is_cat)
                              ).props("flat round dense color=negative").tooltip("löschen")

    def _move(sid: int, delta: int) -> None:
        """Move within siblings only (same category / same top level) by swapping
        sort_order with the adjacent sibling — never jumps across categories."""
        with get_session() as s:
            target = s.get(RevenueStream, sid)
            if target is None:
                return
            sibs = [st for st in s.exec(select(RevenueStream).order_by(
                RevenueStream.sort_order, RevenueStream.id)).all()
                if st.scenario_id == state["scenario"] and st.parent_id == target.parent_id]
            ids = [st.id for st in sibs]
            i = ids.index(sid)
            j = i + delta
            if j < 0 or j >= len(ids):
                return
            sibs[i].sort_order, sibs[j].sort_order = sibs[j].sort_order, sibs[i].sort_order
            s.commit()
        matrix.refresh()
        manage.refresh()

    def _save_field(sid: int, **kw) -> None:
        with get_session() as s:
            st = s.get(RevenueStream, sid)
            if st is None:
                return
            for k, v in kw.items():
                setattr(st, k, v)
            s.add(st)
            s.commit()
        recompute_all()

    def _delete_stream(sid: int, name: str, is_cat: bool = False) -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label(f'„{name}" löschen?').classes("text-lg font-bold")
            ui.label("Kategorie löschen: die enthaltenen Quellen werden zu obersten Quellen "
                     "(nicht gelöscht)." if is_cat
                     else "Alle Monatswerte dieser Quelle werden entfernt.").classes(
                "text-sm text-gray-500")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    with get_session() as s:
                        if is_cat:
                            for kid in s.exec(select(RevenueStream).where(
                                    RevenueStream.parent_id == sid)).all():
                                kid.parent_id = None
                                s.add(kid)
                        for p in s.exec(select(RevenuePlanMonth).where(
                                RevenuePlanMonth.stream_id == sid)).all():
                            s.delete(p)
                        for ce in s.exec(select(RevenueCellEntry).where(
                                RevenueCellEntry.stream_id == sid)).all():
                            s.delete(ce)
                        for d in s.exec(select(ScenarioDisable).where(
                                ScenarioDisable.ref_kind == "revenue",
                                ScenarioDisable.ref_id == sid)).all():
                            s.delete(d)
                        st = s.get(RevenueStream, sid)
                        if st is not None:
                            s.delete(st)
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
            cats = {st.id: st.name for st in s.exec(select(RevenueStream)).all()
                    if st.scenario_id == state["scenario"] and st.is_category}
        with ui.dialog() as dialog, ui.card():
            ui.label("Neue Kategorie" if as_category else "Neue Einnahmequelle").classes(
                "text-lg font-bold")
            name = ui.input("Bezeichnung").classes("w-72")
            if as_category:
                ui.label("Eine Kategorie gruppiert Einnahmequellen. Eigene Werte werden in der "
                         "Zeile Allgemein (direkt) erfasst.").classes("text-xs text-gray-500")
                rtype = days = vat = parent = None
            else:
                rtype = ui.select({t: REVENUE_TYPE_DE[t] for t in RevenueType},
                                  value=RevenueType.RECURRING, label="Typ").classes("w-72")
                parent = ui.select({0: "— keine Kategorie —", **cats}, value=0,
                                   label="Kategorie (optional)").classes("w-72")
                days = ui.number("Zahlungsziel (Tage)", value=30, min=0, max=365, step=1).classes("w-72")
                vat = ui.checkbox("umsatzsteuerpflichtig", value=True)
            with ui.row():
                ui.button("Abbrechen", on_click=dialog.close).props("flat")

                def _create() -> None:
                    if not name.value:
                        ui.notify("Bezeichnung fehlt", type="warning")
                        return
                    with get_session() as s:
                        order = max([x.sort_order for x in s.exec(select(RevenueStream)).all()],
                                    default=0) + 1
                        if as_category:
                            s.add(RevenueStream(name=name.value, is_category=True,
                                                scenario_id=state["scenario"], sort_order=order))
                        else:
                            s.add(RevenueStream(
                                name=name.value, rtype=RevenueType(rtype.value),
                                payment_days=int(days.value or 0), is_vatable=bool(vat.value),
                                parent_id=(int(parent.value) or None),
                                scenario_id=state["scenario"], sort_order=order))
                        s.commit()
                    dialog.close()
                    matrix.refresh()
                    manage.refresh()

                ui.button("Anlegen", on_click=_create)
        dialog.open()

    matrix()
    manage()
