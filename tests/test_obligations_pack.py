"""The obligations pack, classified at import — bite 2's schema, mirroring
`tests/test_packs.py` (checking, bite 1). `classify_schema(SCHEMA)` runs at
module top level, so a field an author forgets to classify stops the build
naming that field (I-11), before this test file ever runs.
"""
from __future__ import annotations

import copy

import pytest

from homestead.keep.rungs import Classified, Rung, classify_schema
from homestead_ledger.packs import obligations


def test_the_pack_classifies_at_import():
    assert isinstance(obligations.FIELDS, dict)
    assert obligations.FIELDS
    assert all(isinstance(r, Rung) for r in obligations.FIELDS.values())
    assert set(obligations.FIELDS) == set(obligations.SCHEMA)


def test_the_pack_spans_the_ladder_with_the_declared_rungs():
    """The four fields the build plan names: a payee/name resolves to a party
    (L3); an amount tied to an obligation is the money category (L4); a due
    date is household activity, not a public record (L2, matching bite 1's
    `date` reasoning); a cadence is descriptive metadata about the household's
    own schedule, no identity and no protected category (L2)."""
    expected = {
        "name": Rung.L3,
        "amount": Rung.L4,
        "due_date": Rung.L2,
        "cadence": Rung.L2,
    }
    assert obligations.FIELDS == expected


def test_the_dangerous_rungs_are_where_they_must_be():
    assert obligations.FIELDS["amount"] is Rung.L4, "an amount tied to an obligation is the money category"
    assert obligations.FIELDS["due_date"] is Rung.L2, "household activity, not a public record — not L1"


def test_every_field_records_the_obligation_kind_and_a_reason():
    for name, spec in obligations.SCHEMA.items():
        assert spec.get("obligation") == obligations.OBLIGATION, name
        assert spec.get("why"), f"{name} declares a rung with no recorded reason"


def test_deleting_a_fields_rung_fails_the_build_naming_it():
    for victim in obligations.SCHEMA:
        wounded = copy.deepcopy(obligations.SCHEMA)
        del wounded[victim]["rung"]
        with pytest.raises(Exception) as caught:
            classify_schema(wounded)
        assert victim in str(caught.value), (
            f"stripping {victim}'s rung must fail the build and name {victim}"
        )


def test_a_name_based_default_is_not_what_saved_this_pack():
    for name in obligations.SCHEMA:
        with pytest.raises(Exception):
            classify_schema({name: None})


def test_l3_and_l4_fields_carry_room_for_a_derived_form():
    with pytest.raises(Exception):
        Classified(obligations.FIELDS["amount"], "-1200.00")  # no derived form
    with pytest.raises(Exception):
        Classified(obligations.FIELDS["name"], "Landlord LLC")  # no derived form
    # L2 needs none
    Classified(obligations.FIELDS["due_date"], "2026-09-01")
    Classified(obligations.FIELDS["cadence"], "monthly")
