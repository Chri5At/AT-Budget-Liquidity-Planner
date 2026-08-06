"""German-aware amount parsing (formatting.parse_de_amount / fmt_amount).

Regression for the "3.000 → 3 €" bug: HTML number inputs read a German
thousands dot as a decimal point, so amount fields are text-based and parsed
with these rules. The JS twin lives in app/ui/grid.py (DE_NUM_PARSER).
"""
import pytest

from app.ui.formatting import fmt_amount, parse_de_amount


@pytest.mark.parametrize("text, expected", [
    # plain digits
    ("3000", 3000.0),
    ("0", 0.0),
    ("-250", -250.0),
    # German thousands dot(s)
    ("3.000", 3000.0),
    ("1.234.567", 1234567.0),
    ("-1.500", -1500.0),
    # comma decimal
    ("3,5", 3.5),
    ("5,58", 5.58),
    (",5", 0.5),
    # both: dot thousands + comma decimal
    ("3.000,50", 3000.5),
    ("1.234.567,89", 1234567.89),
    # dot NOT in groups of three stays a decimal point
    ("3.5", 3.5),
    ("3.14", 3.14),
    ("0.25", 0.25),
    ("1.2345", 1.2345),
    # noise tolerated: € sign and spaces
    ("3.000 €", 3000.0),
    (" 70 ", 70.0),
    # passthrough for numbers
    (70, 70.0),
    (5.58, 5.58),
])
def test_parse_valid(text, expected):
    assert parse_de_amount(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "   ", None, "abc", "3..5", "1,2,3"])
def test_parse_invalid_returns_none(text):
    assert parse_de_amount(text) is None


def test_fmt_amount_roundtrip():
    assert fmt_amount(3000) == "3000"
    assert fmt_amount(3000.0) == "3000"
    assert fmt_amount(5.58) == "5,58"
    assert fmt_amount(None) == ""
    for v in (0, 70, 5.58, 3000, 1234567.89):
        assert parse_de_amount(fmt_amount(v)) == pytest.approx(float(v))
