"""Flipping a position's VSt/USt flag must keep the meaning of stored values.

off → on: a 1.200 € gross figure becomes 1.000 € netto (÷ 1,2)
on → off: a 1.000 € netto figure becomes 1.200 € gross (× 1,2)
Breakdown lines and their cell totals stay consistent; quantities/percentages
are never touched; generated contract lines are left for the regenerator.
"""
from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import VAT_RATE
from app.models import (
    BillingCycle,
    Contract,
    CostCategory,
    CostCellEntry,
    CostPlanMonth,
    PnlLine,
    RevenueCellEntry,
    RevenuePlanMonth,
    RevenueStream,
    RevenueType,
)
from app.services.vat_convert import (
    conversion_factor,
    convert_cost_values,
    convert_revenue_values,
    cost_value_count,
    revenue_value_count,
)


@pytest.fixture
def s() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        yield session


def test_factor_direction():
    assert conversion_factor(True) == pytest.approx(1 / (1 + VAT_RATE))
    assert conversion_factor(False) == pytest.approx(1 + VAT_RATE)


def test_cost_gross_to_net_scales_cells_lines_and_contracts(s):
    cat = CostCategory(name="Versicherung", pnl_line=PnlLine.OPEX, is_vatable=False)
    s.add(cat); s.commit()
    s.add(CostPlanMonth(category_id=cat.id, year=2026, month=1, amount=1200.0))   # single value
    s.add(CostPlanMonth(category_id=cat.id, year=2026, month=2, amount=600.0))    # Σ of lines
    s.add(CostCellEntry(category_id=cat.id, year=2026, month=2, amount=360.0, note="a"))
    s.add(CostCellEntry(category_id=cat.id, year=2026, month=2, amount=240.0, note="b"))
    s.add(CostPlanMonth(category_id=cat.id, year=2026, month=3, amount=0.0))      # empty cell
    s.add(Contract(name="Polizze", category_id=cat.id, amount=2400.0, cycle=BillingCycle.YEARLY,
                    start=date(2026, 1, 1)))
    # a generated line must NOT be scaled here — the regenerator rebuilds it
    s.add(CostCellEntry(category_id=cat.id, year=2026, month=4, amount=2400.0, contract_id=1))
    s.add(CostPlanMonth(category_id=cat.id, year=2026, month=4, amount=2400.0))
    s.commit()

    assert cost_value_count(s, cat.id) == 4          # 3 non-zero cells + 1 contract
    convert_cost_values(s, cat.id, conversion_factor(True))

    pm = {p.month: p.amount for p in s.exec(select(CostPlanMonth)).all()}
    assert pm[1] == pytest.approx(1000.0)
    assert pm[2] == pytest.approx(500.0)             # re-summed from converted lines
    assert pm[3] == 0.0
    lines = {e.note: e.amount for e in s.exec(select(CostCellEntry)).all() if e.contract_id is None}
    assert lines == {"a": 300.0, "b": 200.0}
    gen = next(e for e in s.exec(select(CostCellEntry)).all() if e.contract_id)
    assert gen.amount == 2400.0                      # untouched, regenerated later
    assert s.exec(select(Contract)).first().amount == pytest.approx(2000.0)


def test_cost_net_to_gross_round_trips(s):
    cat = CostCategory(name="Miete", pnl_line=PnlLine.OPEX, is_vatable=True)
    s.add(cat); s.commit()
    s.add(CostPlanMonth(category_id=cat.id, year=2026, month=5, amount=1000.0)); s.commit()
    convert_cost_values(s, cat.id, conversion_factor(False))
    assert s.exec(select(CostPlanMonth)).first().amount == pytest.approx(1200.0)
    convert_cost_values(s, cat.id, conversion_factor(True))
    assert s.exec(select(CostPlanMonth)).first().amount == pytest.approx(1000.0)


def test_revenue_scales_prices_not_quantities(s):
    st = RevenueStream(name="Inspektionen", rtype=RevenueType.PROJECT, is_vatable=True)
    s.add(st); s.commit()
    s.add(RevenuePlanMonth(stream_id=st.id, year=2026, month=6, amount=10 * 300.0 + 500.0, units=10))
    s.add(RevenueCellEntry(stream_id=st.id, year=2026, month=6, qty=10, price=300.0,
                           fixed_fee=500.0, sub_rate=150.0, sub_fixed=100.0,
                           deposit_is_pct=True, deposit_value=30.0))
    s.add(RevenuePlanMonth(stream_id=st.id, year=2026, month=7, amount=1000.0))  # single value
    s.commit()

    assert revenue_value_count(s, st.id) == 2
    convert_revenue_values(s, st.id, conversion_factor(False))   # netto → brutto

    e = s.exec(select(RevenueCellEntry)).first()
    assert e.qty == 10                                   # Menge untouched
    assert e.price == pytest.approx(360.0)
    assert e.fixed_fee == pytest.approx(600.0)
    assert e.sub_rate == pytest.approx(180.0)
    assert e.sub_fixed == pytest.approx(120.0)
    assert e.deposit_value == 30.0                       # percentage untouched
    pm = {p.month: (p.amount, p.units) for p in s.exec(select(RevenuePlanMonth)).all()}
    assert pm[6] == (pytest.approx(10 * 360.0 + 600.0), 10)   # re-summed from lines
    assert pm[7][0] == pytest.approx(1200.0)


def test_revenue_euro_deposit_is_scaled(s):
    st = RevenueStream(name="Hardware", rtype=RevenueType.ONEOFF, is_vatable=False)
    s.add(st); s.commit()
    s.add(RevenuePlanMonth(stream_id=st.id, year=2026, month=9, amount=12000.0))
    s.add(RevenueCellEntry(stream_id=st.id, year=2026, month=9, amount=12000.0,
                           deposit_is_pct=False, deposit_value=6000.0))
    s.commit()
    convert_revenue_values(s, st.id, conversion_factor(True))    # brutto → netto
    e = s.exec(select(RevenueCellEntry)).first()
    assert e.amount == pytest.approx(10000.0)
    assert e.deposit_value == pytest.approx(5000.0)
    assert s.exec(select(RevenuePlanMonth)).first().amount == pytest.approx(10000.0)
