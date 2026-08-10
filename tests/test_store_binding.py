"""homestead-ledger's store is the engine's contract on a SQLite backing.

The record invariants (I-6/I-7/I-9/I-11) are tested in `homestead-affairs`'s own
suite, against every adapter. This file only checks the *binding*: that this
module's `Sidecar`/`Canonical` use the SQLite adapter, persist to the ledger
database in the shared root, and expose the contract — the same shape
homestead-law's `test_store_binding.py` checks for its own db.
"""
from __future__ import annotations

import json

import pytest

from homestead.keep import paths
from homestead.keep.rungs import Classified, Rung
from homestead.keep.store import SIDECAR, SQLiteAdapter
from homestead_ledger.store import Canonical, RecordExists, Sidecar, key


def test_the_store_persists_to_the_ledger_database(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    # A transaction amount tied to an account is money-category — L4 (homestead-rungs).
    Sidecar().put("checking", "transaction", "t1",
                  Classified(Rung.L4, "-42.00", derived="a debit is on file"))
    # a fresh Sidecar reads it back — it is on disk, in the ledger db
    assert Sidecar().get("checking", "transaction", "t1").payload == "-42.00"
    assert (paths.home() / "homestead-ledger.db").exists()


def test_the_store_refuses_to_clobber(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    store.put("checking", "note", "n", Classified(Rung.L2, "first"))
    with pytest.raises(RecordExists):
        store.put("checking", "note", "n", Classified(Rung.L2, "second"))


def test_the_store_fails_closed_to_l5(tmp_path, monkeypatch):
    """The contract's fail-closed rule reaches through the binding: a corrupt row
    written straight to the SQLite adapter reads L5."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    SQLiteAdapter(paths.home() / "homestead-ledger.db").write(
        SIDECAR, key("checking", "transaction", "x"),
        json.dumps({"rung": "L9", "payload": "x"}),
    )
    assert Sidecar().get("checking", "transaction", "x").rung is Rung.L5


def test_canonical_is_read_only_by_type():
    """Mirror, not judge: the books handle has no write path (I-6)."""
    for forbidden in ("put", "write", "update", "delete", "insert"):
        assert not hasattr(Canonical, forbidden)
