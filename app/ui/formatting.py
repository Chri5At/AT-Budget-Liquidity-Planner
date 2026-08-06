"""Small formatting helpers for the German UI."""
from __future__ import annotations

import re

from nicegui import ui

MONTHS_DE = ["Jän", "Feb", "Mär", "Apr", "Mai", "Jun",
             "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

# "1.234" (one dot, groups of three) is a German thousands notation, not 1.234.
_DE_THOUSANDS = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def parse_de_amount(text: str | float | None) -> float | None:
    """Parse a user-typed amount accepting German notation; None if unparseable.

    German users type the dot as a thousands separator ("3.000" = 3000), but an
    HTML number input hands it to us as a decimal point (3.0) — silently wrong by
    a factor of 1000. So amounts are entered through text fields and parsed here:

    - "3.000,50" / "3.000"  → dot = thousands, comma = decimal
    - "3,5"                 → comma = decimal
    - "3.5" / "3.14"        → a dot NOT forming groups of three stays a decimal
    - "1.234.567"           → thousands
    - "" / None             → None (caller decides the fallback)
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = text.strip().replace("€", "").replace(" ", "").replace(" ", "")
    if not s:
        return None
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif _DE_THOUSANDS.match(s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def fmt_amount(value: float | None) -> str:
    """Number → editable text for an amount field: '3000' or '5,58' (no € suffix)."""
    if value is None:
        return ""
    if float(value) == int(value):
        return str(int(value))
    return f"{value:.2f}".replace(".", ",")


def years() -> list[int]:
    """Planning years derived from the configured horizon (Settings → Planungsbeginn/
    -ende). Extend the horizon end year in Settings to add e.g. 2028 everywhere."""
    from ..db import get_session, get_settings
    with get_session() as s:
        st = get_settings(s)
    return list(range(st.horizon_start.year, st.horizon_end.year + 1))


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


def eur_exact(value: float) -> str:
    """Like eur(), but keeps cents when the value has any: 80.16 -> '80,16 €'.

    Used where users cross-check their own entries (e.g. the detail-list sum) —
    the whole-euro rounding of the planning grids would look like a wrong sum.
    """
    if value is None:
        return ""
    return eur(value, 2 if abs(value - round(value)) > 1e-9 else 0)
