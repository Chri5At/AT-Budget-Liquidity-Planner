"""Net-or-gross hint for € entry fields.

Every amount in the plan is the GuV figure. Whether the user has to type it
*exkl.* or *inkl.* MwSt. depends solely on the position's VAT flag
(``CostCategory.is_vatable`` / ``RevenueStream.is_vatable``) — and that flag is
set in a different place than where the number is typed. So every dialog with a
Betrag field shows the rule explicitly instead of leaving the user guessing.

Engine rule (see engine/cashflow._gross): flag on → the entered net amount is
grossed up by VAT_RATE for the cash side and the tax is settled with the
Finanzamt on the 15th of M+2; flag off → the entered amount moves 1:1.
"""
from __future__ import annotations

from nicegui import ui

from ...config import VAT_RATE

_PCT = f"{VAT_RATE * 100:.0f} %"


def amount_label(base: str, is_vatable: bool) -> str:
    """'Betrag' → 'Betrag (exkl. MwSt.)' or 'Betrag (inkl. MwSt.)'."""
    return f"{base} ({'exkl.' if is_vatable else 'inkl.'} MwSt.)"


def vat_hint_text(is_vatable: bool, *, side: str = "cost") -> tuple[str, str]:
    """(headline, explanation) for a position — `side` is 'cost' or 'revenue'."""
    if side == "revenue":
        if is_vatable:
            return (
                "Beträge exkl. MwSt. (netto) eingeben",
                f"USt ist für diese Einnahme aktiv: der Kunde zahlt brutto (+{_PCT}) in die "
                "Liquidität, die USt geht am 15. des übernächsten Monats ans Finanzamt. "
                "In der GuV steht der Nettobetrag.",
            )
        return (
            "Beträge inkl. MwSt. (= Zahlungseingang) eingeben",
            "Keine USt für diese Einnahme (z. B. Reverse Charge, ig. Lieferung, "
            "Drittland): es fließt genau der eingetragene Betrag zu, die App rechnet "
            "keine Steuer dazu oder heraus.",
        )
    if is_vatable:
        return (
            "Beträge exkl. MwSt. (netto) eingeben",
            f"Vorsteuer ist für diese Position aktiv: die Zahlung wird brutto (+{_PCT}) "
            "in die Liquidität gerechnet, die Vorsteuer kommt über die USt-Voranmeldung "
            "am 15. des übernächsten Monats zurück. In der GuV steht der Nettobetrag.",
        )
    return (
        "Beträge inkl. MwSt. (= Zahlbetrag) eingeben",
        "Kein Vorsteuerabzug für diese Position (z. B. Versicherung, Gebühren, Rechnung "
        "ohne abziehbare Vorsteuer): es fließt genau der eingetragene Betrag ab, die "
        "App rechnet keine Steuer dazu oder heraus.",
    )


def vat_flag_tooltip(side: str = "cost") -> str:
    """Tooltip for the VSt/USt checkbox that switches the rule."""
    if side == "revenue":
        return ("Umsatzsteuerpflichtig: Beträge dieser Einnahme sind exkl. MwSt.; der Kunde "
                "zahlt brutto, die USt geht ans Finanzamt. Ohne Haken: Beträge inkl. MwSt. "
                "= Zahlungseingang (Reverse Charge, ig. Lieferung, Drittland).")
    return ("Vorsteuerabzug: Beträge dieser Position sind exkl. MwSt.; die Zahlung wird "
            "brutto gerechnet und die Vorsteuer kommt zurück. Ohne Haken: Beträge inkl. "
            "MwSt. = Zahlbetrag (Versicherung, Gebühren, keine abziehbare Vorsteuer).")


def vat_banner(is_vatable: bool, *, side: str = "cost",
               where_to_change: str | None = None) -> ui.element:
    """Coloured one-glance banner: blue = netto (VAT active), amber = Zahlbetrag."""
    head, detail = vat_hint_text(is_vatable, side=side)
    tone = ("bg-blue-50 text-blue-900 border-blue-200" if is_vatable
            else "bg-amber-50 text-amber-900 border-amber-200")
    with ui.row().classes(f"items-start gap-2 w-full rounded border px-3 py-2 my-1 "
                          f"no-wrap {tone}") as box:
        ui.icon("receipt_long" if is_vatable else "payments").classes("mt-0.5 text-lg")
        with ui.column().classes("gap-0"):
            ui.label(head).classes("text-sm font-semibold")
            ui.label(detail).classes("text-xs")
            if where_to_change:
                ui.label(where_to_change).classes("text-xs opacity-70")
    return box
