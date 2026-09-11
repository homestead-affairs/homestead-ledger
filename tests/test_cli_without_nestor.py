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


def _add_account(label="chk-t", kind="checking", number="9821"):
    rc = run_cli(["account", "add", label, "--kind", kind, "--number", number])
    assert rc == 0
    return label


def test_account_add_list_show(capsys):
    assert run_cli(["account", "add", "chk-main", "--kind", "checking", "--number", "9821"]) == 0
    out = capsys.readouterr().out
    assert "stored: accounts/chk-main" in out
    assert "9821" not in out                        # the number never echoes (I-13)

    assert run_cli(["account", "add", "chk-main", "--kind", "savings", "--number", "1"]) == 1
    assert "--replace" in capsys.readouterr().err
    assert run_cli([
        "account", "add", "chk-main", "--kind", "savings", "--number", "1", "--replace",
    ]) == 0
    assert "replaced" in capsys.readouterr().out

    assert run_cli(["account", "list"]) == 0
    out = capsys.readouterr().out
    assert "chk-main: savings" in out
    assert "9821" not in out                        # the original number never echoes either

    assert run_cli(["account", "show", "chk-main"]) == 0
    out = capsys.readouterr().out
    assert "[L2]  kind: savings" in out
    assert "[L5]  number: (sealed)" in out           # the field name, never the value (I-13)
    assert "9821" not in out                          # neither number ever leaks


