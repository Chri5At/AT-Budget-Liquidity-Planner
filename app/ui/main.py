"""Application shell: header, tabs and panel routing."""
from __future__ import annotations

from nicegui import ui

from ..config import APP_TITLE
from ..db import get_session, get_settings
from ..services.recompute import recompute_all
from .pages import costs, employees, liquidity, pnl, revenue, scenarios, settings, snapshots


@ui.page("/")
def index() -> None:
    with get_session() as s:
        company = get_settings(s).company_name

    with ui.header().classes("items-center justify-between bg-primary"):
        ui.label(f"{APP_TITLE} · {company}").classes("text-lg font-bold")
        ui.button("Neu berechnen", icon="refresh",
                  on_click=lambda: (recompute_all(), ui.notify("Liquidität neu berechnet",
                                                               type="positive"))).props("flat color=white")

    with ui.tabs().classes("w-full") as tabs:
        t_emp = ui.tab("Mitarbeiter", icon="groups")
        t_rev = ui.tab("Einnahmen", icon="trending_up")
        t_cost = ui.tab("Ausgaben", icon="trending_down")
        t_pnl = ui.tab("GuV / Budget", icon="table_chart")
        t_liq = ui.tab("Liquidität", icon="account_balance")
        t_scn = ui.tab("Szenarien", icon="alt_route")
        t_snap = ui.tab("Snapshots", icon="photo_camera")
        t_set = ui.tab("Einstellungen", icon="settings")

    with ui.tab_panels(tabs, value=t_emp).classes("w-full"):
        with ui.tab_panel(t_emp):
            employees.render()
        with ui.tab_panel(t_rev):
            revenue.render()
        with ui.tab_panel(t_cost):
            costs.render()
        with ui.tab_panel(t_pnl):
            pnl.render()
        with ui.tab_panel(t_liq):
            liquidity.render()
        with ui.tab_panel(t_scn):
            scenarios.render()
        with ui.tab_panel(t_snap):
            snapshots.render()
        with ui.tab_panel(t_set):
            settings.render()
