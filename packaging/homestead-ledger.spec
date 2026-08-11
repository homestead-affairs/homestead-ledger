# PyInstaller spec — one file, one window, no console.
# -*- mode: python ; coding: utf-8 -*-
#
# Mirrors the engine's `packaging/homestead.spec` (`homestead/packaging/`):
# same shape, only the entry point and the artifact name change.

a = Analysis(
    ["../homestead_ledger/__main__.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    # NO excludes. The engine's first spec excluded http/socket/ssl/urllib/
    # email/xmlrpc on the principle that a no-egress app never dials — and
    # produced a binary that died on startup with ModuleNotFoundError:
    # urllib, because `pathlib` does `from urllib.parse import
    # quote_from_bytes` at module level and every module imports pathlib. A
    # principled-looking exclusion list that ships a non-starting artifact is
    # worse than none.
    #
    # I-17 (no egress) is enforced where it belongs — an AST scan over our
    # own source (tests/test_no_egress.py) — not by amputating the standard
    # library underneath us. What the interpreter imports for its own
    # plumbing is not this application dialling out.
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="HomesteadLedger",
    console=False,          # it is an app, not a terminal program
    disable_windowed_traceback=False,
    upx=False,
)
