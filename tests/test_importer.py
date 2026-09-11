"""The CSV importer — bite 4's first slice: header auto-detect, hash-dedup
(via the fingerprint seam already proven in `test_books.py`), and `--dry-run`.

Every write goes through `books.import_transaction` — the one canonical
writer (`test_invariants_chokepoint.py` enforces that structurally over this
whole package, `importer.py` included). These tests exercise the importer's
own contract on top of that: which header shape it recognizes, how it signs
a debit/credit split, that a re-import is skipped rather than duplicated,
that `--dry-run` touches no adapter at all, and that a malformed row is
counted and surfaced rather than silently dropped or guessed into a fact.
"""
from __future__ import annotations

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


# ── bite 2a — kind, and a liability's ambiguous debit/credit header ────────

def test_a_debit_credit_header_on_a_liability_kind_is_refused_without_a_column_mapping(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "card.csv", _DEBIT_CREDIT_CSV)

    with pytest.raises(ValueError, match="--liability-columns"):
        importer.import_csv(path, account_number=ACCOUNT_NUMBER, kind="credit_card")

    # nothing landed — refused before any row was written.
    assert Canonical().records("credit_card") == []


def test_liability_columns_reverses_which_header_means_a_charge(tmp_path, monkeypatch):
    """`_DEBIT_CREDIT_CSV` puts the Hardware-Store-shaped charge under
    "Debit" and the payment under "Credit" — the sign the existing reader
    already assumes. Naming them the *other* way round must flip which row
    is negative, proving the mapping is actually read, not merely accepted."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "card.csv", _DEBIT_CREDIT_CSV)

    result = importer.import_csv(
        path, account="credit_card", account_number=ACCOUNT_NUMBER, kind="credit_card",
        liability_columns=("credit", "debit"),  # reversed
    )
    assert result.imported == 2

    canonical = Canonical()
    amounts = sorted(
        record.payload for ref, record in canonical.records("credit_card") if ref[1] == "amount"
    )
    assert amounts == ["-1500.00", "84.23"]


def test_liability_columns_normal_order_matches_the_asset_reading(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "card.csv", _DEBIT_CREDIT_CSV)

    result = importer.import_csv(
        path, account="credit_card", account_number=ACCOUNT_NUMBER, kind="credit_card",
        liability_columns=("debit", "credit"),
    )
    assert result.imported == 2

    canonical = Canonical()
    amounts = sorted(
        record.payload for ref, record in canonical.records("credit_card") if ref[1] == "amount"
    )
    assert amounts == ["-84.23", "1500.00"]


def test_an_asset_kinds_debit_credit_statement_needs_no_mapping(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "debit_credit.csv", _DEBIT_CREDIT_CSV)

    result = importer.import_csv(path, account_number=ACCOUNT_NUMBER)  # checking, no mapping given
    assert result.imported == 2


def test_liability_columns_on_an_asset_kind_is_refused_not_ignored(tmp_path, monkeypatch):
    """A mapping an asset kind has no use for was accepted and silently
    dropped — including one naming columns that are not in the file at all,
    which reported a declaration as honoured that was never read. Refused by
    name instead, before the file is opened."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "debit_credit.csv", _DEBIT_CREDIT_CSV)

    for mapping in (("debit", "credit"), ("nonsense", "garbage")):
        with pytest.raises(ValueError, match="not a liability account"):
            importer.import_csv(
                path, account_number=ACCOUNT_NUMBER, kind="checking",
                liability_columns=mapping,
            )
    assert Canonical().records("checking") == []


def test_an_unregistered_kind_is_refused_before_the_file_is_read(tmp_path, monkeypatch):
    """`registry.account` is strict by design (`KeyError`), and the only
    thing `import_csv` documents raising is `ValueError`. An unregistered
    kind reached that strict lookup mid-run: on a debit/credit header it
    escaped as a bare `KeyError` no caller is told to catch (`__main__`
    catches `ValueError`/`FileNotFoundError` and would have traced back),
    and on a single-amount header it was not caught until a row was already
    being written. Refused up front now, as a `ValueError` naming
    `all_accounts()`, on both header shapes and on a path that does not even
    exist."""
    from homestead_ledger import registry

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    for name, content in (
        ("dc.csv", _DEBIT_CREDIT_CSV),
        ("single.csv", _SINGLE_AMOUNT_CSV),
    ):
        path = _write(tmp_path, name, content)
        with pytest.raises(ValueError) as exc:
            importer.import_csv(path, account_number=ACCOUNT_NUMBER, kind="brokerage")
        assert "brokerage" in str(exc.value)
        for registered in registry.all_accounts():
            assert registered in str(exc.value)

    with pytest.raises(ValueError):
        importer.import_csv(
            tmp_path / "no-such-file.csv", account_number=ACCOUNT_NUMBER, kind="brokerage",
        )


