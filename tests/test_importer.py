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
