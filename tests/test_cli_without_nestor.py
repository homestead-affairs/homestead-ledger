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


def test_an_unknown_account_is_refused_before_the_books_grow_one(capsys):
    """I-23: the registry is the only enumeration, and `--account` is the one
    place a person can name one. `books.import_transaction` writes whatever
    matter string it is handed, so an unvalidated flag grows a whole phantom
    account in the canonical books — rows nothing that iterates
    `all_accounts()` (the queue, the subscription pass, the window) will ever
    reach. That is BUG-6's shape with a bank statement in it."""
    rc = run_cli(["transaction", "add", "2026-08-01", "-1.00", "x",
                  "--account-number", "1", "--account", "mattress"])
    assert rc == 2                                   # a flag value, like an unknown subcommand
    err = capsys.readouterr().err
    assert "unknown account" in err and "checking" in err

    assert run_cli(["transaction", "list", "--account", "mattress"]) == 2
    capsys.readouterr()
    # nothing was written under the phantom name, and nothing under checking
    assert run_cli(["transaction", "list"]) == 0
    assert "nothing on the books" in capsys.readouterr().out


def test_an_amount_that_is_not_finite_is_refused_without_being_echoed(capsys):
    """`float("nan")` succeeds and `f"{float('nan'):.2f}"` is the string "nan".
    And I-15: the refusal names the field, never the value (an amount is L4)."""
    for bad in ("nan", "inf", "-inf"):
        assert run_cli(["transaction", "add", "2026-08-01", bad, "x",
                        "--account-number", "1"]) == 1
        err = capsys.readouterr().err
        assert "finite" in err and "Traceback" not in err

    assert run_cli(["obligation", "add", "rent", "a", "8675.309lots",
                    "2099-10-01", "monthly"]) == 1
    err = capsys.readouterr().err
    assert "8675.309" not in err and "amount" in err

    assert run_cli(["transaction", "list"]) == 0
    assert "nothing on the books" in capsys.readouterr().out


def test_transaction_list_gaps_names_unparsed_rows_by_reference(capsys):
    """fix: G2c-importer-dates — `--gaps` finds a row from before this fix
    (a date written verbatim, never parsed) by its already-served text, never
    by reaching `.payload` of its own (I-16); a row imported the normal way,
    with an ISO date, is not a gap."""
    from homestead_ledger.books import Transaction, import_transaction

    import_transaction(Transaction(
        account="checking", date="9/2/2026", amount="-20.00",
        description="Pre-fix Row", account_number="9821",
    ))
    assert run_cli(["transaction", "add", "2026-09-03", "-30.00", "Normal Row",
                    "--account-number", "9821"]) == 0
    capsys.readouterr()

    assert run_cli(["transaction", "list", "--gaps"]) == 0
    out = capsys.readouterr().out
    assert "9/2/2026" in out
    assert "date:" in out
    assert "2026-09-03" not in out                    # the normal ISO row is not a gap
    assert "Pre-fix Row" not in out and "-20.00" not in out   # L3/L4 never render

    assert run_cli(["transaction", "list"]) == 0
    out = capsys.readouterr().out
    assert "9/2/2026" in out and "2026-09-03" in out   # --gaps narrows; plain list does not


def test_gaps_is_refused_on_a_sub_command_that_is_not_list(capsys):
    """`--gaps` narrows `transaction list` and belongs to no other
    sub-command. It used to be stripped from the argument list before the
    sub-command was dispatched, so `transaction add … --gaps` wrote the row
    and reported success — a flag that looks honoured and is not."""
    from homestead_ledger.store import Canonical

    assert run_cli(["transaction", "add", "2026-09-09", "-5.00", "Gaps Flag Row",
                    "--account-number", "9821", "--gaps"]) == 2
    assert "--gaps is only for `transaction list`" in capsys.readouterr().err

    descriptions = {
        record.payload for ref, record in Canonical().records("checking")
        if ref[1] == "description"
    }
    assert "Gaps Flag Row" not in descriptions   # refused, not written anyway


def test_an_obligation_id_is_one_closed_shape(capsys):
    """The id is a key segment and a string the browser renders back; one
    closed shape, refused at the door rather than escaped at every surface."""
    assert run_cli(["obligation", "add", "a'-alert(1)-'b", "a", "1",
                    "2099-10-01", "monthly"]) == 1
    assert "refused" in capsys.readouterr().err
    assert run_cli(["obligation", "add", "Rent Account", "a", "1",
                    "2099-10-01", "monthly"]) == 1
    capsys.readouterr()
    assert run_cli(["obligation", "list"]) == 0
    assert "no obligations on file" in capsys.readouterr().out


def test_a_racing_second_add_is_refused_at_the_cli_too(capsys):
    """The same I-9 refusal an operator meets: a second `obligation add` under
    an id already on file leaves the first untouched and says how to mean it."""
    assert run_cli(["obligation", "add", "rent", "Sunrise", "1450",
                    "2099-10-01", "monthly"]) == 0
    capsys.readouterr()
    assert run_cli(["obligation", "add", "rent", "Interloper", "9999",
                    "2099-12-25", "weekly"]) == 1
    assert "--replace" in capsys.readouterr().err
    assert run_cli(["obligation", "show", "rent"]) == 0
    out = capsys.readouterr().out
    assert "name: Sunrise" in out and "Interloper" not in out
