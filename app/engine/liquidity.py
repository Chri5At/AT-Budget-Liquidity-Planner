"""Liquidity view: bucketise the cashflow ledger and roll a running balance.

Produces two balance series — with and without EU funding — mirroring the Excel
rows 'Bank Status' and 'Bank Status without EU-Funding'.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, select

from ..db import get_settings
from ..models import CashflowEntry, CashflowKind
from .calendar_at import add_months, last_day_of_month

# Group cashflow kinds into the liquidity report's row sections.
INFLOW_KINDS = {CashflowKind.REVENUE_IN, CashflowKind.FUNDING_IN, CashflowKind.LOAN_IN,
                CashflowKind.INVESTMENT_IN}


@dataclass
class BucketRow:
    bucket: date
    label: str
    inflow: float = 0.0
    outflow: float = 0.0
    net: float = 0.0
    balance: float = 0.0
    balance_no_eu: float = 0.0
    subcontractor: float = 0.0   # subcontractor outflow in this bucket (negative)
    by_kind: dict = field(default_factory=dict)


def bucket_sequence(settings) -> list[date]:
    """Ordered 15th + month-end buckets across the planning horizon."""
    buckets: list[date] = []
    y, m = settings.horizon_start.year, settings.horizon_start.month
    end = settings.horizon_end
    while date(y, m, 1) <= end:
        buckets.append(date(y, m, 15))
        buckets.append(last_day_of_month(y, m))
        y, m = add_months(y, m, 1)
    return buckets


def liquidity_view(session: Session, entries=None) -> list[BucketRow]:
    settings = get_settings(session)
    if entries is None:
        entries = session.exec(select(CashflowEntry)).all()

    by_bucket: dict[date, dict] = defaultdict(lambda: defaultdict(float))
    eu_by_bucket: dict[date, float] = defaultdict(float)
    for e in entries:
        slot = by_bucket[e.bucket]
        slot["__net__"] += e.amount
        if e.amount >= 0:
            slot["__in__"] += e.amount
        else:
            slot["__out__"] += e.amount
        slot[e.kind.value] += e.amount
        if e.source_kind == "subcontractor":
            slot["__sub__"] += e.amount
        if e.is_eu_funding:
            eu_by_bucket[e.bucket] += e.amount

    # The opening balance is the cash on hand *as of* opening_balance_date.
    # Buckets before that date are already reflected in it, so the running
    # balance starts there and earlier buckets are not part of the plan.
    opening_date = settings.opening_balance_date
    balance = settings.opening_balance
    balance_no_eu = settings.opening_balance
    rows: list[BucketRow] = []
    for b in bucket_sequence(settings):
        if b < opening_date:
            continue
        slot = by_bucket.get(b, {})
        net = slot.get("__net__", 0.0)
        balance += net
        balance_no_eu += net - eu_by_bucket.get(b, 0.0)
        label = f"{b.day:02d}.{b.month:02d}.{b.year}"
        rows.append(BucketRow(
            bucket=b, label=label,
            inflow=slot.get("__in__", 0.0), outflow=slot.get("__out__", 0.0),
            net=net, balance=balance, balance_no_eu=balance_no_eu,
            subcontractor=slot.get("__sub__", 0.0),
            by_kind={k: v for k, v in slot.items() if not k.startswith("__")},
        ))
    return rows


def liquidity_view_for_scenario(session: Session, scenario_id: int) -> list[BucketRow]:
    """Liquidity for a scenario, computed in memory (without touching the cache)."""
    from .cashflow import build_entries
    entries = build_entries(session, scenario_id)
    return liquidity_view(session, entries)


@dataclass
class PivotSection:
    name: str
    totals: list[float]                      # per bucket
    items: list[tuple[str, list[float]]]     # (label, per-bucket values)


@dataclass
class LiquidityPivot:
    buckets: list[date]
    labels: list[str]                        # bucket labels (dd.mm.yyyy)
    sections: list[PivotSection]             # Einzahlungen, Auszahlungen
    saldo: list[float]
    bank: list[float]
    bank_no_eu: list[float]


_MONTHS_DE = ["Jän", "Feb", "Mär", "Apr", "Mai", "Jun",
              "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def _group_periods(fine: list[date], granularity: str):
    """Group fine 15./month-end buckets into display periods.
    Returns list of (label, [bucket dates in this period], period_end_bucket)."""
    if granularity == "monthly":
        groups: dict = {}
        for b in fine:
            groups.setdefault((b.year, b.month), []).append(b)
        out = []
        for (y, m), bks in sorted(groups.items()):
            out.append((f"{_MONTHS_DE[m - 1]} {y}", bks, bks[-1]))
        return out
    if granularity == "quarterly":
        groups = {}
        for b in fine:
            groups.setdefault((b.year, (b.month - 1) // 3 + 1), []).append(b)
        out = []
        for (y, q), bks in sorted(groups.items()):
            out.append((f"Q{q} {y}", bks, bks[-1]))
        return out
    # biweekly (default): each fine bucket is its own period
    return [(f"{b.day:02d}.{b.month:02d}.{b.year}", [b], b) for b in fine]


def liquidity_pivot(session: Session, entries=None, *, granularity: str = "biweekly",
                    range_start: date | None = None, range_end: date | None = None) -> LiquidityPivot:
    """Horizontal cash-flow view: time periods as columns, grouped line items as rows.

    `granularity` is 'biweekly' | 'monthly' | 'quarterly'. `range_start`/`range_end`
    limit which periods are shown; the running balance is still cumulative from the
    opening date (so the Bank Status of a shown period includes earlier flows)."""
    from collections import defaultdict
    if entries is None:
        entries = session.exec(select(CashflowEntry)).all()

    rows = liquidity_view(session, entries)        # fine buckets ≥ opening date, with balances
    by_b = {r.bucket: r for r in rows}
    fine = [r.bucket for r in rows]
    disp = [b for b in fine
            if (range_start is None or b >= range_start) and (range_end is None or b <= range_end)]
    periods = _group_periods(disp, granularity)
    n = len(periods)

    bucket_to_p: dict[date, int] = {}
    for pi, (_, bks, _) in enumerate(periods):
        for b in bks:
            bucket_to_p[b] = pi

    sec: dict[str, dict[str, list[float]]] = {
        "Einzahlungen": defaultdict(lambda: [0.0] * n),
        "Auszahlungen": defaultdict(lambda: [0.0] * n),
    }
    for e in entries:
        pi = bucket_to_p.get(e.bucket)
        if pi is None:
            continue
        section = "Einzahlungen" if e.kind in INFLOW_KINDS else "Auszahlungen"
        sec[section][e.memo or "(ohne Bezeichnung)"][pi] += e.amount

    sections = []
    for name in ("Einzahlungen", "Auszahlungen"):
        items = sorted(sec[name].items(), key=lambda kv: -sum(abs(x) for x in kv[1]))
        totals = [sum(vals[i] for _, vals in items) for i in range(n)]
        sections.append(PivotSection(name, totals,
                                     [(lbl, [round(x) for x in vals]) for lbl, vals in items]))

    saldo, bank, bank_no_eu, labels = [], [], [], []
    for lbl, bks, end in periods:
        labels.append(lbl)
        saldo.append(round(sum(by_b[b].net for b in bks)))
        bank.append(round(by_b[end].balance))
        bank_no_eu.append(round(by_b[end].balance_no_eu))

    return LiquidityPivot([end for _, _, end in periods], labels, sections, saldo, bank, bank_no_eu)


def liquidity_pivot_for_scenario(session: Session, scenario_id: int, **kw) -> LiquidityPivot:
    from .cashflow import build_entries
    return liquidity_pivot(session, build_entries(session, scenario_id), **kw)
