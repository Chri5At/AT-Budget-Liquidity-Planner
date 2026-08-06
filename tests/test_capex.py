"""CAPEX (Anlagenzugang): cash-effective, but not a P&L expense.

An asset purchase leaves the account gross and its input VAT is reclaimed, but it
is capitalised — the P&L sees it only later via AfA, never as an expense in the
month of purchase.
"""
from datetime import date

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import VAT_RATE
from app.engine.cashflow import build_cashflows
from app.engine.pnl import pnl_view
from app.models import (CashflowEntry, CashflowKind, CostCategory, CostPlanMonth,
                        PnlLine, Settings, SplitModel)

NET = 100_000.0
YEAR, MONTH = 2026, 3


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


def _with_cost(is_capex: bool) -> Session:
    s = _session()
    cat = CostCategory(name="Asset Deal", pnl_line=PnlLine.OPEX,
                       is_vatable=True, is_capex=is_capex)
    s.add(cat)
    s.commit()
    s.refresh(cat)
    s.add(CostPlanMonth(category_id=cat.id, year=YEAR, month=MONTH, amount=NET))
    s.commit()
    return s


def _ebitda(s: Session) -> list[float]:
    row = next(r for r in pnl_view(s, YEAR) if "EBITDA" in r.label)
    return row.values


def test_capex_is_not_a_pnl_expense():
    ebitda_capex = _ebitda(_with_cost(is_capex=True))
    ebitda_plain = _ebitda(_with_cost(is_capex=False))

    # Flagged as CAPEX the purchase never touches the P&L...
    assert ebitda_capex[MONTH - 1] == 0.0
    assert all(v == 0.0 for v in ebitda_capex)
    # ...whereas an ordinary cost hits EBITDA in full in the month it falls.
    assert round(ebitda_plain[MONTH - 1], 2) == -NET


def test_capex_still_moves_cash_gross_and_reclaims_vat():
    s = _with_cost(is_capex=True)
    build_cashflows(s)
    entries = list(s.exec(select(CashflowEntry)).all())

    out = [e for e in entries if e.kind in (CashflowKind.COST_OUT, CashflowKind.COGS_OUT)]
    vat = [e for e in entries if e.kind == CashflowKind.AUTHORITY_VAT]

    assert round(out[0].amount, 2) == -round(NET * (1 + VAT_RATE), 2)
    assert round(vat[0].amount, 2) == round(NET * VAT_RATE, 2)
    assert round(sum(e.amount for e in entries), 2) == -NET
