"""Copy targets of the cell detail dialog span every planning year."""
from datetime import date

from app.ui.components.cell_copy import parse_target, target_key, target_options


def test_targets_cover_following_years_and_skip_source():
    opts = target_options(2026, 7, date(2026, 7, 1), date(2027, 12, 31))
    assert target_key(2026, 7) not in opts                  # the source cell itself
    assert target_key(2026, 6) not in opts                  # before Planungsbeginn
    assert opts[target_key(2026, 8)].endswith(" 2026")
    assert target_key(2027, 7) in opts                      # same month, next year
    assert target_key(2028, 1) not in opts                  # after Planungsende
    assert len(opts) == 5 + 12
    assert list(opts) == sorted(opts)                        # date order


def test_target_key_roundtrip():
    assert parse_target(target_key(2027, 3)) == (2027, 3)
