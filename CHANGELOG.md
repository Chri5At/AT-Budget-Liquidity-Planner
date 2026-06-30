# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-28

First publicly distributable release: a standalone Windows app you can hand to
non-technical users.

### Added
- **Standalone Windows `.exe`** built with `nicegui-pack` (PyInstaller), opening
  in a native desktop window. Austrian red-white-red app icon.
- **About dialog** (header ℹ button) showing version, author, repository and the
  MIT licence.
- **Data management** (Settings → Daten):
  - **Export** all data to a timestamped ZIP backup (records the app version it
    was created with).
  - **Import** a ZIP backup; the current plan is snapshotted first as a safety
    net, and a version mismatch is detected and reported.
  - **Change the data directory** — relocate the database to a folder of your
    choice; the database is rebound live without a restart.
- Database is stored in a stable per-user location (`%LOCALAPPDATA%`) for the
  packaged build, so data survives restarts and updates.
- Application versioning via a single source of truth (`app/version.py`).

### Fixed
- Native window: the left navigation drawer no longer collapses into an
  unrecoverable mobile overlay; the window opens in desktop layout.
- Tables on every page now fill the available width with a readable minimum
  column width and re-flow on window resize (no more columns crushed to the
  left with an empty right half).
