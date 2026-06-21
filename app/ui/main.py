"""Application shell: a slim header, a collapsible left sidebar, and panel routing."""
from __future__ import annotations

from nicegui import ui

from ..config import APP_TITLE
from ..db import get_session, get_settings
from .pages import costs, employees, liquidity, pnl, revenue, scenarios, settings, snapshots

# (tab key, icon, label, render fn)
_NAV = [
    ("emp", "groups", "Mitarbeiter", employees.render),
    ("rev", "trending_up", "Einnahmen", revenue.render),
    ("cost", "trending_down", "Ausgaben", costs.render),
    ("pnl", "table_chart", "GuV / Budget", pnl.render),
    ("liq", "account_balance", "Liquidität", liquidity.render),
    ("scn", "alt_route", "Szenarien", scenarios.render),
    ("snap", "photo_camera", "Snapshots", snapshots.render),
    ("set", "settings", "Einstellungen", settings.render),
]


@ui.page("/")
def index() -> None:
    with get_session() as s:
        company = get_settings(s).company_name
    nav_state = {"mini": False}

    drawer = (ui.left_drawer(value=True, fixed=True).props("bordered :width=210 :mini-width=60")
              .classes("bg-grey-1"))

    def _toggle() -> None:
        nav_state["mini"] = not nav_state["mini"]
        drawer.props(add="mini") if nav_state["mini"] else drawer.props(remove="mini")

    with ui.header().props("dense").classes("items-center bg-primary"):
        ui.button(icon="menu", on_click=_toggle).props("flat color=white dense round")
        ui.label(f"{APP_TITLE} · {company}").classes("text-base font-bold text-white")

    # Hidden tab controller drives the panels; the sidebar sets its value.
    with ui.tabs().props("vertical").classes("hidden") as tabs:
        tab_refs = {key: ui.tab(label, icon=icon) for key, icon, label, _ in _NAV}

    with drawer:
        with ui.list().props("padding").classes("w-full"):
            for key, icon, label, _ in _NAV:
                with ui.item(on_click=lambda t=tab_refs[key]: tabs.set_value(t)).props("clickable"):
                    with ui.item_section().props("avatar"):
                        ui.icon(icon).classes("text-primary")
                    with ui.item_section():
                        ui.item_label(label)

    with ui.tab_panels(tabs, value=tab_refs["emp"]).classes("w-full"):
        for key, icon, label, render in _NAV:
            with ui.tab_panel(tab_refs[key]):
                render()
