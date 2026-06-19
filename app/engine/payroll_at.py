"""Austrian gross→net payroll estimate, versioned by validity period.

This is a PLANNING ESTIMATE, not a legal payroll calculation. It models the
three things a flat percentage cannot:

1. Sozialversicherung (employee share) — a fixed rate but capped at the monthly
   Höchstbeitragsgrundlage, and waived below the Geringfügigkeitsgrenze.
2. Lohnsteuer — the *progressive* annual tariff (only the slice in each bracket
   is taxed at that bracket's rate), minus the Verkehrsabsetzbetrag.
3. Sonderzahlungen (13./14. — Urlaubs-/Weihnachtsgeld) — taxed favourably: the
   first €620 is free, the rest at 6% (within the Jahressechstel); below the
   Freigrenze it is tax-free entirely.

Because the tariff is annual and the 13./14. are taxed separately, the maths is
done at the **employee-year** level and distributed back to months.

Rule values change (almost) every year; each `Ruleset` carries its validity
period and source so the active formula can be shown in the UI. Update or append
a Ruleset when the BMF/ÖGK publish new values.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Bracket:
    lower: float   # annual taxable income at which this marginal rate starts
    rate: float


@dataclass(frozen=True)
class Ruleset:
    name: str
    valid_from: date
    valid_to: date
    sv_rate: float                 # employee SV share on ongoing salary
    sv_rate_special: float         # employee SV share on Sonderzahlungen
    sv_monthly_cap: float          # Höchstbeitragsgrundlage (monthly, laufend)
    sv_special_annual_cap: float   # separate annual cap for Sonderzahlungen
    geringfuegigkeit: float        # monthly; below this, no employee SV
    brackets: tuple[Bracket, ...]  # annual Lohnsteuer tariff
    traffic_deduction: float       # Verkehrsabsetzbetrag (annual)
    special_free_amount: float     # Sonderzahlung Freibetrag (annual, e.g. 620)
    special_rate: float            # Sonderzahlung rate above the Freibetrag (6%)
    special_freigrenze: float      # below this annual Sonderzahlung total → 0% tax
    source: str


# Values per BMF (Lohnsteuertarif) and ÖGK/Sozialversicherung. See module docstring.
RULESETS: tuple[Ruleset, ...] = (
    Ruleset(
        name="Österreich 2025",
        valid_from=date(2025, 1, 1), valid_to=date(2025, 12, 31),
        sv_rate=0.1807, sv_rate_special=0.1707,
        sv_monthly_cap=6450.0, sv_special_annual_cap=12900.0, geringfuegigkeit=551.10,
        brackets=(Bracket(0, 0.0), Bracket(13308, 0.20), Bracket(21617, 0.30),
                  Bracket(35836, 0.40), Bracket(69166, 0.48), Bracket(103072, 0.50),
                  Bracket(1000000, 0.55)),
        traffic_deduction=487.0, special_free_amount=620.0, special_rate=0.06,
        special_freigrenze=2447.0, source="BMF/ÖGK 2025",
    ),
    Ruleset(
        name="Österreich 2026",
        valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31),
        sv_rate=0.1807, sv_rate_special=0.1707,
        sv_monthly_cap=6930.0, sv_special_annual_cap=13860.0, geringfuegigkeit=551.10,
        brackets=(Bracket(0, 0.0), Bracket(13539, 0.20), Bracket(21992, 0.30),
                  Bracket(36458, 0.40), Bracket(70365, 0.48), Bracket(104859, 0.50),
                  Bracket(1000000, 0.55)),
        traffic_deduction=496.0, special_free_amount=620.0, special_rate=0.06,
        special_freigrenze=2615.0, source="BMF/ÖGK 2026",
    ),
)


def ruleset_for(d: date) -> Ruleset:
    """The ruleset valid for a date; falls back to the most recent one."""
    for rs in RULESETS:
        if rs.valid_from <= d <= rs.valid_to:
            return rs
    return max(RULESETS, key=lambda r: r.valid_from)


def ruleset_for_year(year: int) -> Ruleset:
    return ruleset_for(date(year, 6, 30))


def annual_income_tax(taxable: float, brackets: tuple[Bracket, ...]) -> float:
    """Progressive Lohnsteuer on an annual taxable income (before Absetzbeträge)."""
    if taxable <= 0:
        return 0.0
    tax = 0.0
    for i, b in enumerate(brackets):
        upper = brackets[i + 1].lower if i + 1 < len(brackets) else float("inf")
        if taxable <= b.lower:
            break
        tax += (min(taxable, upper) - b.lower) * b.rate
    return tax


@dataclass
class YearResult:
    net_regular: list[float]    # per-month net of ongoing salary
    net_special: list[float]    # per-month net of Sonderzahlungen
    sv: float                   # annual employee SV (regular + special)
    tax: float                  # annual Lohnsteuer (regular + special)

    @property
    def net(self) -> list[float]:
        return [self.net_regular[m] + self.net_special[m] for m in range(12)]


def compute_year(regular: list[float], special: list[float], rs: Ruleset) -> YearResult:
    """Net of ongoing salary + Sonderzahlungen for one employee over one year."""
    # --- ongoing salary: SV per month (capped, waived below Geringfügigkeit) ----
    sv_reg = [0.0 if g < rs.geringfuegigkeit else min(g, rs.sv_monthly_cap) * rs.sv_rate
              for g in regular]
    annual_reg = sum(regular)
    annual_reg_sv = sum(sv_reg)
    annual_reg_taxable = max(0.0, annual_reg - annual_reg_sv)
    annual_reg_tax = max(0.0, annual_income_tax(annual_reg_taxable, rs.brackets)
                         - rs.traffic_deduction)
    net_reg = []
    for g, sv in zip(regular, sv_reg):
        taxable = g - sv
        share = (taxable / annual_reg_taxable) if annual_reg_taxable > 0 else 0.0
        net_reg.append(g - sv - annual_reg_tax * share)

    # --- Sonderzahlungen (13./14.): SV, then 620 free + 6% above the Freigrenze --
    annual_special = sum(special)
    sv_special = (min(annual_special, rs.sv_special_annual_cap) * rs.sv_rate_special
                  if annual_special > 0 else 0.0)
    if annual_special <= rs.special_freigrenze:
        tax_special = 0.0
    else:
        tax_special = max(0.0, annual_special - sv_special - rs.special_free_amount) * rs.special_rate
    net_special = []
    for sp in special:
        share = (sp / annual_special) if annual_special > 0 else 0.0
        net_special.append(sp - (sv_special + tax_special) * share)

    return YearResult(net_reg, net_special, annual_reg_sv + sv_special,
                      annual_reg_tax + tax_special)


@dataclass
class MonthlyCost:
    gross: list[float]     # regular + special, per month
    net: list[float]       # paid to the employee
    all_in: list[float]    # employer cost = gross * (1 + LNK)
    abgaben: list[float]   # all_in - net (to Finanzamt/ÖGK)
    sv: float
    tax: float


def employee_year_cost(regular: list[float], special: list[float], *,
                       burden_pct: float, rs: Ruleset) -> MonthlyCost:
    """Per-month employer cost / net / Abgaben for one internal employee-year."""
    yr = compute_year(regular, special, rs)
    net = yr.net
    gross = [regular[m] + special[m] for m in range(12)]
    all_in = [g * (1.0 + burden_pct) for g in gross]
    abgaben = [all_in[m] - net[m] for m in range(12)]
    return MonthlyCost(gross, net, all_in, abgaben, yr.sv, yr.tax)
