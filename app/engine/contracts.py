"""Verträge & Abos — due-date series, renewal/cancellation dates, and the
generator that turns a contract into ordinary cost plan cells.

Two independent jobs live here:

1. **Fixkosten-Generator** (`generate_contract_cells`): every due date of every
   paying contract becomes a `CostCellEntry` line in the contract's target
   `CostCategory`, tagged with `contract_id`. From there the ordinary pipeline
   takes over — the P&L books the line in its cell month, the liquidity engine
   dates the payment by the category's Zahlungsziel, VAT follows the category's
   `is_vatable` flag. A yearly premium therefore shows up as a spike in the month
   it is due (monthly accrual over 12 months is deliberately not done here).

   The generator is idempotent: it deletes only the lines it produced
   (`contract_id IS NOT NULL`) and rebuilds them. Hand-entered lines
   (`contract_id IS NULL`) are never touched, and a cell holding both kinds
   simply sums them.

2. **Terminlogik** (pure functions): next due date, next renewal (Hauptfälligkeit),
   the cancellation deadline derived from the notice period, and a traffic light
   that turns yellow 120 days and red 60 days before that deadline.
"""
from __future__ import annotations

import calendar as _cal
from datetime import date

from sqlmodel import Session, select

from ..db import get_settings
from ..models import (
    BillingCycle,
    Contract,
    ContractStatus,
    CostCategory,
    CostCellEntry,
    CYCLE_MONTHS,
)
from .calendar_at import add_months, last_day_of_month, month_in_horizon
from .cost_cells import cell_entries, cell_plan_month, recompute_cell_amount

# Traffic-light thresholds: days left until the cancellation deadline.
RED_DAYS = 60
YELLOW_DAYS = 120

# Safety cap for the due-date series (≈200 years of monthly billing).
_MAX_STEPS = 2400


# --- date helpers ----------------------------------------------------------

def clamp_date(year: int, month: int, day: int) -> date:
    """A date with the day clamped into the month (31 → 30/29/28)."""
    return date(year, month, min(day, _cal.monthrange(year, month)[1]))


def shift_months(d: date, n: int) -> date:
    """Move a date by n months, clamping the day (31.01 + 1 month = 28./29.02).

    Always call this with an offset from the SAME anchor date (not repeatedly on
    the result), otherwise a clamped day would shrink the whole series.
    """
    year, month = add_months(d.year, d.month, n)
    return clamp_date(year, month, d.day)


# --- contract facts --------------------------------------------------------

def base_due(contract: Contract) -> date:
    """First payment: `first_due` when set, otherwise the contract start."""
    return contract.first_due or contract.start


def pays(contract: Contract) -> bool:
    """Does this contract produce payments at all?

    ACTIVE does. CANCELLED keeps paying until its end date, so it does too — but
    only if that end date is known; a cancelled contract without an end date is
    treated as finished. PAUSED and TRIAL never produce plan cells.
    """
    if contract.status == ContractStatus.ACTIVE:
        return True
    return contract.status == ContractStatus.CANCELLED and contract.end is not None


def cycle_months(contract: Contract) -> int:
    return CYCLE_MONTHS[BillingCycle(contract.cycle)]


def monthly_equiv(contract: Contract) -> float:
    """Amount normalised to €/month (yearly/12, quarterly/3, …); ONCE → 0."""
    months = cycle_months(contract)
    return contract.amount / months if months else 0.0


def annual_total(contract: Contract) -> float:
    """Amount normalised to €/year; ONCE → 0 (it is not a running cost)."""
    months = cycle_months(contract)
    return contract.amount * 12.0 / months if months else 0.0


# --- due dates -------------------------------------------------------------

def due_dates(contract: Contract, horizon_start: date, horizon_end: date) -> list[date]:
    """Every due date of the contract inside the planning horizon.

    The series runs from `first_due or start` in the contract's billing rhythm and
    stops at the earlier of the contract's end date and the horizon end. ONCE has
    exactly one due date. Contracts that do not pay (PAUSED/TRIAL, or a cancelled
    contract without an end date) return an empty list.
    """
    if not pays(contract) or contract.amount == 0:
        return []
    first = date(horizon_start.year, horizon_start.month, 1)
    last = last_day_of_month(horizon_end.year, horizon_end.month)
    if contract.end is not None and contract.end < last:
        last = contract.end

    base = base_due(contract)
    step = cycle_months(contract)
    if step == 0:                       # einmalig
        return [base] if first <= base <= last else []

    out: list[date] = []
    for k in range(_MAX_STEPS):
        d = shift_months(base, k * step)
        if d > last:
            break
        if d >= first:
            out.append(d)
    return out


def next_due(contract: Contract, today: date) -> date | None:
    """The next due date on/after `today` (ignores the planning horizon)."""
    if not pays(contract):
        return None
    base = base_due(contract)
    step = cycle_months(contract)
    if step == 0:
        d = base
    else:
        d = base
        k = 0
        while d < today and k < _MAX_STEPS:
            k += 1
            d = shift_months(base, k * step)
        if d < today:
            return None
    if d < today or (contract.end is not None and d > contract.end):
        return None
    return d


