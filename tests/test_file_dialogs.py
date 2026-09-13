"""Save-dialog helpers and the in-memory backup ZIP.

The dialog itself needs a native window, so these tests cover the pure parts:
the path handling around it and the payload it writes.
"""
from pathlib import Path

from app.services import data_io
from app.ui import file_dialogs as fd


def test_ensure_suffix_appends_missing_extension():
    # Windows' save dialog returns the typed name as-is when the user drops ".xlsx".
    assert fd.ensure_suffix(Path(r"C:\tmp\Export"), "x.xlsx") == Path(r"C:\tmp\Export.xlsx")


def test_ensure_suffix_keeps_existing_extension_and_dots_in_name():
    assert fd.ensure_suffix(Path(r"C:\tmp\Export.xlsx"), "x.xlsx") == Path(r"C:\tmp\Export.xlsx")
    assert fd.ensure_suffix(Path(r"C:\tmp\Q1.2027"), "x.xlsx") == Path(r"C:\tmp\Q1.2027.xlsx")


def test_our_file_filters_are_accepted_by_pywebview():
    """An invalid filter raises inside the window process, where the exception is only
    logged — the awaiting request would then hang forever instead of failing."""
    from webview.util import parse_file_type
    for f in (*fd.XLSX_TYPES, *fd.ZIP_TYPES):
        parse_file_type(f)               # raises ValueError if malformed
        assert fd.valid_filters((f,)) == (f,)
    assert fd.valid_filters(("Excel-Arbeitsmappe (*.xlsx)",)) == ()   # hyphen → dropped


def test_first_path_handles_tuple_str_and_cancel():
    assert fd._first_path((r"C:\tmp\a.xlsx",)) == Path(r"C:\tmp\a.xlsx")
    assert fd._first_path(r"C:\tmp\a.xlsx") == Path(r"C:\tmp\a.xlsx")
    assert fd._first_path(None) is None
    assert fd._first_path(()) is None


def test_no_native_window_outside_the_packaged_app():
    assert fd.native_window() is None        # → browser download fallback


class _FakeWindow:
    """Stand-in for NiceGUI's WindowProxy: create_file_dialog is a coroutine."""

    def __init__(self, answer):
        self.answer = answer
        self.kwargs = None

    async def create_file_dialog(self, **kwargs):
        self.kwargs = kwargs
        return self.answer


async def test_save_bytes_writes_to_the_chosen_path(tmp_path, monkeypatch):
    from app import config
    target = tmp_path / "Budget"                     # user typed a name without ".xlsx"
    win = _FakeWindow((str(target),))
    monkeypatch.setattr(fd, "native_window", lambda: win)
    monkeypatch.setattr(fd.ui, "notify", lambda *a, **k: None)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")

    path = await fd.save_bytes(b"xlsx-bytes", "Export.xlsx", file_types=fd.XLSX_TYPES)

    assert path == tmp_path / "Budget.xlsx"
    assert path.read_bytes() == b"xlsx-bytes"
    assert win.kwargs["save_filename"] == "Export.xlsx"
    assert win.kwargs["dialog_type"] == 30            # webview.FileDialog.SAVE
    assert config.read_config()["export_dir"] == str(tmp_path)   # remembered for next time


async def test_save_bytes_cancelled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(fd, "native_window", lambda: _FakeWindow(None))
    monkeypatch.setattr(fd.ui, "notify", lambda *a, **k: None)
    assert await fd.save_bytes(b"x", "Export.xlsx") is None
    assert list(tmp_path.iterdir()) == []


def test_export_bytes_is_a_readable_backup(tmp_path):
    from app.db import init_db
    init_db(seed=True)
    data = data_io.export_bytes()
    path = tmp_path / data_io.export_filename()
    path.write_bytes(data)                   # what save_bytes() does with the dialog's path
    manifest, payload = data_io.read_import(path.read_bytes())
    assert manifest["format"] == data_io.EXPORT_FORMAT
    assert data_io.version_relation(manifest) == "same"
    assert '"Settings"' in payload
