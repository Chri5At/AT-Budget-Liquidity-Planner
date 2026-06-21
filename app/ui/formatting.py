"""Small formatting helpers for the German UI."""
from __future__ import annotations

from nicegui import ui

MONTHS_DE = ["Jän", "Feb", "Mär", "Apr", "Mai", "Jun",
             "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

YEARS = [2026, 2027]


def page_title(title: str, description: str) -> None:
    """Page heading + a small info icon showing the description as a hover tooltip
    (keeps the long description out of the way to save vertical space)."""
    with ui.row().classes("items-center gap-2"):
        ui.label(title).classes("text-xl font-bold")
        ui.icon("info_outline").classes("text-gray-400 cursor-help").tooltip(description)


def eur(value: float, decimals: int = 0) -> str:
    """Format a number as German euro, e.g. 1234567 -> '1.234.567 €'."""
    if value is None:
        return ""
    s = f"{value:,.{decimals}f}"           # 1,234,567.00
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €"
