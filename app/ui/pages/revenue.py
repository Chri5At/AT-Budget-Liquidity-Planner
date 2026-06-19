"""Einnahmen — revenue streams (typed) with an editable monthly amount matrix."""
from __future__ import annotations

from nicegui import ui
from sqlmodel import select

from ...db import get_session
from ...models import (
    RevenueCellEntry,
    RevenuePlanMonth,
    RevenueStream,
    RevenueType,
    ScenarioDisable,
)
from ...models.enums import REVENUE_TYPE_DE, TERM_DAYS
from ...services.recompute import recompute_all
from ..formatting import MONTHS_DE, YEARS, eur
from ..components.scenario_ui import base_toggle_panel, scenario_select

# Preset cell background colours (label → CSS).
CELL_COLORS = {"": "keine", "#fff3cd": "Gelb", "#d1e7dd": "Grün",
               "#f8d7da": "Rot", "#cfe2ff": "Blau", "#ffe5d0": "Orange", "#e2e3e5": "Grau"}

# ag-Grid cell JS: numeric parser, per-cell colour, value + marker dot renderer.
_CELL_PARSER = 'params => (params.newValue===""||params.newValue==null)?0:Number(params.newValue)'
_CELL_STYLE = ('params => { var c = params.data["color"+params.colDef.field.substring(1)];'
               ' return c?{backgroundColor:c}:null; }')
_CELL_RENDER = (
    'params => { var f=params.colDef.field.substring(1);'
    ' var v=(params.value!=null&&params.value!=="")?Math.round(params.value).toLocaleString("de-DE")+" €":"";'
    ' return params.data["mark"+f] ? v+" <span style=\'color:#1976d2;font-weight:bold\''
    ' title=\'Detail/Notiz – Doppelklick\'>•</span>" : v; }')


def _stream_days(st: RevenueStream) -> int:
    return st.payment_days if st.payment_days is not None else TERM_DAYS[st.payment_term]


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
    if stream.rtype == RevenueType.PRODUCT:
        total = sum(e.qty * e.price for e in entries)
        units = sum(e.qty for e in entries)
    else:
        total = sum(e.amount for e in entries)
        units = 0.0
    pm = _cell_pm(s, stream.id, year, month)
    pm.amount = total
    pm.units = units
    s.commit()


def _save_amount_cell(stream_id: int, year: int, month: int, amount: float) -> None:
    """Direct (single-click) edit: set the value and drop any line breakdown."""
    with get_session() as s:
        for e in s.exec(select(RevenueCellEntry).where(
                RevenueCellEntry.stream_id == stream_id, RevenueCellEntry.year == year,
                RevenueCellEntry.month == month)).all():
            s.delete(e)
        pm = _cell_pm(s, stream_id, year, month)
        pm.amount = float(amount or 0)
        pm.units = 0.0
        s.commit()
    recompute_all()


def _save_name_cell(stream_id: int, name: str) -> None:
    with get_session() as s:
        st = s.get(RevenueStream, stream_id)
        if st is not None:
            st.name = name
            s.add(st)
            s.commit()


