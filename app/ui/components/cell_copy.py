"""Copy targets for the per-cell detail dialog (Einnahmen + Ausgaben).

A cell can be copied — value, breakdown, note and colour — into any month of the
planning horizon, not only into the months of the year that is open. Targets are
keyed "YYYY-MM" so a single multi-select covers every planning year.
"""
from __future__ import annotations

from datetime import date

from nicegui import ui

from ...db import get_session, get_settings
from ..formatting import MONTHS_DE


def target_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def parse_target(key: str) -> tuple[int, int]:
    year, month = str(key).split("-")
    return int(year), int(month)


def target_options(year: int, month: int, horizon_start: date,
                   horizon_end: date) -> dict[str, str]:
    """Every month of the planning horizon except the source cell, in date order."""
    first = (horizon_start.year, horizon_start.month)
    last = (horizon_end.year, horizon_end.month)
    out: dict[str, str] = {}
    for y in range(horizon_start.year, horizon_end.year + 1):
        for m in range(1, 13):
            if (y, m) != (year, month) and first <= (y, m) <= last:
                out[target_key(y, m)] = f"{MONTHS_DE[m - 1]} {y}"
    return out


def copy_targets_select(year: int, month: int):
    """Multi-select of copy targets plus quick picks. Read the choice with
    `selected_targets(select)`."""
    with get_session() as s:
        settings = get_settings(s)
        options = target_options(year, month, settings.horizon_start, settings.horizon_end)
    sel = ui.select(options, multiple=True,
                    label="Auch in diese Monate kopieren (optional, auch Folgejahre)"
                    ).props("dense outlined use-chips clearable").classes("w-full mt-2")

    def _add(keys: list[str]) -> None:
        sel.value = sorted({*(sel.value or []), *(k for k in keys if k in options)})

    picks = [
        (f"Rest {year}", [target_key(year, m) for m in range(month + 1, 13)]),
        (f"{MONTHS_DE[month - 1]} {year + 1}", [target_key(year + 1, month)]),
        (f"Ganzes Jahr {year + 1}", [target_key(year + 1, m) for m in range(1, 13)]),
    ]
    picks = [(label, keys) for label, keys in picks if any(k in options for k in keys)]
    if picks:
        with ui.row().classes("items-center gap-1"):
            ui.label("Schnellauswahl:").classes("text-xs text-gray-500")
            for label, keys in picks:
                ui.button(label, on_click=lambda keys=keys: _add(keys)
                          ).props("flat dense no-caps")
    return sel


def selected_targets(sel) -> list[tuple[int, int]]:
    return sorted(parse_target(k) for k in (sel.value or []))
