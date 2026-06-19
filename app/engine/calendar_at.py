"""Austrian banking-day calendar and date helpers.

Uses the `holidays` library with the Oberösterreich subdivision ("4"). All
payment dates are moved to the PRIOR banking day if they fall on a weekend or
public holiday — money must arrive in time, never later.
"""
from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta

import holidays

from ..models.enums import TERM_DAYS, PaymentTerm

_HOLIDAY_CACHE: dict[str, object] = {}


def month_in_horizon(year: int, month: int, settings) -> bool:
    """True if (year, month) lies within the planning window [Planungsbeginn,
    Planungsende] (compared at month granularity)."""
    start = (settings.horizon_start.year, settings.horizon_start.month)
    end = (settings.horizon_end.year, settings.horizon_end.month)
    return start <= (year, month) <= end


def _at_holidays(subdiv: str = "4"):
    if subdiv not in _HOLIDAY_CACHE:
        years = range(2024, 2031)
        try:
            _HOLIDAY_CACHE[subdiv] = holidays.Austria(subdiv=subdiv, years=years)
        except Exception:
            # Fall back to nationwide holidays if the subdivision code is unknown.
            _HOLIDAY_CACHE[subdiv] = holidays.Austria(years=years)
    return _HOLIDAY_CACHE[subdiv]


def is_banking_day(d: date, subdiv: str = "4") -> bool:
    return d.weekday() < 5 and d not in _at_holidays(subdiv)


def prev_banking_day(d: date, subdiv: str = "4") -> date:
    while not is_banking_day(d, subdiv):
        d -= timedelta(days=1)
    return d


def last_day_of_month(year: int, month: int) -> date:
    return date(year, month, _cal.monthrange(year, month)[1])


def last_banking_day_of_month(year: int, month: int, subdiv: str = "4") -> date:
    return prev_banking_day(last_day_of_month(year, month), subdiv)


def add_months(year: int, month: int, n: int) -> tuple[int, int]:
    idx = (year * 12 + (month - 1)) + n
    return idx // 12, idx % 12 + 1


def abgaben_due_date(year: int, month: int, pay_day: int = 15, subdiv: str = "4") -> date:
    """Authorities (Finanzamt/ÖGK) due on `pay_day` of the FOLLOWING month."""
    y, m = add_months(year, month, 1)
    day = min(pay_day, _cal.monthrange(y, m)[1])
    return prev_banking_day(date(y, m, day), subdiv)


def vat_due_date(year: int, month: int, subdiv: str = "4") -> date:
    """USt-Voranmeldung due on the 15th of the SECOND following month."""
    y, m = add_months(year, month, 2)
    return prev_banking_day(date(y, m, 15), subdiv)


def shift_by_term(invoice_date: date, term: PaymentTerm, subdiv: str = "4") -> date:
    """Cash date = invoice date + payment-term days, moved to prior banking day."""
    return prev_banking_day(invoice_date + timedelta(days=TERM_DAYS[term]), subdiv)


def shift_by_days(invoice_date: date, days: int, subdiv: str = "4") -> date:
    """Cash date = invoice date + N days, moved to the prior banking day."""
    return prev_banking_day(invoice_date + timedelta(days=int(days)), subdiv)


def bucket_for(d: date) -> date:
    """Map a date into its half-month bucket: the 15th or the month end."""
    if d.day <= 15:
        return date(d.year, d.month, 15)
    return last_day_of_month(d.year, d.month)
