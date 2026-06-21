"""Liquidität — dated cash timeline with running bank balance.

Recomputes the cashflow ledger on open so it always reflects current plan data.
Shows Bank Status with and without EU funding, plus a balance chart.
"""
from __future__ import annotations

from datetime import date, datetime

from nicegui import ui
from sqlmodel import select

from ...db import get_session
from ...engine.calendar_at import last_day_of_month
from ...engine.liquidity import (
    liquidity_pivot,
    liquidity_pivot_for_scenario,
    liquidity_view,
)
from ...engine.scenarios import list_scenarios
from ...models import Investment
from ...services.recompute import recompute_all
from ..formatting import eur, page_title

_PRESETS = {"all": "Gesamter Zeitraum", "this_year": "Dieses Jahr", "next_year": "Nächstes Jahr",
            "this_q": "Dieses Quartal", "next_q": "Nächstes Quartal", "custom": "Benutzerdefiniert"}
_GRANS = {"biweekly": "14-tägig (15./Monatsende)", "monthly": "Monatlich", "quarterly": "Quartal"}


def _quarter_range(year: int, q: int) -> tuple[date, date]:
    sm = (q - 1) * 3 + 1
    return date(year, sm, 1), last_day_of_month(year, sm + 2)


def _preset_range(preset: str) -> tuple[date | None, date | None]:
    today = datetime.now().date()
    q = (today.month - 1) // 3 + 1
    if preset == "this_year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if preset == "next_year":
        return date(today.year + 1, 1, 1), date(today.year + 1, 12, 31)
    if preset == "this_q":
        return _quarter_range(today.year, q)
    if preset == "next_q":
        return _quarter_range(today.year + 1, 1) if q == 4 else _quarter_range(today.year, q + 1)
    return None, None  # "all" / "custom" handled by the caller

# Pivot grid JS: caret for sections, bold for subtotal/balance rows, red for negatives.
_PIV_NAME = (
    'params => { var k=params.data.kind, nm=params.data.pos||"";'
    ' if(k==="section"){var ic=params.data.expanded?"▼":"▶";'
    '   return "<span style=\'cursor:pointer;font-weight:bold\'>"+ic+" "+nm+"</span>";}'
    ' if(k==="total"||k==="balance") return "<b>"+nm+"</b>";'
    ' return "<span style=\'padding-left:14px;color:#374151\'>"+nm+"</span>"; }')
_PIV_STYLE = (
    'params => { var k=params.data.kind, s={};'
    ' if(k==="section"||k==="total") s={fontWeight:"bold",backgroundColor:"#eef2ff"};'
    ' else if(k==="balance"){ s={fontWeight:"bold"}; if(params.value<0) s.color="#b91c1c"; }'
    ' return Object.keys(s).length?s:null; }')


