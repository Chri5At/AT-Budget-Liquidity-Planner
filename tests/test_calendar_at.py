"""Banking-day / holiday rules."""
from datetime import date

from app.engine.calendar_at import (
    abgaben_due_date,
    bucket_for,
    is_banking_day,
    last_banking_day_of_month,
    prev_banking_day,
    vat_due_date,
)


def test_weekend_moves_to_prior_banking_day():
    # 15.02.2026 is a Sunday -> previous banking day is Fri 13.02.2026.
    assert date(2026, 2, 15).weekday() == 6
    assert prev_banking_day(date(2026, 2, 15)) == date(2026, 2, 13)


def test_abgaben_due_15th_of_following_month():
    # Salary month January 2026 -> Abgaben due 15.02.2026 (Sun) -> 13.02.2026.
    assert abgaben_due_date(2026, 1) == date(2026, 2, 13)
    # March 2026 -> 15.04.2026 is a Wednesday (banking day).
    assert abgaben_due_date(2026, 3) == date(2026, 4, 15)


def test_holiday_is_not_a_banking_day():
    # 01.01.2026 (Neujahr) is a public holiday.
    assert not is_banking_day(date(2026, 1, 1))


def test_last_banking_day_of_month():
    # 31.05.2026 is a Sunday -> last banking day is Fri 29.05.2026.
    assert last_banking_day_of_month(2026, 5) == date(2026, 5, 29)


def test_vat_due_second_following_month():
    # January 2026 VAT due 15.03.2026 (Sun) -> 13.03.2026.
    assert vat_due_date(2026, 1) == date(2026, 3, 13)


def test_bucket_for():
    assert bucket_for(date(2026, 3, 10)) == date(2026, 3, 15)
    assert bucket_for(date(2026, 3, 20)) == date(2026, 3, 31)
