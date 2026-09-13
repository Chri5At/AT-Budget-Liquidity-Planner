"""The net/gross hint must follow the position's VAT flag exactly — it is the
only thing that tells the user whether to type a Betrag with or without MwSt."""
from app.config import VAT_RATE
from app.ui.components.vat_hint import amount_label, vat_flag_tooltip, vat_hint_text


def test_amount_label_says_exkl_or_inkl():
    assert amount_label("Betrag", True) == "Betrag (exkl. MwSt.)"
    assert amount_label("Betrag", False) == "Betrag (inkl. MwSt.)"
    assert amount_label("Einzelwert", True).startswith("Einzelwert (")


def test_cost_hint_matches_engine_rule():
    head_on, detail_on = vat_hint_text(True, side="cost")
    head_off, detail_off = vat_hint_text(False, side="cost")
    assert "exkl. MwSt." in head_on and "inkl. MwSt." in head_off
    # the netto case names the real rate and the refund path
    assert f"{VAT_RATE * 100:.0f} %" in detail_on
    assert "Vorsteuer" in detail_on
    # the Zahlbetrag case promises that nothing is added
    assert "keine Steuer" in detail_off


def test_revenue_hint_uses_customer_wording():
    head_on, detail_on = vat_hint_text(True, side="revenue")
    head_off, detail_off = vat_hint_text(False, side="revenue")
    assert "exkl. MwSt." in head_on and "inkl. MwSt." in head_off
    assert "Kunde" in detail_on and "Finanzamt" in detail_on
    assert "Reverse Charge" in detail_off


def test_flag_tooltips_explain_both_states():
    for side in ("cost", "revenue"):
        tip = vat_flag_tooltip(side)
        assert "exkl. MwSt." in tip and "inkl. MwSt." in tip
