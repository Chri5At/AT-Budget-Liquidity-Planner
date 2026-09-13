"""Headless smoke test for the Verträge & Abos tab.

Renders the real page (grid options, selects, KPI tiles) and opens the create
dialog — the kind of runtime error a plain server start would not surface. Read
only: nothing here writes to the database.
"""
import pytest
from nicegui.testing import User

from app.db import init_db


@pytest.fixture(autouse=True)
def _seed_db():
    init_db(seed=True)


async def test_contracts_tab_renders(user: User) -> None:
    await user.open("/")
    await user.should_see("Verträge & Abos")
    await user.should_see("Fixkosten je Monat (norm.)")
    await user.should_see("Aktive Verträge")
    await user.should_see("Nächster Kündigungsstichtag")


async def test_new_contract_dialog_opens(user: User) -> None:
    await user.open("/")
    user.find("Vertrag hinzufügen").click()
    await user.should_see("Neuer Vertrag")
    # The Betrag field and the banner must follow the VSt flag of the position
    # that is preselected (the first selectable cost row).
    from sqlmodel import select

    from app.db import get_session
    from app.models import CostCategory
    with get_session() as s:
        first = next(c for c in s.exec(select(CostCategory).order_by(
            CostCategory.sort_order, CostCategory.id)).all() if not c.is_category)
        vatable = bool(first.is_vatable)
    await user.should_see("Betrag je Intervall (exkl. MwSt.)" if vatable
                          else "Betrag je Intervall (inkl. MwSt.)")
    await user.should_see("Beträge exkl. MwSt. (netto) eingeben" if vatable
                          else "Beträge inkl. MwSt. (= Zahlbetrag) eingeben")
    await user.should_see("Kündigungsfrist (Monate)")
