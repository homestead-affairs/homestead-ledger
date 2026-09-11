"""The checking pack, classified at import — the ledger's analog of
homestead-law's `tests/test_packs.py`. `classify_schema(SCHEMA)` runs at
module top level, so a field an author forgets to classify stops the build
naming that field (I-11), before this test file ever runs.

Bite 2a adds three more account packs (`savings`, `credit_card`, `loan`) and
the tests below that hold every registered pack to the same contract:
the four settled fields at the four settled rungs, a `LIABILITY` bool, a
`why` that names its classification step, and an amount whose
`derived_by_sign` never states a number.
"""
from __future__ import annotations

import copy
import re

import pytest

from homestead.keep.rungs import Rung, classify_schema
from homestead_ledger import registry
from homestead_ledger.packs import checking, credit_card, loan, savings


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


# ── bite 2a — every registered account pack, held to the same contract ─────

_SETTLED_RUNGS = {
    "date": Rung.L2, "description": Rung.L3, "amount": Rung.L4, "account_number": Rung.L5,
}

#: Of the four, the three `books.import_transaction` actually writes since
#: bite G2b (provisional I-43): the bank-issued number stopped being a
#: per-transaction record and moved to the account instance. `account_number`
#: stays declared here — rows imported before that change are still on disk,
#: with no migration, and these packs are where the repo says what rung such
#: a row carries.
_WRITTEN = tuple(f for f in _SETTLED_RUNGS if f != "account_number")


def test_every_account_pack_declares_the_four_transaction_fields_at_the_settled_rungs():
    for kind in registry.all_accounts():
        schema = registry.account(kind).schema
        for field, rung in _SETTLED_RUNGS.items():
            assert field in schema, f"{kind} is missing {field!r}"
            assert schema[field]["rung"] is rung, f"{kind}.{field} is not {rung}"


def test_the_settled_rungs_and_what_books_writes_say_the_same_thing():
    """I-43, held from both ends at once. `_SETTLED_RUNGS` is a list typed
    here; `books._FIELD_ORDER` is what actually reaches disk. Nothing tied
    them together, so this file could have gone on asserting four fields
    while `books.py` wrote three, or five, and neither side would notice.

    The claim: every field `books.py` writes is declared, at its settled
    rung, by every registered pack — and `account_number` is declared and
    **not** written, which is what I-43 means by "one record". Re-adding the
    per-transaction write fails here rather than in a household's books.
    """
    from homestead_ledger.books import _FIELD_ORDER

    assert set(_FIELD_ORDER) == set(_WRITTEN)
    assert "account_number" not in _FIELD_ORDER
    for kind in registry.all_accounts():
        schema = registry.account(kind).schema
        for field in _FIELD_ORDER:
            assert field in schema, f"{kind} is missing the written field {field!r}"
            assert schema[field]["rung"] is _SETTLED_RUNGS[field]


def test_liability_packs_declare_liability_and_asset_packs_do_not():
    expected = {"checking": False, "savings": False, "credit_card": True, "loan": True}
    assert set(expected) == set(registry.all_accounts())
    for kind, liability in expected.items():
        entry = registry.account(kind)
        assert isinstance(entry.liability, bool)
        assert entry.liability is liability, f"{kind}.LIABILITY should be {liability}"


def test_derived_by_sign_never_states_a_number():
    """`amount`'s derived form stands in for the payload — it may say a
    charge or a payment happened, never the magnitude. Every account pack
    declares `derived_by_sign` for `amount` (bite 2a); none of its two
    strings may contain a digit."""
    for kind in registry.all_accounts():
        spec = registry.account(kind).schema["amount"]
        assert "derived_by_sign" in spec, f"{kind}'s amount has no derived_by_sign"
        sign_forms = spec["derived_by_sign"]
        assert set(sign_forms) == {"-", "+"}
        for text in sign_forms.values():
            assert not any(ch.isdigit() for ch in text), (
                f"{kind}'s derived_by_sign states a number: {text!r}"
            )


#: The literal citation every account pack's `why` must carry — the "(step
#: N)" phrasing `homestead/packs/custody.py` uses, which says *which* step of
#: the classification procedure answered, not merely that the author had a
#: reason. Held against every registered pack, `checking` included: its
#: bite-1 sentences were amended to cite their steps rather than be exempted,
#: because an exemption checked only by loose keyword ("household",
#: "categor…", "key material") is satisfied by prose that names no step at
#: all — see `test_a_step_less_why_is_caught_in_every_registered_pack`.
_STEP_PATTERN = re.compile(r"\bstep\s*\d\b", re.IGNORECASE)


