"""Single source of truth for the application version and project metadata.

Keep ``__version__`` in sync with the ``[project] version`` in pyproject.toml.
Bump it following SemVer (MAJOR.MINOR.PATCH) on every released build.
"""
from __future__ import annotations

__version__ = "1.3.2"

APP_NAME = "Budget- & Liquiditätsplanung"
AUTHOR = "Chri5At"                       # GitHub handle (intentionally not a real name)
REPO_URL = "https://github.com/Chri5At/AT-Budget-Liquidity-Planner"
LICENSE = "MIT"
