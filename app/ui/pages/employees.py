"""Mitarbeiter — employees, the editable monthly salary matrix, and a live
net/Abgaben preview derived from the chosen split model.
"""
from __future__ import annotations

from nicegui import ui
from sqlmodel import select

from ...db import get_session, get_settings
from ...models import Employee, PaymentTerm, SalaryMonth, SplitModel
from ...models.enums import PAYMENT_TERM_DE, SPLIT_MODEL_DE
from ...engine.payroll_at import employee_year_cost, ruleset_for_year
from ...services.recompute import recompute_all
from ..formatting import MONTHS_DE, YEARS, eur, page_title
from ..components.month_grid import editable_month_grid

SONDER_MONTHS = (6, 11)


def _load_special_rows(year: int) -> list[dict]:
    """Sonderzahlung (13./14.) per month for internal employees only."""
    with get_session() as s:
        emps = s.exec(select(Employee).where(Employee.is_contractor == False)  # noqa: E712
                      .order_by(Employee.sort_order, Employee.id)).all()
        rows = []
        for e in emps:
            months = {sm.month: sm.special for sm in s.exec(
                select(SalaryMonth).where(SalaryMonth.employee_id == e.id,
                                          SalaryMonth.year == year)).all()}
            row = {"id": e.id, "name": e.name}
            for m in range(1, 13):
                row[f"m{m}"] = round(months.get(m, 0.0))
            rows.append(row)
        return rows


def _save_special_row(year: int, data: dict) -> None:
    with get_session() as s:
        emp = s.get(Employee, int(data["id"]))
        if emp is None:
            return
        for m in range(1, 13):
            try:
                val = float(data.get(f"m{m}", 0) or 0)
            except (TypeError, ValueError):
                val = 0.0
            sm = s.exec(select(SalaryMonth).where(
                SalaryMonth.employee_id == emp.id, SalaryMonth.year == year,
                SalaryMonth.month == m)).first()
            if sm is None:
                s.add(SalaryMonth(employee_id=emp.id, year=year, month=m, gross=0.0, special=val))
            else:
                sm.special = val
        s.commit()


def _load_rows(year: int) -> list[dict]:
    with get_session() as s:
        emps = s.exec(select(Employee).order_by(Employee.sort_order, Employee.id)).all()
        rows = []
        for e in emps:
            months = {sm.month: sm.gross for sm in s.exec(
                select(SalaryMonth).where(SalaryMonth.employee_id == e.id,
                                          SalaryMonth.year == year)).all()}
            row = {"id": e.id, "name": e.name, "function": e.function, "fte": e.fte,
                   "extern": "Ja" if e.is_contractor else "Nein"}
            for m in range(1, 13):
                row[f"m{m}"] = round(months.get(m, 0.0))
            rows.append(row)
        return rows


def _save_row(year: int, data: dict) -> None:
    with get_session() as s:
        emp = s.get(Employee, int(data["id"]))
        if emp is None:
            return
        emp.name = data.get("name", emp.name)
        emp.function = data.get("function", emp.function)
        try:
            emp.fte = float(data.get("fte") or 0)
        except (TypeError, ValueError):
            pass
        s.add(emp)
        for m in range(1, 13):
            val = data.get(f"m{m}", 0) or 0
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0.0
            sm = s.exec(select(SalaryMonth).where(
                SalaryMonth.employee_id == emp.id, SalaryMonth.year == year,
                SalaryMonth.month == m)).first()
            if sm is None:
                s.add(SalaryMonth(employee_id=emp.id, year=year, month=m, gross=val))
            else:
                sm.gross = val
        s.commit()


