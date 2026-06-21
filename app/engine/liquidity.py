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
