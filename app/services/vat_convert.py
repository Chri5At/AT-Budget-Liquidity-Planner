"""Convert a position's stored values when its VSt/USt flag is flipped.

The flag decides how the engine reads a stored figure (see engine/cashflow._gross):
flag on → the figure is netto and gets grossed up for the cash side; flag off →
the figure is the Zahlbetrag. Flipping the flag therefore silently changes the
meaning of every value already typed for that position. These helpers rewrite
the values so their meaning is preserved:

* off → on: values were gross, the position now expects netto → ÷ (1 + VAT)
* on → off: values were netto, the position now expects gross → × (1 + VAT)

Everything that carries a € figure for the position is scaled — the plan cells,
the hand-entered breakdown lines, contract amounts assigned to a cost position
(their generated lines are rebuilt on the next recompute), and for revenue the
per-unit prices, fees, subcontractor rates and € deposits. Quantities and
percentages are untouched. Cells with breakdown lines are re-summed from the
converted lines so the dialog's "Summe Aufstellung" still matches the cell.
"""
from __future__ import annotations

from sqlmodel import Session, select

from ..config import VAT_RATE
from ..engine.contracts import contract_positions, dump_positions
from ..engine.cost_cells import recompute_cell_amount
from ..engine.revenue_cells import cell_total
from ..models import (
    Contract,
    CostCellEntry,
    CostPlanMonth,
    RevenueCellEntry,
    RevenuePlanMonth,
    RevenueStream,
)


def conversion_factor(new_is_vatable: bool) -> float:
    """Factor that keeps the meaning of existing values when the flag becomes `new_is_vatable`."""
    return 1.0 / (1.0 + VAT_RATE) if new_is_vatable else 1.0 + VAT_RATE


def _scale(value: float | None, factor: float) -> float:
    return round((value or 0.0) * factor, 2)


# --- Ausgaben ----------------------------------------------------------------

def cost_value_count(session: Session, category_id: int) -> int:
    """Number of non-zero € figures stored for the position (cells + contracts)."""
    cells = sum(1 for pm in session.exec(select(CostPlanMonth).where(
        CostPlanMonth.category_id == category_id)).all() if pm.amount)
    contracts = sum(1 for c in session.exec(select(Contract).where(
        Contract.category_id == category_id)).all() if c.amount)
    return cells + contracts


def convert_cost_values(session: Session, category_id: int, factor: float) -> int:
    """Scale every stored € figure of the cost position by `factor`; returns the count.

    Generated contract lines are left alone: the contract amount is scaled and
    the caller's recompute rebuilds those lines from it.
    """
    n = 0
    for e in session.exec(select(CostCellEntry).where(
            CostCellEntry.category_id == category_id,
            CostCellEntry.contract_id == None)).all():  # noqa: E711
        if e.amount:
            e.amount = _scale(e.amount, factor)
            session.add(e)
            n += 1
    for c in session.exec(select(Contract).where(Contract.category_id == category_id)).all():
        positions = contract_positions(c)
        if positions:                     # keep amount == Σ of the scaled positions
            for p in positions:
                p["amount"] = _scale(p["amount"], factor)
            c.positions = dump_positions(positions)
            c.amount = round(sum(p["amount"] for p in positions), 2)
            session.add(c)
            n += 1
        elif c.amount:
            c.amount = _scale(c.amount, factor)
            session.add(c)
            n += 1
    session.commit()
    cells = session.exec(select(CostPlanMonth).where(
        CostPlanMonth.category_id == category_id)).all()
    with_lines = {(e.year, e.month) for e in session.exec(select(CostCellEntry).where(
        CostCellEntry.category_id == category_id)).all()}
    for pm in cells:
        if (pm.year, pm.month) in with_lines:
            recompute_cell_amount(session, category_id, pm.year, pm.month)
        elif pm.amount:
            pm.amount = _scale(pm.amount, factor)
            session.add(pm)
            n += 1
    session.commit()
    return n


# --- Einnahmen ---------------------------------------------------------------

def revenue_value_count(session: Session, stream_id: int) -> int:
    """Number of non-zero cell values stored for the stream."""
    return sum(1 for pm in session.exec(select(RevenuePlanMonth).where(
        RevenuePlanMonth.stream_id == stream_id)).all() if pm.amount)


def convert_revenue_values(session: Session, stream_id: int, factor: float) -> int:
    """Scale every stored € figure of the revenue stream by `factor`; returns the count."""
    stream = session.get(RevenueStream, stream_id)
    if stream is None:
        return 0
    n = 0
    entries = session.exec(select(RevenueCellEntry).where(
        RevenueCellEntry.stream_id == stream_id)).all()
    for e in entries:
        for field in ("price", "amount", "fixed_fee", "sub_rate", "sub_fixed"):
            v = getattr(e, field)
            if v:
                setattr(e, field, _scale(v, factor))
        if e.deposit_value and not e.deposit_is_pct:   # € deposit, not a percentage
            e.deposit_value = _scale(e.deposit_value, factor)
        session.add(e)
        n += 1
    session.commit()
    by_cell: dict[tuple[int, int], list[RevenueCellEntry]] = {}
    for e in entries:
        by_cell.setdefault((e.year, e.month), []).append(e)
    for pm in session.exec(select(RevenuePlanMonth).where(
            RevenuePlanMonth.stream_id == stream_id)).all():
        lines = by_cell.get((pm.year, pm.month))
        if lines:
            pm.amount, pm.units = cell_total(stream.rtype, lines)
            session.add(pm)
        elif pm.amount:
            pm.amount = _scale(pm.amount, factor)
            session.add(pm)
            n += 1
    session.commit()
    return n
