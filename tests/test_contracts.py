"""Verträge & Abos: due-date series, generated cost cells, and the term logic.

The generator has to be idempotent (recompute runs on every save) and must never
touch a hand-entered line — those two properties carry most of the tests here.
"""
from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.engine.contracts import (
    annual_total,
    cancellation_deadline,
    due_dates,
    generate_contract_cells,
    monthly_equiv,
    next_due,
    renewal_date,
    shift_months,
    traffic_light,
)
from app.models import (
    BillingCycle,
    Contract,
    ContractStatus,
    CostCategory,
    CostCellEntry,
    CostPlanMonth,
    PnlLine,
    Settings,
    SplitModel,
)

HORIZON_START = date(2026, 1, 1)
HORIZON_END = date(2027, 12, 31)


def _session() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    s = Session(eng)
    s.add(Settings(id=1, split_model=SplitModel.FIXED_PCT, abgaben_pct=0.30,
                   employer_burden_pct=0.30, opening_balance=0.0,
                   horizon_start=HORIZON_START, horizon_end=HORIZON_END))
    s.commit()
    return s


def _category(s: Session, name: str = "Versicherungen") -> CostCategory:
    cat = CostCategory(name=name, pnl_line=PnlLine.OPEX, is_vatable=False)
    s.add(cat)
    s.commit()
    s.refresh(cat)
    return cat


def _contract(s: Session, category: CostCategory, **kw) -> Contract:
    data = dict(name="Drohnen-Haftpflicht", partner="R+V", category_id=category.id,
                amount=321.90, cycle=BillingCycle.YEARLY, start=date(2026, 8, 19),
                notice_months=3)
    data.update(kw)
    c = Contract(**data)
    s.add(c)
    s.commit()
    s.refresh(c)
    return c


def _cells(s: Session, category_id: int) -> dict[tuple[int, int], float]:
    return {(p.year, p.month): round(p.amount, 2)
            for p in s.exec(select(CostPlanMonth).where(
                CostPlanMonth.category_id == category_id)).all() if p.amount}


def _lines(s: Session) -> list[CostCellEntry]:
    return list(s.exec(select(CostCellEntry).order_by(
        CostCellEntry.year, CostCellEntry.month, CostCellEntry.sort_order)).all())


# --- 1. due-date series ----------------------------------------------------

def test_monthly_series_covers_every_month_of_the_horizon():
    s = _session()
    c = _contract(s, _category(s), cycle=BillingCycle.MONTHLY, start=date(2026, 1, 15))
    dues = due_dates(c, HORIZON_START, HORIZON_END)
    assert len(dues) == 24
    assert dues[0] == date(2026, 1, 15) and dues[-1] == date(2027, 12, 15)


def test_quarterly_and_yearly_and_once():
    s = _session()
    cat = _category(s)
    quarterly = _contract(s, cat, cycle=BillingCycle.QUARTERLY, start=date(2026, 2, 1))
    assert due_dates(quarterly, HORIZON_START, HORIZON_END) == [
        date(2026, 2, 1), date(2026, 5, 1), date(2026, 8, 1), date(2026, 11, 1),
        date(2027, 2, 1), date(2027, 5, 1), date(2027, 8, 1), date(2027, 11, 1)]

    yearly = _contract(s, cat, cycle=BillingCycle.YEARLY, start=date(2026, 8, 19))
    assert due_dates(yearly, HORIZON_START, HORIZON_END) == [
        date(2026, 8, 19), date(2027, 8, 19)]

    semi = _contract(s, cat, cycle=BillingCycle.SEMIANNUAL, start=date(2026, 3, 31))
    assert due_dates(semi, HORIZON_START, HORIZON_END) == [
        date(2026, 3, 31), date(2026, 9, 30), date(2027, 3, 31), date(2027, 9, 30)]

    once = _contract(s, cat, cycle=BillingCycle.ONCE, start=date(2026, 6, 10))
    assert due_dates(once, HORIZON_START, HORIZON_END) == [date(2026, 6, 10)]


