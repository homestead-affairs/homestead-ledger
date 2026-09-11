"""The CSV importer — bite 4's first slice: header auto-detect, hash-dedup
(via the fingerprint seam already proven in `test_books.py`), and `--dry-run`.

Every write goes through `books.import_transaction` — the one canonical
writer (`test_invariants_chokepoint.py` enforces that structurally over this
whole package, `importer.py` included). These tests exercise the importer's
own contract on top of that: which header shape it recognizes, how it signs
a debit/credit split, that a re-import is skipped rather than duplicated,
that `--dry-run` touches no adapter at all, and that a malformed row is
counted and surfaced rather than silently dropped or guessed into a fact.

Bite fix: G2c-importer-dates adds one more contract on top of the above —
every row's date is parsed to ISO (`_row_date`) before it ever reaches
`books.Transaction`, so the fingerprint (which hashes the date string
verbatim) is computed over ISO regardless of which accepted spelling a
statement used. `BANK_DATE_FORMATS` is the closed table a slashed,
genuinely-ambiguous date needs `--bank` to resolve; without one, it is a row
error naming that `--bank` is needed, never a guess at the day/month order.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from homestead.keep.store import RecordExists

from homestead_ledger import importer
from homestead_ledger.store import Canonical

ACCOUNT_NUMBER = "9821"

_SINGLE_AMOUNT_CSV = """Date,Description,Amount
2026-08-01,Whole Foods Market,-84.23
2026-08-03,Employer Payroll,1500.00
"""

_DEBIT_CREDIT_CSV = """Date,Description,Debit,Credit
2026-08-01,Whole Foods Market,84.23,
2026-08-03,Employer Payroll,,1500.00
"""

_UNKNOWN_HEADER_CSV = """Foo,Bar,Baz
1,2,3
"""

_MALFORMED_CSV = """Date,Description,Amount
2026-08-01,Whole Foods Market,-84.23
,Missing Date,12.00
2026-08-02,Bad Amount,notanumber
2026-08-03,Employer Payroll,1500.00
"""


def _write(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


# ── header auto-detect ──────────────────────────────────────────────────────

def test_detect_format_single_amount():
    assert importer.detect_format(["Date", "Description", "Amount"]) == "single_amount"


def test_detect_format_single_amount_is_case_insensitive():
    assert importer.detect_format(["date", "DESCRIPTION", "amount"]) == "single_amount"


def test_detect_format_debit_credit():
    assert importer.detect_format(["Date", "Description", "Debit", "Credit"]) == "debit_credit"


def test_detect_format_unknown_header_raises_a_clear_error():
    with pytest.raises(ValueError, match="unrecognized|unknown|not recognized"):
        importer.detect_format(["Foo", "Bar", "Baz"])


def test_import_csv_unknown_header_raises_before_writing_anything(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "unknown.csv", _UNKNOWN_HEADER_CSV)
    with pytest.raises(ValueError):
        importer.import_csv(path, account_number=ACCOUNT_NUMBER)

    canonical = Canonical()
    assert canonical.records("checking") == []


# ── debit/credit split → correctly-signed amount strings ───────────────────

def test_debit_credit_split_produces_correctly_signed_amounts(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "debit_credit.csv", _DEBIT_CREDIT_CSV)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.imported == 2
    assert result.skipped == 0
    assert result.errors == 0

    canonical = Canonical()
    amounts = sorted(
        record.payload for ref, record in canonical.records("checking") if ref[1] == "amount"
    )
    # a debit (84.23 in the Debit column) becomes a leading '-'; a credit
    # (1500.00 in the Credit column) stays positive — books._derived_for's
    # exact convention.
    assert amounts == ["-84.23", "1500.00"]


def test_single_amount_format_passes_the_given_sign_through(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "single.csv", _SINGLE_AMOUNT_CSV)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.imported == 2

    canonical = Canonical()
    amounts = sorted(
        record.payload for ref, record in canonical.records("checking") if ref[1] == "amount"
    )
    assert amounts == ["-84.23", "1500.00"]


# ── idempotency — re-import is skipped, not duplicated ──────────────────────

def test_reimporting_the_same_file_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "single.csv", _SINGLE_AMOUNT_CSV)

    first = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert first.imported == 2
    assert first.skipped == 0
    assert first.errors == 0

    second = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert second.imported == 0
    assert second.skipped == 2
    assert second.errors == 0

    # exactly one copy on the books — four fields per transaction, two
    # transactions, not eight-times-two.
    canonical = Canonical()
    dates = [ref for ref, record in canonical.records("checking") if ref[1] == "date"]
    assert len(dates) == 2


# ── --dry-run writes nothing ────────────────────────────────────────────────

def test_dry_run_writes_nothing_and_reports_what_would_import(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "single.csv", _SINGLE_AMOUNT_CSV)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER, dry_run=True)
    assert result.imported == 2
    assert result.skipped == 0
    assert result.errors == 0

    canonical = Canonical()
    assert canonical.records("checking") == []


def test_dry_run_touches_no_adapter(tmp_path, monkeypatch):
    """A stricter form of the above: even the *attempt* to write must not
    happen. Patch `books.import_transaction` to blow up if called at all, and
    prove a dry run never calls it."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "single.csv", _SINGLE_AMOUNT_CSV)

    def _boom(*args, **kwargs):
        raise AssertionError("dry_run must not call books.import_transaction")

    monkeypatch.setattr("homestead_ledger.books.import_transaction", _boom)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER, dry_run=True)
    assert result.imported == 2


