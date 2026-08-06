"""P&L (GuV) aggregation — Austrian Deckungsbeitragsrechnung.

Pure accrual by plan month (no cash timing). Reads the SAME source rows the
liquidity engine uses, so Personalaufwand here equals the salary matrix all-in
sum by construction.

Umsatz → (Material/COGS/External) → DB I → (Personal) → DB II →
(sonstige betr. Aufw.) → EBITDA → (Abschreibung) → EBIT → (Zinsen) → EBT
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from ..db import get_settings
from ..models import (
    CostCategory,
    CostPlanMonth,
    Depreciation,
    Employee,
    LoanSchedule,
    OpexCategory,
    PnlLine,
    RevenueCellEntry,
    RevenuePlanMonth,
    RevenueStream,
    RevenueType,
    SalaryMonth,
)
from .calendar_at import month_in_horizon
from .scenarios import effective_cost_ids, effective_revenue_ids, get_scenario

MONTHS = list(range(1, 13))


@dataclass
class PnlRow:
    label: str
    values: list[float] = field(default_factory=lambda: [0.0] * 12)
    kind: str = "line"   # 'line' | 'subtotal' | 'section'
    indent: int = 0
    editable_key: str = ""   # non-empty → cells are editable (routes the save), e.g. "depreciation"

    @property
    def annual(self) -> float:
        return sum(self.values)


def _zeros() -> list[float]:
    return [0.0] * 12


def pnl_view(session: Session, year: int, scenario_id: int = 1) -> list[PnlRow]:
    settings = get_settings(session)
    scenario = get_scenario(session, scenario_id)
    rev_ids = effective_revenue_ids(session, scenario)
    cost_ids = effective_cost_ids(session, scenario)

    # Revenue, kept per stream (itemised like the Excel 'Budget' sheet)
    streams = {s.id: s for s in session.exec(
        select(RevenueStream).order_by(RevenueStream.sort_order, RevenueStream.id)).all()}
    revenue = _zeros()
    rev_by_stream: dict[int, list[float]] = {}
    for rp in session.exec(select(RevenuePlanMonth).where(RevenuePlanMonth.year == year)).all():
        if rp.stream_id not in rev_ids or not month_in_horizon(year, rp.month, settings):
            continue
        revenue[rp.month - 1] += rp.amount
        rev_by_stream.setdefault(rp.stream_id, _zeros())[rp.month - 1] += rp.amount

    # Costs by P&L line
    # Two distinct sources of "bezogene Leistungen", shown as separate P&L rows:
    #   external_sub — subcontractors booked inside project revenue cells (inspections)
    #   external_cat — cost categories assigned to PnlLine.EXTERNAL_SERVICES
    material, cogs = _zeros(), _zeros()
    external_cat, external_sub = _zeros(), _zeros()
    opex_by_cat: dict[str, list[float]] = {}
    categories = {c.id: c for c in session.exec(select(CostCategory)).all()}
    for cp in session.exec(select(CostPlanMonth).where(CostPlanMonth.year == year)).all():
        cat = categories.get(cp.category_id)
        if cat is None or cp.category_id not in cost_ids or not month_in_horizon(year, cp.month, settings):
            continue
        if cat.is_capex:
            continue  # capitalised — reaches the P&L via AfA, not as an expense
        amt = abs(cp.amount)
        if cat.pnl_line == PnlLine.MATERIAL:
            material[cp.month - 1] += amt
        elif cat.pnl_line == PnlLine.COGS:
            cogs[cp.month - 1] += amt
        elif cat.pnl_line == PnlLine.EXTERNAL_SERVICES:
            external_cat[cp.month - 1] += amt
        else:  # OPEX
            key = (cat.opex_category.value if cat.opex_category else OpexCategory.OTHER.value)
            opex_by_cat.setdefault(key, _zeros())[cp.month - 1] += amt

    # Project subcontractor costs (embedded in revenue cells) → bezogene Inspektionen.
    for ce in session.exec(select(RevenueCellEntry).where(RevenueCellEntry.year == year)).all():
        if ce.stream_id not in rev_ids or not month_in_horizon(year, ce.month, settings):
            continue
        st = streams.get(ce.stream_id)
        if st is None or st.rtype != RevenueType.PROJECT:
            continue
        sub = (ce.qty or 0) * (ce.sub_rate or 0) + (ce.sub_fixed or 0)
        if sub:
            external_sub[ce.month - 1] += sub

    # Personnel (internal all-in vs external/contractor)
    personnel_int, personnel_ext = _zeros(), _zeros()
    employees = {e.id: e for e in session.exec(select(Employee)).all()}
    for sm in session.exec(select(SalaryMonth).where(SalaryMonth.year == year)).all():
        emp = employees.get(sm.employee_id)
        total = sm.gross + sm.special
        if emp is None or not total or not month_in_horizon(year, sm.month, settings):
            continue
        if emp.is_contractor:
            personnel_ext[sm.month - 1] += total
        else:
            personnel_int[sm.month - 1] += total * (1.0 + settings.employer_burden_pct)

    # Depreciation & interest
    depreciation = _zeros()
    for dp in session.exec(select(Depreciation).where(Depreciation.year == year)).all():
        if not month_in_horizon(year, dp.month, settings):
            continue
        depreciation[dp.month - 1] += abs(dp.amount)
    interest = _zeros()
    for sch in session.exec(select(LoanSchedule)).all():
        if sch.date.year == year and sch.interest and month_in_horizon(year, sch.date.month, settings):
            interest[sch.date.month - 1] += abs(sch.interest)

    # Assemble rows with subtotals
    def neg(a: list[float]) -> list[float]:
        return [-x for x in a]

    def add(*arrs: list[float]) -> list[float]:
        return [sum(col) for col in zip(*arrs)]

    db1 = add(revenue, neg(material), neg(cogs), neg(external_sub), neg(external_cat))
    db2 = add(db1, neg(personnel_int), neg(personnel_ext))
    opex_total = add(*opex_by_cat.values()) if opex_by_cat else _zeros()
    ebitda = add(db2, neg(opex_total))
    ebit = add(ebitda, neg(depreciation))
    ebt = add(ebit, neg(interest))

    rows: list[PnlRow] = []

    # 1. Umsatzerlöse — itemised per revenue stream, then the total.
    rows.append(PnlRow("1.  Umsatzerlöse", _zeros(), kind="section"))
    for sid in sorted(rev_by_stream, key=lambda i: (streams[i].sort_order if i in streams else 0, i)):
        arr = rev_by_stream[sid]
        if any(arr):
            label = streams[sid].name if sid in streams else "Sonstige Erlöse"
            rows.append(PnlRow(f"      {label}", arr, indent=1))
    rows.append(PnlRow("= Umsatzerlöse gesamt", revenue, kind="subtotal"))

    # 2. Material- & Leistungseinsatz
    rows.append(PnlRow("2.  Material & bezogene Leistungen", _zeros(), kind="section"))
    rows.append(PnlRow("      − Material", neg(material), indent=1))
    rows.append(PnlRow("      − Wareneinsatz", neg(cogs), indent=1))
    rows.append(PnlRow("      − Bezogene Inspektionsdienstleistungen", neg(external_sub), indent=1))
    rows.append(PnlRow("      − Bezogene Leistungen", neg(external_cat), indent=1))
    rows.append(PnlRow("3.  = Deckungsbeitrag I", db1, kind="subtotal"))

    # 4. Personalaufwand
    rows.append(PnlRow("4.  Personalaufwand", _zeros(), kind="section"))
    rows.append(PnlRow("      − Personalaufwand intern", neg(personnel_int), indent=1))
    rows.append(PnlRow("      − Personalaufwand extern", neg(personnel_ext), indent=1))
    rows.append(PnlRow("5.  = Deckungsbeitrag II", db2, kind="subtotal"))

    # 6. Sonstige betriebliche Aufwendungen (OPEX)
    rows.append(PnlRow("6.  Sonstige betriebliche Aufwendungen", _zeros(), kind="section"))
    for cat_name in sorted(opex_by_cat):
        rows.append(PnlRow(f"      − {cat_name}", neg(opex_by_cat[cat_name]), indent=1))
    rows.append(PnlRow("7.  = EBITDA", ebitda, kind="subtotal"))

    # 8.–10. Abschreibung, EBIT, Zinsen, EBT
    rows.append(PnlRow("8.  − Abschreibungen", neg(depreciation), editable_key="depreciation"))
    rows.append(PnlRow("9.  = EBIT", ebit, kind="subtotal"))
    rows.append(PnlRow("      − Zinsen", neg(interest), indent=1))
    rows.append(PnlRow("10. = EBT (Ergebnis vor Steuern)", ebt, kind="subtotal"))
    return rows
