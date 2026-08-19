"""Resolve which revenue/cost rows are *effective* for a given scenario.

Delta model: a child scenario inherits all of its base's rows, minus the ones it
disabled (ScenarioDisable), plus its own added rows (tagged with its scenario_id).
The base scenario simply owns the rows tagged with its id.
"""
from __future__ import annotations

from sqlmodel import Session, select

from ..models import (
    CostCategory,
    CostCellEntry,
    CostPlanMonth,
    RevenueCellEntry,
    RevenuePlanMonth,
    RevenueStream,
    Scenario,
    ScenarioDisable,
)

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


def _fork_rows(session: Session, sc_id: int, base_id: int, model, plan_model,
               plan_fk: str, cell_model, cell_fk: str, ref_kind: str) -> None:
    """Deep-copy every base row (+ plan months + cell breakdowns) into the new
    scenario, remapping parent_id, then disable the base rows so they don't also
    inherit (avoids double-counting). The scenario becomes an independent copy."""
    base_rows = [r for r in session.exec(select(model).order_by(
        model.sort_order, model.id)).all() if r.scenario_id == base_id]
    id_map: dict[int, int] = {}
    for r in base_rows:
        data = r.model_dump(exclude={"id"})
        data["scenario_id"] = sc_id
        data["parent_id"] = None                      # remapped in the second pass
        copy = model(**data)
        session.add(copy)
        session.flush()                               # assign copy.id
        id_map[r.id] = copy.id
        for p in session.exec(select(plan_model).where(getattr(plan_model, plan_fk) == r.id)).all():
            pd = p.model_dump(exclude={"id"})
            pd[plan_fk] = copy.id
            session.add(plan_model(**pd))
        for c in session.exec(select(cell_model).where(getattr(cell_model, cell_fk) == r.id)).all():
            cd = c.model_dump(exclude={"id"})
            cd[cell_fk] = copy.id
            # A scenario is an independent copy, so contract-generated lines become
            # ordinary lines here: the contract keeps driving its own (base) row,
            # while the scenario's copy stays editable instead of being wiped by the
            # next run of the generator.
            if "contract_id" in cd:
                cd["contract_id"] = None
            session.add(cell_model(**cd))
    for r in base_rows:
        if r.parent_id and r.parent_id in id_map:
            copy = session.get(model, id_map[r.id])
            copy.parent_id = id_map[r.parent_id]
            session.add(copy)
        session.add(ScenarioDisable(scenario_id=sc_id, ref_kind=ref_kind, ref_id=r.id))
    session.commit()


def create_scenario(session: Session, name: str, base_id: int = BASE_SCENARIO_ID) -> Scenario:
    order = max([s.sort_order for s in list_scenarios(session)], default=0) + 1
    sc = Scenario(name=name, base_id=base_id, sort_order=order)
    session.add(sc)
    session.commit()
    session.refresh(sc)
    # Fork: the scenario gets its own independent, editable copy of all base rows.
    _fork_rows(session, sc.id, base_id, RevenueStream, RevenuePlanMonth, "stream_id",
               RevenueCellEntry, "stream_id", "revenue")
    _fork_rows(session, sc.id, base_id, CostCategory, CostPlanMonth, "category_id",
               CostCellEntry, "category_id", "cost")
    return sc


def delete_scenario(session: Session, scenario_id: int) -> None:
    """Delete a child scenario plus its added rows and disable markers."""
    if scenario_id == BASE_SCENARIO_ID:
        return
    for sd in session.exec(select(ScenarioDisable).where(
            ScenarioDisable.scenario_id == scenario_id)).all():
        session.delete(sd)
    for row in session.exec(select(RevenueStream).where(
            RevenueStream.scenario_id == scenario_id)).all():
        for pm in session.exec(select(RevenuePlanMonth).where(
                RevenuePlanMonth.stream_id == row.id)).all():
            session.delete(pm)
        for ce in session.exec(select(RevenueCellEntry).where(
                RevenueCellEntry.stream_id == row.id)).all():
            session.delete(ce)
        session.delete(row)
    for row in session.exec(select(CostCategory).where(
            CostCategory.scenario_id == scenario_id)).all():
        for pm in session.exec(select(CostPlanMonth).where(
                CostPlanMonth.category_id == row.id)).all():
            session.delete(pm)
        for ce in session.exec(select(CostCellEntry).where(
                CostCellEntry.category_id == row.id)).all():
            session.delete(ce)
        session.delete(row)
    sc = session.get(Scenario, scenario_id)
    if sc is not None:
        session.delete(sc)
    session.commit()
