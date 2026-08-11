"""The stdlib `ttk.Style` theme (bite 3). `theme.py` reaches no tkinter name
at module scope (see its own docstring), so importing it and reading its
palette/`apply` needs no display at all; only *exercising* `apply` against a
real `Tk` root needs one, and CI has neither `tkinter` nor a display — those
cases are guarded with `pytest.importorskip("tkinter")` plus a `TclError`
skip, so they skip cleanly there instead of failing.
"""
from __future__ import annotations

import pytest

from homestead.keep.rungs import Rung

from homestead_ledger.app import theme


def test_theme_imports_cleanly_with_no_tkinter_available(monkeypatch):
    """Purge and re-import under a poisoned `tkinter`, so this fails loudly
    if a future edit promotes a tkinter import to module scope."""
    import sys

    for name in list(sys.modules):
        if name == "homestead_ledger.app.theme":
            del sys.modules[name]
    monkeypatch.setitem(sys.modules, "tkinter", None)

    import homestead_ledger.app.theme as reimported

    assert callable(reimported.apply)


def test_apply_and_helpers_are_callable():
    assert callable(theme.apply)
    assert callable(theme.rung_color)
    assert callable(theme.style_listbox)


def test_rung_color_covers_every_real_rung():
    """Every `Rung` the engine defines has a colour — a `KeyError` here means
    the engine grew a rung this theme has not caught up to."""
    for rung in Rung:
        color = theme.rung_color(rung)
        assert isinstance(color, str) and color.startswith("#")


def test_l1_is_quiet_l3_is_ink_l4_is_amber():
    """The three rungs the build plan names explicitly, pinned so a palette
    edit that quietly drops the "protected/derived draws the eye" contrast
    is a test failure, not a look-and-feel regression nobody notices."""
    assert theme.rung_color(Rung.L1) == theme.MUTED
    assert theme.rung_color(Rung.L3) == theme.INK
    assert theme.rung_color(Rung.L4) == theme.AMBER
    # L1/L3/L4 are visibly distinct from one another — the whole point of a
    # per-rung colour is that they don't collapse to the same line colour.
    assert len({theme.rung_color(Rung.L1), theme.rung_color(Rung.L3), theme.rung_color(Rung.L4)}) == 3


def test_font_preferences_is_a_nonempty_tuple_of_names():
    assert isinstance(theme.FONT_PREFERENCES, tuple)
    assert all(isinstance(name, str) and name for name in theme.FONT_PREFERENCES)


def test_apply_configures_a_real_root():
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("tkinter is importable but no display is available")
    try:
        style = theme.apply(root)
        assert isinstance(style, ttk.Style)
        assert root.cget("background") == theme.BACKGROUND
        # the clam base is used whenever the interpreter's Tk ships it —
        # every desktop Tk 8.6 does, but a minimal build might not.
        if "clam" in style.theme_names():
            assert style.theme_use() == "clam"
        # applying twice must not raise (idempotent re-`configure`).
        theme.apply(root)
    finally:
        root.destroy()


def test_style_listbox_paints_the_theme_surface_flat():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("tkinter is importable but no display is available")
    try:
        theme.apply(root)
        box = tk.Listbox(root)
        theme.style_listbox(box)
        assert box.cget("background") == theme.SURFACE
        assert box.cget("foreground") == theme.INK
        assert str(box.cget("relief")) == "flat"
        assert str(box.cget("activestyle")) == "none"
    finally:
        root.destroy()
