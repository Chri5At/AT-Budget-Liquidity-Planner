"""Sanity checks for the Austrian gross->net payroll estimate."""
from app.engine.payroll_at import (
    annual_income_tax,
    compute_year,
    employee_year_cost,
    ruleset_for_year,
)

RS = ruleset_for_year(2026)


def test_ruleset_selection():
    assert ruleset_for_year(2026).name == "Österreich 2026"
    assert ruleset_for_year(2025).name == "Österreich 2025"
    # Unknown future year falls back to the most recent ruleset.
    assert ruleset_for_year(2030).name == "Österreich 2026"


def test_progressive_tariff_only_taxes_the_slice():
    # 30,000 annual taxable: 20% on (21992-13539) + 30% on (30000-21992).
    expected = (21992 - 13539) * 0.20 + (30000 - 21992) * 0.30
    assert round(annual_income_tax(30000, RS.brackets), 2) == round(expected, 2)
    # Below the first bracket -> no tax.
    assert annual_income_tax(10000, RS.brackets) == 0.0


def test_geringfuegig_pays_no_employee_sv():
    res = compute_year([500.0] * 12, [0.0] * 12, RS)
    # Below Geringfügigkeitsgrenze and below the tax-free threshold -> net == gross.
    assert round(sum(res.net), 2) == round(500.0 * 12, 2)
    assert res.sv == 0.0 and res.tax == 0.0


def test_net_below_gross_and_consistent():
    res = compute_year([3000.0] * 12, [0.0] * 12, RS)
    annual_net = sum(res.net)
    annual_gross = 3000.0 * 12
    assert 0 < annual_net < annual_gross
    # net == gross - SV - tax
    assert round(annual_gross - res.sv - res.tax, 2) == round(annual_net, 2)


def test_sonderzahlung_taxed_at_six_percent():
    # Big enough 13./14. to clear the Freigrenze, no ongoing salary to isolate it.
    res = compute_year([0.0] * 12, [5000.0 if m in (5, 10) else 0.0 for m in range(12)], RS)
    special = 5000.0 * 2
    sv = special * RS.sv_rate_special
    tax = (special - sv - RS.special_free_amount) * RS.special_rate
    assert round(sum(res.net_special), 2) == round(special - sv - tax, 2)


def test_employee_year_cost_reconciles():
    mc = employee_year_cost([5000.0] * 12, [5000.0 if m in (5, 10) else 0.0 for m in range(12)],
                            burden_pct=0.30, rs=RS)
    for m in range(12):
        # all_in = gross*(1+LNK); abgaben = all_in - net, all per month.
        assert round(mc.all_in[m], 2) == round(mc.gross[m] * 1.30, 2)
        assert round(mc.abgaben[m] + mc.net[m], 2) == round(mc.all_in[m], 2)
    # Higher earner: effective net rate clearly below 100% (progressive bite).
    assert sum(mc.net) < sum(mc.gross) * 0.75