def test_first_due_overrides_the_start_and_end_caps_the_series():
    s = _session()
    cat = _category(s)
    c = _contract(s, cat, cycle=BillingCycle.MONTHLY, start=date(2026, 1, 1),
                  first_due=date(2026, 4, 5), end=date(2026, 7, 31))
    assert due_dates(c, HORIZON_START, HORIZON_END) == [
        date(2026, 4, 5), date(2026, 5, 5), date(2026, 6, 5), date(2026, 7, 5)]


def test_dates_outside_the_horizon_are_dropped_on_both_ends():
    s = _session()
    cat = _category(s)
    # Starts two years before the horizon and runs beyond it.
    c = _contract(s, cat, cycle=BillingCycle.YEARLY, start=date(2024, 5, 20))
    assert due_dates(c, HORIZON_START, HORIZON_END) == [
        date(2026, 5, 20), date(2027, 5, 20)]
    # Entirely after the horizon.
    later = _contract(s, cat, cycle=BillingCycle.ONCE, start=date(2029, 1, 1))
    assert due_dates(later, HORIZON_START, HORIZON_END) == []


def test_month_end_days_are_clamped_not_dropped():
    assert shift_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert shift_months(date(2028, 1, 31), 1) == date(2028, 2, 29)   # leap year
    # Clamping never shrinks the series: every step is measured from the anchor.
    s = _session()
    c = _contract(s, _category(s), cycle=BillingCycle.MONTHLY, start=date(2026, 1, 31))
    dues = due_dates(c, HORIZON_START, date(2026, 4, 30))
    assert dues == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


# --- 2. generator: cells, idempotency, manual lines -------------------------

def test_generator_writes_one_cell_per_due_date():
    s = _session()
    cat = _category(s)
    _contract(s, cat)                       # 321,90 € yearly, 19.08.
    written = generate_contract_cells(s)

    assert written == 2
    assert _cells(s, cat.id) == {(2026, 8): 321.90, (2027, 8): 321.90}
    assert all(line.contract_id is not None for line in _lines(s))


def test_generating_twice_changes_nothing():
    s = _session()
    cat = _category(s)
    _contract(s, cat)
    generate_contract_cells(s)
    before = [(line.category_id, line.year, line.month, line.amount, line.note)
              for line in _lines(s)]

    generate_contract_cells(s)

    after = [(line.category_id, line.year, line.month, line.amount, line.note)
             for line in _lines(s)]
    assert after == before
    assert _cells(s, cat.id) == {(2026, 8): 321.90, (2027, 8): 321.90}


def test_manual_line_in_the_same_cell_survives_and_is_summed():
    s = _session()
    cat = _category(s)
    s.add(CostCellEntry(category_id=cat.id, year=2026, month=8, amount=100.0,
                        note="Selbstbehalt"))
    s.commit()
    _contract(s, cat)

    generate_contract_cells(s)
    generate_contract_cells(s)              # twice — must not duplicate or drop anything

    manual = [line for line in _lines(s) if line.contract_id is None]
    assert [(m.amount, m.note) for m in manual] == [(100.0, "Selbstbehalt")]
    assert _cells(s, cat.id)[(2026, 8)] == 421.90


def test_a_typed_cell_value_is_kept_as_a_manual_line():
    """Typing 50 € into the grid and then adding a contract must not lose the 50 €."""
    s = _session()
    cat = _category(s)
    s.add(CostPlanMonth(category_id=cat.id, year=2026, month=8, amount=50.0))
    s.commit()
    _contract(s, cat)

    generate_contract_cells(s)

    manual = [line for line in _lines(s) if line.contract_id is None]
    assert [m.amount for m in manual] == [50.0]
    assert _cells(s, cat.id)[(2026, 8)] == 371.90


def test_deleting_the_contract_removes_its_cells_only():
    s = _session()
    cat = _category(s)
    s.add(CostCellEntry(category_id=cat.id, year=2026, month=8, amount=100.0, note="manuell"))
    s.commit()
    contract = _contract(s, cat)
    generate_contract_cells(s)

    s.delete(contract)
    s.commit()
    generate_contract_cells(s)

    assert [line.note for line in _lines(s)] == ["manuell"]
    assert _cells(s, cat.id) == {(2026, 8): 100.0}