# ── malformed rows — counted, surfaced, never crash, never a partial fact ──

def test_malformed_rows_are_counted_as_errors_and_do_not_crash(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "malformed.csv", _MALFORMED_CSV)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.imported == 2
    assert result.errors == 2
    assert result.skipped == 0
    assert len(result.error_messages) == 2
    err = capsys.readouterr().err
    assert err  # a stderr line for each unparseable row

    # the two good rows landed; the two bad ones left no partial trace.
    canonical = Canonical()
    dates = [record.payload for ref, record in canonical.records("checking") if ref[1] == "date"]
    assert sorted(dates) == ["2026-08-01", "2026-08-03"]


def test_missing_amount_in_debit_credit_row_is_an_error_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    csv_text = "Date,Description,Debit,Credit\n2026-08-01,No Amount At All,,\n"
    path = _write(tmp_path, "no_amount.csv", csv_text)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.imported == 0
    assert result.errors == 1


def test_non_numeric_amount_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    csv_text = "Date,Description,Amount\n2026-08-01,Bad Row,not-a-number\n"
    path = _write(tmp_path, "bad_amount.csv", csv_text)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.imported == 0
    assert result.errors == 1


# ── the torn-write RecordExists is an error, never a silent skip (I-9) ─────

def test_torn_write_record_exists_is_surfaced_as_an_error_not_a_skip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "single.csv", _SINGLE_AMOUNT_CSV)

    def _torn(*args, **kwargs):
        raise RecordExists(
            "checking/amount/deadbeef: this field already exists but 'date' for "
            "the same transaction did not — a partial record from an earlier "
            "interrupted import, not an ordinary re-import."
        )

    monkeypatch.setattr("homestead_ledger.books.import_transaction", _torn)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.imported == 0
    assert result.skipped == 0
    assert result.errors == 2
    assert len(result.error_messages) == 2


# ── the account identity is a parameter, not a per-row column ──────────────

def test_account_number_is_taken_as_a_parameter_not_a_csv_column(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "single.csv", _SINGLE_AMOUNT_CSV)

    importer.import_csv(path, account_number="1234")

    canonical = Canonical()
    numbers = {
        record.payload for ref, record in canonical.records("checking") if ref[1] == "account_number"
    }
    assert numbers == {"1234"}


# ── fix: G2c-importer-dates — dates parsed to ISO, per-bank, never guessed ──

