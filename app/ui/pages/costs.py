"""Kosten — cost categories (mapped to P&L lines) with a monthly amount matrix."""
from __future__ import annotations

from nicegui import ui
from sqlmodel import select

from ...db import get_session
from ...models import CostCategory, CostPlanMonth, OpexCategory, PaymentTerm, PnlLine
from ...models.enums import PAYMENT_TERM_DE, PNL_LINE_DE
from ..formatting import YEARS, eur
from ..components.month_grid import editable_month_grid
from ..components.scenario_ui import base_toggle_panel, scenario_select


def _load_rows(year: int, scenario_id: int) -> list[dict]:
    with get_session() as s:
        cats = [c for c in s.exec(select(CostCategory).order_by(
            CostCategory.pnl_line, CostCategory.sort_order, CostCategory.id)).all()
            if c.scenario_id == scenario_id]
        rows = []
        for c in cats:
            months = {p.month: p.amount for p in s.exec(select(CostPlanMonth).where(
                CostPlanMonth.category_id == c.id, CostPlanMonth.year == year)).all()}
            grp = PNL_LINE_DE[c.pnl_line]
            if c.pnl_line == PnlLine.OPEX and c.opex_category:
                grp = c.opex_category.value
            row = {"id": c.id, "name": c.name, "bereich": grp}
            for m in range(1, 13):
                row[f"m{m}"] = round(months.get(m, 0.0))
            rows.append(row)
        return rows


def _save_row(year: int, data: dict) -> None:
    with get_session() as s:
        c = s.get(CostCategory, int(data["id"]))
        if c is None:
            return
        c.name = data.get("name", c.name)
        s.add(c)
        for m in range(1, 13):
            try:
                val = float(data.get(f"m{m}", 0) or 0)
            except (TypeError, ValueError):
                val = 0.0
            p = s.exec(select(CostPlanMonth).where(
                CostPlanMonth.category_id == c.id, CostPlanMonth.year == year,
                CostPlanMonth.month == m)).first()
            if p is None:
                s.add(CostPlanMonth(category_id=c.id, year=year, month=m, amount=val))
            else:
                p.amount = val
        s.commit()


def render() -> None:
    state = {"year": YEARS[0], "scenario": 1}

    ui.label("Ausgaben").classes("text-xl font-bold")
    ui.label("Aufwände je Kategorie und Monat. Die P&L-Zuordnung steuert, in welchen "
             "Deckungsbeitrag die Ausgaben einfließen.").classes("text-sm text-gray-500")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.select(YEARS, value=state["year"], label="Jahr",
                  on_change=lambda e: _change_year(e.value)).props("outlined dense").classes("w-28")
        scenario_select(state["scenario"], lambda v: _change_scenario(v))
        ui.button("Ausgabenkategorie hinzufügen", icon="add", on_click=lambda: _add_dialog())

    @ui.refreshable
    def matrix() -> None:
        lead = [
            {"headerName": "Kategorie", "field": "name", "editable": True,
             "pinned": "left", "width": 230},
            {"headerName": "Bereich", "field": "bereich", "width": 180},
        ]
        rows = _load_rows(state["year"], state["scenario"])
        total = sum(r[f"m{m}"] for r in rows for m in range(1, 13))
        if not rows and state["scenario"] != 1:
            ui.label("Keine eigenen Ausgaben in diesem Szenario — füge welche hinzu oder "
                     "schalte unten Basis-Positionen ein/aus.").classes("text-sm text-gray-500")
        editable_month_grid(rows, lead, lambda data: _save_row(state["year"], data),
                             fill_height=True)
        ui.label(f"Eigene Ausgaben {state['year']}: {eur(total)}").classes("text-sm font-semibold mt-1")
        base_toggle_panel(state["scenario"], "cost", CostCategory, matrix.refresh)

    def _change_year(value: int) -> None:
        state["year"] = int(value)
        matrix.refresh()

    def _change_scenario(value: int) -> None:
        state["scenario"] = int(value)
        matrix.refresh()

    def _add_dialog() -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label("Neue Ausgabenkategorie").classes("text-lg font-bold")
            name = ui.input("Bezeichnung").classes("w-72")
            line = ui.select({l: PNL_LINE_DE[l] for l in PnlLine},
                             value=PnlLine.OPEX, label="P&L-Zuordnung").classes("w-72")
            opex = ui.select({o: o.value for o in OpexCategory},
                             value=OpexCategory.OTHER, label="OPEX-Kategorie (falls Sonstige)").classes("w-72")
            term = ui.select({t: PAYMENT_TERM_DE[t] for t in PaymentTerm},
                             value=PaymentTerm.NET30, label="Zahlungsziel").classes("w-72")
            vat = ui.checkbox("vorsteuerabzugsfähig", value=True)
            with ui.row():
                ui.button("Abbrechen", on_click=dialog.close).props("flat")

                def _create() -> None:
                    if not name.value:
                        ui.notify("Bezeichnung fehlt", type="warning")
                        return
                    with get_session() as s:
                        order = max([x.sort_order for x in s.exec(select(CostCategory)).all()], default=0) + 1
                        pl = PnlLine(line.value)
                        s.add(CostCategory(
                            name=name.value, pnl_line=pl,
                            opex_category=(OpexCategory(opex.value) if pl == PnlLine.OPEX else None),
                            payment_term=PaymentTerm(term.value), is_vatable=bool(vat.value),
                            scenario_id=state["scenario"], sort_order=order))
                        s.commit()
                    dialog.close()
                    matrix.refresh()

                ui.button("Anlegen", on_click=_create)
        dialog.open()

    matrix()