def test_a_cell_falls_back_to_zero_when_the_contract_is_gone():
    s = _session()
    cat = _category(s)
    contract = _contract(s, cat)
    generate_contract_cells(s)
    assert _cells(s, cat.id)

    s.delete(contract)
    s.commit()
    generate_contract_cells(s)

    assert _cells(s, cat.id) == {}
    assert _lines(s) == []


def test_a_group_row_is_never_a_generation_target():
    s = _session()
    group = _category(s, "Fixkosten")
    group.is_category = True
    s.add(group)
    s.commit()
    _contract(s, group)

    assert generate_contract_cells(s) == 0


# --- 3. status ------------------------------------------------------------

@pytest.mark.parametrize("status", [ContractStatus.PAUSED, ContractStatus.TRIAL])
def test_paused_and_trial_generate_nothing(status):
    s = _session()
    cat = _category(s)
    _contract(s, cat, status=status)
    assert generate_contract_cells(s) == 0
    assert _cells(s, cat.id) == {}


def test_cancelled_keeps_paying_until_its_end_date():
    s = _session()
    cat = _category(s)
    _contract(s, cat, cycle=BillingCycle.MONTHLY, start=date(2026, 1, 10),
              status=ContractStatus.CANCELLED, end=date(2026, 3, 31))

    generate_contract_cells(s)

    assert _cells(s, cat.id) == {(2026, 1): 321.90, (2026, 2): 321.90, (2026, 3): 321.90}


def test_cancelled_without_an_end_date_generates_nothing():
    s = _session()
    cat = _category(s)
    _contract(s, cat, status=ContractStatus.CANCELLED)
    assert generate_contract_cells(s) == 0


# --- 4. renewal, cancellation deadline, traffic light ----------------------

def test_renewal_is_the_next_anniversary_of_the_start():
    s = _session()
    c = _contract(s, _category(s))          # start 19.08.2026
    assert renewal_date(c, date(2026, 8, 19)) == date(2026, 8, 19)   # today counts
    assert renewal_date(c, date(2026, 8, 20)) == date(2027, 8, 19)
    assert renewal_date(c, date(2027, 1, 1)) == date(2027, 8, 19)


def test_explicit_renewal_day_and_month_win_over_the_start():
    s = _session()
    c = _contract(s, _category(s), renewal_day=1, renewal_month=10)
    assert renewal_date(c, date(2026, 9, 1)) == date(2026, 10, 1)


def test_cancellation_deadline_is_the_renewal_minus_the_notice_period():
    s = _session()
    c = _contract(s, _category(s))          # 19.08., 3 months' notice
    assert cancellation_deadline(c, date(2026, 8, 20)) == date(2027, 5, 19)


def test_cancellation_deadline_handles_month_end_edge_cases():
    s = _session()
    cat = _category(s)
    # 31.05. minus 3 months = 28.02. (the day is clamped, not rolled over).
    c = _contract(s, cat, start=date(2026, 5, 31), notice_months=3)
    assert cancellation_deadline(c, date(2026, 6, 1)) == date(2027, 2, 28)
    # 31.03. minus 1 month = 28.02.2027.
    c2 = _contract(s, cat, start=date(2026, 3, 31), notice_months=1)
    assert cancellation_deadline(c2, date(2026, 4, 1)) == date(2027, 2, 28)
    # No notice period at all → the deadline is the renewal date itself.
    c3 = _contract(s, cat, start=date(2026, 3, 31), notice_months=0)
    assert cancellation_deadline(c3, date(2026, 4, 1)) == date(2027, 3, 31)


def test_traffic_light_thresholds():
    s = _session()
    cat = _category(s)
    c = _contract(s, cat, start=date(2026, 8, 19), notice_months=3)
    deadline = cancellation_deadline(c, date(2026, 8, 20))     # 19.05.2027
    assert traffic_light(c, deadline.replace(day=18)) == "red"          # 1 day left
    assert traffic_light(c, date(2027, 3, 25)) == "red"                 # 55 days
    assert traffic_light(c, date(2027, 3, 15)) == "yellow"              # 65 days
    assert traffic_light(c, date(2027, 1, 20)) == "yellow"              # 119 days
    assert traffic_light(c, date(2027, 1, 19)) == "green"               # 120 days exactly
    assert traffic_light(c, date(2026, 12, 1)) == "green"               # 169 days


