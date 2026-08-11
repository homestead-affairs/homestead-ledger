"""The entry point — `--smoke` and `--demo` still work; `--help` and the
default path's headless fallback (bite 3) are ported from homestead-law's
`tests/test_main.py`.

`python -m homestead_ledger` with no recognized flag used to fall straight
through to a placeholder print (bite 0-2). Bite 3 makes the default path
`view.run()`, so this file locks in the same fix law's did: `--help` prints
usage and exits 0 without ever touching tkinter, and the default path
degrades to a one-line message and a non-zero exit rather than raising, when
the window can't be opened.
"""
from __future__ import annotations

import sys

from homestead_ledger import __main__ as entry
from homestead_ledger.__main__ import main


def test_smoke_still_exits_zero_and_imports_every_new_module(capsys):
    assert main(["--smoke"]) == 0
    out = capsys.readouterr().out
    assert "homestead-ledger ok" in out


def test_demo_exits_zero_and_prints_the_pipeline(tmp_path, monkeypatch, capsys):
    assert main(["--demo"]) == 0
    out = capsys.readouterr().out
    assert "S1_LIST" in out
    assert "S1_DETAIL" in out
    assert "cover (resting)" in out


def test_demo_prints_the_whats_due_queue_and_recurring_pass(capsys):
    """Bite 2's addition: after the books output, `--demo` prints the
    obligations queue, its resting cover, and the recurring-charge pass over
    the demo transactions."""
    assert main(["--demo"]) == 0
    out = capsys.readouterr().out
    assert "what's due" in out
    assert "overdue by" in out
    assert "recurring" in out.lower()
    # books (bite 1) prints "cover (resting)" twice (start and end of its
    # pipeline); the queue (bite 2) adds a third, independent one.
    assert out.count("cover (resting)") == 3


def test_demo_uses_its_own_throwaway_home_not_the_ambient_one(tmp_path, monkeypatch):
    """`--demo` must not write into whatever HOMESTEAD_HOME the caller
    happens to have set — it opens its own temporary root and restores
    nothing real is touched."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    main(["--demo"])
    # the ambient root the caller set is untouched — no ledger db landed there
    assert not (tmp_path / "homestead-ledger.db").exists()


def test_help_prints_usage_and_exits_zero_without_tkinter(capsys, monkeypatch):
    # If `--help` imported `homestead_ledger.app.view` (which imports tkinter
    # inside `run()`), this would blow up on a box with no tkinter — so guard
    # by making a tkinter import explode, and prove `--help` never gets there.
    monkeypatch.setitem(sys.modules, "tkinter", None)  # any import raises ImportError

    rc = entry.main(["--help"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "usage" in out
    assert "--smoke" in out
    assert "--demo" in out
    assert "--help" in out

    # -h is the same door.
    rc = entry.main(["-h"])
    assert rc == 0


def test_missing_tkinter_returns_nonzero_with_guidance(capsys, monkeypatch):
    # Simulate a Python build with no tkinter: importing it raises
    # ModuleNotFoundError(name="tkinter"), exactly what happens on most of the
    # boxes this suite runs on.
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "tkinter" or name.startswith("tkinter."):
            raise ModuleNotFoundError("No module named 'tkinter'", name="tkinter")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    rc = entry.main([])

    assert isinstance(rc, int)
    assert rc != 0
    err = capsys.readouterr().err
    assert "--demo" in err
    assert "--smoke" in err


def test_no_display_returns_nonzero_with_guidance(capsys, monkeypatch):
    # tkinter is importable, but opening a window fails the way it does on a
    # headless server/container: TclError "couldn't connect to display". Stub
    # tkinter itself so this doesn't require tkinter to actually be installed
    # (most boxes this suite runs on don't have it) — only that `__main__`
    # catches whatever class its own `import tkinter; tkinter.TclError` is.
    import types

    fake_tkinter = types.ModuleType("tkinter")

    class FakeTclError(Exception):
        pass

    fake_tkinter.TclError = FakeTclError
    monkeypatch.setitem(sys.modules, "tkinter", fake_tkinter)

    def fake_run() -> int:
        raise FakeTclError('couldn\'t connect to display ""')

    monkeypatch.setattr("homestead_ledger.app.view.run", fake_run)

    rc = entry.main([])

    assert isinstance(rc, int)
    assert rc != 0
    err = capsys.readouterr().err
    assert "--demo" in err
    assert "--smoke" in err
