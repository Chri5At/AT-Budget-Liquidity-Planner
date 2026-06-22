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
        # ag-Grid only reflows on a resize signal; the drawer animates ~300ms, so
        # nudge it a few times across the transition to avoid stale widths/glitches.
        ui.run_javascript("[60,180,320,420].forEach(t => setTimeout("
                          "() => window.dispatchEvent(new Event('resize')), t));")

    # After the user stops resizing the window, fire one clean resize so every
    # ag-Grid does a final settled reflow (guards against recursion).
    ui.add_body_html(
        "<script>(function(){let busy=false;window.addEventListener('resize',function(){"
        "if(busy)return;clearTimeout(window.__agReflow);window.__agReflow=setTimeout("
        "function(){busy=true;window.dispatchEvent(new Event('resize'));"
        "setTimeout(function(){busy=false;},80);},160);});})();</script>")

    with ui.header().props("dense").classes("items-center bg-primary"):
        ui.button(icon="menu", on_click=_toggle).props("flat color=white dense round")
        ui.label(f"{APP_TITLE} · {company}").classes("text-base font-bold text-white")

    # Hidden tab controller drives the panels; the sidebar sets its value.
    with ui.tabs().props("vertical").classes("hidden") as tabs:
        tab_refs = {key: ui.tab(key) for key, icon, label, _ in _NAV}  # tab name == key

    with drawer:
        with ui.list().props("padding").classes("w-full"):
            for key, icon, label, _ in _NAV:
                with ui.item(on_click=lambda t=tab_refs[key]: tabs.set_value(t)).props("clickable"):
                    with ui.item_section().props("avatar"):
                        ui.icon(icon).classes("text-primary")
                    with ui.item_section():
                        ui.item_label(label)

    # Pages may return an on-show refresh fn so computed views (GuV, Liquidität)
    # pick up the latest source data whenever the tab is opened.
    on_show: dict = {}
    with ui.tab_panels(tabs, value=tab_refs["emp"]).classes("w-full"):
        for key, icon, label, render in _NAV:
            with ui.tab_panel(tab_refs[key]):
                fn = render()
                if callable(fn):
                    on_show[key] = fn

    def _on_tab(e) -> None:
        fn = on_show.get(e.value)
        if fn:
            fn()
    tabs.on_value_change(_on_tab)
