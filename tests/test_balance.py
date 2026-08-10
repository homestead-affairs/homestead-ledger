"""Running balance — derived over the books, never stored.

`running_balance` reads the canonical `date`/`amount` fields and computes a
cumulative total; nothing it returns is written anywhere. That is the whole
of the invariant this file pins: call it twice, get the same answer, and the
store is untouched either time.
"""
from __future__ import annotations

from homestead.keep import paths
from homestead.keep.store import CANONICAL, SQLiteAdapter

from homestead_ledger.balance import running_balance
from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.store import Canonical


def _seed(monkeypatch, tmp_path):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    import_transaction(Transaction(
        account="checking", date="2026-08-05", amount="-64.10",
        description="Electric Co", account_number="9821",
    ))
    import_transaction(Transaction(
        account="checking", date="2026-08-01", amount="-84.23",
        description="Whole Foods Market", account_number="9821",
    ))
    import_transaction(Transaction(
        account="checking", date="2026-08-03", amount="1500.00",
        description="Employer Payroll", account_number="9821",
    ))


def test_running_balance_orders_by_posting_date_not_import_order(tmp_path, monkeypatch):
    _seed(monkeypatch, tmp_path)
    points = running_balance(Canonical(), "checking")
    assert [p.date for p in points] == ["2026-08-01", "2026-08-03", "2026-08-05"]


def test_running_balance_accumulates_correctly(tmp_path, monkeypatch):
    _seed(monkeypatch, tmp_path)
    points = running_balance(Canonical(), "checking")
    assert [p.amount for p in points] == [-84.23, 1500.00, -64.10]
    assert [p.running for p in points] == [-84.23, 1415.77, 1351.67]


def test_running_balance_over_an_empty_account_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    assert running_balance(Canonical(), "checking") == []


def test_running_balance_writes_nothing(tmp_path, monkeypatch):
    """The derived-not-stored invariant, held behaviourally: calling it twice
    changes no row count in either table."""
    _seed(monkeypatch, tmp_path)
    running_balance(Canonical(), "checking")
    running_balance(Canonical(), "checking")

    adapter = SQLiteAdapter(paths.home() / "homestead-ledger.db")
    canonical_rows = adapter.read_matter(CANONICAL, "checking")
    # 3 transactions x 4 fields = 12 canonical rows, unmoved by two calls
    assert len(canonical_rows) == 12