def test_a_slashed_date_without_a_bank_is_refused_not_guessed(tmp_path, monkeypatch):
    """`08/11/2026` is genuinely ambiguous (August 11th or November 8th) and
    the engine's own parser refuses the whole slashed family for exactly that
    reason. With no `--bank` named, this module must not pick an order for
    the operator — the row is an error, and the two good rows around it still
    land."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    csv_text = (
        "Date,Description,Amount\n"
        "2026-08-01,Whole Foods Market,-84.23\n"
        "08/11/2026,Ambiguous Row,-12.00\n"
        "2026-08-03,Employer Payroll,1500.00\n"
    )
    path = _write(tmp_path, "slashed.csv", csv_text)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.imported == 2
    assert result.errors == 1
    assert "--bank" in result.error_messages[0]

    canonical = Canonical()
    dates = sorted(
        record.payload for ref, record in canonical.records("checking") if ref[1] == "date"
    )
    assert dates == ["2026-08-01", "2026-08-03"]


def test_a_bank_format_parses_to_iso_and_dedups_against_an_iso_reimport(tmp_path, monkeypatch):
    """A statement written `MM/DD/YYYY` and read with `--bank chase` lands as
    ISO on the books; the very same transaction, re-imported later already in
    ISO form (no `--bank` needed at all), computes the same fingerprint and
    is skipped rather than duplicated — proof the stored date, not the input
    spelling, is what identity is built from."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    slashed_csv = _write(
        tmp_path, "slashed.csv",
        "Date,Description,Amount\n08/11/2026,Whole Foods Market,-84.23\n",
    )
    iso_csv = _write(
        tmp_path, "iso.csv",
        "Date,Description,Amount\n2026-08-11,Whole Foods Market,-84.23\n",
    )

    first = importer.import_csv(slashed_csv, account_number=ACCOUNT_NUMBER, bank="chase")
    assert first.imported == 1
    assert first.errors == 0

    canonical = Canonical()
    dates = [
        record.payload for ref, record in canonical.records("checking") if ref[1] == "date"
    ]
    assert dates == ["2026-08-11"]                    # stored as ISO, not "08/11/2026"

    second = importer.import_csv(iso_csv, account_number=ACCOUNT_NUMBER)
    assert second.imported == 0
    assert second.skipped == 1                          # same fingerprint — deduped
    assert second.errors == 0


def test_a_bank_format_that_does_not_fit_is_an_error_never_the_other_order(tmp_path, monkeypatch):
    """`2026/08/11` does not fit `chase`'s declared `%m/%d/%Y` at all (2026
    is not a month) — this must be an error, never a second attempt reading
    it as `%d/%m/%Y` or any other order."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    csv_text = "Date,Description,Amount\n2026/08/11,Whole Foods Market,-84.23\n"
    path = _write(tmp_path, "bad_bank_date.csv", csv_text)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER, bank="chase")
    assert result.imported == 0
    assert result.errors == 1

    canonical = Canonical()
    assert canonical.records("checking") == []


def test_an_unknown_bank_is_refused_by_name(tmp_path, monkeypatch):
    """`BANK_DATE_FORMATS` is closed — a bank not in it is refused up front,
    before any row is read, the same way an unrecognized header shape is."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "single.csv", _SINGLE_AMOUNT_CSV)

    with pytest.raises(ValueError, match="unknown bank"):
        importer.import_csv(path, account_number=ACCOUNT_NUMBER, bank="not-a-real-bank")

    canonical = Canonical()
    assert canonical.records("checking") == []


def test_every_bank_format_reads_one_order_only(tmp_path):
    """Per *format*, not across the table: every entry in `BANK_DATE_FORMATS`
    commits to exactly one day/month order and reads the same input the same
    way every time.

    The original form of this test asserted that every entry parses
    `"03/04/2026"` to March 4th — which is a statement about today's table
    (all-US, all month-first), not about the rule. Plant a day-first bank and
    that version fails, so it could never have been the guard for "no format
    admits both orders". This one checks each format against *itself*: a
    sample date formatted by that format parses back to that same date
    (round-trip), and the transposed digit string parses to a different date
    (the format commits to an order rather than accepting both). Both hold
    for `%d/%m/%Y` and `%Y-%d-%m` just as they do for `%m/%d/%Y`, which is
    what makes them the rule and not the contents."""
    planted = dict(importer.BANK_DATE_FORMATS)
    planted["_fake-day-first"] = "%d/%m/%Y"        # the plant: not month-first
    planted["_fake-year-day-month"] = "%Y-%d-%m"   # and not even slashed

    sample = datetime(2026, 3, 4).date()
    for bank, fmt in planted.items():
        assert isinstance(bank, str) and isinstance(fmt, str)

        # round-trip: the format reads back exactly what it writes
        assert datetime.strptime(sample.strftime(fmt), fmt).date() == sample

        # deterministic: the same text, twice, is the same date — never one
        # reading for an unambiguous value and another for an ambiguous one
        text = sample.strftime(fmt)
        assert datetime.strptime(text, fmt) == datetime.strptime(text, fmt)

        # committed to one order: the *other* reading of the same digits is a
        # different date under this format, so no entry can be satisfied by
        # both readings at once.
        transposed = datetime(2026, 4, 3).date().strftime(fmt)
        assert datetime.strptime(transposed, fmt).date() != sample