def _load_rows(year: int, scenario_id: int) -> list[dict]:
    with get_session() as s:
        streams = [st for st in s.exec(select(RevenueStream).order_by(
            RevenueStream.sort_order, RevenueStream.id)).all() if st.scenario_id == scenario_id]
        rows = []
        for st in streams:
            months = {p.month: p for p in s.exec(select(RevenuePlanMonth).where(
                RevenuePlanMonth.stream_id == st.id, RevenuePlanMonth.year == year)).all()}
            ent_months = {e.month for e in s.exec(select(RevenueCellEntry).where(
                RevenueCellEntry.stream_id == st.id, RevenueCellEntry.year == year)).all()}
            row = {"id": st.id, "name": st.name, "typ": REVENUE_TYPE_DE[st.rtype]}
            for m in range(1, 13):
                pm = months.get(m)
                row[f"m{m}"] = round(pm.amount) if pm else 0
                row[f"color{m}"] = pm.color if pm else ""
                row[f"mark{m}"] = bool((pm and pm.note) or m in ent_months)
            rows.append(row)
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
    state = {"year": YEARS[0], "scenario": 1}

    ui.label("Einnahmen").classes("text-xl font-bold")
    ui.label("Umsatz je Einnahmequelle und Monat. Zahlungsziel steuert den Geldeingang "
             "in der Liquidität.").classes("text-sm text-gray-500")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.select(YEARS, value=state["year"], label="Jahr",
                  on_change=lambda e: _change_year(e.value)).props("outlined dense").classes("w-28")
        scenario_select(state["scenario"], lambda v: _change_scenario(v))
        ui.button("Einnahmequelle hinzufügen", icon="add", on_click=lambda: _add_dialog())

    @ui.refreshable
    def matrix() -> None:
        rows = _load_rows(state["year"], state["scenario"])
        if not rows and state["scenario"] != 1:
            ui.label("Keine eigenen Einnahmen in diesem Szenario — füge welche hinzu oder "
                     "schalte unten Basis-Positionen ein/aus.").classes("text-sm text-gray-500")
        col_defs = [
            {"headerName": "", "rowDrag": True, "width": 40, "pinned": "left",
             "sortable": False, "resizable": False, "suppressMenu": True, "valueGetter": "''"},
            {"headerName": "Einnahmequelle", "field": "name", "editable": True,
             "pinned": "left", "width": 200},
            {"headerName": "Typ", "field": "typ", "width": 150},
        ]
        for m in range(1, 13):
            col_defs.append({"headerName": MONTHS_DE[m - 1], "field": f"m{m}", "editable": True,
                             "width": 96, "type": "numericColumn", ":valueParser": _CELL_PARSER,
                             ":cellStyle": _CELL_STYLE, ":cellRenderer": _CELL_RENDER})
        year_getter = "params => " + "+".join(f"(Number(params.data.m{m})||0)" for m in range(1, 13))
        col_defs.append({"headerName": "Jahr", "field": "jahr", "pinned": "right", "width": 110,
                         "type": "numericColumn", "cellClass": "font-bold", ":valueGetter": year_getter,
                         ":valueFormatter": "p=>Math.round(p.value||0).toLocaleString('de-DE')+' €'"})
        grid = ui.aggrid({
            "columnDefs": col_defs, "rowData": rows,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            "singleClickEdit": True, "stopEditingWhenCellsLoseFocus": True,
            "rowDragManaged": True, "animateRows": True, "domLayout": "autoHeight",
            ":getRowId": "params => String(params.data.id)",
        }).classes("w-full").style("height: auto")
        grid.on("cellValueChanged", _on_cell_edit)
        grid.on("cellDoubleClicked", _on_cell_dblclick)
        grid.on("rowDragEnd", _on_drag_end)
        total = sum(r[f"m{m}"] for r in rows for m in range(1, 13))
        ui.label(f"Eigene Einnahmen {state['year']}: {eur(total)}").classes("text-sm font-semibold mt-1")
        ui.label("Einfachklick = Wert eingeben · Doppelklick = Detail/Notiz/Farbe · "
                 "Ziehen am Griff ⠿ = Reihenfolge").classes("text-xs text-gray-500")
        base_toggle_panel(state["scenario"], "revenue", RevenueStream, matrix.refresh)

    def _cell_col(args) -> str:
        return args.get("colId") or args.get("column") or ""

    def _on_cell_edit(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        col = _cell_col(a)
        if "id" not in data:
            return
        sid = int(data["id"])
        if col == "name":
            _save_name_cell(sid, data.get("name", ""))
        elif isinstance(col, str) and col.startswith("m") and col[1:].isdigit():
            _save_amount_cell(sid, state["year"], int(col[1:]), data.get(col, 0))

    def _on_cell_dblclick(e) -> None:
        a = e.args or {}
        data = a.get("data") or {}
        col = _cell_col(a)
        if "id" in data and isinstance(col, str) and col.startswith("m") and col[1:].isdigit():
            _open_cell_modal(int(data["id"]), state["year"], int(col[1:]))

    async def _on_drag_end(e) -> None:
        try:
            client_rows = await e.sender.get_client_data()
        except Exception:
            return
        order = [int(r["id"]) for r in client_rows if "id" in r]
        with get_session() as s:
            for i, sid in enumerate(order):
                st = s.get(RevenueStream, sid)
                if st is not None:
                    st.sort_order = i
            s.commit()
        matrix.refresh()
        manage.refresh()
        ui.notify("Reihenfolge gespeichert", type="positive")

    def _open_cell_modal(stream_id: int, year: int, month: int) -> None:
        with get_session() as s:
            stream = s.get(RevenueStream, stream_id)
            if stream is None:
                return
            is_product = stream.rtype == RevenueType.PRODUCT
            sname = stream.name
            pm = s.exec(select(RevenuePlanMonth).where(
                RevenuePlanMonth.stream_id == stream_id, RevenuePlanMonth.year == year,
                RevenuePlanMonth.month == month)).first()
            note0 = pm.note if pm else ""
            color0 = pm.color if pm else ""
            items = [{"qty": e.qty, "price": e.price, "amount": e.amount, "note": e.note}
                     for e in s.exec(select(RevenueCellEntry).where(
                         RevenueCellEntry.stream_id == stream_id, RevenueCellEntry.year == year,
                         RevenueCellEntry.month == month).order_by(
                         RevenueCellEntry.sort_order, RevenueCellEntry.id)).all()]
        if not items:
            items = [{"qty": 0.0, "price": 0.0, "amount": 0.0, "note": ""}]
        modal = {"color": color0}

        def _total() -> float:
            if is_product:
                return sum((it["qty"] or 0) * (it["price"] or 0) for it in items)
            return sum((it["amount"] or 0) for it in items)

        with ui.dialog() as dlg, ui.card().classes("min-w-[700px]"):
            ui.label(f"{sname} — {MONTHS_DE[month - 1]} {year}").classes("text-lg font-bold")
            ui.label("Detail-Aufstellung — die Summe ergibt den Zellenwert.").classes(
                "text-xs text-gray-500")
            total_label = ui.label().classes("text-sm font-semibold")
            total_label.text = f"Summe: {eur(_total())}"

            def _refresh_total() -> None:
                total_label.text = f"Summe: {eur(_total())}"

            @ui.refreshable
            def lines() -> None:
                with ui.row().classes("items-center gap-2 text-xs text-gray-500 font-medium"):
                    if is_product:
                        ui.label("Menge").classes("w-24")
                        ui.label("Preis").classes("w-24")
                        ui.label("Notiz").classes("w-72")
                    else:
                        ui.label("Betrag").classes("w-32")
                        ui.label("Notiz").classes("w-80")
                    ui.label("").classes("w-8")
                for it in items:
                    with ui.row().classes("items-center gap-2"):
                        if is_product:
                            ui.number(value=it["qty"], step=1,
                                      on_change=lambda e, it=it: (it.__setitem__("qty", e.value or 0),
                                                                  _refresh_total())
                                      ).props("dense outlined").classes("w-24")
                            ui.number(value=it["price"], step=1,
                                      on_change=lambda e, it=it: (it.__setitem__("price", e.value or 0),
                                                                  _refresh_total())
                                      ).props("dense outlined").classes("w-24")
                            ui.input(value=it["note"],
                                     on_change=lambda e, it=it: it.__setitem__("note", e.value or "")
                                     ).props("dense outlined").classes("w-72")
                        else:
                            ui.number(value=it["amount"], step=100,
                                      on_change=lambda e, it=it: (it.__setitem__("amount", e.value or 0),
                                                                  _refresh_total())
                                      ).props("dense outlined").classes("w-32")
                            ui.input(value=it["note"],
                                     on_change=lambda e, it=it: it.__setitem__("note", e.value or "")
                                     ).props("dense outlined").classes("w-80")

                        def _remove(it=it) -> None:
                            items.remove(it)
                            if not items:
                                items.append({"qty": 0.0, "price": 0.0, "amount": 0.0, "note": ""})
                            lines.refresh()
                            _refresh_total()

                        ui.button(icon="close", on_click=_remove).props("flat round dense").classes("w-8")

            lines()

            def _add_line() -> None:
                items.append({"qty": 0.0, "price": 0.0, "amount": 0.0, "note": ""})
                lines.refresh()

            with ui.row().classes("items-center gap-3 mt-2"):
                ui.button("Zeile hinzufügen", icon="add", on_click=_add_line).props("flat")
                note_in = ui.input("Notiz (Zelle)", value=note0).classes("w-64")
                ui.select(CELL_COLORS, value=color0, label="Zellenfarbe",
                          on_change=lambda e: modal.update(color=e.value)
                          ).props("dense outlined").classes("w-40")

            with ui.row().classes("mt-2"):
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _save() -> None:
                    with get_session() as s:
                        for e in s.exec(select(RevenueCellEntry).where(
                                RevenueCellEntry.stream_id == stream_id,
                                RevenueCellEntry.year == year,
                                RevenueCellEntry.month == month)).all():
                            s.delete(e)
                        kept = [it for it in items if (it["qty"] or it["price"] or it["amount"] or it["note"])]
                        for i, it in enumerate(kept):
                            s.add(RevenueCellEntry(
                                stream_id=stream_id, year=year, month=month, sort_order=i,
                                qty=float(it["qty"] or 0), price=float(it["price"] or 0),
                                amount=float(it["amount"] or 0), note=it["note"] or ""))
                        pm2 = _cell_pm(s, stream_id, year, month)
                        pm2.note = note_in.value or ""
                        pm2.color = modal["color"] or ""
                        s.commit()
                        _recompute_cell(s, s.get(RevenueStream, stream_id), year, month)
                    recompute_all()
                    dlg.close()
                    matrix.refresh()
                    ui.notify("Zelle gespeichert", type="positive")

                ui.button("Speichern", icon="save", on_click=_save)
        dlg.open()

    @ui.refreshable
    def manage() -> None:
        with get_session() as s:
            streams = [st for st in s.exec(select(RevenueStream).order_by(
                RevenueStream.sort_order, RevenueStream.id)).all()
                if st.scenario_id == state["scenario"]]
            data = [(st.id, st.name, st.rtype, _stream_days(st), st.is_vatable) for st in streams]
        with ui.expansion("Einnahmequellen bearbeiten (Typ, Zahlungsziel, löschen)",
                          icon="tune").classes("w-full"):
            if not data:
                ui.label("Keine eigenen Einnahmequellen in diesem Szenario.").classes(
                    "text-sm text-gray-500")
            for sid, name, rtype, days, vat in data:
                with ui.row().classes("items-center gap-2"):
                    with ui.column().classes("gap-0"):
                        ui.button(icon="keyboard_arrow_up", on_click=lambda sid=sid: _move(sid, -1)
                                  ).props("flat dense").classes("w-6 h-4").tooltip("nach oben")
                        ui.button(icon="keyboard_arrow_down", on_click=lambda sid=sid: _move(sid, 1)
                                  ).props("flat dense").classes("w-6 h-4").tooltip("nach unten")
                    ui.input("Bezeichnung", value=name,
                             on_change=lambda e, sid=sid: _save_field(sid, name=e.value)
                             ).props("dense outlined").classes("w-52")
                    ui.select({t: REVENUE_TYPE_DE[t] for t in RevenueType}, value=rtype, label="Typ",
                              on_change=lambda e, sid=sid: _save_field(sid, rtype=RevenueType(e.value))
                              ).props("dense outlined").classes("w-48")
                    ui.number("Zahlungsziel (Tage)", value=days, min=0, max=365, step=1,
                              on_change=lambda e, sid=sid: _save_field(sid, payment_days=int(e.value or 0))
                              ).props("dense outlined").classes("w-36")
                    ui.checkbox("USt", value=vat,
                                on_change=lambda e, sid=sid: _save_field(sid, is_vatable=bool(e.value)))
                    ui.button(icon="delete", on_click=lambda sid=sid, name=name: _delete_stream(sid, name)
                              ).props("flat round dense color=negative").tooltip("Einnahmequelle löschen")

    def _move(sid: int, delta: int) -> None:
        with get_session() as s:
            ids = [st.id for st in s.exec(select(RevenueStream).order_by(
                RevenueStream.sort_order, RevenueStream.id)).all()
                if st.scenario_id == state["scenario"]]
            if sid not in ids:
                return
            i = ids.index(sid)
            j = i + delta
            if j < 0 or j >= len(ids):
                return
            ids[i], ids[j] = ids[j], ids[i]
            for order, _id in enumerate(ids):
                st = s.get(RevenueStream, _id)
                st.sort_order = order
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

    def _delete_stream(sid: int, name: str) -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label(f'Einnahmequelle „{name}" löschen?').classes("text-lg font-bold")
            ui.label("Alle Monatswerte dieser Quelle werden entfernt.").classes(
                "text-sm text-gray-500")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    with get_session() as s:
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

    def _add_dialog() -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label("Neue Einnahmequelle").classes("text-lg font-bold")
            name = ui.input("Bezeichnung").classes("w-72")
            rtype = ui.select({t: REVENUE_TYPE_DE[t] for t in RevenueType},
                              value=RevenueType.RECURRING, label="Typ").classes("w-72")
            days = ui.number("Zahlungsziel (Tage)", value=30, min=0, max=365, step=1).classes("w-72")
            vat = ui.checkbox("umsatzsteuerpflichtig", value=True)
            with ui.row():
                ui.button("Abbrechen", on_click=dialog.close).props("flat")

                def _create() -> None:
                    if not name.value:
                        ui.notify("Bezeichnung fehlt", type="warning")
                        return
                    with get_session() as s:
                        order = max([x.sort_order for x in s.exec(select(RevenueStream)).all()], default=0) + 1
                        s.add(RevenueStream(name=name.value, rtype=RevenueType(rtype.value),
                                            payment_days=int(days.value or 0), is_vatable=bool(vat.value),
                                            scenario_id=state["scenario"], sort_order=order))
                        s.commit()
                    dialog.close()
                    matrix.refresh()
                    manage.refresh()

                ui.button("Anlegen", on_click=_create)
        dialog.open()

    matrix()
    manage()