def render() -> None:
    state = {"year": YEARS[0]}

    page_title("Mitarbeiter & Personalkosten",
               "Laufendes Bruttogehalt je Monat eingeben. Sonderzahlungen (13./14., Urlaubs-/"
               "Weihnachtsgeld) separat darunter — so sind sie einzeln anpassbar (z. B. anteilig "
               "bei unterjährigem Eintritt). Netto wird nach österreichischem Tarif berechnet.")

    with ui.row().classes("items-center gap-3 my-2"):
        ui.select(YEARS, value=state["year"], label="Jahr",
                  on_change=lambda e: _change_year(e.value)).props("outlined dense").classes("w-28")
        ui.button("Mitarbeiter hinzufügen", icon="person_add", on_click=lambda: _add_dialog())

    @ui.refreshable
    def matrix() -> None:
        ui.label("Laufendes Bruttogehalt").classes("text-sm font-medium")
        lead = [
            {"headerName": "Mitarbeiter", "field": "name", "editable": True,
             "pinned": "left", "width": 150},
            {"headerName": "Funktion", "field": "function", "editable": True, "width": 180},
            {"headerName": "FTE", "field": "fte", "editable": True, "width": 70,
             "type": "numericColumn"},
            {"headerName": "Extern", "field": "extern", "width": 80},
        ]
        rows = _load_rows(state["year"])

        def on_change(data: dict) -> None:
            _save_row(state["year"], data)
            preview.refresh()

        editable_month_grid(rows, lead, on_change)

    @ui.refreshable
    def special_matrix() -> None:
        with ui.row().classes("items-center gap-3 mt-3"):
            ui.label("Sonderzahlungen").classes("text-sm font-medium")
            ui.button("Urlaubs und Weihnachtsgeld errechnen", icon="content_copy",
                      on_click=lambda: _fill_sonder()).props("outline").tooltip(
                "Berechnet je Sonderzahlung das aliquote Jahressechstel aus dem laufenden "
                "Bruttogehalt (1 Monat pro vollem Jahr, anteilig nach Dienstmonaten). "
                "Urlaubsgeld → Juni bzw. erster beschäftigter Monat (z. B. Juli bei Eintritt "
                "nach Juni); Weihnachtsgeld → November bzw. letzter beschäftigter Monat. "
                "Einzelne Werte bleiben danach editierbar.")
        lead = [{"headerName": "Mitarbeiter", "field": "name", "pinned": "left", "width": 230}]
        rows = _load_special_rows(state["year"])

        def on_change(data: dict) -> None:
            _save_special_row(state["year"], data)
            preview.refresh()

        editable_month_grid(rows, lead, on_change)

    @ui.refreshable
    def preview() -> None:
        year = state["year"]
        with get_session() as s:
            burden = get_settings(s).employer_burden_pct
            rs = ruleset_for_year(year)
            emps = s.exec(select(Employee).order_by(Employee.sort_order, Employee.id)).all()
            # Per-employee monthly Brutto / Netto / Gesamtkosten (Brutto + LNK).
            per_emp: list[tuple] = []
            tot_brutto = [0.0] * 12
            tot_net = [0.0] * 12
            tot_allin = [0.0] * 12
            tot_abg = [0.0] * 12
            for e in emps:
                regular = [0.0] * 12
                special = [0.0] * 12
                for sm in s.exec(select(SalaryMonth).where(
                        SalaryMonth.employee_id == e.id, SalaryMonth.year == year)).all():
                    regular[sm.month - 1] += sm.gross
                    special[sm.month - 1] += sm.special
                if not any(regular) and not any(special):
                    continue
                if e.is_contractor:
                    brutto = [regular[m] + special[m] for m in range(12)]
                    net, allin, abg = brutto[:], brutto[:], [0.0] * 12
                else:
                    mc = employee_year_cost(regular, special, burden_pct=burden, rs=rs)
                    brutto, net, allin, abg = mc.gross, mc.net, mc.all_in, mc.abgaben
                per_emp.append((e, brutto, net, allin))
                for m in range(12):
                    tot_brutto[m] += brutto[m]
                    tot_net[m] += net[m]
                    tot_allin[m] += allin[m]
                    tot_abg[m] += abg[m]

        ui.label(f"Brutto / Netto / Gesamtkosten je Mitarbeiter — Netto nach österr. "
                 f"Tarif ({rs.name}), LNK {burden * 100:.0f} %"
                 ).classes("text-sm font-medium mt-4")

        col_defs = [{"headerName": "Mitarbeiter / Position", "field": "label",
                     "pinned": "left", "width": 270}]
        for m in range(1, 13):
            col_defs.append({"headerName": MONTHS_DE[m - 1], "field": f"m{m}",
                             "type": "numericColumn", "width": 84,
                             ":valueFormatter":
                             "p => p.value? Math.round(p.value).toLocaleString('de-DE')+' €':''"})
        col_defs.append({"headerName": "Jahr", "field": "jahr", "pinned": "right",
                         "width": 120, "cellClass": "font-bold", "type": "numericColumn",
                         ":valueFormatter":
                         "p => Math.round(p.value||0).toLocaleString('de-DE')+' €'"})

        def mk(label: str, arr: list[float], kind: str = "line") -> dict:
            r = {"label": label, "jahr": round(sum(arr)), "_kind": kind}
            for m in range(1, 13):
                r[f"m{m}"] = round(arr[m - 1])
            return r

        rows: list[dict] = []
        for e, brutto, net, allin in per_emp:
            head = e.name + (" (extern)" if e.is_contractor else "")
            if e.function:
                head += f" · {e.function}"
            rows.append({"label": head, "_kind": "section",
                         **{f"m{m}": None for m in range(1, 13)}, "jahr": None})
            rows.append(mk("    Brutto", brutto))
            rows.append(mk("    Netto (Auszahlung Monatsende)", net))
            rows.append(mk("    Gesamtkosten (Brutto + LNK)", allin, kind="subtotal"))

        # Company-wide totals.
        rows.append(mk("Σ Brutto (alle MA)", tot_brutto, kind="subtotal"))
        rows.append(mk("Σ Netto (alle MA)", tot_net, kind="subtotal"))
        rows.append(mk("Σ Gesamtkosten / Personalaufwand (alle MA)", tot_allin, kind="subtotal"))

        # Deterministic height from row count (avoids autoHeight collapsing at 4K/high-DPI).
        grid_h = 34 + max(1, len(rows)) * 30 + 20
        ui.aggrid({
            "columnDefs": col_defs,
            "rowData": rows,
            "defaultColDef": {"sortable": False, "resizable": True, "suppressMovable": True},
            "rowHeight": 30,
            "headerHeight": 34,
            ":rowClassRules": "{'font-bold bg-blue-50': p => p.data._kind === 'subtotal',"
                              " 'font-semibold bg-gray-100': p => p.data._kind === 'section'}",
        }).classes("w-full").style(f"height: {grid_h}px")

        ui.label(f"Jahr {year} — Brutto {eur(sum(tot_brutto))}  ·  Netto {eur(sum(tot_net))}  ·  "
                 f"Gesamtkosten {eur(sum(tot_allin))}  ·  Abgaben FA/ÖGK {eur(sum(tot_abg))}"
                 ).classes("text-sm font-semibold mt-1")

    def _change_year(value: int) -> None:
        state["year"] = int(value)
        matrix.refresh()
        special_matrix.refresh()
        preview.refresh()

    def _fill_sonder() -> None:
        """Compute aliquot Urlaubs-/Weihnachtsgeld from the entered ongoing salary.

        Austrian rule: each Sonderzahlung (13./14.) = annual ongoing gross / 12
        (= one month's salary for a full year, pro-rated by months actually worked).
        Only placed in months that are actually employed (gross > 0), so an
        employee starting in Aug gets nothing in June.
        """
        year = state["year"]
        with get_session() as s:
            for e in s.exec(select(Employee).where(Employee.is_contractor == False)).all():  # noqa: E712
                months = {sm.month: sm for sm in s.exec(select(SalaryMonth).where(
                    SalaryMonth.employee_id == e.id, SalaryMonth.year == year)).all()}
                # Clear any previous Sonderzahlungen first (idempotent re-run).
                for sm in months.values():
                    sm.special = 0.0
                employed = sorted(m for m in range(1, 13)
                                  if months.get(m) and months[m].gross > 0)
                if not employed:
                    continue
                # Aliquot per Sonderzahlung = (sum of ongoing gross over the year) / 12.
                aliquot = sum(months[m].gross for m in employed) / 12.0
                # Urlaubsgeld → June if employed, else first employed month.
                # Weihnachtsgeld → November if employed, else last employed month.
                u_month = 6 if 6 in employed else employed[0]
                w_month = 11 if 11 in employed else employed[-1]

                def _add_special(m: int, amount: float) -> None:
                    sm = months.get(m)
                    if sm is None:
                        sm = SalaryMonth(employee_id=e.id, year=year, month=m,
                                         gross=0.0, special=0.0)
                        s.add(sm)
                        months[m] = sm
                    sm.special += amount

                _add_special(u_month, aliquot)   # Urlaubsgeld
                _add_special(w_month, aliquot)   # Weihnachtsgeld
            s.commit()
        special_matrix.refresh()
        preview.refresh()
        ui.notify("Urlaubs- & Weihnachtsgeld aliquot berechnet (anteilig nach Dienstmonaten)",
                  type="positive")

    def _add_dialog() -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label("Neuer Mitarbeiter").classes("text-lg font-bold")
            name = ui.input("Name").classes("w-64")
            fn = ui.input("Funktion").classes("w-64")
            fte = ui.number("FTE", value=1.0, step=0.1, min=0, max=2).classes("w-32")
            extern = ui.checkbox("Externer Mitarbeiter (Werkvertrag/freelance)")
            with ui.row():
                ui.button("Abbrechen", on_click=dialog.close).props("flat")

                def _create() -> None:
                    if not name.value:
                        ui.notify("Name fehlt", type="warning")
                        return
                    with get_session() as s:
                        nxt = (s.exec(select(Employee)).all() or [])
                        order = max([e.sort_order for e in nxt], default=0) + 1
                        s.add(Employee(name=name.value, function=fn.value or "",
                                       fte=float(fte.value or 1.0),
                                       is_contractor=bool(extern.value), sort_order=order))
                        s.commit()
                    dialog.close()
                    matrix.refresh()
                    special_matrix.refresh()
                    preview.refresh()

                ui.button("Anlegen", on_click=_create)
        dialog.open()

    matrix()
    special_matrix()
    _settings_panel()
    preview()
    _formula_panel(state["year"])


