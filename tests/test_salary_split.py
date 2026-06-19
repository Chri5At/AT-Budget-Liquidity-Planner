"""Both salary split models."""
from app.engine.salary_split import split_salary
from app.models import Settings, SplitModel


def test_fixed_pct_model():
    st = Settings(split_model=SplitModel.FIXED_PCT, abgaben_pct=0.30, employer_burden_pct=0.30)
    sp = split_salary(6540.0, st)
    assert round(sp.burden) == round(6540 * 0.30)
    assert round(sp.all_in) == round(6540 * 1.30)              # 8502
    assert round(sp.abgaben) == round(sp.all_in * 0.30)
    assert round(sp.net + sp.abgaben) == round(sp.all_in)      # net + Abgaben == all-in


def test_accounting_model():
    st = Settings(split_model=SplitModel.ACCOUNTING, salary_net_pct=0.55, employer_burden_pct=0.30)
    sp = split_salary(6540.0, st)
    assert round(sp.net) == round(6540 * 0.55)
    assert round(sp.abgaben) == round(sp.all_in - sp.net)
    assert round(sp.net + sp.abgaben) == round(sp.all_in)


def test_employee_override_pct():
    from app.models import Employee
    st = Settings(split_model=SplitModel.FIXED_PCT, abgaben_pct=0.30, employer_burden_pct=0.30)
    emp = Employee(name="x", abgaben_pct_override=0.40)
    sp = split_salary(1000.0, st, emp)
    assert round(sp.abgaben) == round(sp.all_in * 0.40)
