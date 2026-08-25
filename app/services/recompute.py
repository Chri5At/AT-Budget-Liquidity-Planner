"""Rebuild all derived data from source rows.

Call this after any source row changes, or via the header "Neu berechnen" button.
Two steps run in order:

1. **Contract cells** — the Verträge & Abos register regenerates its plan cells
   (`CostCellEntry` lines tagged with a contract) so the cost matrix reflects the
   current contract data before anything is derived from it.
2. **Cashflow ledger** — the `CashflowEntry` cache the liquidity view reads.

The P&L view does not depend on the cache (it reads source rows directly), but it
does see the contract cells from step 1.
"""
from __future__ import annotations

from ..db import get_session
from ..engine.cashflow import build_cashflows
from ..engine.contracts import generate_contract_cells


def recompute_all() -> int:
    with get_session() as session:
        generate_contract_cells(session)
        return build_cashflows(session)
