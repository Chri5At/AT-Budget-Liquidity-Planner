"""All SQLModel tables — the single source of truth.

Source tables hold *plan* rows (and later *actual* rows). The P&L (GuV) and the
liquidity ledger are both DERIVED from these by the engine; the CashflowEntry
table is a regenerated cache, never hand-edited.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from .enums import (
    CashflowKind,
    LoanKind,
    OpexCategory,
    PaymentTerm,
    PnlLine,
    RevenueType,
    SplitModel,
)


class Settings(SQLModel, table=True):
    """Singleton row (id=1) holding global planning parameters."""
    id: Optional[int] = Field(default=1, primary_key=True)
    company_name: str = "Muster GmbH"
    # salary -> cash split
    split_model: SplitModel = Field(default=SplitModel.FIXED_PCT)
    abgaben_pct: float = 0.30           # model A: share of all-in paid to authorities
    employer_burden_pct: float = 0.30   # Lohnnebenkosten (Dienstgeberanteil)
    salary_net_pct: float = 0.55        # model B: net take-home as share of gross
    abgaben_pay_day: int = 15           # Abgaben due on the 15th of the following month
    bundesland_subdiv: str = "4"        # Oberösterreich (holidays library)
    # liquidity
    opening_balance: float = 0.0
    opening_balance_date: date = Field(default=date(2026, 1, 1))
    horizon_start: date = Field(default=date(2026, 1, 1))
    horizon_end: date = Field(default=date(2027, 12, 31))
    # True once demo data has been seeded (or the user cleared the DB on purpose),
    # so we never re-seed over an intentionally-empty database.
    seeded: bool = False


class Scenario(SQLModel, table=True):
    """A planning scenario. The base scenario has base_id = None; child scenarios
    inherit the base's revenue/cost rows and layer their own deltas on top
    (added rows tagged with their scenario_id, removed rows via ScenarioDisable).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    base_id: Optional[int] = Field(default=None, foreign_key="scenario.id")
    sort_order: int = 0


class ScenarioDisable(SQLModel, table=True):
    """A base row switched OFF within a child scenario."""
    __table_args__ = (UniqueConstraint("scenario_id", "ref_kind", "ref_id", name="uq_scendis"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    scenario_id: int = Field(foreign_key="scenario.id", index=True)
    ref_kind: str   # 'revenue' | 'cost'
    ref_id: int


class Employee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    function: str = ""
    fte: float = 1.0
    is_contractor: bool = False                       # external personnel paid in full
    active_from: Optional[date] = None
    active_to: Optional[date] = None
    split_model_override: Optional[SplitModel] = None
    abgaben_pct_override: Optional[float] = None
    payment_term: PaymentTerm = Field(default=PaymentTerm.SOFORT)  # contractor payout lag
    sort_order: int = 0


class SalaryMonth(SQLModel, table=True):
    """One month of an employee's salary: ongoing gross plus any Sonderzahlung."""
    __table_args__ = (UniqueConstraint("employee_id", "year", "month", name="uq_salary_emp_ym"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    year: int
    month: int
    gross: float = 0.0      # ongoing monthly gross (laufender Bezug)
    special: float = 0.0    # Sonderzahlung (13./14.) paid in this month, taxed at 6%


class RevenueStream(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    scenario_id: int = Field(default=1, foreign_key="scenario.id", index=True)
    rtype: RevenueType = Field(default=RevenueType.RECURRING)
    customer: str = ""
    payment_term: PaymentTerm = Field(default=PaymentTerm.NET30)
    payment_days: Optional[int] = None   # flexible Zahlungsziel in days; overrides payment_term
    unit_price: Optional[float] = None   # for PRODUCT type
    is_vatable: bool = True
    sort_order: int = 0


class RevenuePlanMonth(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("stream_id", "year", "month", name="uq_rev_ym"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: int = Field(foreign_key="revenuestream.id", index=True)
    year: int
    month: int
    units: float = 0.0
    amount: float = 0.0     # authoritative cell value (Σ of cell entries when present)
    note: str = ""          # free note shown on the cell
    color: str = ""         # optional cell background colour (CSS, e.g. "#fff3cd")


class RevenueCellEntry(SQLModel, table=True):
    """One line of a cell's breakdown (the 'Advanced' modal).

    For Produkt streams the line value is qty*price; for other types it is `amount`.
    The owning RevenuePlanMonth.amount is recomputed as the sum of its lines.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: int = Field(foreign_key="revenuestream.id", index=True)
    year: int
    month: int
    sort_order: int = 0
    qty: float = 0.0        # Menge
    price: float = 0.0      # Preis
    amount: float = 0.0     # Betrag (non-product types)
    note: str = ""          # Notiz


class CostCategory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    scenario_id: int = Field(default=1, foreign_key="scenario.id", index=True)
    pnl_line: PnlLine = Field(default=PnlLine.OPEX)
    opex_category: Optional[OpexCategory] = None
    supplier: str = ""
    payment_term: PaymentTerm = Field(default=PaymentTerm.NET30)
    is_vatable: bool = True
    sort_order: int = 0


class CostPlanMonth(SQLModel, table=True):
    """Cost amounts are stored as positive magnitudes; sign is applied by P&L/engine."""
    __table_args__ = (UniqueConstraint("category_id", "year", "month", name="uq_cost_ym"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="costcategory.id", index=True)
    year: int
    month: int
    amount: float = 0.0


class Depreciation(SQLModel, table=True):
    """Abschreibung — P&L only (between EBITDA and EBIT); non-cash, excluded from liquidity."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "Abschreibung Sachanlagen"
    year: int
    month: int
    amount: float = 0.0


class Investment(SQLModel, table=True):
    """Capital paid into the company by a named investor — a liquidity inflow.

    Tracked separately from loans so it's always clear who put in how much, when,
    and for what. Pure cash-in: it does not appear in the P&L.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    investor: str                       # who paid the money in
    label: str = ""                     # which investment / round / purpose
    amount: float = 0.0
    date: date                          # when the money was paid in
    note: str = ""


class Loan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    kind: LoanKind = Field(default=LoanKind.BANK_LOAN)
    principal: float = 0.0
    disbursement_date: Optional[date] = None
    is_eu_funding: bool = False


class LoanSchedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    loan_id: int = Field(foreign_key="loan.id", index=True)
    date: date
    principal_repay: float = 0.0
    interest: float = 0.0


class ActualValue(SQLModel, table=True):
    """Generic Ist-value side-table for later Plan-vs-Ist (design-for-later)."""
    __table_args__ = (UniqueConstraint("ref_kind", "ref_id", "year", "month", name="uq_actual"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    ref_kind: str   # 'revenue' | 'cost' | 'salary' | 'cashflow'
    ref_id: int
    year: int
    month: int
    amount: float = 0.0


class CashflowEntry(SQLModel, table=True):
    """DERIVED ledger — rebuilt by services.recompute; do not edit by hand."""
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date                       # actual cash date (banking-day adjusted)
    bucket: date                     # the 15th or month-end bucket it falls into
    kind: CashflowKind
    amount: float                    # + inflow, - outflow
    source_kind: str = ""
    source_id: Optional[int] = None
    is_eu_funding: bool = False
    memo: str = ""