def test_traffic_light_is_grey_without_supervision():
    s = _session()
    cat = _category(s)
    assert traffic_light(_contract(s, cat, status=ContractStatus.PAUSED),
                         date(2026, 1, 1)) == "grey"
    assert traffic_light(_contract(s, cat, auto_renew=False), date(2026, 1, 1)) == "grey"
    assert traffic_light(_contract(s, cat, cycle=BillingCycle.ONCE),
                         date(2026, 1, 1)) == "grey"


def test_next_due_is_the_first_date_from_today():
    s = _session()
    cat = _category(s)
    c = _contract(s, cat, cycle=BillingCycle.QUARTERLY, start=date(2026, 1, 15))
    assert next_due(c, date(2026, 1, 1)) == date(2026, 1, 15)
    assert next_due(c, date(2026, 1, 15)) == date(2026, 1, 15)
    assert next_due(c, date(2026, 1, 16)) == date(2026, 4, 15)
    # Past the end date there is nothing left to pay.
    ended = _contract(s, cat, cycle=BillingCycle.MONTHLY, start=date(2026, 1, 1),
                      end=date(2026, 3, 31))
    assert next_due(ended, date(2026, 5, 1)) is None


# --- 5. normalisation ------------------------------------------------------

@pytest.mark.parametrize("cycle, monthly, annual", [
    (BillingCycle.MONTHLY, 120.0, 1440.0),
    (BillingCycle.QUARTERLY, 40.0, 480.0),
    (BillingCycle.SEMIANNUAL, 20.0, 240.0),
    (BillingCycle.YEARLY, 10.0, 120.0),
    (BillingCycle.ONCE, 0.0, 0.0),
])
def test_monthly_and_annual_normalisation(cycle, monthly, annual):
    s = _session()
    c = _contract(s, _category(s), cycle=cycle, amount=120.0)
    assert monthly_equiv(c) == pytest.approx(monthly)
    assert annual_total(c) == pytest.approx(annual)


# --- 6. snapshots ---------------------------------------------------------

def test_snapshot_roundtrip_keeps_contracts_and_their_cells():
    """A snapshot restore must not wipe the contract register (or its cells)."""
    from app.services.snapshots import create_snapshot, restore_snapshot

    s = _session()
    cat = _category(s)
    _contract(s, cat)
    generate_contract_cells(s)
    snapshot = create_snapshot(s, "mit Verträgen")

    # Someone deletes the contract afterwards…
    for contract in s.exec(select(Contract)).all():
        s.delete(contract)
    s.commit()
    generate_contract_cells(s)
    assert _cells(s, cat.id) == {}

    # …and restores the snapshot.
    assert restore_snapshot(s, snapshot.id) is True

    restored = list(s.exec(select(Contract)).all())
    assert [(c.name, c.amount, c.contract_no) for c in restored] == \
           [("Drohnen-Haftpflicht", 321.90, "")]
    assert restored[0].start == date(2026, 8, 19)
    category_id = restored[0].category_id
    assert _cells(s, category_id) == {(2026, 8): 321.90, (2027, 8): 321.90}
    assert all(line.contract_id == restored[0].id for line in _lines(s))


# --- 7. the ordinary pipeline picks the generated cells up -----------------

