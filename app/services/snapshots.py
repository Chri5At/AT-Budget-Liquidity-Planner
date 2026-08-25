"""Snapshots — save the full plan, restore it, or compare its KPIs to the current one.

A snapshot serialises every *source* table to JSON (the derived CashflowEntry cache
is rebuilt, never stored). Comparison loads the snapshot into a throwaway in-memory
database and runs the same engines on it, so the figures are computed identically.
"""
from __future__ import annotations

import json
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


def compute_kpis(session: Session, year: int, scenario_id: int = 1) -> dict[str, float]:
    """Key figures for one (year, scenario), computed by the real engines."""
    from ..engine.pnl import pnl_view
    from ..engine.liquidity import liquidity_view_for_scenario

    rows = pnl_view(session, year, scenario_id)

    def annual(part: str) -> float:
        r = next((r for r in rows if part in r.label), None)
        return round(r.annual) if r else 0.0

    liq = liquidity_view_for_scenario(session, scenario_id)
    low = round(min((r.balance for r in liq), default=0.0))
    end = round(liq[-1].balance) if liq else 0.0
    return {
        "Umsatzerlöse": annual("Umsatzerlöse gesamt"),
        "Deckungsbeitrag I": annual("Deckungsbeitrag I"),
        "Personalaufwand intern": -annual("Personalaufwand intern"),
        "Deckungsbeitrag II": annual("Deckungsbeitrag II"),
        "EBITDA": annual("EBITDA"),
        "EBIT": annual("= EBIT"),
        "EBT": annual("EBT"),
        "Tiefststand Liquidität": low,
        "Endsaldo Liquidität": end,
    }


def snapshot_kpis(snapshot: Snapshot, year: int, scenario_id: int = 1) -> dict[str, float]:
    sess = _temp_session(snapshot.payload)
    try:
        return compute_kpis(sess, year, scenario_id)
    finally:
        sess.close()