def test_a_planted_day_first_bank_is_honoured_not_overridden(tmp_path, monkeypatch):
    """The audit's finding: `_row_date` used to try the engine's parser
    *first* and the declared bank format only if that refused — safe only
    because every entry in today's table happens to be a slashed form the
    engine refuses as a family. Plant two entries the engine's parser has an
    opinion about and the operator's own declaration must still win.

    `2026-04-03` under `%Y-%d-%m` is March 4th; `parse_deadline` reads the
    same string as April 3rd and would have silently overruled the statement
    the operator said they were importing — a wrong date on the books, with
    no refusal anywhere."""
    monkeypatch.setitem(importer.BANK_DATE_FORMATS, "_fake-day-first", "%d/%m/%Y")
    monkeypatch.setitem(importer.BANK_DATE_FORMATS, "_fake-year-day-month", "%Y-%d-%m")

    # 01/02/2026 under a day-first bank is the 1st of February, never Jan 2nd
    assert importer._row_date("01/02/2026", "_fake-day-first") == "2026-02-01"
    # and the case the engine's own parser accepts under a different order
    assert importer._row_date("2026-04-03", "_fake-year-day-month") == "2026-03-04"
    # no bank named: the engine's reading of the same string, unchanged
    assert importer._row_date("2026-04-03", None) == "2026-04-03"


def test_an_unambiguous_row_inside_a_bank_statement_still_imports(tmp_path, monkeypatch):
    """Consulting the bank format first must not make an ISO row in an
    otherwise-slashed statement an error: the declared format does not fit
    it, and the only remaining *unambiguous* reading is taken. That is not a
    second guess at the day/month order — there is no order left to guess."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(
        tmp_path, "mixed.csv",
        "Date,Description,Amount\n"
        "08/11/2026,Whole Foods Market,-84.23\n"
        "2026-08-12,Employer Payroll,1500.00\n"
        '"August 13, 2026",Rent,-1450.00\n',
    )

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER, bank="chase")
    assert (result.imported, result.errors) == (3, 0)

    canonical = Canonical()
    dates = sorted(
        record.payload for ref, record in canonical.records("checking") if ref[1] == "date"
    )
    assert dates == ["2026-08-11", "2026-08-12", "2026-08-13"]


def test_a_relative_word_in_the_date_column_is_refused_not_resolved(tmp_path, monkeypatch):
    """`Today` in a date column must never become the import date. The
    engine's parser has no relative forms at all (that is BUG-4's ground),
    and this pins the ledger's side of it: with or without `--bank`, a
    relative word is a row error and nothing reaches the books."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    for word in ("Today", "today", "tomorrow", "next Tuesday", "Monday"):
        for bank in (None, "chase"):
            with pytest.raises(ValueError):
                importer._row_date(word, bank)

    path = _write(
        tmp_path, "relative.csv",
        "Date,Description,Amount\nToday,Whole Foods Market,-84.23\n",
    )
    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert (result.imported, result.errors) == (0, 1)
    assert Canonical().records("checking") == []


