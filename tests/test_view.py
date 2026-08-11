"""The tkinter view stays import-clean on a headless box (bite 3).

`view.py` defers `import tkinter` to inside `run()` specifically so this
module can be imported without a display — the suite reads this file, it
does not open a window. Driving the real window is `python -m
homestead_ledger --smoke` (import-only, in CI) and the auditor's screenshot
under a virtual display; `view.run()` blocks in `root.mainloop()`, so this
suite never calls it directly.
"""
from __future__ import annotations

import ast
from pathlib import Path

VIEW = Path(__file__).resolve().parent.parent / "homestead_ledger" / "app" / "view.py"


def test_view_imports_cleanly_with_no_tkinter_available(monkeypatch):
    """Purge and re-import under a poisoned `tkinter`, so this fails loudly
    if a future edit promotes a tkinter import to module scope — exactly the
    regression law's own `__main__.py` fix exists to prevent."""
    import sys

    for name in list(sys.modules):
        if name == "homestead_ledger.app.view":
            del sys.modules[name]
    monkeypatch.setitem(sys.modules, "tkinter", None)

    import homestead_ledger.app.view as reimported

    assert callable(reimported.run)


def test_run_is_callable_and_takes_no_arguments():
    from homestead_ledger.app import view

    assert callable(view.run)
    import inspect

    assert list(inspect.signature(view.run).parameters) == []


def test_no_tkinter_import_at_module_scope_by_source_inspection():
    """A structural double-check alongside the poisoned-import test above:
    `import tkinter` (or `from tkinter import ...`) may only appear nested
    inside a function body, never at the module's own top level."""
    tree = ast.parse(VIEW.read_text("utf-8"))
    for node in tree.body:  # only the module's direct top-level statements
        if isinstance(node, ast.Import):
            names = {alias.name for alias in node.names}
            assert "tkinter" not in names, "tkinter imported at module scope"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("tkinter"), (
                "tkinter imported at module scope"
            )


# ── bite 4, piece 1 — real store vs. demo fallback (`compose_store`) ───────
#
# `compose_store()` is the seam factored out of `run()` precisely so the
# real-vs-demo decision can be driven headlessly, the same posture the rest
# of this file already takes with `run` itself: no tkinter, no display.


def test_compose_store_is_callable_with_no_arguments():
    from homestead_ledger.app import view

    assert callable(view.compose_store)
    import inspect

    assert list(inspect.signature(view.compose_store).parameters) == []


def test_compose_store_falls_back_to_demo_when_the_real_store_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead_ledger.app import view

    ledger = view.compose_store()

    assert ledger.demo is True
    assert ledger.today == view.demo.TODAY
    assert ledger.canonical.records(view.checking.ACCOUNT) != []  # the seeded demo rows


def test_compose_store_never_seeds_the_real_root_on_fallback(tmp_path, monkeypatch):
    """The real root (`tmp_path` here) is checked, found empty, and left
    exactly that way — the demo fallback seeds a *different*, fresh tmpdir,
    never this one."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead.keep.store import CANONICAL, SQLiteAdapter
    from homestead_ledger.app import view

    ledger = view.compose_store()

    assert ledger.demo is True
    # `compose_store()` redirected `HOMESTEAD_HOME` to the fallback's own
    # tmpdir; point back at the real root to inspect it directly.
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    real_adapter = SQLiteAdapter(tmp_path / "homestead-ledger.db")
    assert real_adapter.read_matter(CANONICAL, view.checking.ACCOUNT) == []


def test_compose_store_opens_the_real_store_when_it_holds_a_transaction(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    import os

    from homestead_ledger import importer
    from homestead_ledger.app import view

    csv_path = tmp_path / "statement.csv"
    csv_path.write_text(
        "Date,Description,Amount\n2026-08-01,Whole Foods Market,-84.23\n",
        encoding="utf-8",
    )
    result = importer.import_csv(csv_path, account_number="9821")
    assert result.imported == 1

    ledger = view.compose_store()

    assert ledger.demo is False
    assert ledger.canonical.records(view.checking.ACCOUNT) != []
    # the real root, not a fallback tmpdir the decision quietly redirected to
    assert os.environ["HOMESTEAD_HOME"] == str(tmp_path)


def test_compose_store_opens_the_real_store_when_only_an_obligation_exists(tmp_path, monkeypatch):
    """A real store with no transaction yet but a real sidecar obligation
    still counts as real — the fallback is for a store with nothing at all,
    not "no transactions specifically."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead.keep.rungs import Classified, Rung

    from homestead_ledger.app import view
    from homestead_ledger.store import Sidecar

    Sidecar().put("obligations", "due_date", "rent", Classified(Rung.L2, "2026-08-05"))

    ledger = view.compose_store()

    assert ledger.demo is False


def test_demo_banner_names_the_import_flag():
    from homestead_ledger.app import view

    assert "--import" in view.DEMO_BANNER
    assert "demonstration" in view.DEMO_BANNER.lower()


def test_compose_store_over_a_real_import_reflects_the_imported_rows_headless(tmp_path, monkeypatch):
    """The end-to-end proof piece 1 exists for: import a tiny statement, then
    show the composed window reflects the REAL rows the import produced —
    driven through `Window` the way the rest of this file drives the view,
    no display required."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead_ledger import importer
    from homestead_ledger.app import view
    from homestead_ledger.app.window import Window

    csv_path = tmp_path / "statement.csv"
    csv_path.write_text(
        "Date,Description,Amount\n"
        "2026-08-01,Whole Foods Market,-84.23\n"
        "2026-08-03,Employer Payroll,1500.00\n",
        encoding="utf-8",
    )
    result = importer.import_csv(csv_path, account_number="9821")
    assert result.imported == 2

    ledger = view.compose_store()
    assert ledger.demo is False

    window = Window()
    window.open_list(ledger.canonical.records(view.checking.ACCOUNT))
    texts = [row.text for row in window.rows]

    assert any("Whole Foods Market" in t for t in texts)
    assert any("Employer Payroll" in t for t in texts)
    assert any(t == "a debit is on file" for t in texts)   # amount derives (L4)
    assert any(t == "a credit is on file" for t in texts)  # the payroll credit
    assert not any("9821" in t for t in texts), "account_number (L5) must never be a row"
    assert not any("84.23" in t for t in texts), "the raw amount must never be in the list"