def test_account_label_cannot_be_a_kind_name(capsys):
    assert run_cli(["account", "add", "checking", "--kind", "checking", "--number", "1"]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and "kind" in err


def test_account_show_of_an_unknown_label(capsys):
    assert run_cli(["account", "show", "no-such-label"]) == 1
    assert "no such account" in capsys.readouterr().err


def test_transaction_add_and_list(capsys):
    label = _add_account()
    capsys.readouterr()
    assert run_cli(["transaction", "add", "2026-08-01", "-84.23", "Whole Foods Market",
                    "--account", label]) == 0
    assert f"on the books: {label}/" in capsys.readouterr().out
    assert run_cli(["transaction", "add", "2026-08-01", "-84.23", "Whole Foods Market",
                    "--account", label]) == 1
    assert "already on the books" in capsys.readouterr().err

    assert run_cli(["transaction", "list", "--account", label]) == 0
    out = capsys.readouterr().out
    assert "description: Whole Foods Market" in out
    assert "amount: a debit is on file" in out
    assert "84.23" not in out and "9821" not in out           # L4 derived, L5 absent


def test_transaction_refusals(capsys):
    label = _add_account()
    capsys.readouterr()
    assert run_cli(["transaction", "add", "2026-08-01", "-84.23", "x"]) == 2   # no --account
    assert run_cli(["transaction", "add", "yesterday", "-84.23", "x", "--account", label]) == 1
    assert run_cli(["transaction", "add", "2026-08-01", "lots", "x", "--account", label]) == 1
    assert run_cli(["transaction", "list", "--account", label]) == 0
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
    """Bite 2b: `--account` is the one place a person can name an instance.
    `books.import_transaction` writes whatever matter string it is handed,
    so an unvalidated flag grows a whole phantom matter in the canonical
    books — rows nothing that iterates `accounts.instances()` (the queue,
    the subscription pass, the window) will ever reach. That is BUG-6's
    shape with a bank statement in it."""
    rc = run_cli(["transaction", "add", "2026-08-01", "-1.00", "x", "--account", "mattress"])
    assert rc == 2                                   # a flag value, like an unknown subcommand
    err = capsys.readouterr().err
    assert "unknown account" in err and "mattress" in err

    assert run_cli(["transaction", "list", "--account", "mattress"]) == 2
    capsys.readouterr()
    # nothing was written under the phantom label
    assert run_cli(["transaction", "list", "--account", "mattress"]) == 2


def test_an_amount_that_is_not_finite_is_refused_without_being_echoed(capsys):
    """`float("nan")` succeeds and `f"{float('nan'):.2f}"` is the string "nan".
    And I-15: the refusal names the field, never the value (an amount is L4)."""
    label = _add_account()
    capsys.readouterr()
    for bad in ("nan", "inf", "-inf"):
        assert run_cli(["transaction", "add", "2026-08-01", bad, "x", "--account", label]) == 1
        err = capsys.readouterr().err
        assert "finite" in err and "Traceback" not in err

    assert run_cli(["obligation", "add", "rent", "a", "8675.309lots",
                    "2099-10-01", "monthly"]) == 1
    err = capsys.readouterr().err
    assert "8675.309" not in err and "amount" in err

    assert run_cli(["transaction", "list", "--account", label]) == 0
    assert "nothing on the books" in capsys.readouterr().out


def test_transaction_list_gaps_names_unparsed_rows_by_reference(capsys):
    """fix: G2c-importer-dates — `--gaps` finds a row from before this fix
    (a date written verbatim, never parsed) by its already-served text, never
    by reaching `.payload` of its own (I-16); a row imported the normal way,
    with an ISO date, is not a gap."""
    from homestead_ledger.books import Transaction, import_transaction

    label = _add_account()
    capsys.readouterr()
    import_transaction(Transaction(
        account=label, kind="checking", date="9/2/2026", amount="-20.00",
        description="Pre-fix Row",
    ))
    assert run_cli(["transaction", "add", "2026-09-03", "-30.00", "Normal Row",
                    "--account", label]) == 0
    capsys.readouterr()

    assert run_cli(["transaction", "list", "--account", label, "--gaps"]) == 0
    out = capsys.readouterr().out
    assert "9/2/2026" in out
    assert "date:" in out
    assert "2026-09-03" not in out                    # the normal ISO row is not a gap
    assert "Pre-fix Row" not in out and "-20.00" not in out   # L3/L4 never render

    assert run_cli(["transaction", "list", "--account", label]) == 0
    out = capsys.readouterr().out
    assert "9/2/2026" in out and "2026-09-03" in out   # --gaps narrows; plain list does not


def test_gaps_is_refused_on_a_sub_command_that_is_not_list(capsys):
    """`--gaps` narrows `transaction list` and belongs to no other
    sub-command. It used to be stripped from the argument list before the
    sub-command was dispatched, so `transaction add … --gaps` wrote the row
    and reported success — a flag that looks honoured and is not."""
    from homestead_ledger.store import Canonical

    label = _add_account()
    capsys.readouterr()
    assert run_cli(["transaction", "add", "2026-09-09", "-5.00", "Gaps Flag Row",
                    "--account", label, "--gaps"]) == 2
    assert "--gaps is only for `transaction list`" in capsys.readouterr().err

    descriptions = {
        record.payload for ref, record in Canonical().records(label)
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


# ── bite 2b, audit: a retired flag is refused, never written into the books ──

_NUMBER_PLANT = "4111222233334444"


def test_a_retired_flag_on_transaction_add_is_refused_and_never_reaches_a_row(capsys):
    """`transaction add`'s description is positional — everything from the
    third argument on is joined into it — so a flag this bite retired is not
    merely ignored, it is written into the books as part of the payee.

    `--account-number 4111…` landed the bank-issued number in the row's
    **L3** `description`, where `transaction list` renders it in full: the
    one crossing I-43 ("an account number lives in exactly one record") and
    I-13 ("L5 has no override anywhere") exist to stop, reached by typing
    the flag the README documented until this bite. `__main__.py` refused
    both flags on the `--import` path already, but that check sits *after*
    the sub-command routing, so `transaction add` never saw it.
    """
    from homestead_ledger.store import Canonical

    label = _add_account("visa-chase", "credit_card", _NUMBER_PLANT)
    capsys.readouterr()

    for retired in ("--account-number", "--kind"):
        argv = ["transaction", "add", "2026-08-01", "-1.00", "Coffee",
                "--account", label, retired, _NUMBER_PLANT]
        assert run_cli(argv) == 2, argv
        err = capsys.readouterr().err
        assert retired in err and "retired" in err
        assert "account add" in err
        # I-15: the refusal names the flag, never the value it was given
        assert _NUMBER_PLANT not in err

    # …and no row was written at all, so nothing carries the plant
    assert Canonical().records(label) == []

    # the same flag with no --account at all is still refused by name,
    # rather than falling through to the bare usage
    assert run_cli(["transaction", "add", "2026-08-01", "-1.00", "Coffee",
                    "--account-number", _NUMBER_PLANT]) == 2
    assert "retired" in capsys.readouterr().err


def test_an_unrecognized_flag_on_transaction_add_is_refused_not_joined_in(capsys):
    """The general case behind the retired two: any leftover `--flag` would
    be joined into the description. Refused by name with the usage, and the
    books stay empty — the same posture `--gaps` on `transaction add`
    already takes."""
    from homestead_ledger.store import Canonical

    label = _add_account()
    capsys.readouterr()
    assert run_cli(["transaction", "add", "2026-08-01", "-1.00", "Coffee",
                    "--account", label, "--bogus", "x"]) == 2
    err = capsys.readouterr().err
    assert "--bogus" in err and "usage:" in err
    assert Canonical().records(label) == []


def test_naming_a_kind_where_a_label_belongs_points_somewhere_that_works(capsys):
    """An operator coming from before this bite types `--account checking`,
    the only spelling that ever worked. The refusal used to answer "`account
    add checking --kind K --number N` first" — and `account add checking` is
    itself refused, because a label may never equal a kind name. A refusal
    that routes to a refusal is a dead end (I-11 asks for a refusal *by
    name*, which means one the household can act on)."""
    for kind in ("checking", "credit_card"):
        assert run_cli(["transaction", "list", "--account", kind]) == 2
        err = capsys.readouterr().err
        assert "kind" in err
        assert f"--kind {kind}" in err          # the way out, not `account add <kind>`
        assert f"account add {kind} " not in err


# ── bite 4: `transaction tag` — the household's own layer, by reference ────

def _add_transaction(label, *, date="2026-08-01", amount="-84.23", description="Whole Foods Market"):
    from homestead_ledger.books import Transaction, import_transaction
    return import_transaction(Transaction(
        account=label, kind="checking", date=date, amount=amount, description=description,
    ))


def test_transaction_tag_category_and_list_shows_it(capsys):
    label = _add_account()
    fp = _add_transaction(label)
    capsys.readouterr()

    assert run_cli(["transaction", "tag", fp, "--category", "groceries"]) == 0
    out = capsys.readouterr().out
    assert "tagged: overlay/" in out and "category" in out

    assert run_cli(["transaction", "list", "--account", label]) == 0
    assert "category: groceries" in capsys.readouterr().out


def test_transaction_tag_protected_category_and_note_derive_never_the_content(capsys):
    label = _add_account()
    fp = _add_transaction(label)
    capsys.readouterr()

    assert run_cli(["transaction", "tag", fp, "--category", "medical-copay",
                    "--note", "call the bank"]) == 0
    capsys.readouterr()
    assert run_cli(["transaction", "list", "--account", label]) == 0
    out = capsys.readouterr().out
    assert "a category is on file" in out and "a note is on file" in out
    assert "medical-copay" not in out and "call the bank" not in out


def test_transaction_tag_do_not_use_marks_by_reference(capsys):
    label = _add_account()
    fp = _add_transaction(label)
    capsys.readouterr()

    assert run_cli(["transaction", "tag", fp, "--do-not-use"]) == 0
    capsys.readouterr()
    assert run_cli(["transaction", "list", "--account", label]) == 0
    out = capsys.readouterr().out
    assert "do-not-use" in out
    assert "-84.23" not in out and "84.23" not in out


def test_transaction_tag_unknown_fingerprint_is_refused_by_name(capsys):
    _add_account()
    assert run_cli(["transaction", "tag", "0" * 64, "--category", "groceries"]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and "no such transaction" in err


def test_transaction_tag_twice_without_replace_is_refused(capsys):
    label = _add_account()
    fp = _add_transaction(label)
    capsys.readouterr()
    assert run_cli(["transaction", "tag", fp, "--category", "groceries"]) == 0
    capsys.readouterr()
    assert run_cli(["transaction", "tag", fp, "--category", "dining"]) == 1
    err = capsys.readouterr().err
    assert "already tagged" in err and "--replace" in err

    assert run_cli(["transaction", "tag", fp, "--category", "dining", "--replace"]) == 0
    assert "tagged" in capsys.readouterr().out


def test_transaction_tag_with_nothing_given_is_refused(capsys):
    label = _add_account()
    fp = _add_transaction(label)
    capsys.readouterr()
    assert run_cli(["transaction", "tag", fp]) == 1
    assert "refused" in capsys.readouterr().err


def test_transaction_tag_refusal_never_echoes_the_row(capsys):
    label = _add_account()
    fp = _add_transaction(label, description="Very Secret Payee", amount="-999.99")
    capsys.readouterr()
    assert run_cli(["transaction", "tag", fp, "--category", "Not Valid"]) == 1
    err = capsys.readouterr().err
    assert "Very Secret Payee" not in err and "999.99" not in err