def _formula_panel(year: int) -> None:
    """Show the active Austrian net-calculation formula and its validity period."""
    rs = ruleset_for_year(year)
    parts = []
    for i, b in enumerate(rs.brackets):
        upper = rs.brackets[i + 1].lower if i + 1 < len(rs.brackets) else None
        parts.append(f"{b.rate * 100:.0f}% bis {eur(upper)}" if upper
                     else f"{b.rate * 100:.0f}% darüber")
    brackets_text = ", ".join(parts)
    with ui.expansion(f"Berechnungsgrundlage Netto — {rs.name} "
                      f"(gültig {rs.valid_from.isoformat()} bis {rs.valid_to.isoformat()})",
                      icon="functions").classes("w-full mt-2"):
        ui.markdown(
            f"**Netto = Brutto − Sozialversicherung − Lohnsteuer** "
            f"(Planungs-Schätzung, keine Lohnverrechnung).\n\n"
            f"- **Sozialversicherung (DN-Anteil):** {rs.sv_rate * 100:.2f} % vom Brutto, "
            f"gedeckelt bei {eur(rs.sv_monthly_cap)}/Monat (Höchstbeitragsgrundlage); "
            f"unter {eur(rs.geringfuegigkeit)} (geringfügig) keine SV.\n"
            f"- **Lohnsteuer (progressiv, Jahrestarif):** {brackets_text}; "
            f"minus Verkehrsabsetzbetrag {eur(rs.traffic_deduction)}/Jahr.\n"
            f"- **Sonderzahlung 13./14.:** SV {rs.sv_rate_special * 100:.2f} %, erste "
            f"{eur(rs.special_free_amount)} steuerfrei, darüber {rs.special_rate * 100:.0f} % "
            f"(innerhalb Jahressechstel); bis {eur(rs.special_freigrenze)} gesamt steuerfrei.\n"
            f"- **Gesamtkosten:** Brutto + Lohnnebenkosten (LNK, Einstellungen).\n\n"
            f"Quelle: {rs.source}. Werte ändern sich (fast) jährlich — neue Tarife als weiteres "
            f"Ruleset in `app/engine/payroll_at.py` ergänzen (mit Gültigkeitszeitraum)."
        )


