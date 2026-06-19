"""Szenarien — create, list and delete planning scenarios (base + deltas)."""
from __future__ import annotations

from nicegui import ui

from ...db import get_session
from ...engine.scenarios import (
    BASE_SCENARIO_ID,
    create_scenario,
    delete_scenario,
    list_scenarios,
)


def render() -> None:
    ui.label("Szenarien").classes("text-xl font-bold")
    ui.label("Ein Basis-Szenario plus abgeleitete Szenarien. Ein abgeleitetes Szenario erbt "
             "alle Einnahmen/Ausgaben der Basis; in den Reitern Einnahmen/Ausgaben kannst du "
             "Basis-Positionen ab-/zuschalten und eigene hinzufügen. Vergleichen in GuV und "
             "Liquidität.").classes("text-sm text-gray-500")

    @ui.refreshable
    def table() -> None:
        with get_session() as s:
            scs = list_scenarios(s)
            names = {sc.id: sc.name for sc in scs}
            data = [(sc.id, sc.name, ("—" if sc.base_id is None else names.get(sc.base_id, "?")))
                    for sc in scs]
        with ui.card().classes("w-full max-w-2xl"):
            with ui.row().classes("items-center gap-3 text-xs text-gray-500 font-medium"):
                ui.label("Szenario").classes("w-64")
                ui.label("Basis").classes("w-48")
            for sid, name, base in data:
                with ui.row().classes("items-center gap-3"):
                    tag = " (Basis)" if sid == BASE_SCENARIO_ID else ""
                    ui.label(name + tag).classes("w-64 font-medium")
                    ui.label(base).classes("w-48 text-gray-600")
                    if sid != BASE_SCENARIO_ID:
                        ui.button(icon="delete", on_click=lambda sid=sid, name=name: _confirm_delete(sid, name)
                                  ).props("flat round dense color=negative").tooltip("Szenario löschen")
            ui.button("Szenario hinzufügen", icon="add", on_click=_add_dialog).classes("mt-2")

    def _add_dialog() -> None:
        with get_session() as s:
            opts = {sc.id: sc.name for sc in list_scenarios(s)}
        with ui.dialog() as dlg, ui.card():
            ui.label("Neues Szenario").classes("text-lg font-bold")
            name = ui.input("Name").classes("w-72")
            base = ui.select(opts, value=BASE_SCENARIO_ID, label="Basis-Szenario").classes("w-72")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _create() -> None:
                    if not name.value:
                        ui.notify("Name fehlt", type="warning")
                        return
                    with get_session() as s:
                        create_scenario(s, name.value, int(base.value))
                    dlg.close()
                    ui.notify("Szenario angelegt", type="positive")
                    table.refresh()

                ui.button("Anlegen", icon="add", on_click=_create)
        dlg.open()

    def _confirm_delete(sid: int, name: str) -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label(f'Szenario „{name}" löschen?').classes("text-lg font-bold")
            ui.label("Eigene Positionen und Ab-/Zuschaltungen dieses Szenarios werden entfernt. "
                     "Die Basisdaten bleiben unberührt.").classes("text-sm text-gray-500")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    with get_session() as s:
                        delete_scenario(s, sid)
                    dlg.close()
                    ui.notify("Szenario gelöscht", type="positive")
                    table.refresh()

                ui.button("Löschen", icon="delete", color="negative", on_click=_do)
        dlg.open()

    table()
