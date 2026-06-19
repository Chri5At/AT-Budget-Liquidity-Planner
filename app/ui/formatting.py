"""Small formatting helpers for the German UI."""
from __future__ import annotations

MONTHS_DE = ["Jän", "Feb", "Mär", "Apr", "Mai", "Jun",
             "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

YEARS = [2026, 2027]


def eur(value: float, decimals: int = 0) -> str:
    """Format a number as German euro, e.g. 1234567 -> '1.234.567 €'."""
    if value is None:
        return ""
    s = f"{value:,.{decimals}f}"           # 1,234,567.00
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €"