def test_a_date_cell_is_never_echoed_back_in_its_own_refusal(tmp_path, monkeypatch, capsys):
    """I-15, the half the row-content test does not reach. A mis-aligned CSV
    puts an L3 description (or worse) in the date column, and the engine's
    own `UnparseableDate` quotes the text it refused — so propagating it
    would print that cell on stderr and store it in the tally. This module
    restates the refusal by field name instead, the same way
    `money.decimal_amount` does for an amount."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    misplaced = "Confidential Merchant Name LLC"
    path = _write(
        tmp_path, "misaligned.csv",
        f"Date,Description,Amount\n{misplaced},2026-08-01,-84.23\n",
    )

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.errors == 1
    joined = " ".join(result.error_messages)
    assert misplaced not in joined
    assert "date" in joined                      # the field is named
    assert misplaced not in capsys.readouterr().err

    # and the same cell with a --bank named, which takes the other branch
    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER, bank="chase")
    assert result.errors == 1
    assert misplaced not in " ".join(result.error_messages)
    assert misplaced not in capsys.readouterr().err


def test_a_date_error_never_echoes_the_rows_content(tmp_path, monkeypatch, capsys):
    """I-15: a row's amount and description are never a date refusal's
    business. A distinctive amount and description in the offending row must
    not appear anywhere in the tally's error text or on stderr."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    secret_amount = "-31337.42"
    secret_description = "Confidential Merchant Name LLC"
    csv_text = (
        f"Date,Description,Amount\n08/11/2026,{secret_description},{secret_amount}\n"
    )
    path = _write(tmp_path, "secret.csv", csv_text)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)
    assert result.errors == 1
    joined = " ".join(result.error_messages)
    assert secret_amount not in joined
    assert secret_description not in joined

    err = capsys.readouterr().err
    assert secret_amount not in err
    assert secret_description not in err


def test_the_same_iso_day_with_different_amounts_never_collides(tmp_path, monkeypatch):
    """Dedup across spellings must not become dedup across *transactions*.
    The fingerprint is over `(date, amount, description, account_number)`, so
    two rows written in different date spellings that normalize to the same
    ISO day are still two rows whenever anything else differs — the coffee
    bought twice on the same morning is not one purchase."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(
        tmp_path, "same_day.csv",
        "Date,Description,Amount\n"
        "08/11/2026,Whole Foods Market,-84.23\n"
        "2026-08-11,Whole Foods Market,-12.00\n"
        '"August 11, 2026",Whole Foods Market,-84.24\n',
    )

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER, bank="chase")
    assert (result.imported, result.skipped, result.errors) == (3, 0, 0)

    canonical = Canonical()
    ids = {ref[2] for ref, _ in canonical.records("checking")}
    assert len(ids) == 3
    dates = {
        record.payload for ref, record in canonical.records("checking") if ref[1] == "date"
    }
    assert dates == {"2026-08-11"}     # one day, three transactions


def test_a_pre_fix_row_is_not_deduped_against_its_iso_reimport(tmp_path, monkeypatch):
    """The README's and `--help`'s "no migration" note, pinned as behaviour
    rather than prose. A row already on the books with an unparsed slashed
    date (what the importer wrote before fix: G2c-importer-dates) has a
    fingerprint over that raw text, so re-importing the same statement in the
    new ISO form writes a *second* row rather than skipping — the same
    transaction, twice, under two ids. That is the documented consequence of
    shipping no migration for v1's synthetic-only books; `transaction list
    --gaps` is the surface that makes the old one findable, and this test is
    what stops the docs and the behaviour drifting apart silently."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead_ledger.books import Transaction, import_transaction

    pre_fix_id = import_transaction(Transaction(
        account="checking", date="08/11/2026", amount="-84.23",
        description="Whole Foods Market", account_number=ACCOUNT_NUMBER,
    ))

    path = _write(
        tmp_path, "reimport.csv",
        "Date,Description,Amount\n08/11/2026,Whole Foods Market,-84.23\n",
    )
    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER, bank="chase")
    assert (result.imported, result.skipped) == (1, 0)   # NOT deduped — no migration

    canonical = Canonical()
    ids = {ref[2] for ref, _ in canonical.records("checking")}
    assert len(ids) == 2 and pre_fix_id in ids
    dates = {
        record.payload for ref, record in canonical.records("checking") if ref[1] == "date"
    }
    assert dates == {"08/11/2026", "2026-08-11"}

    # …and the second import of the *same* statement now dedups normally.
    again = importer.import_csv(path, account_number=ACCOUNT_NUMBER, bank="chase")
    assert (again.imported, again.skipped) == (0, 1)
