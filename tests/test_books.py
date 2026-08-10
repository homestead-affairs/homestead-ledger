"""The books — importing transactions into the canonical record, and the
invariants that make that safe: idempotent identity (I-7/I-9) and "mirror,
not judge" (I-6/I-25, the app has no write path to a transaction).

`homestead.keep.store.Canonical` ships with no write method at all — by
design (see its own docstring: "the operator's own tools grow the canonical
record; the app reads it and never edits or deletes it"). `books.py` is that
operator tool for this bite: it writes straight to the CANONICAL table via
the low-level adapter, which is why these tests exist here rather than
against `Canonical`/`Sidecar`.
"""
from __future__ import annotations

import json

import pytest
from homestead.keep import paths
from homestead.keep.rungs import Rung
from homestead.keep.store import CANONICAL, RecordExists, SQLiteAdapter, key

from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.fingerprint import fingerprint
from homestead_ledger.store import Canonical


def _txn(**overrides) -> Transaction:
    base = dict(
        account="checking",
        date="2026-08-01",
        amount="-84.23",
        description="Whole Foods Market",
        account_number="9821",
    )
    base.update(overrides)
    return Transaction(**base)


def test_import_writes_one_record_per_field(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    txn = _txn()
    item_id = import_transaction(txn)

    assert item_id == fingerprint(
        date=txn.date, amount=txn.amount, description=txn.description, account=txn.account_number
    )
    canonical = Canonical()
    assert canonical.get("checking", "date", item_id).payload == "2026-08-01"
    assert canonical.get("checking", "amount", item_id).payload == "-84.23"
    assert canonical.get("checking", "description", item_id).payload == "Whole Foods Market"
    assert canonical.get("checking", "account_number", item_id).payload == "9821"


def test_import_classifies_each_field_at_the_packs_declared_rung(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    txn = _txn()
    item_id = import_transaction(txn)
    canonical = Canonical()

    assert canonical.get("checking", "date", item_id).rung is Rung.L2
    assert canonical.get("checking", "description", item_id).rung is Rung.L3
    assert canonical.get("checking", "amount", item_id).rung is Rung.L4
    assert canonical.get("checking", "account_number", item_id).rung is Rung.L5


def test_l4_amount_carries_a_generic_derived_form_not_the_number(tmp_path, monkeypatch):
    """The derived form stands in for the payload on a surface that cannot
    take the real amount — it must not itself leak the magnitude, only that a
    debit or a credit is on file (the same convention the bite-0 store-binding
    fixture already used: `derived="a debit is on file"`)."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    debit_id = import_transaction(_txn(amount="-84.23"))
    credit_id = import_transaction(_txn(date="2026-08-02", amount="1500.00", description="Payroll"))

    canonical = Canonical()
    debit = canonical.get("checking", "amount", debit_id)
    credit = canonical.get("checking", "amount", credit_id)
    assert debit.derived == "a debit is on file"
    assert credit.derived == "a credit is on file"
    assert "84.23" not in debit.derived
    assert "1500" not in credit.derived


# ── idempotent re-import — I-7 (one key) / I-9 (no silent clobber) ─────────

def test_reimporting_the_same_transaction_is_refused_not_duplicated(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    txn = _txn()
    first_id = import_transaction(txn)

    with pytest.raises(RecordExists):
        import_transaction(txn)

    # and nothing was overwritten or duplicated: the one record is still there,
    # unchanged, and there is exactly one row for this transaction's amount.
    canonical = Canonical()
    assert canonical.get("checking", "amount", first_id).payload == "-84.23"

    adapter = SQLiteAdapter(paths.home() / "homestead-ledger.db")
    rows = adapter.read_matter(CANONICAL, "checking")
    amount_rows = [r for r in rows if r[0][1] == "amount"]
    assert len(amount_rows) == 1


def test_reimport_refusal_does_not_touch_a_different_transaction(tmp_path, monkeypatch):
    """A refused re-import must not disturb an unrelated transaction sharing
    the same account — the refusal is scoped to the one occupied key."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    first = _txn()
    second = _txn(date="2026-08-02", amount="1500.00", description="Payroll")
    import_transaction(first)
    import_transaction(second)

    with pytest.raises(RecordExists):
        import_transaction(first)

    canonical = Canonical()
    # the second transaction is untouched
    second_id = fingerprint(
        date=second.date, amount=second.amount, description=second.description,
        account=second.account_number,
    )
    assert canonical.get("checking", "amount", second_id).payload == "1500.00"


def test_two_genuinely_different_transactions_both_import(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    a = import_transaction(_txn())
    b = import_transaction(_txn(date="2026-08-02", amount="1500.00", description="Payroll"))
    assert a != b


# ── mirror, not judge — the app has no write path to a transaction ─────────

def test_canonical_still_exposes_no_write_method():
    """Restated here, at the point books.py is what actually writes to
    CANONICAL: the read-only handle the rest of the app uses is untouched by
    that fact. Same shape as tests/test_store_binding.py's
    test_canonical_is_read_only_by_type."""
    for forbidden in ("put", "write", "update", "delete", "insert"):
        assert not hasattr(Canonical, forbidden)


def test_import_transaction_bypasses_canonical_and_sidecar_deliberately(tmp_path, monkeypatch):
    """books.py does not — cannot — call `Canonical.put` (it does not exist)
    or `Sidecar.put` (that would land a transaction in the household's
    overlay, not the books). It writes through the adapter directly, at the
    one place the operator's own import tool is allowed to. This test pins
    that the round-trip still reads back correctly through the real engine's
    own `Canonical.get`, so a future change to the store's serialization
    format would be caught here rather than only in the engine's own suite.
    """
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    txn = _txn()
    item_id = import_transaction(txn)
    adapter = SQLiteAdapter(paths.home() / "homestead-ledger.db")
    raw = adapter.read(CANONICAL, key(txn.account, "amount", item_id))
    assert json.loads(raw) == {"rung": "L4", "payload": "-84.23", "derived": "a debit is on file"}
