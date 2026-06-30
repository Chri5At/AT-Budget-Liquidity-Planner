🇬🇧 **English** · 🇩🇪 [Deutsch](README.de.md)

# Budget & Liquidity Planner

**Free, open-source budget and liquidity planning software for Austrian
businesses.** Plan your budget, forecast cash flow (liquidity), and see your
profit & loss (P&L / GuV) in one local app — an Excel-free alternative for
financial planning. Built-in Austrian payroll, tax (ÖGK / Finanzamt) and
banking-day rules make it a fit for GmbHs, startups and small and medium-sized
businesses (KMU / SME) in Austria.

A local web app (NiceGUI + SQLite) for **budget and liquidity planning of an
Austrian company** (any legal form — GmbH, sole proprietor, etc.). It replaces
linked Excel files:
**one database is the single source of truth**, while the P&L (income statement)
and the liquidity plan are just two *views* of the same data — no fragile
cross-references, no `#REF!`.

Everything runs **locally on your machine**. No data is sent to the cloud or to
any third party.

> **About the sample data:** On first launch the app loads **entirely fictional
> demo data** (company "Muster GmbH", employees "A. Beispiel", "B. Muster" … with
> round placeholder numbers). It exists only to illustrate the app and is fully
> editable in the UI. Your real planning data lives solely in
> `data/planung.sqlite`, which is **never** committed to Git (see `.gitignore`).

> **Note:** The UI is in **German** (Austrian terminology), and the payroll/tax
> logic is **Austria-specific** (ÖGK, tax-office deadlines, Austrian public
> holidays — the federal state used for regional holidays defaults to Upper
> Austria and is configurable). For other countries these rules would need to be
> adapted.

## Quick start (Windows)

### Option A — Python + venv (standard)

```powershell
# one-time: create the virtual environment + install dependencies
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# run
.\.venv\Scripts\python run.py
```

### Option B — with uv (faster)

[uv](https://docs.astral.sh/uv/) is a modern, very fast Python package and
environment manager.

```powershell
# create the environment + install dependencies
uv venv
uv pip install -r requirements.txt
# (or, via pyproject.toml:  uv sync )

# run
uv run run.py
```

The browser opens automatically (default port **8137**, falling back to the next
free port if it is busy). On Windows you can also just double-click `start.bat`.

> **Requirement:** Python **3.11 or newer**.

## For non-technical users — standalone Windows `.exe`

Users without Python can run a **single self-contained `.exe`** that opens the app
in its own native desktop window (no browser, no console). Build it yourself:

```powershell
# from the project root, with the .venv already created (see Quick start)
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
```

This installs the build-only dependencies (PyInstaller + pywebview), then uses
`nicegui-pack` to produce **`dist\BudgetLiquidity.exe`** (~55 MB). Hand that one
file to anyone — no Python required.

- **First launch** creates a fresh database under
  `%LOCALAPPDATA%\BudgetLiquidity\` (seeded with the fictional demo data). Your
  own planning data never leaves your machine and is **not** part of the `.exe`.
- **SmartScreen:** the `.exe` is **not code-signed**, so Windows shows an
  "unrecognized app" prompt — click **More info → Run anyway**. This is expected;
  an installer or certificate would not change it (unsigned reputation builds up
  per version over time).

Pre-built releases may also be published under **[Releases](../../releases)**.

## Tabs

- **Mitarbeiter** (Employees) — add employees, edit the monthly gross-salary
  matrix (double salary in Jun/Nov = Austrian 13th/14th payment), live net/
  contributions preview.
- **Einnahmen** (Revenue) — revenue streams (product / recurring / project /
  one-off) with payment terms.
- **Kosten** (Costs) — cost categories by P&L line (materials / cost of goods /
  external services / OPEX).
- **GuV / Budget** (P&L) — contribution-margin statement (CM I/II, EBITDA, EBIT,
  EBT), calculated automatically.
- **Liquidität** (Liquidity) — cash flow in 15th-of-month / month-end buckets
  with a running balance (with & without EU funding) and a trend chart.
- **Szenarien** (Scenarios) — a base plan plus derived what-if scenarios. A
  derived scenario inherits all revenue/cost items from the base; you can switch
  individual base items on/off and add your own, then compare the effect in the
  GuV (P&L) and Liquidität tabs.
- **Einstellungen** (Settings) — split model, percentages, opening balance,
  planning horizon.

## Salary → liquidity (Austria)

Each month the gross salary is split into:
- **Net** → paid out on the **last banking day** of the month.
- **Contributions** (tax office / ÖGK) → due on the **15th of the following
  month** (moved to the previous banking day if that falls on a weekend or an
  Austrian public holiday).

Two switchable models (in Settings):
- **Fixed percentage** (default): contributions = total cost × contribution-%
  (default 30 %).
- **Accounting-accurate**: contributions = gross + employer burden − net.

## Tests

```powershell
.\.venv\Scripts\python -m pip install pytest pytest-asyncio selenium
.\.venv\Scripts\python -m pytest -q
```

Engine tests (banking-day / holiday logic, both split models, reconciliation)
plus a headless UI smoke test.

## Tech

- **Python** (local `.venv`, nothing installed globally)
- **NiceGUI** — UI in pure Python
- **SQLite** single file via **SQLModel**
- UI in German (Austrian terms); code/comments in English

## License

Released under the **[MIT License](LICENSE)** — you may **use, modify and
redistribute** the software **free of charge, including commercially**. The only
condition is that the copyright and license notice must be retained.

If you use this project or build on it, please **link back to the original
project** as the source. 🙏

© 2026 Chri5At
