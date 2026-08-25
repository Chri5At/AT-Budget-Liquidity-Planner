"""Shared helpers for one cost cell (category × year × month).

A cost cell is authoritative in `CostPlanMonth.amount`. When the cell has
breakdown lines (`CostCellEntry` — the Ausgaben "Advanced" dialog, or lines
generated from a Contract) the amount is the SUM of those lines.

The Ausgaben page and the contract generator both write cells, so the sum rule
lives here once instead of being duplicated on either side.
"""
from __future__ import annotations

from sqlmodel import Session, select

from ..models import CostCellEntry, CostPlanMonth


def cell_plan_month(session: Session, category_id: int, year: int, month: int) -> CostPlanMonth:
    """The cell's CostPlanMonth, created (and added to the session) if missing."""
    pm = session.exec(select(CostPlanMonth).where(
        CostPlanMonth.category_id == category_id, CostPlanMonth.year == year,
        CostPlanMonth.month == month)).first()
    if pm is None:
        pm = CostPlanMonth(category_id=category_id, year=year, month=month)
        session.add(pm)
    return pm


def cell_entries(session: Session, category_id: int, year: int, month: int) -> list[CostCellEntry]:
    """All breakdown lines of the cell (manual and generated), in display order."""
    return list(session.exec(select(CostCellEntry).where(
        CostCellEntry.category_id == category_id, CostCellEntry.year == year,
        CostCellEntry.month == month).order_by(
        CostCellEntry.sort_order, CostCellEntry.id)).all())


def recompute_cell_amount(session: Session, category_id: int, year: int, month: int) -> float:
    """Set the cell amount to Σ of its lines (manual + generated) and commit."""
    entries = cell_entries(session, category_id, year, month)
    pm = cell_plan_month(session, category_id, year, month)
    pm.amount = sum(e.amount for e in entries)
    session.commit()
    return pm.amount
