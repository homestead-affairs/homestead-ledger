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
