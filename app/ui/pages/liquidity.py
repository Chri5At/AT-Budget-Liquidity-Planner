"""Liquidität — dated cash timeline with running bank balance.

Recomputes the cashflow ledger on open so it always reflects current plan data.
Shows Bank Status with and without EU funding, plus a balance chart.
"""
from __future__ import annotations

from datetime import date

from nicegui import ui
from sqlmodel import select

from ...db import get_session
from ...engine.liquidity import liquidity_view, liquidity_view_for_scenario
from ...engine.scenarios import list_scenarios
from ...models import Investment
from ...services.recompute import recompute_all
from ..formatting import eur


def render() -> None:
    ui.label("Liquidität").classes("text-xl font-bold")
    ui.label("Geldflüsse in 15.-/Monatsende-Buckets. Gehälter: Netto am Monatsende, "
             "Abgaben am 15. des Folgemonats (Banktag-Anpassung).").classes("text-sm text-gray-500")

    container = ui.column().classes("w-full")

    def build() -> None:
        container.clear()
        recompute_all()
        with get_session() as s:
            scs = list_scenarios(s)
            rows = liquidity_view(s)                      # base (persisted ledger)
            multi = len(scs) > 1
            scenario_rows = []
            if multi:
                for sc in scs:
                    r = rows if sc.base_id is None else liquidity_view_for_scenario(s, sc.id)
                    scenario_rows.append((sc.name, r))
        with container:
            if not rows:
                ui.label("Keine Daten — bitte zuerst Mitarbeiter/Einnahmen/Ausgaben erfassen.")
                return

            labels = [r.label for r in rows]
            if multi:
                # Overlay one balance curve per scenario for comparison.
                series = [{"name": nm, "type": "line", "smooth": True,
                           "data": [round(x.balance) for x in r]} for nm, r in scenario_rows]
                ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "legend": {"data": [nm for nm, _ in scenario_rows]},
                    "xAxis": {"type": "category", "data": labels,
                              "axisLabel": {"rotate": 60, "fontSize": 9}},
                    "yAxis": {"type": "value"},
                    "series": series,
                }).classes("w-full").style("height: 320px")
                with ui.row().classes("gap-6 my-2 flex-wrap"):
                    for nm, r in scenario_rows:
                        low = min(x.balance for x in r)
                        ui.label(f"{nm}: Tief {eur(low)} · End {eur(r[-1].balance)}").classes(
                            "text-sm font-semibold " + ("text-red-600" if low < 0 else "text-green-700"))
                ui.label("Detailtabelle: Basis-Szenario").classes("text-xs text-gray-500 mt-2")
            else:
                bal = [round(r.balance) for r in rows]
                bal_no_eu = [round(r.balance_no_eu) for r in rows]
                ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "legend": {"data": ["Bank Status", "ohne EU-Förderung"]},
                    "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 60, "fontSize": 9}},
                    "yAxis": {"type": "value"},
                    "series": [
                        {"name": "Bank Status", "type": "line", "smooth": True, "data": bal},
                        {"name": "ohne EU-Förderung", "type": "line", "smooth": True,
                         "data": bal_no_eu, "lineStyle": {"type": "dashed"}},
                    ],
                }).classes("w-full").style("height: 320px")

            low = min(r.balance for r in rows)
            end = rows[-1].balance
            with ui.row().classes("gap-6 my-2"):
                ui.label(f"Tiefststand: {eur(low)}").classes(
                    "text-sm font-semibold " + ("text-red-600" if low < 0 else "text-green-700"))
                ui.label(f"Endsaldo: {eur(end)}").classes("text-sm font-semibold")

            col_defs = [
                {"headerName": "Datum", "field": "label", "pinned": "left", "width": 110},
                {"headerName": "Einzahlungen", "field": "inflow", "type": "numericColumn", "width": 130,
                 ":valueFormatter": "p => p.value? Math.round(p.value).toLocaleString('de-DE')+' €':''"},
                {"headerName": "Auszahlungen", "field": "outflow", "type": "numericColumn", "width": 130,
                 ":valueFormatter": "p => p.value? Math.round(p.value).toLocaleString('de-DE')+' €':''"},
                {"headerName": "Saldo", "field": "net", "type": "numericColumn", "width": 120,
                 ":valueFormatter": "p => Math.round(p.value||0).toLocaleString('de-DE')+' €'"},
                {"headerName": "Bank Status", "field": "balance", "type": "numericColumn", "width": 140,
                 "cellClass": "font-bold",
                 ":valueFormatter": "p => Math.round(p.value||0).toLocaleString('de-DE')+' €'",
                 ":cellClassRules": "{'text-red-600': p => p.value < 0}"},
                {"headerName": "ohne EU", "field": "balance_no_eu", "type": "numericColumn", "width": 140,
                 ":valueFormatter": "p => Math.round(p.value||0).toLocaleString('de-DE')+' €'"},
            ]
            row_data = [{
                "label": r.label, "inflow": round(r.inflow), "outflow": round(r.outflow),
                "net": round(r.net), "balance": round(r.balance),
                "balance_no_eu": round(r.balance_no_eu),
            } for r in rows]
            ui.aggrid({
                "columnDefs": col_defs,
                "rowData": row_data,
                "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
                "domLayout": "autoHeight",
            }).classes("w-full").style("height: auto")

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

    investments_panel()
    ui.button("Aktualisieren", icon="refresh", on_click=build).props("outline").classes("my-2")
    build()
