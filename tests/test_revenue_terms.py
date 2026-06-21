"""Liquidity-critical: product payment routines produce the right cash dates/amounts."""
from datetime import date

from app.engine.revenue_terms import (
    deposit_amount,
    product_line_cashflows,
    project_line_cashflows,
    project_line_revenue,
    project_line_sub,
)
from app.models.enums import RevenuePayRoutine as R


def _sum(bits):
    return round(sum(b.amount for b in bits), 2)


def test_on_order_pays_full_in_cell_month():
    bits = product_line_cashflows(2026, 3, 10000, R.ON_ORDER, payment_days=30)
    assert len(bits) == 1
    assert _sum(bits) == 10000
    # 31.03.2026 is a Tuesday (banking day) -> same day.
    assert bits[0].date == date(2026, 3, 31)


def test_on_delivery_adds_payment_days():
    bits = product_line_cashflows(2026, 3, 10000, R.ON_DELIVERY, payment_days=30)
    assert len(bits) == 1 and _sum(bits) == 10000
    # 31.03 + 30 days = 30.04.2026 (Thu, banking day).
    assert bits[0].date == date(2026, 4, 30)


def test_deposit_rest_splits_and_sums():
    bits = product_line_cashflows(2026, 3, 10000, R.DEPOSIT_REST, payment_days=30,
                                  deposit_is_pct=True, deposit_value=30)
    assert _sum(bits) == 10000
    dep = next(b for b in bits if b.label == "Anzahlung")
    rest = next(b for b in bits if "Rest" in b.label)
    assert dep.amount == 3000 and rest.amount == 7000
    assert dep.date == date(2026, 3, 31)        # deposit in cell month
    assert rest.date == date(2026, 4, 30)       # rest at delivery


def test_deposit_fixed_euro():
    assert deposit_amount(10000, False, 2500) == 2500
    assert deposit_amount(10000, True, 25) == 2500
    # clamped to total
    assert deposit_amount(1000, False, 5000) == 1000


def test_installments_anzahlung_plus_rates_sum_exactly():
    # 12,000 total, 25% deposit, 3 Raten over 6 months, 30-day delivery lag.
    bits = product_line_cashflows(2026, 1, 12000, R.INSTALLMENTS, payment_days=30,
                                  deposit_is_pct=True, deposit_value=25,
                                  rate_count=3, rate_months=6)
    assert _sum(bits) == 12000                      # nothing lost to rounding
    dep = bits[0]
    assert dep.label == "Anzahlung" and dep.amount == 3000
    rates = [b for b in bits if b.label.startswith("Rate")]
    assert len(rates) == 3
    assert round(sum(r.amount for r in rates), 2) == 9000
    # interval = round(6/3) = 2 months; first rate at delivery (Jan31 + 30d = 02.03.2026, Mon).
    assert rates[0].date == date(2026, 3, 2)
    # +2 months = 02.05 (Sat) and 01.05 (Feiertag) -> prior banking day 30.04; +4 months = 02.07.
    assert rates[1].date == date(2026, 4, 30)
    assert rates[2].date == date(2026, 7, 2)
    assert rates[0].date < rates[1].date < rates[2].date


def test_rounding_remainder_on_last_rate():
    # 100 / 3 doesn't divide evenly; last rate absorbs the cent remainder.
    bits = product_line_cashflows(2026, 1, 100, R.INSTALLMENTS, payment_days=0,
                                  deposit_is_pct=False, deposit_value=0,
                                  rate_count=3, rate_months=3)
    assert _sum(bits) == 100
    rates = [b for b in bits if b.label.startswith("Rate")]
    assert rates[0].amount == 33.33 and rates[2].amount == 33.34


# --- Projekt (inspection) economics ----------------------------------------------

def test_project_line_amounts():
    # 10 turbines × 2000 + 5000 fixed fees = 25000 customer income.
    assert project_line_revenue(10, 2000, 5000) == 25000
    # subcontractor: 10 × 800 + 2000 fixed add-on = 10000.
    assert project_line_sub(10, 800, 2000) == 10000


def test_project_line_cashflow_dates_and_net():
    # Inspection in March: customer pays in 60 days, subcontractor in 30 days.
    pc = project_line_cashflows(2026, 3, qty=10, price=2000, fixed_fee=5000,
                                customer_days=60, sub_rate=800, sub_fixed=2000, sub_days=30)
    assert pc.revenue == 25000 and pc.sub == 10000
    # 31.03.2026 + 60 days = 30.05 (Sat) → prior banking day 29.05.2026.
    assert pc.revenue_date == date(2026, 5, 29)
    # 31.03.2026 + 30 days = 30.04.2026 (Thu).
    assert pc.sub_date == date(2026, 4, 30)
    # Subcontractor is paid (Apr) before the customer pays (May) — the liquidity gap.
    assert pc.sub_date < pc.revenue_date


def test_project_line_zero_parts_omitted():
    pc = project_line_cashflows(2026, 1, qty=0, price=0, fixed_fee=0,
                                customer_days=30, sub_rate=0, sub_fixed=0, sub_days=30)
    assert pc.revenue == 0 and pc.sub == 0
    assert pc.revenue_date is None and pc.sub_date is None
