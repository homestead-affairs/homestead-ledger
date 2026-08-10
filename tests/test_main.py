"""The entry point — `--smoke` still works, and `--demo` composes headless.
"""
from __future__ import annotations

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


def test_demo_uses_its_own_throwaway_home_not_the_ambient_one(tmp_path, monkeypatch):
    """`--demo` must not write into whatever HOMESTEAD_HOME the caller
    happens to have set — it opens its own temporary root and restores
    nothing real is touched."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    main(["--demo"])
    # the ambient root the caller set is untouched — no ledger db landed there
    assert not (tmp_path / "homestead-ledger.db").exists()


def test_no_args_does_not_crash():
    assert main([]) == 0