# --- renewal & cancellation ------------------------------------------------

def renewal_date(contract: Contract, today: date) -> date | None:
    """The next Hauptfälligkeit (renewal anniversary) on/after `today`.

    Taken from `renewal_day`/`renewal_month` when set, otherwise from the
    contract start. Returns None for a one-off charge (nothing renews) and for a
    contract that ends before its next renewal.
    """
    if cycle_months(contract) == 0:
        return None
    day = contract.renewal_day or contract.start.day
    month = contract.renewal_month or contract.start.month
    cand = clamp_date(today.year, month, day)
    if cand < today:
        cand = clamp_date(today.year + 1, month, day)
    # Never before the contract itself starts.
    while cand < contract.start:
        cand = clamp_date(cand.year + 1, month, day)
    if contract.end is not None and cand > contract.end:
        return None
    return cand


def cancellation_deadline(contract: Contract, today: date) -> date | None:
    """Last day to give notice: renewal date minus the notice period in months.

    Returns the next deadline the user can still act on. Once this term's deadline
    has passed the contract renews anyway, so the answer rolls on to the following
    renewal — a date in the past would only tell the user something they can no
    longer change.
    """
    renewal = renewal_date(contract, today)
    if renewal is None:
        return None
    notice = int(contract.notice_months or 0)
    for _ in range(3):
        deadline = shift_months(renewal, -notice) if notice else renewal
        if deadline >= today:
            return deadline
        renewal = clamp_date(renewal.year + 1, renewal.month, renewal.day)
        if contract.end is not None and renewal > contract.end:
            return None
    return None


def days_until_deadline(contract: Contract, today: date) -> int | None:
    deadline = cancellation_deadline(contract, today)
    return None if deadline is None else (deadline - today).days


def traffic_light(contract: Contract, today: date) -> str:
    """'red' | 'yellow' | 'green' | 'grey' — urgency of the cancellation deadline.

    Grey means "nothing to watch": the contract is not active, does not renew
    silently, or has no renewal at all (one-off / ends first).
    """
    if contract.status != ContractStatus.ACTIVE or not contract.auto_renew:
        return "grey"
    days = days_until_deadline(contract, today)
    if days is None:
        return "grey"
    if days < RED_DAYS:
        return "red"
    if days < YELLOW_DAYS:
        return "yellow"
    return "green"


# --- generator -------------------------------------------------------------

def _note_for(contract: Contract) -> str:
    return f"{contract.name} ({BillingCycle(contract.cycle).value})"


def _keep_manual_amount(session: Session, category_id: int, year: int, month: int) -> None:
    """Turn a hand-typed single cell value into a manual line before generating.

    Once a cell has lines its amount is Σ of those lines, so a value the user
    typed straight into the grid would otherwise be replaced by the contract's
    line. Converting it keeps it visible, editable and part of the sum.
    """
    if cell_entries(session, category_id, year, month):
        return                                    # already a list — nothing to rescue
    pm = cell_plan_month(session, category_id, year, month)
    if not pm.amount:
        return
    session.add(CostCellEntry(category_id=category_id, year=year, month=month,
                              sort_order=0, amount=pm.amount,
                              note=pm.note or "manuell erfasst"))
    session.flush()


def generate_contract_cells(session: Session) -> int:
    """Rebuild every contract-generated cost cell line. Returns the line count.

    Idempotent by design: generated lines are dropped and recreated, hand-entered
    lines survive untouched, and every cell that gained or lost a generated line
    is re-summed afterwards.
    """
    settings = get_settings(session)

    # 1. Drop the previously generated lines, remembering their cells.
    was_generated: set[tuple[int, int, int]] = set()
    for e in session.exec(select(CostCellEntry).where(
            CostCellEntry.contract_id != None)).all():        # noqa: E711 (SQL IS NOT NULL)
        was_generated.add((e.category_id, e.year, e.month))
        session.delete(e)
    session.commit()

    # 2. Regenerate from the contracts.
    categories = {c.id: c for c in session.exec(select(CostCategory)).all()}
    touched: set[tuple[int, int, int]] = set(was_generated)
    count = 0
    for contract in session.exec(select(Contract).order_by(
            Contract.sort_order, Contract.id)).all():
        category = categories.get(contract.category_id)
        if category is None or category.is_category:
            continue          # target row gone or turned into a group — nothing to write
        for due in due_dates(contract, settings.horizon_start, settings.horizon_end):
            if not month_in_horizon(due.year, due.month, settings):
                continue
            cell = (category.id, due.year, due.month)
            if cell not in was_generated:
                _keep_manual_amount(session, *cell)
            existing = cell_entries(session, *cell)
            session.add(CostCellEntry(
                category_id=category.id, year=due.year, month=due.month,
                sort_order=len(existing), amount=contract.amount,
                note=_note_for(contract), contract_id=contract.id))
            session.flush()
            touched.add(cell)
            count += 1
    session.commit()

    # 3. A cell's amount is Σ of its lines — re-sum everything we touched.
    for cell in touched:
        recompute_cell_amount(session, *cell)
    session.commit()
    return count
