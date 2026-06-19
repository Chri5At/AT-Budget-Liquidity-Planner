"""The cashflow ledger must reconcile with the salary split, on the right dates."""
from datetime import date

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.engine.cashflow import build_cashflows
from app.engine.payroll_at import employee_year_cost, ruleset_for_year
from app.models import CashflowEntry, CashflowKind, Employee, SalaryMonth, Settings, SplitModel


def _session() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def test_salary_cashflows_reconcile_and_dates():
    s = _session()
    st = Settings(id=1, split_model=SplitModel.FIXED_PCT, abgaben_pct=0.30, employer_burden_pct=0.30,
                  opening_balance=0.0, horizon_start=date(2026, 1, 1), horizon_end=date(2026, 12, 31))
    s.add(st)
    emp = Employee(name="Test", is_contractor=False)
    s.add(emp)
    s.commit()
    s.refresh(emp)
    s.add(SalaryMonth(employee_id=emp.id, year=2026, month=1, gross=6540.0))
    s.commit()

    build_cashflows(s)

    entries = s.exec(select(CashflowEntry)).all()
    net = [e for e in entries if e.kind == CashflowKind.SALARY_NET]
    abg = [e for e in entries if e.kind == CashflowKind.SALARY_ABGABEN]
    assert len(net) == 1 and len(abg) == 1

    mc = employee_year_cost([6540.0] + [0.0] * 11, [0.0] * 12,
                            burden_pct=0.30, rs=ruleset_for_year(2026))
    assert round(-net[0].amount) == round(mc.net[0])
    assert round(-abg[0].amount) == round(mc.abgaben[0])
    # Net on last banking day of Jan 2026 (31.01 is Sat -> 30.01 Fri).
    assert net[0].date == date(2026, 1, 30)
    # Abgaben on 15.02.2026 (Sun) -> 13.02.2026 Fri.
    assert abg[0].date == date(2026, 2, 13)
    # Net + Abgaben == all-in employer cost.
    assert round(-(net[0].amount + abg[0].amount)) == round(mc.all_in[0])
