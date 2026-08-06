"""Cash moves gross; the VAT part settles separately via the UVA.

The net cash impact of a vatable position must equal its net amount — the app
must not hand back input VAT that never left the account (nor remit output VAT
that was never collected).
"""
from datetime import date

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import VAT_RATE
from app.engine.cashflow import build_cashflows
from app.models import (CashflowEntry, CashflowKind, CostCategory, CostPlanMonth,
                        PaymentTerm, PnlLine, RevenuePlanMonth, RevenueStream,
                        RevenueType, Settings, SplitModel)

NET = 100_000.0


def _session() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    s = Session(eng)
    s.add(Settings(id=1, split_model=SplitModel.FIXED_PCT, abgaben_pct=0.30,
                   employer_burden_pct=0.30, opening_balance=0.0,
                   horizon_start=date(2026, 1, 1), horizon_end=date(2026, 12, 31)))
    s.commit()
    return s


def _entries(s: Session) -> list[CashflowEntry]:
    build_cashflows(s)
    return list(s.exec(select(CashflowEntry)).all())


def test_vatable_cost_pays_gross_and_reclaims_vat():
    s = _session()
    cat = CostCategory(name="Asset Deal", pnl_line=PnlLine.OPEX, is_vatable=True)
    s.add(cat)
    s.commit()
    s.refresh(cat)
    s.add(CostPlanMonth(category_id=cat.id, year=2026, month=3, amount=NET))
    s.commit()

    entries = _entries(s)
    out = [e for e in entries if e.kind == CashflowKind.COST_OUT]
    vat = [e for e in entries if e.kind == CashflowKind.AUTHORITY_VAT]

    # The supplier is paid gross, the Finanzamt refunds the input VAT at M+2.
    assert round(out[0].amount, 2) == -round(NET * (1 + VAT_RATE), 2)
    assert round(vat[0].amount, 2) == round(NET * VAT_RATE, 2)
    assert vat[0].date == date(2026, 5, 15)
    # Net cash impact is the net price — no free money.
    assert round(sum(e.amount for e in entries), 2) == -NET


def test_vatable_revenue_collects_gross_and_remits_vat():
    s = _session()
    st = RevenueStream(name="Kundenprojekt", rtype=RevenueType.RECURRING,
                       payment_term=PaymentTerm.NET30, is_vatable=True)
    s.add(st)
    s.commit()
    s.refresh(st)
    s.add(RevenuePlanMonth(stream_id=st.id, year=2026, month=3, amount=NET))
    s.commit()

    entries = _entries(s)
    inflow = [e for e in entries if e.kind == CashflowKind.REVENUE_IN]
    vat = [e for e in entries if e.kind == CashflowKind.AUTHORITY_VAT]

    assert round(inflow[0].amount, 2) == round(NET * (1 + VAT_RATE), 2)
    assert round(vat[0].amount, 2) == -round(NET * VAT_RATE, 2)
    assert round(sum(e.amount for e in entries), 2) == NET


def test_non_vatable_position_moves_net_only():
    """A non-vatable stream (e.g. an EU grant) must not gross up, nor hit the UVA."""
    s = _session()
    st = RevenueStream(name="Förderung", rtype=RevenueType.ONEOFF,
                       payment_term=PaymentTerm.NET30, is_vatable=False)
    s.add(st)
    s.commit()
    s.refresh(st)
    s.add(RevenuePlanMonth(stream_id=st.id, year=2026, month=3, amount=NET))
    s.commit()

    entries = _entries(s)
    assert not [e for e in entries if e.kind == CashflowKind.AUTHORITY_VAT]
    assert round(sum(e.amount for e in entries), 2) == NET
