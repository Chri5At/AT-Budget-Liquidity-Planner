"""Import contracts from a JSON file — additively, never destructively.

The regular backup import (`data_io.apply_import`) REPLACES the whole plan, which
is exactly wrong for handing someone a couple of prepared contracts. This reads
the same payload shape (`{"Contract": [ … ]}`, the `data.json` of an export) but
only adds the contracts it contains, leaving everything else alone.

Two optional hint fields may accompany a row so it can find its cost row in a
database whose ids differ from the exporter's:

- ``_category_name``  — target CostCategory, matched by name; created if missing.
- ``_opex_category``  — OPEX sub-category used when such a row has to be created.
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

from ..engine.contracts import contract_positions, dump_positions
from ..models import Contract, CostCategory, OpexCategory, PnlLine

CONTRACT_KEY = "Contract"

# Fields never taken from the file (assigned by the database / resolved here).
_SKIP_FIELDS = {"id", "category_id"}


def read_contracts_payload(raw: bytes | str) -> list[dict]:
    """Parse a JSON file into a list of contract rows. Raises ValueError if unusable."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError("Keine gültige JSON-Datei.") from exc
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get(CONTRACT_KEY) or []
    else:
        rows = []
    if not rows:
        raise ValueError('Die Datei enthält keine Verträge (erwartet: {"Contract": [ … ]}).')
    return [r for r in rows if isinstance(r, dict)]


def _resolve_category(session: Session, row: dict, default_category_id: int | None) -> int | None:
    """Find (or create) the cost row a contract's amounts should land in."""
    cid = row.get("category_id")
    if cid is not None:
        cat = session.get(CostCategory, int(cid))
        if cat is not None and not cat.is_category:
            return cat.id

    name = (row.get("_category_name") or "").strip()
    if name:
        for cat in session.exec(select(CostCategory)).all():
            if not cat.is_category and cat.name.strip().lower() == name.lower():
                return cat.id
        try:
            opex = OpexCategory(row.get("_opex_category") or OpexCategory.OTHER.value)
        except ValueError:
            opex = OpexCategory.OTHER
        order = max([c.sort_order for c in session.exec(select(CostCategory)).all()],
                    default=0) + 1
        cat = CostCategory(name=name, pnl_line=PnlLine.OPEX, opex_category=opex,
                           scenario_id=1, sort_order=order)
        session.add(cat)
        session.commit()
        session.refresh(cat)
        return cat.id

    return default_category_id


def _is_duplicate(session: Session, row: dict) -> bool:
    name = (row.get("name") or "").strip().lower()
    number = (row.get("contract_no") or "").strip().lower()
    for existing in session.exec(select(Contract)).all():
        if existing.name.strip().lower() == name and \
                existing.contract_no.strip().lower() == number:
            return True
    return False


def import_contracts(session: Session, rows: list[dict], *,
                     default_category_id: int | None = None) -> tuple[int, int]:
    """Add the contracts from `rows`. Returns (imported, skipped).

    A row is skipped when a contract with the same name and contract number
    already exists, or when no target cost row can be determined.
    """
    from ..services.snapshots import _coerce_dates      # ISO strings → date objects

    fields = set(Contract.model_fields)
    order = max([c.sort_order for c in session.exec(select(Contract)).all()], default=0)
    imported = skipped = 0
    for row in rows:
        if not (row.get("name") or "").strip() or not row.get("start"):
            skipped += 1                    # a contract needs a name and a start date
            continue
        if _is_duplicate(session, row):
            skipped += 1
            continue
        category_id = _resolve_category(session, row, default_category_id)
        if category_id is None:
            skipped += 1
            continue
        known = {k: v for k, v in row.items() if k in fields and k not in _SKIP_FIELDS}
        known["category_id"] = category_id
        if isinstance(known.get("positions"), list):    # friendlier hand-written files
            known["positions"] = dump_positions(known["positions"])
        if known.get("positions"):                      # amount is always Σ positions
            parsed = contract_positions(Contract(name="", category_id=0, start=None,
                                                 positions=known["positions"]))
            if parsed:
                known["amount"] = round(sum(p["amount"] for p in parsed), 2)
        order += 1
        known.setdefault("sort_order", order)
        session.add(Contract(**_coerce_dates(Contract, known)))
        imported += 1
    session.commit()
    return imported, skipped