def _settings_panel() -> None:
    """Per-employee flags (extern, payment term, split overrides)."""
    with ui.expansion("Mitarbeiter-Einstellungen (extern, Zahlungsziel, Abgaben-Override)",
                      icon="tune").classes("w-full"):
        with get_session() as s:
            emps = s.exec(select(Employee).order_by(Employee.sort_order, Employee.id)).all()
            for e in emps:
                _employee_settings_row(e.id)


def _employee_settings_row(emp_id: int) -> None:
    with get_session() as s:
        e = s.get(Employee, emp_id)
        name = e.name
        is_contractor = e.is_contractor
        term = e.payment_term
        ov_model = e.split_model_override
        ov_pct = e.abgaben_pct_override

    def save(**kw):
        with get_session() as s:
            emp = s.get(Employee, emp_id)
            for k, v in kw.items():
                setattr(emp, k, v)
            s.add(emp)
            s.commit()

    with ui.row().classes("items-center gap-3"):
        ui.label(name).classes("w-40")
        ui.checkbox("extern", value=is_contractor,
                    on_change=lambda ev: save(is_contractor=bool(ev.value)))
        ui.select({t.value: PAYMENT_TERM_DE[t] for t in PaymentTerm}, value=term.value, label="Zahlungsziel",
                  on_change=lambda ev: save(payment_term=PaymentTerm(ev.value))).props("dense outlined").classes("w-40")
        ui.select({"": "Global", SplitModel.FIXED_PCT.value: SPLIT_MODEL_DE[SplitModel.FIXED_PCT],
                   SplitModel.ACCOUNTING.value: SPLIT_MODEL_DE[SplitModel.ACCOUNTING]},
                  value=(ov_model.value if ov_model else ""), label="Modell-Override",
                  on_change=lambda ev: save(split_model_override=(SplitModel(ev.value) if ev.value else None))
                  ).props("dense outlined").classes("w-56")
        ui.number("Abgaben %-Override", value=(ov_pct * 100 if ov_pct is not None else None),
                  step=1, min=0, max=100,
                  on_change=lambda ev: save(
                      abgaben_pct_override=(ev.value / 100 if ev.value not in (None, "") else None))
                  ).props("dense outlined").classes("w-40")
        ui.button(icon="delete", on_click=lambda: _confirm_delete(emp_id, name)
                  ).props("flat round color=negative").tooltip("Mitarbeiter löschen")


def _confirm_delete(emp_id: int, name: str) -> None:
    with ui.dialog() as dlg, ui.card():
        ui.label(f'„{name}“ wirklich löschen?').classes("text-lg font-bold")
        ui.label("Der Mitarbeiter und alle zugehörigen Gehaltsdaten (alle Jahre/Monate) "
                 "werden entfernt.").classes("text-sm text-gray-500")
        with ui.row():
            ui.button("Abbrechen", on_click=dlg.close).props("flat")

            def _do() -> None:
                with get_session() as s:
                    for sm in s.exec(select(SalaryMonth).where(
                            SalaryMonth.employee_id == emp_id)).all():
                        s.delete(sm)
                    emp = s.get(Employee, emp_id)
                    if emp is not None:
                        s.delete(emp)
                    s.commit()
                recompute_all()
                dlg.close()
                ui.notify(f'„{name}“ gelöscht', type="positive")
                ui.navigate.reload()

            ui.button("Löschen", icon="delete", color="negative", on_click=_do)
    dlg.open()
