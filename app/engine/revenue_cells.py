"""Shared sum rule for one revenue cell (stream × year × month).

A revenue cell is authoritative in `RevenuePlanMonth.amount`. When the cell has
breakdown lines (`RevenueCellEntry`) the amount is derived from them — Menge ×
Preis for driver-based types, plus fixed fees for projects, plain Betrag
otherwise. The Einnahmen page and the VAT conversion both re-sum cells, so the
rule lives here once.
"""
from __future__ import annotations

from collections.abc import Iterable

from ..models import RevenueCellEntry, RevenueType

# Types whose breakdown lines are entered as Menge × Preis rather than a plain
# Betrag. Recurring income often has a price per unit (e.g. per sync) with a
# different quantity each month; projects are turbines × price + fees.
QTY_PRICE_TYPES = (RevenueType.PRODUCT, RevenueType.RECURRING, RevenueType.PROJECT)


def uses_qty_price(rtype: RevenueType) -> bool:
    return rtype in QTY_PRICE_TYPES


def cell_total(rtype: RevenueType, entries: Iterable[RevenueCellEntry]) -> tuple[float, float]:
    """(amount, units) of a cell from its lines."""
    entries = list(entries)
    if rtype == RevenueType.PROJECT:
        # Project income = turbines × price + fixed fees (subcontractor is a cost).
        return (sum(e.qty * e.price + e.fixed_fee for e in entries),
                sum(e.qty for e in entries))
    if uses_qty_price(rtype):
        return (sum(e.qty * e.price for e in entries), sum(e.qty for e in entries))
    return (sum(e.amount for e in entries), 0.0)
