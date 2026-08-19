"""Verträge & Abos — the register of running contracts, subscriptions and fixed costs.

Each row is the master record of a recurring obligation. From its billing data the
engine writes the plan cells into the contract's cost row (Ausgaben), so a yearly
insurance premium no longer has to be typed into the right month by hand — and not
again for every planning year. From its renewal data this page derives the next due
date and the cancellation deadline, with a traffic light that turns yellow 120 days
and red 60 days before notice must be given.

Contracts are deliberately scenario-independent: they are real obligations. Which
scenarios they show up in follows from their cost category, exactly like a manually
entered cost.
"""
from __future__ import annotations

from datetime import date, datetime

from nicegui import ui
from sqlmodel import select

from ...db import get_session
from ...engine.contracts import (
    annual_total,
    cancellation_deadline,
    monthly_equiv,
    next_due,
    renewal_date,
    traffic_light,
)
from ...models import (
    BillingCycle,
    Contract,
    ContractStatus,
    CostCategory,
    CostCellEntry,
    Scenario,
)
from ...services.contracts_io import import_contracts, read_contracts_payload
from ...services.recompute import recompute_all
from ..components.amount_input import AmountInput
from ..file_dialogs import pick_folder
from ..formatting import MONTHS_DE, eur, page_title
from ..grid import fit_grid
from ..path_open import open_folder

_LIGHT_TEXT = {
    "red": "text-red-600", "yellow": "text-amber-600",
    "green": "text-green-700", "grey": "text-gray-500",
}
_STATUS_FILTER = {"all": "Alle", **{s.value: s.value for s in ContractStatus}}

_AMPEL_RENDER = (
    'params => { var m = {red:"#dc2626", yellow:"#f59e0b", green:"#16a34a", grey:"#9ca3af"};'
    ' var c = m[params.value] || m.grey;'
    ' return "<span title=\'" + (params.data.ampel_hint || "") + "\'"'
    ' + " style=\'color:" + c + ";font-size:17px\'>&#9679;</span>"; }')
_ACTION_RENDER = ('params => params.value'
                  ' ? "<span style=\'cursor:pointer\'>" + params.value + "</span>" : ""')
_ROW_STYLE = ('params => params.data.status === "aktiv" ? null'
              ' : {color: "#6b7280", fontStyle: "italic"}')


# --- small helpers ---------------------------------------------------------

def _today() -> date:
    return datetime.now().date()


