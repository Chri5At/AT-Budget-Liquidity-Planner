"""Budget- & Liquiditätsplanung — local single-user planning app.

One SQLite database is the single source of truth. The budget P&L (GuV) and the
liquidity timeline are two *views* derived from the same source rows — never
cross-linked. See .vibe/ for design docs.
"""