def test_every_why_names_a_step():
    """Every registered account pack writes each field's `why` in the literal
    "step N" style, so the sentence says which step of the procedure answered
    and a reviewer can check the answer rather than take the rung on trust."""
    for kind in registry.all_accounts():
        schema = registry.account(kind).schema
        for field, spec in schema.items():
            assert _STEP_PATTERN.search(spec["why"]), (
                f"{kind}.{field}'s why does not name its step: {spec['why']!r}"
            )


def test_a_step_less_why_is_caught_in_every_registered_pack():
    """A scan that has never fired has not been shown to check anything.
    Plant, per registered pack and per field, a `why` that reads like a
    plausible justification and cites no step — including the exact prose the
    superseded keyword check would have accepted ("household", "money
    category", "key material") — and confirm the check fires on each."""
    step_less = (
        "household activity, and the money category is obvious from the "
        "key material on the row, so this rung is right"
    )
    assert not _STEP_PATTERN.search(step_less)
    for kind in registry.all_accounts():
        schema = registry.account(kind).schema
        for field in schema:
            wounded = copy.deepcopy(dict(schema))
            wounded[field] = {**wounded[field], "why": step_less}
            assert not all(
                _STEP_PATTERN.search(spec["why"]) for spec in wounded.values()
            ), f"a step-less why planted in {kind}.{field} passed the check"


def test_a_pack_amount_whose_derived_form_states_a_value_is_caught():
    """The other half of the derived-form rule (`docs/homestead-rungs-
    procedure.md` § 4): the stand-in names that something exists, never its
    magnitude. `test_derived_by_sign_never_states_a_number` asserts that of
    the real packs; plant both shapes it is meant to catch — a magnitude, and
    the payload restated — and confirm the digit check fires."""
    def states_a_number(sign_forms: dict[str, str]) -> bool:
        return any(
            any(ch.isdigit() for ch in text) for text in sign_forms.values()
        )

    assert not states_a_number(checking.SCHEMA["amount"]["derived_by_sign"])
    assert states_a_number({"-": "a charge of 84.23 is on file", "+": "a credit is on file"})
    assert states_a_number({"-": "-84.23", "+": "1500.00"})


# ── the new packs individually, mirroring checking's own contract tests ────
#
# `test_every_account_pack_declares_the_four_transaction_fields_at_the_settled_
# rungs` above already holds every registered pack (checking included) to the
# settled rungs via `SCHEMA`; what is left worth pinning per new pack is that
# `FIELDS` (the classified dict `classify_schema` actually produces) agrees,
# and that each new pack's own `classify_schema` call still enforces I-11.

@pytest.mark.parametrize("pack", [savings, credit_card, loan])
def test_deleting_a_new_packs_field_rung_fails_the_build_naming_it(pack):
    for victim in pack.SCHEMA:
        wounded = copy.deepcopy(pack.SCHEMA)
        del wounded[victim]["rung"]
        with pytest.raises(Exception) as caught:
            classify_schema(wounded)
        assert victim in str(caught.value)


def test_credit_card_and_loan_amount_use_charge_and_payment_wording():
    for pack in (credit_card, loan):
        sign_forms = pack.SCHEMA["amount"]["derived_by_sign"]
        assert sign_forms["-"] == "a charge is on file"
        assert sign_forms["+"] == "a payment or credit is on file"


def test_savings_amount_uses_debit_and_credit_wording_like_checking():
    assert savings.SCHEMA["amount"]["derived_by_sign"] == checking.SCHEMA["amount"]["derived_by_sign"]


def test_loans_extra_fields_are_l4_and_not_written_by_the_four_settled_fields():
    """`principal`/`interest` are declared, at L4, but are not among the
    four fields every account pack shares — `books.py`'s `_FIELD_ORDER`
    never writes them (see `loan.py`'s own docstring)."""
    from homestead_ledger.books import _FIELD_ORDER

    for extra in ("principal", "interest"):
        assert extra in loan.SCHEMA
        assert loan.FIELDS[extra] is Rung.L4
        assert extra not in _SETTLED_RUNGS
        assert extra not in _FIELD_ORDER


def test_every_account_number_declaration_says_it_is_no_longer_written():
    """A declared field nothing writes is drift unless the declaration says
    why it is still there. Each pack's `account_number` `why` carries the
    dated note — struck through, never deleted (house style) — so a reader
    who finds the field does not go looking for the write that stopped."""
    for kind in registry.all_accounts():
        why = registry.account(kind).schema["account_number"]["why"]
        assert "I-43" in why, f"{kind}'s account_number does not cite I-43"
        assert "~~" in why, f"{kind}'s account_number strikes nothing through"
        assert "no migration" in why, kind