def test_a_contract_flows_through_pnl_and_liquidity_like_any_cost():
    from app.config import VAT_RATE
    from app.engine.cashflow import build_cashflows
    from app.engine.pnl import pnl_view
    from app.models import CashflowEntry, CashflowKind, PaymentTerm

    s = _session()
    cat = _category(s)
    cat.is_vatable = True
    cat.payment_term = PaymentTerm.SOFORT
    s.add(cat)
    s.commit()
    _contract(s, cat)                       # 321,90 € yearly, due 19.08.

    generate_contract_cells(s)
    build_cashflows(s)

    # P&L: the premium hits the month it is due, nothing is spread over the year.
    ebitda = next(r for r in pnl_view(s, 2026) if "EBITDA" in r.label).values
    assert round(ebitda[7], 2) == -321.90                    # August
    assert all(round(v, 2) == 0.0 for i, v in enumerate(ebitda) if i != 7)

    # Liquidity: paid gross at the category's payment term, VAT reclaimed later.
    entries = list(s.exec(select(CashflowEntry)).all())
    out = [e for e in entries if e.kind == CashflowKind.COST_OUT and e.date.year == 2026]
    vat = [e for e in entries if e.kind == CashflowKind.AUTHORITY_VAT and e.date.year == 2026]
    assert len(out) == 1
    assert round(out[0].amount, 2) == -round(321.90 * (1 + VAT_RATE), 2)
    assert out[0].date == date(2026, 8, 31)                  # month end, a Monday
    assert round(vat[0].amount, 2) == round(321.90 * VAT_RATE, 2)
    # 2026 nets out to the two premiums (2026 + 2027 VAT settles in 2027/2028).
    assert round(sum(e.amount for e in entries), 2) == -round(321.90 * 2, 2)


# --- 8. additive JSON import ----------------------------------------------

def test_importing_the_prepared_contracts_file_adds_them_without_touching_the_plan():
    """The shipped .vibe/08-initial-contracts.json must import as-is."""
    from pathlib import Path

    from app.services.contracts_io import import_contracts, read_contracts_payload

    s = _session()
    keep = _category(s, "Miete")
    s.add(CostPlanMonth(category_id=keep.id, year=2026, month=1, amount=1200.0))
    s.commit()

    prepared = Path(__file__).resolve().parent.parent / ".vibe" / "08-initial-contracts.json"
    if not prepared.exists():
        pytest.skip(".vibe is a local working folder and not part of the repository")
    raw = prepared.read_bytes()
    imported, skipped = import_contracts(s, read_contracts_payload(raw))
    assert (imported, skipped) == (2, 0)

    # The target cost row was created from the _category_name hint.
    insurance = s.exec(select(CostCategory).where(
        CostCategory.name == "Versicherungen")).first()
    assert insurance is not None

    generate_contract_cells(s)
    assert _cells(s, insurance.id) == {(2026, 8): 643.80, (2027, 8): 643.80}
    # The unrelated plan row is untouched.
    assert _cells(s, keep.id) == {(2026, 1): 1200.0}

    # Importing the same file twice does not duplicate anything.
    assert import_contracts(s, read_contracts_payload(raw)) == (0, 2)


def test_import_falls_back_to_the_chosen_category_and_rejects_junk():
    import pytest as _pytest

    from app.services.contracts_io import import_contracts, read_contracts_payload

    s = _session()
    cat = _category(s)
    rows = [{"name": "Hosting", "amount": 11.5, "cycle": "monatlich", "start": "2026-01-01"},
            {"name": "Ohne Startdatum", "amount": 5.0}]
    imported, skipped = import_contracts(s, rows, default_category_id=cat.id)
    assert (imported, skipped) == (1, 1)
    assert s.exec(select(Contract)).first().category_id == cat.id

    with _pytest.raises(ValueError):
        read_contracts_payload(b"not json at all")
    with _pytest.raises(ValueError):
        read_contracts_payload(b'{"Settings": []}')


def test_contracts_are_part_of_the_backup_payload():
    """Export/import go through the snapshot payload — contracts must be in it."""
    import json

    from app.services.snapshots import dump_all, replace_all_from_payload

    s = _session()
    _contract(s, _category(s))
    payload = dump_all(s)
    assert json.loads(payload)["Contract"][0]["name"] == "Drohnen-Haftpflicht"

    target = _session()
    replace_all_from_payload(target, payload)
    restored = list(target.exec(select(Contract)).all())
    assert [c.name for c in restored] == ["Drohnen-Haftpflicht"]
    assert _cells(target, restored[0].category_id) == {(2026, 8): 321.90, (2027, 8): 321.90}


def test_a_passed_deadline_rolls_on_to_the_next_renewal():
    """On the renewal day itself the notice window is gone — show the next one."""
    s = _session()
    c = _contract(s, _category(s))          # start/renewal 19.08., 3 months' notice
    assert cancellation_deadline(c, date(2026, 8, 19)) == date(2027, 5, 19)
    assert traffic_light(c, date(2026, 8, 19)) == "green"
