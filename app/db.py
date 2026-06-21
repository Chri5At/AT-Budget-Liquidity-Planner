"""Database engine, initialisation and small session helpers."""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from .config import DB_URL
from .models import Settings  # noqa: F401  (ensures all tables are imported/registered)
from . import models as _models  # noqa: F401

engine = create_engine(DB_URL, echo=False)


def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    insp = inspect(conn)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if column not in cols:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _migrate() -> bool:
    """Tiny additive migrations for SQLite (create_all never ALTERs existing tables).

    Returns True if the SalaryMonth.special column was just added (so the caller
    can split previously-doubled Jun/Nov salaries into ongoing + Sonderzahlung).
    """
    added_special = False
    with engine.begin() as conn:
        _add_column_if_missing(conn, "settings", "seeded", "seeded BOOLEAN DEFAULT 0")
        # Scenario support: existing revenue/cost rows belong to the base scenario (id=1).
        _add_column_if_missing(conn, "revenuestream", "scenario_id",
                               "scenario_id INTEGER DEFAULT 1")
        _add_column_if_missing(conn, "costcategory", "scenario_id",
                               "scenario_id INTEGER DEFAULT 1")
        # Flexible payment term in days (overrides the PaymentTerm enum when set).
        _add_column_if_missing(conn, "revenuestream", "payment_days", "payment_days INTEGER")
        # Revenue category grouping (UI only).
        _add_column_if_missing(conn, "revenuestream", "is_category",
                               "is_category BOOLEAN DEFAULT 0")
        _add_column_if_missing(conn, "revenuestream", "parent_id", "parent_id INTEGER")
        _add_column_if_missing(conn, "revenuestream", "color", "color VARCHAR DEFAULT ''")
        # Per-cell note + colour for the Einnahmen grid.
        _add_column_if_missing(conn, "revenueplanmonth", "note", "note VARCHAR DEFAULT ''")
        _add_column_if_missing(conn, "revenueplanmonth", "color", "color VARCHAR DEFAULT ''")
        # Produkt line-item payment routine (liquidity timing).
        _add_column_if_missing(conn, "revenuecellentry", "pay_routine",
                               "pay_routine VARCHAR DEFAULT 'on_delivery'")
        _add_column_if_missing(conn, "revenuecellentry", "payment_days", "payment_days INTEGER")
        _add_column_if_missing(conn, "revenuecellentry", "deposit_is_pct",
                               "deposit_is_pct BOOLEAN DEFAULT 1")
        _add_column_if_missing(conn, "revenuecellentry", "deposit_value",
                               "deposit_value FLOAT DEFAULT 0")
        _add_column_if_missing(conn, "revenuecellentry", "rate_count", "rate_count INTEGER DEFAULT 0")
        _add_column_if_missing(conn, "revenuecellentry", "rate_months", "rate_months INTEGER DEFAULT 0")
        # Projekt (inspection) line extras: income fixed fee + subcontractor cost/terms.
        _add_column_if_missing(conn, "revenuecellentry", "fixed_fee", "fixed_fee FLOAT DEFAULT 0")
        _add_column_if_missing(conn, "revenuecellentry", "sub_rate", "sub_rate FLOAT DEFAULT 0")
        _add_column_if_missing(conn, "revenuecellentry", "sub_fixed", "sub_fixed FLOAT DEFAULT 0")
        _add_column_if_missing(conn, "revenuecellentry", "sub_days", "sub_days INTEGER")
        if "salarymonth" in inspect(conn).get_table_names():
            cols = {c["name"] for c in inspect(conn).get_columns("salarymonth")}
            if "special" not in cols:
                conn.execute(text("ALTER TABLE salarymonth ADD COLUMN special FLOAT DEFAULT 0"))
                added_special = True
    return added_special


def _split_doubled_salaries() -> None:
    """One-off: convert old 'doubled Jun/Nov gross' rows into ongoing + Sonderzahlung.

    Detects the doubling (month gross ≈ 2× the employee's typical monthly gross) and
    moves the extra month into `special`. Idempotent once split.
    """
    from collections import Counter
    from .models import SalaryMonth
    with Session(engine) as s:
        rows = list(s.exec(select(SalaryMonth)).all())
        by_emp_year: dict = {}
        for sm in rows:
            by_emp_year.setdefault((sm.employee_id, sm.year), []).append(sm)
        for group in by_emp_year.values():
            if any(sm.special for sm in group):
                continue  # already split
            grosses = [sm.gross for sm in group if sm.gross]
            if not grosses:
                continue
            base = Counter(round(g) for g in grosses).most_common(1)[0][0]
            if base <= 0:
                continue
            for sm in group:
                if sm.gross and abs(sm.gross - 2 * base) < 1.0:
                    sm.special = base
                    sm.gross = base
                    s.add(sm)
        s.commit()


def init_db(seed: bool = True) -> None:
    """Create tables, ensure Settings + base Scenario exist, optionally seed demo data."""
    SQLModel.metadata.create_all(engine)
    added_special = _migrate()
    if added_special:
        _split_doubled_salaries()
    from .models import Scenario
    with Session(engine) as session:
        if session.get(Settings, 1) is None:
            session.add(Settings(id=1))
            session.commit()
        if session.get(Scenario, 1) is None:
            session.add(Scenario(id=1, name="Basis", base_id=None, sort_order=0))
            session.commit()
    if seed:
        from .seed import seed_if_empty
        with Session(engine) as session:
            seed_if_empty(session)


def get_session() -> Session:
    """Return a new SQLModel session (use as a context manager)."""
    return Session(engine)


def get_settings(session: Session) -> Settings:
    st = session.get(Settings, 1)
    if st is None:
        st = Settings(id=1)
        session.add(st)
        session.commit()
        session.refresh(st)
    return st