def _de(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def parse_date(text: str | None) -> date | None:
    """Parse a typed date: '19.08.2026', '19.8.26' or ISO '2026-08-19'. None if empty/bad."""
    s = (text or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _category_options() -> dict[int, str]:
    """Selectable cost rows (groups excluded — they only sum their children)."""
    with get_session() as s:
        scenarios = {sc.id: sc.name for sc in s.exec(select(Scenario)).all()}
        out: dict[int, str] = {}
        for c in s.exec(select(CostCategory).order_by(
                CostCategory.sort_order, CostCategory.id)).all():
            if c.is_category:
                continue
            label = c.name
            if c.scenario_id != 1:
                label += f" · {scenarios.get(c.scenario_id, 'Szenario')}"
            out[c.id] = label
        return out


def _row(contract: Contract, category_name: str, today: date) -> dict:
    light = traffic_light(contract, today)
    deadline = cancellation_deadline(contract, today)
    hints = {"red": "Kündigungsstichtag in weniger als 60 Tagen",
             "yellow": "Kündigungsstichtag in weniger als 120 Tagen",
             "green": "Kündigungsfrist noch nicht kritisch",
             "grey": "keine Terminüberwachung (nicht aktiv, keine Verlängerung "
                     "oder einmalig)"}
    return {
        "id": contract.id,
        "ampel": light,
        "ampel_hint": hints[light] + (f" — {_de(deadline)}" if deadline else ""),
        "name": contract.name,
        "partner": contract.partner,
        "contract_no": contract.contract_no,
        "category": category_name,
        "amount": round(contract.amount, 2),
        "cycle": BillingCycle(contract.cycle).value,
        "monthly": round(monthly_equiv(contract), 2),
        "next_due": _de(next_due(contract, today)),
        "renewal": _de(renewal_date(contract, today)),
        "deadline": _de(deadline),
        "payment_method": contract.payment_method,
        "status": ContractStatus(contract.status).value,
        "edit": "edit",
        "hint_edit": "bearbeiten",
        "doc": "folder_open" if contract.doc_path else "",
        "hint_doc": f"Ablage öffnen: {contract.doc_path}",
        "del": "delete",
        "hint_del": "löschen",
    }


def _load(status_filter: str) -> tuple[list[dict], dict]:
    """Grid rows plus the KPI figures (always over ALL active contracts)."""
    today = _today()
    with get_session() as s:
        categories = {c.id: c.name for c in s.exec(select(CostCategory)).all()}
        contracts = list(s.exec(select(Contract).order_by(
            Contract.sort_order, Contract.id)).all())
        rows = [_row(c, categories.get(c.category_id, "— Kategorie fehlt —"), today)
                for c in contracts
                if status_filter == "all" or ContractStatus(c.status).value == status_filter]
        active = [c for c in contracts if c.status == ContractStatus.ACTIVE]
        deadlines = [(cancellation_deadline(c, today), c) for c in active if c.auto_renew]
        upcoming = sorted(((d, c) for d, c in deadlines if d is not None), key=lambda t: t[0])
        kpi = {
            "monthly": sum(monthly_equiv(c) for c in active),
            "annual": sum(annual_total(c) for c in active),
            "count": len(active),
            # Plain values — the session (and with it the ORM objects) closes below.
            "next": (upcoming[0][0], upcoming[0][1].name) if upcoming else None,
            "light": traffic_light(upcoming[0][1], today) if upcoming else "grey",
        }
    return rows, kpi


def render():
    state = {"filter": "all"}

    page_title("Verträge & Abos",
               "Register aller laufenden Verträge, Abos und Fixkosten. Aus den Vertragsdaten "
               "werden die Monatszellen der zugeordneten Ausgaben-Position automatisch erzeugt "
               "(Jahresprämie = Spitze im Fälligkeitsmonat) — diese Zeilen sind im Ausgaben-"
               "Raster gesperrt und werden hier gepflegt. Die Ampel warnt vor dem "
               "Kündigungsstichtag: gelb ab 120, rot ab 60 Tagen.")

    @ui.refreshable
    def kpi_row() -> None:
        _, kpi = _load(state["filter"])
        with ui.row().classes("w-full gap-3 my-2 flex-wrap"):
            def tile(label: str, value: str, classes: str = "") -> None:
                with ui.card().classes("py-2 px-4 min-w-[190px]"):
                    ui.label(label).classes("text-xs text-gray-500")
                    ui.label(value).classes(f"text-lg font-bold {classes}")

            tile("Fixkosten je Monat (norm.)", eur(kpi["monthly"], 2))
            tile("Fixkosten je Jahr (norm.)", eur(kpi["annual"], 2))
            tile("Aktive Verträge", str(kpi["count"]))
            if kpi["next"]:
                deadline, contract_name = kpi["next"]
                tile("Nächster Kündigungsstichtag", f"{_de(deadline)} · {contract_name}",
                     _LIGHT_TEXT[kpi["light"]])
            else:
                tile("Nächster Kündigungsstichtag", "—", _LIGHT_TEXT["grey"])

    with ui.row().classes("items-center gap-3 my-2 flex-wrap"):
        ui.select(_STATUS_FILTER, value="all", label="Status",
                  on_change=lambda e: _change_filter(e.value)
                  ).props("dense outlined").classes("w-40")
        ui.button("Vertrag hinzufügen", icon="add", on_click=lambda: _edit_dialog(None))
        ui.button("Verträge importieren", icon="upload_file",
                  on_click=lambda: _import_dialog()).props("outline").tooltip(
            "Verträge aus einer JSON-Datei ergänzen (z. B. .vibe/08-initial-contracts.json). "
            "Bestehende Daten bleiben erhalten.")

    kpi_row()

    @ui.refreshable
    def table() -> None:
        rows, _ = _load(state["filter"])
        col_defs = [
            {"headerName": "", "field": "ampel", "width": 46, "pinned": "left",
             "suppressSizeToFit": True, "sortable": True, ":cellRenderer": _AMPEL_RENDER},
            {"headerName": "Vertrag", "field": "name", "width": 180, "pinned": "left",
             "suppressSizeToFit": True},
            {"headerName": "Partner", "field": "partner", "width": 130,
             "suppressSizeToFit": True},
            {"headerName": "Vertrags-Nr.", "field": "contract_no", "width": 120,
             "suppressSizeToFit": True},
            {"headerName": "Ausgaben-Position", "field": "category", "width": 140,
             "suppressSizeToFit": True},
            {"headerName": "Betrag", "field": "amount", "type": "numericColumn",
             ":valueFormatter": "p => p.value != null ? p.value.toLocaleString('de-DE',"
                               "{minimumFractionDigits:2, maximumFractionDigits:2}) + ' €' : ''"},
            {"headerName": "Rhythmus", "field": "cycle", "width": 100,
             "suppressSizeToFit": True},
            {"headerName": "€/Monat", "field": "monthly", "type": "numericColumn",
             ":valueFormatter": "p => p.value ? p.value.toLocaleString('de-DE',"
                               "{minimumFractionDigits:2, maximumFractionDigits:2}) + ' €' : ''"},
            {"headerName": "nächste Fälligkeit", "field": "next_due", "width": 112,
             "suppressSizeToFit": True},
            {"headerName": "Hauptfälligkeit", "field": "renewal", "width": 106,
             "suppressSizeToFit": True},
            {"headerName": "Kündigungsstichtag", "field": "deadline", "width": 122,
             "suppressSizeToFit": True},
            {"headerName": "Zahlweg", "field": "payment_method", "width": 110,
             "suppressSizeToFit": True},
            {"headerName": "Status", "field": "status", "width": 86,
             "suppressSizeToFit": True},
            {"headerName": "", "field": "edit", "width": 40, "pinned": "right",
             "sortable": False, "suppressSizeToFit": True, ":cellRenderer": _ACTION_RENDER},
            {"headerName": "", "field": "doc", "width": 40, "pinned": "right",
             "sortable": False, "suppressSizeToFit": True, ":cellRenderer": _ACTION_RENDER},
            {"headerName": "", "field": "del", "width": 40, "pinned": "right",
             "sortable": False, "suppressSizeToFit": True, ":cellRenderer": _ACTION_RENDER},
        ]
        if not rows:
            ui.label("Noch keine Verträge erfasst — „Vertrag hinzufügen“ legt den ersten an."
                     ).classes("text-sm text-gray-500")
        grid = ui.aggrid(fit_grid({
            "columnDefs": col_defs, "rowData": rows,
            "defaultColDef": {"sortable": True, "resizable": True, "suppressMovable": True},
            "rowHeight": 30, "headerHeight": 34,
            ":getRowId": "params => 'c' + params.data.id",
            ":getRowStyle": _ROW_STYLE,
        })).classes("w-full").style(f"height: {34 + max(1, len(rows)) * 30 + 20}px")
        grid.on("cellClicked", _on_click)
        grid.on("rowDoubleClicked", lambda e: _edit_dialog(int((e.args or {})
                                                              .get("data", {}).get("id", 0))))
        ui.label("Doppelklick auf eine Zeile oder das Stift-Symbol = bearbeiten · "
                 "Ordner-Symbol = Ablage öffnen · Papierkorb = löschen. Die erzeugten "
                 "Monatswerte stehen im Reiter Ausgaben."
                 ).classes("text-xs text-gray-500")

    def _on_click(e) -> None:
        args = e.args or {}
        col = args.get("colId") or args.get("column") or ""
        data = args.get("data") or {}
        cid = int(data.get("id") or 0)
        if not cid:
            return
        if col == "edit":
            _edit_dialog(cid)
        elif col == "del":
            _delete_dialog(cid, data.get("name", ""))
        elif col == "doc":
            with get_session() as s:
                contract = s.get(Contract, cid)
                path = contract.doc_path if contract else ""
            problem = open_folder(path)
            ui.notify(problem or f"Ablage geöffnet: {path}",
                      type="warning" if problem else "positive")

    def _change_filter(value: str) -> None:
        state["filter"] = value
        table.refresh()

    def _refresh_all() -> None:
        kpi_row.refresh()
        table.refresh()
        locked_cells.refresh()

    # --- create / edit ------------------------------------------------------

    def _edit_dialog(contract_id: int | None) -> None:
        cats = _category_options()
        if not cats:
            ui.notify("Lege zuerst im Reiter Ausgaben eine Position an, der die Verträge "
                      "zugeordnet werden.", type="warning")
            return
        if contract_id:
            with get_session() as s:
                c = s.get(Contract, contract_id)
                if c is None:
                    return
                values = c.model_dump()
        else:
            values = Contract(name="", category_id=next(iter(cats)),
                              start=_today()).model_dump()

        with ui.dialog() as dlg, ui.card().classes("min-w-[720px]"):
            ui.label("Vertrag bearbeiten" if contract_id else "Neuer Vertrag"
                     ).classes("text-lg font-bold")
            with ui.row().classes("gap-3 w-full"):
                name_in = ui.input("Bezeichnung", value=values["name"]
                                   ).props("dense outlined").classes("w-72")
                partner_in = ui.input("Vertragspartner", value=values["partner"]
                                      ).props("dense outlined").classes("w-60")
                no_in = ui.input("Vertrags-/Polizzennummer", value=values["contract_no"]
                                 ).props("dense outlined").classes("w-60")
            with ui.row().classes("gap-3 w-full items-center"):
                cat_sel = ui.select(cats, value=(values["category_id"] if values["category_id"]
                                                 in cats else next(iter(cats))),
                                    label="Ausgaben-Position").props("dense outlined").classes("w-72")
                amount_in = AmountInput("Betrag je Intervall (€)",
                                        value=values["amount"]).classes("w-48")
                cycle_sel = ui.select({c.value: c.value for c in BillingCycle},
                                      value=BillingCycle(values["cycle"]).value,
                                      label="Rhythmus").props("dense outlined").classes("w-44")
            ui.label("Der Betrag wird genau wie ein händischer Zellenwert behandelt — "
                     "Zahlungsziel und USt kommen aus der gewählten Ausgaben-Position."
                     ).classes("text-xs text-gray-500")

            with ui.row().classes("gap-3 w-full"):
                start_in = ui.input("Beginn (TT.MM.JJJJ)", value=_de(values["start"])
                                    ).props("dense outlined").classes("w-44")
                first_in = ui.input("Erste Zahlung (optional)", value=_de(values["first_due"])
                                    ).props("dense outlined").classes("w-44")
                end_in = ui.input("Ende (leer = unbefristet)", value=_de(values["end"])
                                  ).props("dense outlined").classes("w-44")
            with ui.row().classes("gap-3 w-full items-center"):
                renew_cb = ui.checkbox("Stillschweigende Verlängerung",
                                       value=bool(values["auto_renew"]))
                notice_in = ui.number("Kündigungsfrist (Monate)", value=values["notice_months"],
                                      min=0, max=36, step=1).props("dense outlined").classes("w-44")
                day_in = ui.number("Hauptfälligkeit Tag", value=values["renewal_day"],
                                   min=1, max=31, step=1).props("dense outlined").classes("w-40")
                month_sel = ui.select({0: "— aus Beginn —",
                                       **{m: MONTHS_DE[m - 1] for m in range(1, 13)}},
                                      value=values["renewal_month"] or 0,
                                      label="Hauptfälligkeit Monat"
                                      ).props("dense outlined").classes("w-44")
            ui.label("Hauptfälligkeit leer lassen = Jahrestag des Beginns. "
                     "Kündigungsstichtag = Hauptfälligkeit minus Kündigungsfrist."
                     ).classes("text-xs text-gray-500")

            with ui.row().classes("gap-3 w-full items-center"):
                pay_in = ui.input("Zahlweg", value=values["payment_method"],
                                  placeholder="SEPA-Lastschrift, Kreditkarte, Rechnung …"
                                  ).props("dense outlined").classes("w-60")
                status_sel = ui.select({s.value: s.value for s in ContractStatus},
                                       value=ContractStatus(values["status"]).value,
                                       label="Status").props("dense outlined").classes("w-44")
            ui.label("„ruhend“ und „Testphase“ erzeugen keine Kosten. „gekündigt“ zahlt bis "
                     "zum Enddatum weiter — ohne Enddatum entstehen keine Zellen."
                     ).classes("text-xs text-gray-500")

            with ui.row().classes("gap-3 w-full items-center"):
                doc_in = ui.input("Ablage (Ordner/Datei)", value=values["doc_path"]
                                  ).props("dense outlined").classes("w-[420px]")

                async def _browse() -> None:
                    folder = await pick_folder()
                    if folder is not None:
                        doc_in.value = str(folder)

                ui.button("Durchsuchen…", icon="folder_open", on_click=_browse).props("outline")
            note_in = ui.textarea("Notiz", value=values["note"]
                                  ).props("dense outlined").classes("w-full")

            with ui.row().classes("mt-2"):
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _save() -> None:
                    if not (name_in.value or "").strip():
                        ui.notify("Bezeichnung fehlt", type="warning")
                        return
                    start = parse_date(start_in.value)
                    if start is None:
                        ui.notify("Beginn fehlt oder ist kein gültiges Datum "
                                  "(z. B. 19.08.2026)", type="warning")
                        return
                    first_due = parse_date(first_in.value)
                    if (first_in.value or "").strip() and first_due is None:
                        ui.notify("„Erste Zahlung“ ist kein gültiges Datum", type="warning")
                        return
                    end = parse_date(end_in.value)
                    if (end_in.value or "").strip() and end is None:
                        ui.notify("„Ende“ ist kein gültiges Datum", type="warning")
                        return
                    if end is not None and end < start:
                        ui.notify("Das Ende liegt vor dem Beginn", type="warning")
                        return
                    status = ContractStatus(status_sel.value)
                    fields = dict(
                        name=name_in.value.strip(), partner=partner_in.value or "",
                        contract_no=no_in.value or "", category_id=int(cat_sel.value),
                        amount=amount_in.amount, cycle=BillingCycle(cycle_sel.value),
                        start=start, first_due=first_due, end=end,
                        auto_renew=bool(renew_cb.value),
                        notice_months=int(notice_in.value or 0),
                        renewal_day=(int(day_in.value) if day_in.value else None),
                        renewal_month=(int(month_sel.value) or None),
                        payment_method=pay_in.value or "", status=status,
                        doc_path=(doc_in.value or "").strip(), note=note_in.value or "")
                    with get_session() as s:
                        if contract_id:
                            contract = s.get(Contract, contract_id)
                            if contract is None:
                                return
                            for key, value in fields.items():
                                setattr(contract, key, value)
                        else:
                            order = max([c.sort_order for c in s.exec(select(Contract)).all()],
                                        default=0) + 1
                            contract = Contract(sort_order=order, **fields)
                        s.add(contract)
                        s.commit()
                    recompute_all()
                    dlg.close()
                    _refresh_all()
                    if status == ContractStatus.CANCELLED and end is None:
                        ui.notify("Gespeichert — gekündigt ohne Enddatum erzeugt keine "
                                  "Kostenzellen.", type="warning")
                    else:
                        ui.notify("Vertrag gespeichert — Kostenzellen wurden erzeugt",
                                  type="positive")

                ui.button("Speichern", icon="save", on_click=_save)
        dlg.open()

    def _delete_dialog(contract_id: int, name: str) -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label(f'„{name}“ löschen?').classes("text-lg font-bold")
            ui.label("Die aus dem Vertrag erzeugten Monatswerte verschwinden damit ebenfalls; "
                     "händisch erfasste Werte in denselben Zellen bleiben erhalten."
                     ).classes("text-sm text-gray-500")
            with ui.row():
                ui.button("Abbrechen", on_click=dlg.close).props("flat")

                def _do() -> None:
                    with get_session() as s:
                        contract = s.get(Contract, contract_id)
                        if contract is not None:
                            s.delete(contract)
                            s.commit()
                    recompute_all()
                    dlg.close()
                    _refresh_all()
                    ui.notify(f'„{name}“ gelöscht', type="positive")

                ui.button("Löschen", icon="delete", color="negative", on_click=_do)
        dlg.open()

    # --- JSON import --------------------------------------------------------

    def _import_dialog() -> None:
        with ui.dialog() as dlg, ui.card().classes("min-w-[520px]"):
            ui.label("Verträge importieren").classes("text-lg font-bold")
            ui.label('JSON im Export-Format ({"Contract": [ … ]}). Die Verträge werden '
                     "ergänzt — vorhandene Daten bleiben unverändert. Verträge mit gleicher "
                     "Bezeichnung und Nummer werden übersprungen."
                     ).classes("text-xs text-gray-500")

            def _on_upload(e) -> None:
                try:
                    rows = read_contracts_payload(e.content.read())
                except ValueError as exc:
                    ui.notify(str(exc), type="negative")
                    return
                with get_session() as s:
                    imported, skipped = import_contracts(s, rows)
                recompute_all()
                dlg.close()
                _refresh_all()
                ui.notify(f"{imported} Verträge importiert"
                          + (f", {skipped} übersprungen" if skipped else ""),
                          type="positive" if imported else "warning")

            ui.upload(label="JSON-Datei wählen", auto_upload=True, on_upload=_on_upload
                      ).props("accept=.json").classes("w-full")
            ui.button("Schließen", on_click=dlg.close).props("flat").classes("self-end")
        dlg.open()

    @ui.refreshable
    def locked_cells() -> None:
        _locked_cells_hint()

    table()
    locked_cells()
    return _refresh_all


def _locked_cells_hint() -> None:
    """Show which cost cells are currently driven by contracts (read-only there)."""
    with ui.expansion("Erzeugte Kostenzellen (schreibgeschützt im Reiter Ausgaben)",
                      icon="lock").classes("w-full mt-2"):
        with get_session() as s:
            names = {c.id: c.name for c in s.exec(select(Contract)).all()}
            categories = {c.id: c.name for c in s.exec(select(CostCategory)).all()}
            lines = list(s.exec(select(CostCellEntry).where(
                CostCellEntry.contract_id != None)).all())        # noqa: E711
        if not lines:
            ui.label("Derzeit erzeugt kein Vertrag Kostenzellen.").classes(
                "text-sm text-gray-500")
            return
        by_contract: dict[int, list] = {}
        for line in lines:
            by_contract.setdefault(line.contract_id, []).append(line)
        for contract_id, entries in by_contract.items():
            entries.sort(key=lambda e: (e.year, e.month))
            months = ", ".join(f"{MONTHS_DE[e.month - 1]} {e.year}" for e in entries[:24])
            more = "" if len(entries) <= 24 else f" … (+{len(entries) - 24})"
            total = sum(e.amount for e in entries)
            category = categories.get(entries[0].category_id, "?")
            ui.label(f"{names.get(contract_id, '?')} → {category}: {months}{more} "
                     f"· Σ {eur(total, 2)}").classes("text-sm")
