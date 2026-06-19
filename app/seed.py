"""Seed fictional demo data so the first run shows something meaningful.
Only runs when the database is empty.

All names, companies and figures below are invented placeholders for a generic
Austrian GmbH (Sonderzahlungen in Jun/Nov, 30 % employer burden). They are not
real and carry no meaning — edit everything in the UI; this is only a starting
point to illustrate the app.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from .models import (
    CostCategory,
    CostPlanMonth,
    Depreciation,
    Employee,
    Loan,
    LoanKind,
    LoanSchedule,
    OpexCategory,
    PaymentTerm,
    PnlLine,
    RevenuePlanMonth,
    RevenueStream,
    RevenueType,
    SalaryMonth,
    Settings,
)

YEARS = (2026, 2027)
SONDER_MONTHS = (6, 11)  # 13th/14th salary appear as double-salary months


def _salary_row(session: Session, emp: Employee, base: float, *, start_month: int = 1):
    """Fill 12 months for both years; Jun/Nov carry a Sonderzahlung (13./14.)."""
    for year in YEARS:
        for month in range(1, 13):
            if year == YEARS[0] and month < start_month:
                gross = 0.0
            else:
                gross = base
            special = base if (gross and month in SONDER_MONTHS) else 0.0
            session.add(SalaryMonth(employee_id=emp.id, year=year, month=month,
                                    gross=gross, special=special))


def _monthly_cost(session: Session, cat: CostCategory, amount: float):
    for year in YEARS:
        for month in range(1, 13):
            session.add(CostPlanMonth(category_id=cat.id, year=year, month=month, amount=amount))


def _monthly_revenue(session: Session, stream: RevenueStream, amount: float):
    for year in YEARS:
        for month in range(1, 13):
            session.add(RevenuePlanMonth(stream_id=stream.id, year=year, month=month, amount=amount))


def seed_if_empty(session: Session) -> bool:
    st0 = session.get(Settings, 1)
    if (st0 is not None and st0.seeded) or session.exec(select(Employee)).first() is not None:
        return False

    # --- Settings ---------------------------------------------------------------
    st = session.get(Settings, 1)
    if st is None:
        st = Settings(id=1)
        session.add(st)
    st.company_name = "Muster GmbH"
    st.opening_balance = 50000.0
    st.opening_balance_date = date(2026, 1, 1)
    st.horizon_start = date(2026, 1, 1)
    st.horizon_end = date(2027, 12, 31)
    st.seeded = True
    session.commit()

    # --- Employees (fictional placeholder team) --------------------------------
    team = [
        ("A. Beispiel", "Geschäftsführung", 1.0, 5000.0, 1),
        ("B. Muster", "Software Engineer", 1.0, 4500.0, 1),
        ("C. Demo", "Sales", 1.0, 4000.0, 1),
        ("D. Example", "Operations", 0.8, 3000.0, 1),
        ("E. Test", "Qualitätsmanagement", 0.1, 500.0, 1),
        ("F. Sample", "Marketing", 1.0, 3500.0, 1),
    ]
    for i, (name, fn, fte, base, start) in enumerate(team):
        emp = Employee(name=name, function=fn, fte=fte, is_contractor=False, sort_order=i)
        session.add(emp)
        session.commit()
        session.refresh(emp)
        _salary_row(session, emp, base, start_month=start)

    # One external contractor example
    ext = Employee(name="G. Extern", function="Beratung (extern)",
                   fte=1.0, is_contractor=True, payment_term=PaymentTerm.NET15, sort_order=10)
    session.add(ext)
    session.commit()
    session.refresh(ext)
    _salary_row(session, ext, 2500.0)
    session.commit()

    # --- Revenue streams (income segmentation) ---------------------------------
    streams = [
        ("Produkt A", RevenueType.PRODUCT, PaymentTerm.NET30, 15000.0),
        ("Wartung / Lizenz", RevenueType.RECURRING, PaymentTerm.NET30, 8000.0),
        ("Projekt-Dienstleistung", RevenueType.PROJECT, PaymentTerm.NET45, 12000.0),
        ("Beratung", RevenueType.PROJECT, PaymentTerm.NET30, 5000.0),
        ("Förderung (EU/AT)", RevenueType.ONEOFF, PaymentTerm.NET30, 0.0),
    ]
    for i, (name, rtype, term, amt) in enumerate(streams):
        s = RevenueStream(name=name, rtype=rtype, payment_term=term,
                          is_vatable=(rtype != RevenueType.ONEOFF), sort_order=i)
        session.add(s)
        session.commit()
        session.refresh(s)
        if amt:
            _monthly_revenue(session, s, amt)
    session.commit()

    # --- Cost categories -------------------------------------------------------
    costs = [
        ("Material", PnlLine.MATERIAL, None, 500.0),
        ("Wareneinsatz", PnlLine.COGS, None, 4000.0),
        ("Bezogene Leistungen", PnlLine.EXTERNAL_SERVICES, None, 3000.0),
        ("Miete", PnlLine.OPEX, OpexCategory.RENT, 2000.0),
        ("IT", PnlLine.OPEX, OpexCategory.IT, 800.0),
        ("Versicherungen", PnlLine.OPEX, OpexCategory.INSURANCE, 200.0),
        ("Reisekosten", PnlLine.OPEX, OpexCategory.TRAVEL, 1000.0),
        ("Marketing/PR", PnlLine.OPEX, OpexCategory.MARKETING, 800.0),
        ("Rechts-/Beratung", PnlLine.OPEX, OpexCategory.LEGAL, 600.0),
    ]
    for i, (name, line, opex, amt) in enumerate(costs):
        c = CostCategory(name=name, pnl_line=line, opex_category=opex, sort_order=i)
        session.add(c)
        session.commit()
        session.refresh(c)
        _monthly_cost(session, c, amt)
    session.commit()

    # --- Depreciation ----------------------------------------------------------
    for year in YEARS:
        for month in range(1, 13):
            session.add(Depreciation(name="Abschreibung Sachanlagen", year=year, month=month, amount=1000.0))

    # --- EU funding + a bank loan ---------------------------------------------
    eu = Loan(name="EU-Förderung", kind=LoanKind.EU_FUNDING, principal=100000.0,
              disbursement_date=date(2026, 7, 15), is_eu_funding=True)
    session.add(eu)
    bank = Loan(name="Bankdarlehen", kind=LoanKind.BANK_LOAN, principal=80000.0,
                disbursement_date=date(2026, 3, 31), is_eu_funding=False)
    session.add(bank)
    session.commit()
    session.refresh(bank)
    for year in YEARS:
        for month in range(1, 13):
            from .engine.calendar_at import last_day_of_month
            d = last_day_of_month(year, month)
            session.add(LoanSchedule(loan_id=bank.id, date=d, principal_repay=1500.0, interest=200.0))
    session.commit()

    # Build the initial cashflow ledger
    from .engine.cashflow import build_cashflows
    build_cashflows(session)
    return True
