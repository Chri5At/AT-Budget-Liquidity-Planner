"""Expand a product line item into dated cash inflows by its payment routine.

This is the LIQUIDITY-critical part: a single product line (sold/delivered in a
given month) may be collected as one payment, a deposit + remainder, or a deposit
plus installments. The GuV always books the full value in the cell month (accrual);
only the *cash dates* differ — that is what this module computes.

All returned dates are already moved to the prior banking day. The returned
amounts always sum (to the cent) to the line total.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..models.enums import RevenuePayRoutine
from .calendar_at import last_day_of_month, prev_banking_day, shift_by_days


@dataclass
class CashBit:
    date: date
    amount: float
    label: str   # short tag for the cashflow memo (e.g. "Anzahlung", "Rate 2/4")


def _round2(x: float) -> float:
    return round(x + 0.0, 2)


def _add_months_to_date(d: date, n: int) -> date:
    """Shift a date by n months, clamping the day to the target month length."""
    total = d.month - 1 + n
    y = d.year + total // 12
    m = total % 12 + 1
    day = min(d.day, last_day_of_month(y, m).day)
    return date(y, m, day)


def deposit_amount(total: float, is_pct: bool, value: float) -> float:
    """The Anzahlung in euro, clamped to [0, total]."""
    dep = total * (value / 100.0) if is_pct else value
    return max(0.0, min(dep, total))


def product_line_cashflows(
    year: int, month: int, total: float, routine: RevenuePayRoutine, *,
    payment_days: int = 0, deposit_is_pct: bool = True, deposit_value: float = 0.0,
    rate_count: int = 0, rate_months: int = 0, subdiv: str = "4",
) -> list[CashBit]:
    """Dated cash inflows for one product line. `total` = Menge × Preis.

    - ON_ORDER:      full amount in the cell month (Bei Bestellung).
    - ON_DELIVERY:   full amount at cell month + payment_days.
    - DEPOSIT_REST:  Anzahlung in the cell month, rest at + payment_days.
    - INSTALLMENTS:  Anzahlung in the cell month, then `rate_count` equal Raten
                     starting at delivery (+ payment_days) and spread over
                     `rate_months` (interval = round(rate_months / rate_count)).
    """
    base = last_day_of_month(year, month)
    order_date = prev_banking_day(base, subdiv)
    delivery_date = shift_by_days(base, payment_days, subdiv)

    if total <= 0:
        return []

    if routine == RevenuePayRoutine.ON_ORDER:
        return [CashBit(order_date, _round2(total), "Bei Bestellung")]

    if routine == RevenuePayRoutine.ON_DELIVERY:
        return [CashBit(delivery_date, _round2(total), "Bei Lieferung")]

    dep = deposit_amount(total, deposit_is_pct, deposit_value)
    rest = _round2(total - dep)
    dep = _round2(dep)

    if routine == RevenuePayRoutine.DEPOSIT_REST:
        bits: list[CashBit] = []
        if dep > 0:
            bits.append(CashBit(order_date, dep, "Anzahlung"))
        if rest > 0:
            bits.append(CashBit(delivery_date, rest, "Rest bei Lieferung"))
        return bits

    # INSTALLMENTS — Anzahlung now, then equal Raten ab Lieferung.
    # The first rate is due at delivery; each later rate steps `interval` months
    # forward from the delivery date (preserving day-of-month).
    bits = []
    if dep > 0:
        bits.append(CashBit(order_date, dep, "Anzahlung"))
    n = max(1, int(rate_count))
    interval = max(1, round(rate_months / n)) if rate_months else 1
    per = _round2(rest / n)
    for k in range(n):
        amt = per if k < n - 1 else _round2(rest - per * (n - 1))  # last absorbs rounding
        if amt == 0:
            continue
        d = prev_banking_day(_add_months_to_date(delivery_date, k * interval), subdiv)
        bits.append(CashBit(d, amt, f"Rate {k + 1}/{n}"))
    return bits
