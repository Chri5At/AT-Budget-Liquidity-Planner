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
    """No-op under the fork model: each scenario owns an independent, editable copy
    of every row, so there is no base-inheritance to toggle. Kept so existing call
    sites stay valid."""
    return
