"""Keeping the books needs only the engine — never the `entity` extra. This file
poisons the `nestor` import so the *absent* branch runs on every checkout."""
from __future__ import annotations

import sys

import pytest

from homestead_ledger import nestor_seam
from homestead_ledger.cli import run_cli


@pytest.fixture(autouse=True)
def _no_nestor(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "nestor", None)
    monkeypatch.setattr(nestor_seam, "_bound", False)
    monkeypatch.setattr(nestor_seam, "_ledger_path", None)
    yield


def test_available_is_false_and_bind_degrades(tmp_path):
    assert nestor_seam.available() is False
    assert nestor_seam.bind(tmp_path) is None
    with pytest.raises(nestor_seam.SeamNotBoundError):
        nestor_seam.resolver_for("merchant", object())


def test_obligation_add_list_show_queue(capsys):
    assert run_cli(["obligation", "add", "rent", "Sunrise Properties LLC", "1450", "2099-10-01", "monthly"]) == 0
    out = capsys.readouterr().out
    assert "stored: obligations/rent" in out and "proposed" not in out
    assert run_cli(["obligation", "add", "rent", "x", "1", "2099-10-01", "monthly"]) == 1
    assert "--replace" in capsys.readouterr().err
    assert run_cli(["obligation", "add", "rent", "Sunrise", "1450", "2099-10-01", "monthly", "--replace"]) == 0
    assert "replaced" in capsys.readouterr().out

    assert run_cli(["obligation", "list"]) == 0
    out = capsys.readouterr().out
    assert "rent: Sunrise  ·  due 2099-10-01  ·  monthly  ·  a payment is due" in out
    assert "1450" not in out                                  # L4 on the list: derived only

    assert run_cli(["obligation", "show", "rent"]) == 0
    assert "[L4]  amount: 1450.00" in capsys.readouterr().out

    assert run_cli(["queue"]) == 0
    assert "rent: 2099-10-01" in capsys.readouterr().out


def test_obligation_refusals_are_one_line_each(capsys):
    assert run_cli(["obligation", "add", "rent", "a", "lots", "2099-10-01", "monthly"]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and "Traceback" not in err
    assert run_cli(["obligation", "add", "rent", "a", "1", "someday", "monthly"]) == 1
    assert run_cli(["obligation", "show", "rent"]) == 1
    assert run_cli(["obligation", "list"]) == 0
    assert "no obligations on file" in capsys.readouterr().out
    assert run_cli(["obligation"]) == 2
    assert run_cli(["obligation", "bogus"]) == 2


def test_transaction_add_and_list(capsys):
    assert run_cli(["transaction", "add", "2026-08-01", "-84.23", "Whole Foods Market",
                    "--account-number", "9821"]) == 0
    assert "on the books: checking/" in capsys.readouterr().out
    assert run_cli(["transaction", "add", "2026-08-01", "-84.23", "Whole Foods Market",
                    "--account-number", "9821"]) == 1
    assert "already on the books" in capsys.readouterr().err

    assert run_cli(["transaction", "list"]) == 0
    out = capsys.readouterr().out
    assert "description: Whole Foods Market" in out
    assert "amount: a debit is on file" in out
    assert "84.23" not in out and "9821" not in out           # L4 derived, L5 absent


def test_transaction_refusals(capsys):
    assert run_cli(["transaction", "add", "2026-08-01", "-84.23", "x"]) == 2   # no account number
    assert run_cli(["transaction", "add", "yesterday", "-84.23", "x", "--account-number", "1"]) == 1
    assert run_cli(["transaction", "add", "2026-08-01", "lots", "x", "--account-number", "1"]) == 1
    assert run_cli(["transaction", "list"]) == 0
    assert "nothing on the books" in capsys.readouterr().out


def test_put_is_retired_and_points_at_the_new_commands(capsys):
    assert run_cli(["put", "name", "x"]) == 1
    err = capsys.readouterr().err
    assert "obligation add" in err and "transaction add" in err


@pytest.mark.parametrize("argv", [
    ["resolve", "Netflix"],
    ["reconcile", "1", "2"],
    ["verify"],
])
def test_nestor_backed_commands_refuse_in_one_line_naming_the_extra(argv, capsys):
    assert run_cli(argv) == 1
    captured = capsys.readouterr()
    assert "homestead-ledger[entity]" in captured.err
    assert "Traceback" not in captured.err
