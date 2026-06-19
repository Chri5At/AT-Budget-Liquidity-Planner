"""Headless UI smoke test: actually build the page and run every render() once.

This catches runtime errors in the NiceGUI pages (aggrid options, selects,
charts) that a plain server start would not surface.
"""
import pytest
from nicegui.testing import User

from app.db import init_db


@pytest.fixture(autouse=True)
def _seed_db():
    init_db(seed=True)


async def test_index_renders_all_tabs(user: User) -> None:
    await user.open("/")
    await user.should_see("Mitarbeiter")
    await user.should_see("Einnahmen")
    await user.should_see("Liquidität")
    await user.should_see("GuV / Budget")