def test_a_card_statement_ends_at_the_amount_the_household_owes(tmp_path, monkeypatch):
    """The whole bite, end to end and in the household's own words: a $100
    purchase and a $40 payment on a credit card leave $60 **owed**. The
    charge is negative on the books and derives as "a charge is on file"; the
    payment is positive and derives as "a payment or credit is on file"; the
    running total read as a liability is a positive 60, never a negative one.
    A convention that disagreed between `books.owed` and the derived wording
    would show up here as a sign that does not match the word."""
    from homestead_ledger.balance import running_balance

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "card.csv", (
        "Date,Description,Debit,Credit\n"
        "2026-08-01,Hardware Store,100.00,\n"
        "2026-08-10,Payment Thank You,,40.00\n"
    ))
    result = importer.import_csv(
        path, account="credit_card", account_number="4242", kind="credit_card",
        liability_columns=("debit", "credit"),
    )
    assert result.imported == 2

    canonical = Canonical()
    by_amount = {
        record.payload: record.derived
        for ref, record in canonical.records("credit_card") if ref[1] == "amount"
    }
    assert by_amount == {
        "-100.00": "a charge is on file",      # money leaving: a charge
        "40.00": "a payment or credit is on file",
    }

    points = running_balance(canonical, "credit_card", liability=True)
    assert [p.running for p in points] == [100.00, 60.00]
    assert points[-1].running == 60.00, "a card with $100 charged and $40 paid owes $60"
    # the same rows read as an asset would say minus sixty — the arithmetic
    # is the same, the word is not.
    assert running_balance(canonical, "credit_card")[-1].running == -60.00


def test_the_same_statement_written_the_other_way_round_reaches_the_same_owed(
    tmp_path, monkeypatch,
):
    """The issuer that lists a charge under "Credit" (its own books' word,
    not the household's) must reach the same $60 owed once the operator says
    so — that is the whole point of `--liability-columns`, and it is what
    makes refusing the unmapped file honest rather than merely cautious."""
    from homestead_ledger.balance import running_balance

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "card-reversed.csv", (
        "Date,Description,Debit,Credit\n"
        "2026-08-01,Hardware Store,,100.00\n"
        "2026-08-10,Payment Thank You,40.00,\n"
    ))
    result = importer.import_csv(
        path, account="credit_card", account_number="4242", kind="credit_card",
        liability_columns=("credit", "debit"),  # this issuer calls a charge a credit
    )
    assert result.imported == 2
    points = running_balance(Canonical(), "credit_card", liability=True)
    assert [p.running for p in points] == [100.00, 60.00]


def test_a_single_amount_card_statement_needs_no_mapping_and_owes_the_same(
    tmp_path, monkeypatch,
):
    """A one-column statement already carries the sign, so there is nothing
    ambiguous to declare — no mapping is required, and the same two rows
    reach the same $60 owed."""
    from homestead_ledger.balance import running_balance

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "card-single.csv", (
        "Date,Description,Amount\n"
        "2026-08-01,Hardware Store,-100.00\n"
        "2026-08-10,Payment Thank You,40.00\n"
    ))
    result = importer.import_csv(
        path, account="credit_card", account_number="4242", kind="credit_card",
    )
    assert result.imported == 2
    points = running_balance(Canonical(), "credit_card", liability=True)
    assert [p.running for p in points] == [100.00, 60.00]


def test_import_csv_classifies_rows_at_the_given_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = _write(tmp_path, "single.csv", _SINGLE_AMOUNT_CSV)

    result = importer.import_csv(
        path, account="savings", account_number=ACCOUNT_NUMBER, kind="savings",
    )
    assert result.imported == 2

    canonical = Canonical()
    assert canonical.records("checking") == []  # nothing landed in the wrong matter
    dates = [record.payload for ref, record in canonical.records("savings") if ref[1] == "date"]
    assert sorted(dates) == ["2026-08-01", "2026-08-03"]


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
