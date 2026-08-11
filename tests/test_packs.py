"""The checking pack, classified at import — the ledger's analog of
homestead-law's `tests/test_packs.py`. `classify_schema(SCHEMA)` runs at
module top level, so a field an author forgets to classify stops the build
naming that field (I-11), before this test file ever runs.
"""
from __future__ import annotations

import copy

import pytest

from homestead.keep.rungs import Rung, classify_schema
from homestead_ledger.packs import checking


def test_the_pack_classifies_at_import():
    assert isinstance(checking.FIELDS, dict)
    assert checking.FIELDS
    assert all(isinstance(r, Rung) for r in checking.FIELDS.values())
    assert set(checking.FIELDS) == set(checking.SCHEMA)


def test_the_pack_spans_the_ladder_with_the_declared_rungs():
    """The four fields this bite classifies, matching the build plan's own
    words: amount tied to an account is L4 (money category); an account
    number is L5 (key material); a posting date is L2 (household, no
    identity, no protected category — not L1, which is public); a
    payee/merchant name is L3 (resolves to a party)."""
    expected = {
        "date": Rung.L2,
        "description": Rung.L3,
        "amount": Rung.L4,
        "account_number": Rung.L5,
    }
    assert checking.FIELDS == expected


def test_the_dangerous_rungs_are_where_they_must_be():
    assert checking.FIELDS["account_number"] is Rung.L5, "key material is L5 — no override anywhere"
    assert checking.FIELDS["amount"] is Rung.L4, "an amount tied to an account is the money category"


def test_every_field_records_the_account_and_a_reason():
    """Step 5 of the classification procedure, money-domain reading: a rung
    is recorded with the account kind it was classified for, and the sentence
    that justifies it — a reviewable record, not a bare rung."""
    for name, spec in checking.SCHEMA.items():
        assert spec.get("account") == checking.ACCOUNT, name
        assert spec.get("why"), f"{name} declares a rung with no recorded reason"


def test_deleting_a_fields_rung_fails_the_build_naming_it():
    for victim in checking.SCHEMA:
        wounded = copy.deepcopy(checking.SCHEMA)
        del wounded[victim]["rung"]
        with pytest.raises(Exception) as caught:
            classify_schema(wounded)
        assert victim in str(caught.value), (
            f"stripping {victim}'s rung must fail the build and name {victim}"
        )


def test_a_name_based_default_is_not_what_saved_this_pack():
    """The rungs are declared, not inferred from the field name — proof:
    every field's declaration removed, classified alone, still fails."""
    for name in checking.SCHEMA:
        with pytest.raises(Exception):
            classify_schema({name: None})


def test_l3_and_l4_fields_carry_room_for_a_derived_form():
    """`Classified` requires a non-empty `derived` string for L3/L4 (the
    rungs that can stand in for their payload on some surface). The pack does
    not construct `Classified`s itself — `books.py` does, per transaction —
    but this pins that the rungs it declared are exactly the ones that will
    demand one, so a future field added at L3/L4 is not a surprise later."""
    from homestead.keep.rungs import Classified

    with pytest.raises(Exception):
        Classified(checking.FIELDS["amount"], "-1.00")  # no derived form
    with pytest.raises(Exception):
        Classified(checking.FIELDS["description"], "Whole Foods")  # no derived form
    # L2 and L5 need none
    Classified(checking.FIELDS["date"], "2026-08-01")
    Classified(checking.FIELDS["account_number"], "1234")
