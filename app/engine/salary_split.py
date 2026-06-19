"""Turn a monthly gross salary into net + Abgaben, using the chosen split model.

Model A (FIXED_PCT):   Abgaben = all_in * abgaben_pct;  net = all_in - Abgaben
Model B (ACCOUNTING):  net = gross * salary_net_pct;     Abgaben = all_in - net
where all_in = gross + employer burden (Lohnnebenkosten).

Settings provide the defaults; an Employee may override the model and the %.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models.enums import SplitModel


@dataclass
class SalarySplit:
    gross: float
    burden: float    # employer Lohnnebenkosten
    all_in: float    # gross + burden (true employer cost, = Personalaufwand)
    net: float       # paid to employee at month-end
    abgaben: float   # paid to Finanzamt/ÖGK on the 15th of the following month


def split_salary(gross: float, settings, employee=None) -> SalarySplit:
    burden = gross * settings.employer_burden_pct
    all_in = gross + burden

    model = settings.split_model
    if employee is not None and employee.split_model_override is not None:
        model = employee.split_model_override

    if model == SplitModel.FIXED_PCT:
        pct = settings.abgaben_pct
        if employee is not None and employee.abgaben_pct_override is not None:
            pct = employee.abgaben_pct_override
        abgaben = all_in * pct
        net = all_in - abgaben
    else:  # ACCOUNTING
        net = gross * settings.salary_net_pct
        abgaben = all_in - net

    return SalarySplit(gross=gross, burden=burden, all_in=all_in, net=net, abgaben=abgaben)
