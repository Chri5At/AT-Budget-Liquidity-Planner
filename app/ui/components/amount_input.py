"""German-aware euro amount field.

`ui.number` is an HTML number input, whose dot is ALWAYS a decimal point — a
German user typing "3.000" (three thousand) silently gets 3.0 while the field
keeps displaying "3.000". This text-based field parses German notation instead
(see formatting.parse_de_amount) and exposes the numeric value as `.amount`.
"""
from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from ..formatting import fmt_amount, parse_de_amount


class AmountInput(ui.input):
    """Text input for € amounts; read `.amount` (float) instead of `.value` (str).

    `on_amount_change` is called with the parsed float on every valid edit; an
    unparseable entry shows a validation error and keeps the last valid amount.
    """

    def __init__(self, label: str | None = None, *, value: float | None = None,
                 on_amount_change: Callable[[float], None] | None = None) -> None:
        super().__init__(label, value=fmt_amount(value),
                         validation={"Ungültige Zahl — z. B. 3.000 oder 3,5":
                                     lambda v: not v or parse_de_amount(v) is not None})
        # inputmode brings up the numeric keypad on touch devices.
        self.props("dense outlined inputmode=decimal")
        self.amount: float = float(value) if value is not None else 0.0
        self._on_amount_change = on_amount_change
        self.on_value_change(self._handle_change)

    def _handle_change(self, e) -> None:
        parsed = parse_de_amount(e.value)
        if e.value and parsed is None:
            return  # invalid — validation message is showing, keep last amount
        self.amount = parsed if parsed is not None else 0.0
        if self._on_amount_change is not None:
            self._on_amount_change(self.amount)
