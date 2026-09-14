"""Snapshot comparison: KPIs must respect the chosen year/period, streams match by id."""
from datetime import date

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.engine.liquidity import liquidity_view_for_scenario
from app.models import RevenuePlanMonth, RevenueStream, Settings, SplitModel
from app.services.snapshots import (
    compare_rows,
    compute_kpis,
    create_snapshot,
    period_ranges,
    plan_figures,
    snapshot_figures,
)


def _session() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    s = Session(eng)
    s.add(Settings(id=1, split_model=SplitModel.FIXED_PCT, abgaben_pct=0.30,
                   employer_burden_pct=0.30, opening_balance=10_000.0,
                   opening_balance_date=date(2026, 1, 1),
                   horizon_start=date(2026, 1, 1), horizon_end=date(2027, 12, 31)))
    st = RevenueStream(name="Alt")
    s.add(st)
    s.commit()
    s.refresh(st)
    # 1.000 €/month in 2026, 5.000 €/month in 2027 → the balance keeps climbing, so the
    # horizon-wide end/low differ from the 2026 ones.
    for y, amt in ((2026, 1000.0), (2027, 5000.0)):
        for m in range(1, 13):
            s.add(RevenuePlanMonth(stream_id=st.id, year=y, month=m, amount=amt))
    s.commit()
    return s


def test_liquidity_kpis_use_the_selected_year_not_the_horizon_end():
    s = _session()
    liq = liquidity_view_for_scenario(s, 1)
    in_2026 = [b for b in liq if b.bucket.year == 2026]

    k = compute_kpis(s, 2026)
    assert k["Endsaldo Liquidität"] == round(in_2026[-1].balance)
    assert k["Tiefststand Liquidität"] == round(min(b.balance for b in in_2026))
    # …and NOT the last / lowest bucket of the whole planning horizon.
    assert k["Endsaldo Liquidität"] != round(liq[-1].balance)
    assert compute_kpis(s, 2027)["Endsaldo Liquidität"] == round(liq[-1].balance)


def test_period_windows_sum_to_the_year():
    s = _session()
    fig = plan_figures(s, 2026)
    from app.services.snapshots import kpis
    quarters = [kpis(fig, r) for _, r in period_ranges("quarter", 2026)]
    assert [q["Umsatzerlöse"] for q in quarters] == [3000, 3000, 3000, 3000]
    assert sum(q["Umsatzerlöse"] for q in quarters) == kpis(fig)["Umsatzerlöse"]
    months = [kpis(fig, r) for _, r in period_ranges("month", 2026)]
    assert len(months) == 12 and all(m["Umsatzerlöse"] == 1000 for m in months)
    # Endsaldo of Q4 is the year-end balance; the March low is within Q1.
    assert quarters[3]["Endsaldo Liquidität"] == kpis(fig)["Endsaldo Liquidität"]
    liq = [b for b in fig.liquidity if b.bucket.year == 2026 and b.bucket.month <= 3]
    assert quarters[0]["Tiefststand Liquidität"] == round(min(b.balance for b in liq))


def test_renamed_and_new_streams_are_matched_by_id():
    s = _session()
    snap = create_snapshot(s, "vorher")
    old = s.exec(__import__("sqlmodel").select(RevenueStream)).first()
    old.name = "Neu"
    s.add(old)
    new = RevenueStream(name="Zusatz")
    s.add(new)
    s.commit()
    s.refresh(new)
    s.add(RevenuePlanMonth(stream_id=new.id, year=2026, month=6, amount=250.0))
    s.commit()

    rows = compare_rows(plan_figures(s, 2026), snapshot_figures(snap, 2026), [(1, 12)])
    by_label = {r.label: r for r in rows}
    renamed = by_label["Neu"]
    assert renamed.indent == 1 and renamed.note == "im Snapshot: Alt"
    assert renamed.snap == [12000] and renamed.cur == [12000]
    added = by_label["Zusatz"]
    assert added.note == "neu, nicht im Snapshot" and added.snap == [0] and added.cur == [250]
    total = by_label["Umsatzerlöse"]
    assert total.indent == 0 and total.diff == [250]
