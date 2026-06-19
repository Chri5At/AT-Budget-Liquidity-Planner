"""Reusable scenario controls: a selector and a base-row on/off panel."""
from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from ...db import get_session
from ...engine.scenarios import (
    base_owned_rows,
    get_scenario,
    is_disabled,
    list_scenarios,
    set_disabled,
)


def scenario_options() -> dict[int, str]:
    with get_session() as s:
        return {sc.id: sc.name for sc in list_scenarios(s)}


def scenario_select(current_id: int, on_change: Callable[[int], None], label: str = "Szenario"):
    return ui.select(scenario_options(), value=current_id, label=label,
                     on_change=lambda e: on_change(int(e.value))
                     ).props("outlined dense").classes("w-60")


def base_toggle_panel(scenario_id: int, ref_kind: str, model, on_change: Callable[[], None]) -> None:
    """For a child scenario, list the inherited base rows with active checkboxes.

    Unchecking a row writes a ScenarioDisable so it drops out of this scenario.
    Renders nothing for the base scenario (it owns the rows directly).
    """
    with get_session() as s:
        sc = get_scenario(s, scenario_id)
        if sc.base_id is None:
            return
        rows = base_owned_rows(s, sc, model)
        states = [(r.id, r.name, not is_disabled(s, scenario_id, ref_kind, r.id)) for r in rows]
    if not states:
        return
    with ui.expansion(f"Basis-Positionen ein-/ausschalten ({len(states)})",
                      icon="rule").classes("w-full"):
        ui.label("Abgewählte Basis-Positionen zählen in diesem Szenario nicht mit.").classes(
            "text-xs text-gray-500")
        for rid, rname, active in states:
            def _toggle(ev, rid=rid) -> None:
                with get_session() as s:
                    set_disabled(s, scenario_id, ref_kind, rid, not bool(ev.value))
                on_change()
            ui.checkbox(rname, value=active, on_change=_toggle)
