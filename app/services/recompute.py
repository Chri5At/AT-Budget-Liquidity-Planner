"""Rebuild all derived data (the CashflowEntry ledger) from source rows.

Call this after any source row changes, or via the header "Neu berechnen" button.
The P&L view does not depend on the cache (it reads source rows directly), but
the liquidity view does.
"""
from __future__ import annotations

from ..db import get_session
from ..engine.cashflow import build_cashflows


def recompute_all() -> int:
    with get_session() as session:
        return build_cashflows(session)
