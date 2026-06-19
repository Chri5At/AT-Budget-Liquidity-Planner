"""Enumerations used across the data model.

All enums are str-based so they serialise cleanly to SQLite and to the UI.
"""
from __future__ import annotations

from enum import Enum


class RevenueType(str, Enum):
    PRODUCT = "product"      # driver-based: units * unit_price
    RECURRING = "recurring"  # monthly fee (e.g. licence, support)
    PROJECT = "project"      # per customer/project
    ONEOFF = "oneoff"        # one-off (e.g. fundings / EU grants)


class PnlLine(str, Enum):
    """Which P&L block a cost rolls into."""
    MATERIAL = "material"
    COGS = "cogs"                      # Wareneinsatz
    EXTERNAL_SERVICES = "external"     # Bezogene Leistungen
    OPEX = "opex"                      # Sonstige betriebliche Aufwendungen


class OpexCategory(str, Enum):
    IT = "IT"
    MAINTENANCE = "Wartung"
    OPERATING = "Betriebskosten"
    INSURANCE = "Versicherungen"
    VEHICLE = "Fahrzeug"
    TELECOM = "Telefon/Internet"
    RENT = "Miete"
    TRAVEL = "Reisekosten"
    TRAINING = "Aus-/Weiterbildung"
    OFFICE = "Büro/Verwaltung"
    BANKFEES = "Geldverkehr"
    MARKETING = "Marketing/PR"
    LEGAL = "Rechts-/Beratung"
    OTHER = "Sonstiges"


class CashflowKind(str, Enum):
    SALARY_NET = "salary_net"
    SALARY_ABGABEN = "salary_abgaben"
    CONTRACTOR = "contractor"
    REVENUE_IN = "revenue_in"
    COST_OUT = "cost_out"
    COGS_OUT = "cogs_out"
    AUTHORITY_VAT = "authority_vat"
    FUNDING_IN = "funding_in"
    LOAN_IN = "loan_in"
    LOAN_REPAY = "loan_repay"
    INTEREST_OUT = "interest_out"
    INVESTMENT_IN = "investment_in"   # capital paid in by an investor


class SplitModel(str, Enum):
    FIXED_PCT = "fixed_pct"     # model A: Abgaben = all_in * abgaben_pct
    ACCOUNTING = "accounting"   # model B: Abgaben = all_in - net(=gross*net_pct)


class PaymentTerm(str, Enum):
    SOFORT = "sofort"
    NET15 = "net15"
    NET30 = "net30"
    NET45 = "net45"


class LoanKind(str, Enum):
    EU_FUNDING = "eu_funding"
    OWNER_LOAN = "owner_loan"
    GF_LOAN = "gf_loan"
    BANK_LOAN = "bank_loan"


TERM_DAYS = {
    PaymentTerm.SOFORT: 0,
    PaymentTerm.NET15: 15,
    PaymentTerm.NET30: 30,
    PaymentTerm.NET45: 45,
}

# German labels for UI selects.
REVENUE_TYPE_DE = {
    RevenueType.PRODUCT: "Produkt (Menge × Preis)",
    RevenueType.RECURRING: "Wiederkehrend",
    RevenueType.PROJECT: "Projekt / Kunde",
    RevenueType.ONEOFF: "Einmalig / Förderung",
}
PNL_LINE_DE = {
    PnlLine.MATERIAL: "Material",
    PnlLine.COGS: "Wareneinsatz",
    PnlLine.EXTERNAL_SERVICES: "Bezogene Leistungen",
    PnlLine.OPEX: "Sonstige betriebl. Aufwendungen",
}
SPLIT_MODEL_DE = {
    SplitModel.FIXED_PCT: "Fixer Prozentsatz (Standard)",
    SplitModel.ACCOUNTING: "Buchhalterisch genau",
}
PAYMENT_TERM_DE = {
    PaymentTerm.SOFORT: "sofort",
    PaymentTerm.NET15: "15 Tage",
    PaymentTerm.NET30: "30 Tage",
    PaymentTerm.NET45: "45 Tage",
}
LOAN_KIND_DE = {
    LoanKind.EU_FUNDING: "EU-Förderung",
    LoanKind.OWNER_LOAN: "Gesellschafterdarlehen",
    LoanKind.GF_LOAN: "GF-Darlehen",
    LoanKind.BANK_LOAN: "Bankdarlehen",
}
