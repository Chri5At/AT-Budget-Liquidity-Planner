"""Shared ag-Grid sizing so values stay readable on every page.

The problem this solves: value columns used to have fixed pixel widths, so on a
wide window they bunched up on the left (empty space on the right, the pinned
total column stranded far away), while on a narrow window they could shrink until
the numbers were unreadable.

`fit_grid()` rewrites every *value* column (a non-pinned `numericColumn`) to:

- **flex** — share the available width, so the columns always fill the grid and
  re-flow automatically when the window is resized (no `sizeColumnsToFit` needed);
- **minWidth** — a readable floor derived from the *largest value actually in the
  column*, so a big number widens its column instead of being clipped, and a
  small window scrolls horizontally instead of crushing the cells.

Pinned columns (labels on the left, totals on the right) and columns explicitly
marked `suppressSizeToFit` keep their fixed widths.

Column groups (`children`) are flattened, so grouped value columns flex too. NiceGUI
only detects `flex` on top-level columns when deciding whether to add its own
`autoSizeStrategy`; with groups, pass `auto_size_columns=False` to `ui.aggrid` or
the grid renders blank.
"""
from __future__ import annotations

# German-aware amount parser for editable grid cells — the JS twin of
# formatting.parse_de_amount (keep the two heuristics in sync). Plain
# Number("3.000") would read a German thousands dot as a decimal point.
DE_NUM_PARSER = (
    "params => {"
    " let s = String(params.newValue ?? '').trim().replace(/[€\\s\\u00a0]/g, '');"
    " if (!s) return 0;"
    " if (s.includes('.') && s.includes(',')) s = s.replace(/\\./g, '').replace(',', '.');"
    " else if (s.includes(',')) s = s.replace(',', '.');"
    " else if (/^-?\\d{1,3}(\\.\\d{3})+$/.test(s)) s = s.replace(/\\./g, '');"
    " const n = Number(s);"
    " return isNaN(n) ? 0 : n; }")

# Readable floor for a money cell, and a rough character-width model used to grow
# the floor so the widest value in a column is never truncated.
_VALUE_FLOOR = 96     # px — comfortably fits values up to ~99.999 €
_PX_PER_CHAR = 8      # px per glyph at the grid's font size
_CELL_PADDING = 24    # px — left/right cell padding + a little headroom


def _money_min_width(max_abs: float) -> int:
    """A minWidth (px) that fits the widest de-DE formatted value in the column."""
    n = abs(int(max_abs or 0))
    digits = len(f"{n:,}")            # 1,234,567 → 9 chars, same as de-DE "1.234.567"
    chars = digits + 2               # headroom for a " €" suffix or a leading sign
    return max(_VALUE_FLOOR, chars * _PX_PER_CHAR + _CELL_PADDING)


def _leaf_columns(cols: list[dict]) -> list[dict]:
    """Flatten ag-Grid column groups (`children`) down to the leaf columns."""
    out: list[dict] = []
    for col in cols:
        if "children" in col:
            out.extend(_leaf_columns(col["children"]))
        else:
            out.append(col)
    return out


def fit_grid(options: dict) -> dict:
    """Make value columns flex to fill the width with a readable minimum.

    Mutates and returns the ag-Grid `options` dict so call sites can simply wrap
    their literal: ``ui.aggrid(fit_grid({...}))``.
    """
    rows = (options.get("rowData") or []) + (options.get("pinnedBottomRowData") or [])
    for col in _leaf_columns(options.get("columnDefs") or []):
        field = col.get("field")
        if not field or col.get("pinned") or col.get("suppressSizeToFit"):
            continue
        if col.get("type") != "numericColumn":
            continue
        max_abs = 0.0
        for r in rows:
            v = r.get(field)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                max_abs = max(max_abs, abs(v))
        col["flex"] = 1
        col["minWidth"] = _money_min_width(max_abs)
        col.pop("width", None)       # let flex own the width

    # flex already fills the grid and re-flows on resize; a sizeColumnsToFit
    # handler or a global opt-out would fight it.
    options.pop(":onGridSizeChanged", None)
    options.pop("suppressSizeToFit", None)
    default_col = options.get("defaultColDef")
    if isinstance(default_col, dict):
        default_col.pop("suppressSizeToFit", None)
    return options
