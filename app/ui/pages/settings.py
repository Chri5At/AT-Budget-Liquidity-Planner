"""Einstellungen — global planning parameters (split model, %, opening balance…)."""
from __future__ import annotations

from datetime import date

from nicegui import ui
from sqlalchemy import delete as sa_delete

from ...db import get_session, get_settings
from ...models import (
    CashflowEntry,
    CostCategory,
    CostPlanMonth,
    Depreciation,
    Employee,
    Investment,
    Loan,
    LoanSchedule,
    RevenuePlanMonth,
    RevenueStream,
    SalaryMonth,
    SplitModel,
)
from ...models.enums import SPLIT_MODEL_DE
from ...services.recompute import recompute_all
from ..formatting import eur

# Source tables wiped by "Alle Daten löschen" (Settings is kept, flagged seeded).
_RESET_TABLES = (
    SalaryMonth, Employee, RevenuePlanMonth, RevenueStream,
    CostPlanMonth, CostCategory, Depreciation, LoanSchedule, Loan,
    Investment, CashflowEntry,
)


def render() -> None:
    ui.label("Einstellungen").classes("text-xl font-bold")
    ui.label("Globale Parameter. Mitarbeiter können einzeln abweichen "
             "(siehe Mitarbeiter-Einstellungen).").classes("text-sm text-gray-500")

    with get_session() as s:
        st = get_settings(s)
        data = {
            "company_name": st.company_name,
            "split_model": st.split_model,
            "abgaben_pct": st.abgaben_pct * 100,
            "employer_burden_pct": st.employer_burden_pct * 100,
            "salary_net_pct": st.salary_net_pct * 100,
            "abgaben_pay_day": st.abgaben_pay_day,
            "opening_balance": st.opening_balance,
            "opening_balance_date": st.opening_balance_date.isoformat(),
            "horizon_start": st.horizon_start.isoformat(),
            "horizon_end": st.horizon_end.isoformat(),
        }

    with ui.card().classes("w-full max-w-3xl"):
        with ui.grid(columns=2).classes("gap-3 w-full"):
            name = ui.input("Firmenname", value=data["company_name"])
            model = ui.select({m: SPLIT_MODEL_DE[m] for m in SplitModel},
                              value=data["split_model"], label="Gehalts-Aufteilungsmodell")
            abg = ui.number("Abgaben % (Modell A)", value=data["abgaben_pct"], step=1, min=0, max=100)
            burden = ui.number("Lohnnebenkosten % (LNK)", value=data["employer_burden_pct"], step=1, min=0, max=100)
            netpct = ui.number("Netto % vom Brutto (Modell B)", value=data["salary_net_pct"], step=1, min=0, max=100)
            payday = ui.number("Abgaben-Zahltag (Folgemonat)", value=data["abgaben_pay_day"], step=1, min=1, max=28)
            opening = ui.number("Anfangskontostand (€)", value=data["opening_balance"], step=1000)
            opening_date = ui.input("Anfangsdatum (YYYY-MM-DD)", value=data["opening_balance_date"])
            hstart = ui.input("Planungsbeginn (YYYY-MM-DD)", value=data["horizon_start"])
            hend = ui.input("Planungsende (YYYY-MM-DD)", value=data["horizon_end"])

        def save() -> None:
            with get_session() as s:
                st = get_settings(s)
                st.company_name = name.value
                st.split_model = SplitModel(model.value)
                st.abgaben_pct = float(abg.value or 0) / 100
                st.employer_burden_pct = float(burden.value or 0) / 100
                st.salary_net_pct = float(netpct.value or 0) / 100
                st.abgaben_pay_day = int(payday.value or 15)
                st.opening_balance = float(opening.value or 0)
                try:
                    st.opening_balance_date = date.fromisoformat(opening_date.value)
                    st.horizon_start = date.fromisoformat(hstart.value)
                    st.horizon_end = date.fromisoformat(hend.value)
                except ValueError:
                    ui.notify("Datumsformat: YYYY-MM-DD", type="warning")
                    return
                s.add(st)
                s.commit()
            recompute_all()
            ui.notify("Gespeichert und neu berechnet", type="positive")

        ui.button("Speichern", icon="save", on_click=save).classes("mt-2")

    ui.label(f"Aktueller Anfangskontostand: {eur(data['opening_balance'])}").classes("text-sm mt-2")

    # --- Danger zone: wipe all data to start from scratch ----------------------
    with ui.card().classes("w-full max-w-3xl mt-4 border border-red-300"):
        ui.label("Gefahrenzone").classes("text-base font-semibold text-red-700")
        ui.label("Löscht alle Mitarbeiter, Einnahmen, Ausgaben, Investitionen, Darlehen und "
                 "Abschreibungen. Die Demodaten werden nicht erneut geladen — du startest mit "
                 "einer leeren Planung.").classes("text-sm text-gray-600")
        ui.button("Alle Daten löschen (leere Planung)", icon="delete_forever",
                  color="negative", on_click=_confirm_reset).props("outline")


def _confirm_reset() -> None:
    with ui.dialog() as dlg, ui.card():
        ui.label("Wirklich ALLE Plandaten löschen?").classes("text-lg font-bold")
        ui.label("Dies kann nicht rückgängig gemacht werden. Die Einstellungen "
                 "(Prozentsätze etc.) bleiben erhalten, der Anfangskontostand wird auf 0 gesetzt."
                 ).classes("text-sm text-gray-500")
        with ui.row():
            ui.button("Abbrechen", on_click=dlg.close).props("flat")

            def _do() -> None:
                with get_session() as s:
                    for table in _RESET_TABLES:
                        s.execute(sa_delete(table))
                    st = get_settings(s)
                    st.opening_balance = 0.0
                    st.seeded = True            # prevent demo data from being re-seeded
                    s.add(st)
                    s.commit()
                dlg.close()
                ui.notify("Alle Daten gelöscht — leere Planung", type="positive")
                ui.navigate.reload()

            ui.button("Alles löschen", icon="delete_forever", color="negative", on_click=_do)
    dlg.open()
