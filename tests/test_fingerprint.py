"""Transaction identity — a content fingerprint (I-7/I-9), tested before it
exists. `books.import_transaction` uses this as the item id: two imports of
the same (date, amount, description, account) must land on the same key, and
two transactions that differ in exactly one of those four fields must not.
"""
from __future__ import annotations

from homestead_ledger.fingerprint import fingerprint


def test_the_same_four_fields_fingerprint_the_same_way():
    """Re-importing the same statement line twice must compute the same id —
    that identity, not a database round-trip, is what idempotency rests on."""
    a = fingerprint(date="2026-08-01", amount="-84.23", description="Whole Foods", account="checking")
    b = fingerprint(date="2026-08-01", amount="-84.23", description="Whole Foods", account="checking")
    assert a == b


def test_it_is_a_sha256_hex_digest():
    result = fingerprint(date="2026-08-01", amount="-84.23", description="Whole Foods", account="checking")
    assert isinstance(result, str)
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_changing_any_one_field_changes_the_fingerprint():
    """Each of the four fields is load-bearing in the identity — a fingerprint
    that ignored one would let two different transactions collide, or (worse)
    let the same transaction re-import as if it were new."""
    base = dict(date="2026-08-01", amount="-84.23", description="Whole Foods", account="checking")
    baseline = fingerprint(**base)
    for field in base:
        varied = dict(base)
        varied[field] = base[field] + "!"
        assert fingerprint(**varied) != baseline, f"varying {field!r} did not change the fingerprint"


def test_concatenation_collision_is_not_possible():
    """A naive `date + amount + description + account` join would let
    ("1", "23", ...) collide with ("12", "3", ...). The separator must prevent
    that — this is the concrete case, not just a property test."""
    a = fingerprint(date="1", amount="23", description="x", account="y")
    b = fingerprint(date="12", amount="3", description="x", account="y")
    assert a != b
