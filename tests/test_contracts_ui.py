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
    await user.should_see("Betrag je Intervall (€)")
    await user.should_see("Kündigungsfrist (Monate)")
