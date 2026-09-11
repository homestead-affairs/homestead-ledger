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


# ── a statement flag with no statement is refused, never quietly dropped ───


def test_kind_and_liability_columns_without_import_are_refused(capsys, monkeypatch):
    """Both flags describe a statement being imported. With no `--import`
    there is nothing for either to describe, and the old behaviour — fall
    through to the window — ran as though the declaration had been honoured:
    the operator who typed `--kind credit_card` got the default view and no
    word that their kind was never read. Refused by name, exit 2, and the
    window never opened."""
    opened: list[int] = []
    monkeypatch.setattr("homestead_ledger.app.view.run", lambda: opened.append(1) or 0)

    for argv in (
        ["--kind", "credit_card"],
        ["--liability-columns", "debit,credit"],
        ["--kind", "credit_card", "--liability-columns", "debit,credit"],
    ):
        assert main(argv) == 2, argv
        err = capsys.readouterr().err
        assert "--import" in err
        assert argv[0] in err
    assert opened == [], "the window opened despite an unhonoured declaration"


def test_kind_and_liability_columns_are_still_honoured_with_import(tmp_path, monkeypatch, capsys):
    """The refusal above must key on the *absence of a statement*, not on the
    flags themselves — the same flags with `--import` still reach the
    importer."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    csv_path = tmp_path / "card.csv"
    csv_path.write_text(
        "Date,Description,Debit,Credit\n2026-08-01,Hardware Store,100.00,\n"
        "2026-08-10,Payment,,40.00\n",
        "utf-8",
    )
    rc = main([
        "--import", str(csv_path), "--account-number", "4242",
        "--account", "credit_card", "--kind", "credit_card",
        "--liability-columns", "debit,credit",
    ])
    assert rc == 0
    assert "imported=2" in capsys.readouterr().out


# ── `--smoke` is the packaging proof, so it must name every runtime module ──
#
# `--smoke` is the only leg CI runs against the built PyInstaller artifact. A
# module it does not import is a module whose packaging is untested: the
# binary can ship without it and the smoke test still prints "ok". The browser
# UI (`server.py`) and the whole CLI layer were exactly that — every import in
# them unproven — until this scan.
#
# The scan is structural rather than a list to keep in step by hand: it reads
# the package directory and the `--smoke` branch out of `__main__.py` and holds
# one against the other, so a module added tomorrow is covered tomorrow.

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "homestead_ledger"

#: `__init__` is imported by importing anything at all; `__main__` is the file
#: doing the importing. Everything else under the package root is runtime.
_NOT_RUNTIME = {"__init__", "__main__"}


def _runtime_modules(pkg: Path) -> set[str]:
    return {p.stem for p in pkg.glob("*.py")} - _NOT_RUNTIME


def _smoke_imported(main_path: Path) -> set[str]:
    """Every `homestead_ledger.<name>` imported inside the `--smoke` branch.

    Reads the branch out of the AST rather than grepping the file, so a module
    merely *mentioned* in the usage text or a comment does not count as
    imported — the thing being proven is that the import runs."""
    tree = ast.parse(main_path.read_text("utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        literals = {
            c.value for c in ast.walk(node.test) if isinstance(c, ast.Constant)
        }
        if "--smoke" not in literals:
            continue
        names: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.ImportFrom) and sub.module == "homestead_ledger":
                names |= {a.name for a in sub.names}
            elif isinstance(sub, ast.Import):
                for alias in sub.names:
                    if alias.name.startswith("homestead_ledger."):
                        names.add(alias.name.split(".", 1)[1].split(".")[0])
        return names
    raise AssertionError(f"no `--smoke` branch found in {main_path}")


def _unproven(pkg: Path, main_path: Path) -> list[str]:
    return sorted(_runtime_modules(pkg) - _smoke_imported(main_path))


def test_smoke_imports_every_runtime_module():
    """Every module under `homestead_ledger/` is named in the `--smoke` import
    block, so the packaged artifact proves the whole runtime imports — not just
    the half the demo happens to touch."""
    assert _unproven(PKG, PKG / "__main__.py") == [], (
        "these modules are not imported by `--smoke`, so nothing proves they "
        "survive packaging. Add them to the `--smoke` branch of __main__.py."
    )


def test_the_smoke_import_scan_catches_an_omission(tmp_path):
    """A scan that has never fired has not been shown to check anything. Plant
    a package whose `--smoke` branch leaves one module out, and the scan must
    name it — and must not name the two that are never runtime imports."""
    pkg = tmp_path / "homestead_ledger"
    pkg.mkdir()
    for name in ("__init__", "server", "cli", "obligations"):
        (pkg / f"{name}.py").write_text("", encoding="utf-8")
    (pkg / "__main__.py").write_text(
        "def main(argv):\n"
        '    if "--smoke" in argv:\n'
        "        from homestead_ledger import cli, obligations  # noqa: F401\n"
        "        return 0\n"
        "    return 1\n",
        encoding="utf-8",
    )
    assert _unproven(pkg, pkg / "__main__.py") == ["server"]

    # and with the omission closed, the same scan is quiet — so a green result
    # means "covered", not "the scan cannot see anything".
    (pkg / "__main__.py").write_text(
        "def main(argv):\n"
        '    if "--smoke" in argv:\n'
        "        from homestead_ledger import cli, obligations, server  # noqa: F401\n"
        "        return 0\n"
        "    return 1\n",
        encoding="utf-8",
    )
    assert _unproven(pkg, pkg / "__main__.py") == []


def test_the_smoke_scan_reads_imports_not_mentions(tmp_path):
    """A module named in the usage string or a comment is not a module that
    imports — the scan must not be satisfied by prose."""
    pkg = tmp_path / "homestead_ledger"
    pkg.mkdir()
    for name in ("__init__", "server"):
        (pkg / f"{name}.py").write_text("", encoding="utf-8")
    (pkg / "__main__.py").write_text(
        'USAGE = "ui — the server, see homestead_ledger.server"\n'
        "def main(argv):\n"
        '    if "--smoke" in argv:\n'
        "        # imports homestead_ledger.server one day\n"
        "        return 0\n"
        "    return 1\n",
        encoding="utf-8",
    )
    assert _unproven(pkg, pkg / "__main__.py") == ["server"]


def test_smoke_actually_imports_the_ui_and_the_cli(tmp_path):
    """The other half of the scan: it proves the block *names* every module;
    this proves a cold interpreter *imports* them. Run in a subprocess, the way
    CI runs it against the built artifact — in-process, `from homestead_ledger
    import server` is satisfied by an attribute already on the imported package
    and would prove nothing about a fresh start."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c",
         "import sys;"
         "from homestead_ledger.__main__ import main;"
         "rc = main(['--smoke']);"
         "missing = [m for m in ('homestead_ledger.server','homestead_ledger.cli',"
         "'homestead_ledger.obligations','homestead_ledger.importer',"
         "'homestead_ledger.intake','homestead_ledger.queue',"
         "'homestead_ledger.recurring','homestead_ledger.nestor_seam',"
         "'homestead_ledger.nestor_store') if m not in sys.modules];"
         "print(rc, missing)"],
        capture_output=True, text=True,
        env={"HOMESTEAD_HOME": str(tmp_path), "PATH": "/usr/bin:/bin",
             "PYTHONPATH": ":".join(sys.path)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("0 []"), result.stdout + result.stderr
