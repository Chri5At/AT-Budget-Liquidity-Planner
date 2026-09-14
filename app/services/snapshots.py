"""Snapshots — save the full plan, restore it, or compare its KPIs to the current one.

A snapshot serialises every *source* table to JSON (the derived CashflowEntry cache
is rebuilt, never stored). Comparison loads the snapshot into a throwaway in-memory
database and runs the same engines on it, so the figures are computed identically.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ..models import (
    Contract,
    CostCategory,
    CostCellEntry,
    CostPlanMonth,
    Depreciation,
    Employee,
    Investment,
    Loan,
    LoanSchedule,
    RevenueCellEntry,
    RevenuePlanMonth,
    RevenueStream,
    SalaryMonth,
    Scenario,
    ScenarioDisable,
    Settings,
    Snapshot,
)

# Source tables captured in a snapshot (NOT Snapshot itself or the CashflowEntry cache).
# Parents before children so a restore inserts in FK-safe order.
SNAPSHOT_MODELS = [
    Settings, Scenario, ScenarioDisable,
    Employee, SalaryMonth,
    RevenueStream, RevenuePlanMonth, RevenueCellEntry,
    CostCategory, Contract, CostPlanMonth, CostCellEntry,
    Depreciation, Investment, Loan, LoanSchedule,
]


def _dump_payload(session: Session) -> str:
    data = {m.__name__: [r.model_dump(mode="json") for r in session.exec(select(m)).all()]
            for m in SNAPSHOT_MODELS}
    return json.dumps(data)


def create_snapshot(session: Session, name: str, note: str = "") -> Snapshot:
    snap = Snapshot(name=name or "Snapshot", note=note,
                    created_at=datetime.now().isoformat(timespec="seconds"),
                    payload=_dump_payload(session))
    session.add(snap)
    session.commit()
    session.refresh(snap)
    return snap


def list_snapshots(session: Session) -> list[Snapshot]:
    return session.exec(select(Snapshot).order_by(Snapshot.created_at.desc())).all()


def delete_snapshot(session: Session, snapshot_id: int) -> None:
    snap = session.get(Snapshot, snapshot_id)
    if snap is not None:
        session.delete(snap)
        session.commit()


def _coerce_dates(model, row: dict) -> dict:
    """Table models skip validation, so parse ISO date strings back to date objects."""
    out = dict(row)
    for fname, finfo in model.model_fields.items():
        ann = finfo.annotation
        is_date = ann is date or date in getattr(ann, "__args__", ())
        if is_date and isinstance(out.get(fname), str) and out[fname]:
            out[fname] = date.fromisoformat(out[fname])
    return out


def _load_payload(session: Session, payload: str) -> None:
    """Insert all rows from a snapshot/export payload into the given (empty) session.

    Unknown keys are dropped so a payload exported by a *newer* app version (with
    extra columns) still imports; missing columns fall back to the model defaults.
    """
    data = json.loads(payload or "{}")
    by_name = {m.__name__: m for m in SNAPSHOT_MODELS}
    for name in (m.__name__ for m in SNAPSHOT_MODELS):
        model = by_name[name]
        fields = set(model.model_fields)
        for row in data.get(name, []):
            known = {k: v for k, v in row.items() if k in fields}
            session.add(model(**_coerce_dates(model, known)))
    session.commit()


def dump_all(session: Session) -> str:
    """Public JSON dump of every source table (used by the data export)."""
    return _dump_payload(session)


def replace_all_from_payload(session: Session, payload: str) -> None:
    """Destructively replace the current plan with the payload, then rebuild cashflows."""
    for m in reversed(SNAPSHOT_MODELS):   # children first
        session.execute(sa_delete(m))
    session.commit()
    _load_payload(session, payload)
    from ..engine.cashflow import build_cashflows
    from ..engine.contracts import generate_contract_cells
    generate_contract_cells(session)
    build_cashflows(session)


def restore_snapshot(session: Session, snapshot_id: int) -> bool:
    """Replace the current plan with the snapshot (destructive), then rebuild cashflows."""
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        return False
    replace_all_from_payload(session, snap.payload)
    return True


def _temp_session(payload: str) -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    sess = Session(eng)
    _load_payload(sess, payload)
    return sess


# --- comparison --------------------------------------------------------------------
#
# A comparison evaluates each side (current plan / snapshot) ONCE per (year,
# scenario) with the real engines and then slices those monthly figures per
# period, so a month-by-month view costs the same as the annual one.

KPI_KEYS = [
    "Umsatzerlöse", "Deckungsbeitrag I", "Personalaufwand intern", "Deckungsbeitrag II",
    "EBITDA", "EBIT", "EBT", "Tiefststand Liquidität", "Endsaldo Liquidität",
]

# P&L KPI -> (substring of the pnl_view row label, sign applied to the row's values)
_PNL_KPIS = {
    "Umsatzerlöse": ("Umsatzerlöse gesamt", 1),
    "Deckungsbeitrag I": ("Deckungsbeitrag I", 1),
    "Personalaufwand intern": ("Personalaufwand intern", -1),
    "Deckungsbeitrag II": ("Deckungsbeitrag II", 1),
    "EBITDA": ("EBITDA", 1),
    "EBIT": ("= EBIT", 1),
    "EBT": ("EBT", 1),
}

# Display granularities (key -> label) of the comparison.
GRANULARITIES = {"year": "Jahr", "quarter": "Quartal", "month": "Monat"}


def period_ranges(granularity: str, year: int) -> list[tuple[str, tuple[int, int]]]:
    """[(label, (first_month, last_month))] for one planning year."""
    if granularity == "quarter":
        return [(f"Q{q} {year}", (3 * q - 2, 3 * q)) for q in range(1, 5)]
    if granularity == "month":
        from ..ui.formatting import MONTHS_DE
        return [(f"{MONTHS_DE[m - 1]} {year}", (m, m)) for m in range(1, 13)]
    return [(str(year), (1, 12))]


@dataclass
class PlanFigures:
    """Everything a comparison needs from one side, for one (year, scenario)."""
    year: int
    pnl: list                                    # list[PnlRow] — 12 monthly values each
    liquidity: list                              # list[BucketRow] — the full running balance
    streams: dict[int, tuple[str, list[float]]]  # stream id -> (name, 12 monthly amounts)


def plan_figures(session: Session, year: int, scenario_id: int = 1) -> PlanFigures:
    """Run the engines once for (year, scenario) — the current plan in `session`."""
    from ..db import get_settings
    from ..engine.calendar_at import month_in_horizon
    from ..engine.liquidity import liquidity_view_for_scenario
    from ..engine.pnl import pnl_view
    from ..engine.scenarios import effective_revenue_ids, get_scenario

    pnl = pnl_view(session, year, scenario_id)
    liq = liquidity_view_for_scenario(session, scenario_id)

    # Revenue per stream, keyed by the stream *id* so a renamed Einnahmequelle still
    # matches its snapshot counterpart (names are display-only).
    settings = get_settings(session)
    rev_ids = effective_revenue_ids(session, get_scenario(session, scenario_id))
    order = session.exec(select(RevenueStream)
                         .order_by(RevenueStream.sort_order, RevenueStream.id)).all()
    streams: dict[int, tuple[str, list[float]]] = {
        st.id: (st.name, [0.0] * 12) for st in order if st.id in rev_ids}
    for rp in session.exec(select(RevenuePlanMonth).where(RevenuePlanMonth.year == year)).all():
        if rp.stream_id in streams and month_in_horizon(year, rp.month, settings):
            streams[rp.stream_id][1][rp.month - 1] += rp.amount
    return PlanFigures(year=year, pnl=pnl, liquidity=liq, streams=streams)


def snapshot_figures(snapshot: Snapshot, year: int, scenario_id: int = 1) -> PlanFigures:
    sess = _temp_session(snapshot.payload)
    try:
        return plan_figures(sess, year, scenario_id)
    finally:
        sess.close()


def kpis(fig: PlanFigures, months: tuple[int, int] = (1, 12)) -> dict[str, float]:
    """Key figures of one side for the months `first..last` (inclusive) of its year.

    P&L figures are the sum over those months. The liquidity figures come from the
    running balance *within that window only*: the lowest balance of any 15./month-
    end bucket in it, and the balance at its last bucket — never the low/end of the
    whole planning horizon.
    """
    first, last = months
    out: dict[str, float] = {}
    for key, (needle, sign) in _PNL_KPIS.items():
        row = next((r for r in fig.pnl if needle in r.label), None)
        out[key] = round(sign * sum(row.values[first - 1:last])) if row else 0.0
    window = [b for b in fig.liquidity
              if b.bucket.year == fig.year and first <= b.bucket.month <= last]
    out["Tiefststand Liquidität"] = round(min((b.balance for b in window), default=0.0))
    out["Endsaldo Liquidität"] = round(window[-1].balance) if window else 0.0
    return out


def compute_kpis(session: Session, year: int, scenario_id: int = 1,
                 months: tuple[int, int] = (1, 12)) -> dict[str, float]:
    """Key figures for one (year, scenario[, month window]), computed by the real engines."""
    return kpis(plan_figures(session, year, scenario_id), months)


def snapshot_kpis(snapshot: Snapshot, year: int, scenario_id: int = 1,
                  months: tuple[int, int] = (1, 12)) -> dict[str, float]:
    return kpis(snapshot_figures(snapshot, year, scenario_id), months)


@dataclass
class CompareRow:
    label: str
    snap: list[float]      # one value per period
    cur: list[float]
    indent: int = 0        # 1 = per-stream detail under Umsatzerlöse
    note: str = ""         # e.g. "im Snapshot: <old name>", "nur im Snapshot"

    @property
    def diff(self) -> list[float]:
        return [c - s for s, c in zip(self.snap, self.cur)]


def compare_rows(cur: PlanFigures, snp: PlanFigures,
                 ranges: list[tuple[int, int]]) -> list[CompareRow]:
    """KPI rows (plus one detail row per Einnahmequelle) for each month window in `ranges`.

    Streams are matched by id, so a renamed stream lines up with its old self and the
    row carries the snapshot name as a note. Streams present on one side only are
    shown too (marked), so nothing silently drops out of the Umsatzerlöse total.
    """
    cur_k = [kpis(cur, r) for r in ranges]
    snp_k = [kpis(snp, r) for r in ranges]
    rows: list[CompareRow] = []
    for key in KPI_KEYS:
        rows.append(CompareRow(key, [k[key] for k in snp_k], [k[key] for k in cur_k]))
        if key == "Umsatzerlöse":
            rows.extend(_stream_rows(cur, snp, ranges))
    return rows


def _stream_rows(cur: PlanFigures, snp: PlanFigures,
                 ranges: list[tuple[int, int]]) -> list[CompareRow]:
    def window_sum(values: list[float] | None, r: tuple[int, int]) -> float:
        return round(sum(values[r[0] - 1:r[1]])) if values else 0.0

    ids = list(cur.streams) + [i for i in snp.streams if i not in cur.streams]
    rows: list[CompareRow] = []
    for sid in ids:
        c_name, c_vals = cur.streams.get(sid, ("", None))
        s_name, s_vals = snp.streams.get(sid, ("", None))
        if not any(c_vals or []) and not any(s_vals or []):
            continue
        if c_vals is None:
            label, note = s_name, "nur im Snapshot"
        elif s_vals is None:
            label, note = c_name, "neu, nicht im Snapshot"
        else:
            label = c_name
            note = f"im Snapshot: {s_name}" if s_name != c_name else ""
        rows.append(CompareRow(label, [window_sum(s_vals, r) for r in ranges],
                               [window_sum(c_vals, r) for r in ranges], indent=1, note=note))
    return rows
