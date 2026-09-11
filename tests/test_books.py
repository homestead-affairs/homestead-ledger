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
        kind="checking",
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


# ── bite 2a — classification is registry-driven, not `checking`-shaped ─────

def test_import_classifies_by_the_registered_kind_not_checking(tmp_path, monkeypatch):
    """A `credit_card` import must derive the *card's* words for its amount
    ("a charge is on file"), not checking's ("a debit is on file") — proof
    that `import_transaction` reads the pack `txn.kind` names, never the one
    pack this module used to import by name."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    txn = _txn(
        account="credit_card", kind="credit_card", amount="-42.00",
        description="Hardware Store",
    )
    item_id = import_transaction(txn)

    canonical = Canonical()
    amount = canonical.get("credit_card", "amount", item_id)
    assert amount.rung is Rung.L4
    assert amount.derived == "a charge is on file"
    assert amount.derived != "a debit is on file"

    payment = _txn(
        account="credit_card", kind="credit_card", date="2026-08-02",
        amount="42.00", description="Payment Received",
    )
    payment_id = import_transaction(payment)
    assert canonical.get("credit_card", "amount", payment_id).derived == (
        "a payment or credit is on file"
    )


def test_an_unregistered_kind_is_refused_by_name(tmp_path, monkeypatch):
    """A phantom kind must never reach the store — refused by name, as a
    `ValueError` naming `all_accounts()`, before any row is written."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead_ledger import registry

    txn = _txn(account="brokerage", kind="brokerage")
    with pytest.raises(ValueError) as exc:
        import_transaction(txn)
    assert "brokerage" in str(exc.value)
    for name in registry.all_accounts():
        assert name in str(exc.value)

    # and nothing landed on the books for the refused kind.
    assert Canonical().records("brokerage") == []


def _transaction_calls_missing_kind(tree) -> list[int]:
    """Line numbers of every `Transaction(...)` construction in `tree` that
    does not pass `kind=` explicitly."""
    import ast

    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "Transaction":
            continue
        if not any(kw.arg == "kind" for kw in node.keywords):
            missing.append(node.lineno)
    return missing


def test_every_transaction_in_the_package_says_which_kind_it_is():
    """`Transaction.kind` defaults to `checking` so bite 1's callers keep
    working — which means a caller that forgets it does not fail, it
    classifies a card's or a loan's fields against the *checking* pack and
    writes "a debit is on file" over a charge. Nothing silent about it is
    visible at the call site, so the call sites are held here: every
    `Transaction(...)` built inside the package names its kind."""
    import ast
    from pathlib import Path

    pkg = Path(__file__).resolve().parent.parent / "homestead_ledger"
    offenders = []
    for mod in sorted(pkg.rglob("*.py")):
        if "__pycache__" in mod.parts:
            continue
        for lineno in _transaction_calls_missing_kind(ast.parse(mod.read_text("utf-8"))):
            offenders.append(f"{mod.relative_to(pkg.parent)}:{lineno}")
    assert not offenders, (
        f"a Transaction is built without naming its kind at {offenders} — it "
        "would be classified against the checking pack whatever account it "
        "is filed under."
    )


def test_the_kind_scan_catches_a_planted_call_without_it():
    """A scan that has never fired has not been shown to check anything."""
    import ast

    planted = ast.parse(
        "books.Transaction(account='credit_card', date='2026-08-01', "
        "amount='-42.00', description='x', account_number='1')\n"
    )
    assert _transaction_calls_missing_kind(planted) == [1]
    clean = ast.parse(
        "books.Transaction(account='credit_card', kind='credit_card', "
        "date='2026-08-01', amount='-42.00', description='x', account_number='1')\n"
    )
    assert _transaction_calls_missing_kind(clean) == []


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