def render() -> None:
    page_title("Liquidität",
               "Horizontale Zeitachse: Buckets (15./Monatsende) als Spalten, Positionen als "
               "Zeilen — gruppiert in Ein-/Auszahlungen (auf-/zuklappbar). Gehälter: Netto am "
               "Monatsende, Abgaben am 15. des Folgemonats (Banktag-Anpassung).")

    state = {"collapsed": set(), "gran": "biweekly", "preset": "all",
             "start": "", "end": ""}
    controls_area = ui.column().classes("w-full")
    container = ui.column().classes("w-full")

    def _range() -> tuple[date | None, date | None]:
        if state["preset"] == "custom":
            try:
                rs = date.fromisoformat(state["start"]) if state["start"] else None
            except ValueError:
                rs = None
            try:
                re = date.fromisoformat(state["end"]) if state["end"] else None
            except ValueError:
                re = None
            return rs, re
        return _preset_range(state["preset"])

    @ui.refreshable
    def controls() -> None:
        with ui.row().classes("items-center gap-3 my-1 flex-wrap"):
            ui.select(_PRESETS, value=state["preset"], label="Zeitraum",
                      on_change=lambda e: (state.update(preset=e.value), controls.refresh(), build())
                      ).props("dense outlined").classes("w-44")
            if state["preset"] == "custom":
                ui.input("Von (YYYY-MM-DD)", value=state["start"],
                         on_change=lambda e: (state.update(start=e.value), build())
                         ).props("dense outlined").classes("w-44")
                ui.input("Bis (YYYY-MM-DD)", value=state["end"],
                         on_change=lambda e: (state.update(end=e.value), build())
                         ).props("dense outlined").classes("w-44")
            ui.toggle(_GRANS, value=state["gran"],
                      on_change=lambda e: (state.update(gran=e.value), build())).props("dense")

    def build() -> None:
        container.clear()
        recompute_all()
        gran = state["gran"]
        rs, re = _range()
        with get_session() as s:
            scs = list_scenarios(s)
            multi = len(scs) > 1
            piv_scen = ([(sc.name,
                          liquidity_pivot(s, granularity=gran, range_start=rs, range_end=re)
                          if sc.base_id is None
                          else liquidity_pivot_for_scenario(s, sc.id, granularity=gran,
                                                            range_start=rs, range_end=re))
                         for sc in scs] if multi else [])
            pivot = liquidity_pivot(s, granularity=gran, range_start=rs, range_end=re)
        with container:
            if not pivot.labels:
                ui.label("Keine Daten im gewählten Zeitraum — Zeitraum/Granularität anpassen "
                         "oder Werte erfassen.").classes("text-sm text-gray-500")
                return

            labels = pivot.labels
            if multi:
                series = [{"name": nm, "type": "line", "smooth": True, "data": p.bank}
                          for nm, p in piv_scen]
                legend = [nm for nm, _ in piv_scen]
            else:
                series = [
                    {"name": "Bank Status", "type": "line", "smooth": True, "data": pivot.bank},
                    {"name": "ohne EU-Förderung", "type": "line", "smooth": True,
                     "data": pivot.bank_no_eu, "lineStyle": {"type": "dashed"}},
                ]
                legend = ["Bank Status", "ohne EU-Förderung"]
            ui.echart({
                "tooltip": {"trigger": "axis"},
                "legend": {"data": legend},
                "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 60, "fontSize": 9}},
                "yAxis": {"type": "value"},
                "series": series,
            }).classes("w-full").style("height: 320px")
            ui.label("„ohne EU-Förderung“ = derselbe Verlauf ohne die EU-Förder-Einzahlung "
                     "(kein Szenario). Mehrere Szenarien werden im Diagramm überlagert."
                     ).classes("text-xs text-gray-500")

            low = min(pivot.bank)
            with ui.row().classes("gap-6 my-2 flex-wrap"):
                ui.label(f"Tiefststand: {eur(low)}").classes(
                    "text-sm font-semibold " + ("text-red-600" if low < 0 else "text-green-700"))
                ui.label(f"Endsaldo: {eur(pivot.bank[-1])}").classes("text-sm font-semibold")
                if multi:
                    for nm, p in piv_scen:
                        lo = min(p.bank)
                        ui.label(f"{nm}: Tief {eur(lo)} · End {eur(p.bank[-1])}").classes(
                            "text-xs font-semibold " + ("text-red-600" if lo < 0 else "text-green-700"))
                    ui.label("Detailtabelle: Basis-Szenario").classes("text-xs text-gray-500")

            _render_pivot(pivot)

    def _render_pivot(pivot) -> None:
        cols = [{"headerName": "Position", "field": "pos", "pinned": "left", "width": 250,
                 ":cellRenderer": _PIV_NAME}]
        for i, lab in enumerate(pivot.labels):
            cols.append({"headerName": lab, "field": f"b{i}", "type": "numericColumn", "width": 108,
                         "headerClass": "ag-center-header", ":cellStyle": _PIV_STYLE,
                         ":valueFormatter": "p=>p.value?Math.round(p.value).toLocaleString('de-DE'):''"})
        cols.append({"headerName": "Summe", "field": "sum", "pinned": "right", "width": 120,
                     "type": "numericColumn", "cellClass": "font-bold",
                     ":valueFormatter": "p=>Math.round(p.value||0).toLocaleString('de-DE')+' €'"})

        rows_data = []

        def mk(kind, pos, vals, expanded=None):
            total = round(vals[-1]) if kind == "balance" else round(sum(vals))
            d = {"rid": f"{kind}-{pos}", "kind": kind, "pos": pos, "sum": total}
            if expanded is not None:
                d["expanded"] = expanded
            for i, v in enumerate(vals):
                d[f"b{i}"] = round(v)
            return d

        for sec in pivot.sections:
            expanded = sec.name not in state["collapsed"]
            rows_data.append(mk("section", sec.name, sec.totals, expanded))
            if expanded:
                for label, vals in sec.items:
                    rows_data.append(mk("item", label, vals))
        rows_data.append(mk("total", "= Saldo", pivot.saldo))
        rows_data.append(mk("balance", "Bank Status", pivot.bank))
        rows_data.append(mk("balance", "Bank Status ohne EU-Förderung", pivot.bank_no_eu))

        grid = ui.aggrid({
            "columnDefs": cols, "rowData": rows_data,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True,
                              "suppressSizeToFit": True},
            "suppressSizeToFit": True,
            "rowHeight": 28, "headerHeight": 34,
            ":getRowId": "params => params.data.rid",
        }).classes("w-full").style(f"height: {34 + len(rows_data) * 28 + 22}px")

        def _toggle(e) -> None:
            a = e.args or {}
            data = a.get("data") or {}
            col = a.get("colId") or a.get("column") or ""
            if data.get("kind") == "section" and col == "pos":
                state["collapsed"] ^= {data["pos"]}
                build()

        grid.on("cellClicked", _toggle)

    @ui.refreshable
    def investments_panel() -> None:
        with get_session() as s:
            invs = s.exec(select(Investment).order_by(Investment.date, Investment.id)).all()
            rows = [(i.id, i.date.isoformat(), i.investor, i.label, i.amount) for i in invs]
            total = sum(i.amount for i in invs)
        with ui.card().classes("w-full"):
            with ui.row().classes("items-center justify-between w-full"):
                ui.label("Investitionen / Kapitaleinlagen").classes("text-base font-semibold")
                ui.label(f"Summe: {eur(total)}").classes("text-sm font-semibold text-green-700")
            ui.label("Wer hat wann wie viel eingezahlt? Fließt als Einzahlung in die Liquidität "
                     "(nicht in die GuV).").classes("text-xs text-gray-500")
            if rows:
                with ui.row().classes("items-center gap-3 text-xs text-gray-500 font-medium mt-1"):
                    ui.label("Datum").classes("w-28")
                    ui.label("Investor").classes("w-44")
                    ui.label("Bezeichnung / Zweck").classes("w-64")
                    ui.label("Betrag").classes("w-32 text-right")
                for iid, d, investor, label, amount in rows:
                    with ui.row().classes("items-center gap-3"):
                        ui.label(d).classes("w-28")
                        ui.label(investor).classes("w-44 font-medium")
                        ui.label(label or "—").classes("w-64 text-gray-600")
                        ui.label(eur(amount)).classes("w-32 text-right")
                        ui.button(icon="delete", on_click=lambda iid=iid: _delete_investment(iid)
                                  ).props("flat round dense color=negative").tooltip("löschen")
            else:
                ui.label("Noch keine Investitionen erfasst.").classes("text-sm text-gray-500 mt-1")
            ui.button("Investment hinzufügen", icon="add",
                      on_click=_add_investment_dialog).classes("mt-2")

    def _refresh_all() -> None:
        investments_panel.refresh()
        build()

    def _add_investment_dialog() -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label("Neues Investment / Kapitaleinlage").classes("text-lg font-bold")
            investor = ui.input("Investor (Person)").classes("w-72")
            label = ui.input("Bezeichnung / Zweck").classes("w-72")
            amount = ui.number("Betrag (€)", value=0, step=1000, min=0).classes("w-40")
            d = ui.input("Datum (YYYY-MM-DD)", value=date.today().isoformat()).classes("w-48")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _create() -> None:
                    if not investor.value:
                        ui.notify("Investor fehlt", type="warning")
                        return
                    try:
                        dd = date.fromisoformat(d.value)
                    except ValueError:
                        ui.notify("Datum: YYYY-MM-DD", type="warning")
                        return
                    with get_session() as s:
                        s.add(Investment(investor=investor.value, label=label.value or "",
                                         amount=float(amount.value or 0), date=dd))
                        s.commit()
                    dlg.close()
                    ui.notify("Investment hinzugefügt", type="positive")
                    _refresh_all()

                ui.button("Speichern", icon="save", on_click=_create)
        dlg.open()

    def _delete_investment(iid: int) -> None:
        with get_session() as s:
            inv = s.get(Investment, iid)
            if inv is not None:
                s.delete(inv)
                s.commit()
        ui.notify("Investment gelöscht", type="positive")
        _refresh_all()

    with controls_area:
        controls()
    build()
    ui.separator().classes("my-3")
    investments_panel()

    def _on_show() -> None:
        # Rebuild the cashflow ledger + view so opening the tab shows current data.
        investments_panel.refresh()
        build()

    return _on_show
