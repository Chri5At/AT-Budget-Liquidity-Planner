"""Resolve which revenue/cost rows are *effective* for a given scenario.

Delta model: a child scenario inherits all of its base's rows, minus the ones it
disabled (ScenarioDisable), plus its own added rows (tagged with its scenario_id).
The base scenario simply owns the rows tagged with its id.
"""
from __future__ import annotations

from sqlmodel import Session, select

from ..models import CostCategory, RevenueStream, Scenario, ScenarioDisable

BASE_SCENARIO_ID = 1


def get_scenario(session: Session, scenario_id: int) -> Scenario:
    sc = session.get(Scenario, scenario_id)
    if sc is None:
        sc = session.get(Scenario, BASE_SCENARIO_ID)
    if sc is None:
        # Bare DB (e.g. a unit test) without a seeded base scenario — treat as base.
        sc = Scenario(id=BASE_SCENARIO_ID, name="Basis", base_id=None)
    return sc


def _base_id(scenario: Scenario) -> int:
    return scenario.base_id if scenario.base_id is not None else scenario.id


def _disabled_ids(session: Session, scenario: Scenario, ref_kind: str) -> set[int]:
    if scenario.base_id is None:
        return set()
    return {d.ref_id for d in session.exec(
        select(ScenarioDisable).where(ScenarioDisable.scenario_id == scenario.id,
                                      ScenarioDisable.ref_kind == ref_kind)).all()}


def _effective_ids(session: Session, scenario: Scenario, model, ref_kind: str) -> set[int]:
    base_id = _base_id(scenario)
    disabled = _disabled_ids(session, scenario, ref_kind)
    ids: set[int] = set()
    for row in session.exec(select(model)).all():
        if row.scenario_id == base_id and row.id not in disabled:
            ids.add(row.id)                       # inherited base row, still active
        elif scenario.base_id is not None and row.scenario_id == scenario.id:
            ids.add(row.id)                       # row added by this child scenario
    return ids


def effective_revenue_ids(session: Session, scenario: Scenario) -> set[int]:
    return _effective_ids(session, scenario, RevenueStream, "revenue")


def effective_cost_ids(session: Session, scenario: Scenario) -> set[int]:
    return _effective_ids(session, scenario, CostCategory, "cost")


# --- management helpers (used by the UI) -----------------------------------------

def list_scenarios(session: Session) -> list[Scenario]:
    return session.exec(select(Scenario).order_by(Scenario.sort_order, Scenario.id)).all()


def base_owned_rows(session: Session, scenario: Scenario, model):
    """Rows owned by this scenario's base (the ones a child inherits/can toggle)."""
    base_id = _base_id(scenario)
    return [r for r in session.exec(select(model).order_by(model.sort_order, model.id)).all()
            if r.scenario_id == base_id]


def is_disabled(session: Session, scenario_id: int, ref_kind: str, ref_id: int) -> bool:
    return session.exec(select(ScenarioDisable).where(
        ScenarioDisable.scenario_id == scenario_id, ScenarioDisable.ref_kind == ref_kind,
        ScenarioDisable.ref_id == ref_id)).first() is not None


def set_disabled(session: Session, scenario_id: int, ref_kind: str, ref_id: int,
                 disabled: bool) -> None:
    existing = session.exec(select(ScenarioDisable).where(
        ScenarioDisable.scenario_id == scenario_id, ScenarioDisable.ref_kind == ref_kind,
        ScenarioDisable.ref_id == ref_id)).first()
    if disabled and existing is None:
        session.add(ScenarioDisable(scenario_id=scenario_id, ref_kind=ref_kind, ref_id=ref_id))
    elif not disabled and existing is not None:
        session.delete(existing)
    session.commit()


def create_scenario(session: Session, name: str, base_id: int = BASE_SCENARIO_ID) -> Scenario:
    order = max([s.sort_order for s in list_scenarios(session)], default=0) + 1
    sc = Scenario(name=name, base_id=base_id, sort_order=order)
    session.add(sc)
    session.commit()
    session.refresh(sc)
    return sc


def delete_scenario(session: Session, scenario_id: int) -> None:
    """Delete a child scenario plus its added rows and disable markers."""
    if scenario_id == BASE_SCENARIO_ID:
        return
    for sd in session.exec(select(ScenarioDisable).where(
            ScenarioDisable.scenario_id == scenario_id)).all():
        session.delete(sd)
    from ..models import CostPlanMonth, RevenuePlanMonth
    for row in session.exec(select(RevenueStream).where(
            RevenueStream.scenario_id == scenario_id)).all():
        for pm in session.exec(select(RevenuePlanMonth).where(
                RevenuePlanMonth.stream_id == row.id)).all():
            session.delete(pm)
        session.delete(row)
    for row in session.exec(select(CostCategory).where(
            CostCategory.scenario_id == scenario_id)).all():
        for pm in session.exec(select(CostPlanMonth).where(
                CostPlanMonth.category_id == row.id)).all():
            session.delete(pm)
        session.delete(row)
    sc = session.get(Scenario, scenario_id)
    if sc is not None:
        session.delete(sc)
    session.commit()
