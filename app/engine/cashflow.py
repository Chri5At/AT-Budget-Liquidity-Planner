"""Build the dated cashflow ledger from all source plan rows.

This is the heart of the "one DB, two views" design: the SAME source rows that
feed the P&L are run through Austrian timing rules here to produce dated cash
movements. Salaries become net (month-end) + Abgaben (15th of next month);
revenue/cost respect payment terms; VAT settles on the 15th of M+2.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete as sa_delete
from sqlmodel import Session, select

from ..config import VAT_RATE
from ..db import get_settings
from ..models import (
    CashflowEntry,
    CashflowKind,
    CostCategory,
    CostPlanMonth,
    Employee,
    Investment,
    Loan,
    LoanKind,
    LoanSchedule,
    PnlLine,
    RevenuePlanMonth,
    RevenueStream,
    SalaryMonth,
)
from ..models.enums import TERM_DAYS
from .calendar_at import (
    abgaben_due_date,
    bucket_for,
    last_banking_day_of_month,
    last_day_of_month,
    month_in_horizon,
    prev_banking_day,
    shift_by_days,
    shift_by_term,
    vat_due_date,
)
from .payroll_at import employee_year_cost, ruleset_for_year
from .scenarios import effective_cost_ids, effective_revenue_ids, get_scenario


def build_cashflows(session: Session) -> int:
    """Wipe and rebuild the persisted CashflowEntry ledger (base scenario)."""
    entries = build_entries(session, scenario_id=1)
    session.execute(sa_delete(CashflowEntry))
    for e in entries:
        session.add(e)
    session.commit()
    return len(entries)


def build_entries(session: Session, scenario_id: int = 1) -> list[CashflowEntry]:
    """Compute the dated cashflow entries for a scenario (with buckets set).

    Not persisted — callers either store them (base ledger) or use them in memory
    for a scenario's liquidity view. Revenue and costs are filtered to the rows
    effective for the scenario; salaries, loans and investments are shared.
    """
    settings = get_settings(session)
    subdiv = settings.bundesland_subdiv
    scenario = get_scenario(session, scenario_id)
    rev_ids = effective_revenue_ids(session, scenario)
    cost_ids = effective_cost_ids(session, scenario)

    entries: list[CashflowEntry] = []
    vat_by_month: dict[tuple[int, int], float] = defaultdict(float)  # output - input VAT

    # --- Salaries & contractors (per employee-year, Austrian net) ---------------
    employees = {e.id: e for e in session.exec(select(Employee)).all()}
    sal: dict[tuple[int, int], dict[str, list[float]]] = {}
    for sm in session.exec(select(SalaryMonth)).all():
        if (sm.employee_id not in employees
                or not month_in_horizon(sm.year, sm.month, settings)):
            continue
        slot = sal.setdefault((sm.employee_id, sm.year),
                              {"regular": [0.0] * 12, "special": [0.0] * 12})
        slot["regular"][sm.month - 1] += sm.gross
        slot["special"][sm.month - 1] += sm.special
    for (emp_id, year), data in sal.items():
        emp = employees[emp_id]
        rs = ruleset_for_year(year)
        if emp.is_contractor:
            for m in range(12):
                amt = data["regular"][m] + data["special"][m]
                if not amt:
                    continue
                pay = shift_by_term(last_day_of_month(year, m + 1), emp.payment_term, subdiv)
                entries.append(CashflowEntry(
                    date=pay, kind=CashflowKind.CONTRACTOR, amount=-amt,
                    source_kind="employee", source_id=emp_id, memo=f"{emp.name} (extern)"))
        else:
            mc = employee_year_cost(data["regular"], data["special"],
                                    burden_pct=settings.employer_burden_pct, rs=rs)
            for m in range(12):
                if mc.net[m]:
                    entries.append(CashflowEntry(
                        date=last_banking_day_of_month(year, m + 1, subdiv),
                        kind=CashflowKind.SALARY_NET, amount=-mc.net[m],
                        source_kind="employee", source_id=emp_id, memo=f"{emp.name} Netto"))
                if mc.abgaben[m]:
                    entries.append(CashflowEntry(
                        date=abgaben_due_date(year, m + 1, settings.abgaben_pay_day, subdiv),
                        kind=CashflowKind.SALARY_ABGABEN, amount=-mc.abgaben[m],
                        source_kind="employee", source_id=emp_id, memo=f"{emp.name} Abgaben"))

    # --- Revenue ---------------------------------------------------------------
    streams = {s.id: s for s in session.exec(select(RevenueStream)).all()}
    for rp in session.exec(select(RevenuePlanMonth)).all():
        stream = streams.get(rp.stream_id)
        if (stream is None or not rp.amount or rp.stream_id not in rev_ids
                or not month_in_horizon(rp.year, rp.month, settings)):
            continue
        inv = last_day_of_month(rp.year, rp.month)
        days = stream.payment_days if stream.payment_days is not None else TERM_DAYS[stream.payment_term]
        cash = shift_by_days(inv, days, subdiv)
        entries.append(CashflowEntry(
            date=cash, kind=CashflowKind.REVENUE_IN, amount=+rp.amount,
            source_kind="revenue", source_id=stream.id, memo=stream.name))
        if stream.is_vatable:
            vat_by_month[(rp.year, rp.month)] += rp.amount * VAT_RATE

    # --- Costs (Material/COGS/External/OPEX) -----------------------------------
    categories = {c.id: c for c in session.exec(select(CostCategory)).all()}
    for cp in session.exec(select(CostPlanMonth)).all():
        cat = categories.get(cp.category_id)
        if (cat is None or not cp.amount or cp.category_id not in cost_ids
                or not month_in_horizon(cp.year, cp.month, settings)):
            continue
        amount = abs(cp.amount)
        inv = last_day_of_month(cp.year, cp.month)
        cash = shift_by_term(inv, cat.payment_term, subdiv)
        kind = CashflowKind.COGS_OUT if cat.pnl_line == PnlLine.COGS else CashflowKind.COST_OUT
        entries.append(CashflowEntry(
            date=cash, kind=kind, amount=-amount,
            source_kind="cost", source_id=cat.id, memo=cat.name))
        if cat.is_vatable:
            vat_by_month[(cp.year, cp.month)] -= amount * VAT_RATE

    # --- VAT settlement (USt-Voranmeldung, 15th of M+2) ------------------------
    for (year, month), vat in vat_by_month.items():
        if abs(vat) < 0.005:
            continue
        # vat > 0 => Zahllast (pay out); vat < 0 => Guthaben (refund in)
        entries.append(CashflowEntry(
            date=vat_due_date(year, month, subdiv), kind=CashflowKind.AUTHORITY_VAT,
            amount=-vat, source_kind="vat", source_id=None,
            memo="USt-Zahllast" if vat > 0 else "USt-Guthaben"))

    # --- Investments (capital paid in by named investors) ----------------------
    for inv in session.exec(select(Investment)).all():
        if not inv.amount or inv.date is None:
            continue
        memo = inv.investor + (f" · {inv.label}" if inv.label else "")
        entries.append(CashflowEntry(
            date=prev_banking_day(inv.date, subdiv), kind=CashflowKind.INVESTMENT_IN,
            amount=+abs(inv.amount), source_kind="investment", source_id=inv.id, memo=memo))

    # --- Loans & funding -------------------------------------------------------
    for loan in session.exec(select(Loan)).all():
        if loan.disbursement_date and loan.principal:
            kind = CashflowKind.FUNDING_IN if loan.kind == LoanKind.EU_FUNDING else CashflowKind.LOAN_IN
            entries.append(CashflowEntry(
                date=prev_banking_day(loan.disbursement_date, subdiv), kind=kind,
                amount=+loan.principal, source_kind="loan", source_id=loan.id,
                is_eu_funding=loan.is_eu_funding, memo=loan.name))
        for sch in session.exec(select(LoanSchedule).where(LoanSchedule.loan_id == loan.id)).all():
            d = prev_banking_day(sch.date, subdiv)
            if sch.principal_repay:
                entries.append(CashflowEntry(
                    date=d, kind=CashflowKind.LOAN_REPAY, amount=-abs(sch.principal_repay),
                    source_kind="loan", source_id=loan.id, memo=f"{loan.name} Tilgung"))
            if sch.interest:
                entries.append(CashflowEntry(
                    date=d, kind=CashflowKind.INTEREST_OUT, amount=-abs(sch.interest),
                    source_kind="loan", source_id=loan.id, memo=f"{loan.name} Zinsen"))

    # --- Assign buckets (caller decides whether to persist) --------------------
    for e in entries:
        e.bucket = bucket_for(e.date)
    return entries
