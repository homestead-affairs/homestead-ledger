"""The loan pack — bite 2a's second liability account kind (a mortgage, a car
loan, any debt serviced by a scheduled payment), and the only account pack
that declares fields beyond the four every kind shares.

The four settled fields (`date` L2, `description` L3, `amount` L4,
`account_number` L5) carry the same reasoning `packs/credit_card.py` gives
them — a loan is a liability the same shape a card balance is, just serviced
by a payment schedule instead of discretionary charges. `LIABILITY = True`
and the same sign convention apply: a charge (an amount the loan accrues —
a draw, a fee) is negative, a payment is positive, and the balance is
reported as owed (`balance.running_balance(..., liability=True)`).

**`principal` and `interest` (both L4) — the split some statements give.** A
loan servicer's statement commonly breaks one payment into how much reduced
the principal and how much was interest, rather than reporting only the one
combined `amount` a checking or card transaction gets. Both resolve to this
account (step 2) and carry the same money category `amount` does (step 3),
so both take `amount`'s own rung — a portion of a payment is exactly as
sensitive as the payment itself, not less. Neither is written by this bite's
`books.import_transaction`, which only ever writes the four fields every
`Transaction` carries (see `books.py`); a servicer's split is future work
that would extend `Transaction` or add a second write path, not a reason to
leave the fields unclassified now — an unclassified field is a build failure
the moment anything does try to write one (I-11), and declaring the schema
here is what makes that failure land in the right place. Each takes a plain
`derived` form rather than `amount`'s sign-keyed one: a payment's principal
and interest portions are both positive by construction (a payment reduces
what is owed), so there is no second sign to name.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["ACCOUNT", "LIABILITY", "SCHEMA", "FIELDS"]

ACCOUNT = "loan"

#: A liability kind — see the module docstring's sign convention.
LIABILITY = True


def _field(
    rung: Rung, why: str, *, derived: str | None = None,
    derived_by_sign: dict[str, str] | None = None,
) -> dict[str, Any]:
    decl: dict[str, Any] = {"rung": rung, "account": ACCOUNT, "why": why}
    if derived is not None:
        decl["derived"] = derived
    if derived_by_sign is not None:
        decl["derived_by_sign"] = derived_by_sign
    return decl


#: The closed transaction schema for a loan account. Ordered by rung so the
#: ladder reads down the page, matching `checking.py`'s layout; `principal`
#: and `interest` sit alongside `amount` at L4 rather than after it, since
#: nothing about their rung differs from it.
SCHEMA: dict[str, dict[str, Any]] = {
    "date": _field(
        Rung.L2,
        "step 1 (public in this account's own forum?) answers no — a loan "
        "statement's posting date is posted nowhere public. Step 2 (identity "
        "or protected category?) also answers no: household activity, never "
        "a public record. L2, the same answer `checking.py`'s `date` gives "
        "for the same two steps.",
    ),
    "description": _field(
        Rung.L3,
        "step 2 answers yes — the description as imported (a draw, a fee, "
        "'scheduled payment') resolves to a party or a labeled event on this "
        "account. Step 3 (a protected category of its own?) answers no, so "
        "it climbs no higher — the same posture `checking.py`'s "
        "`description` takes.",
        derived="a payee is on file",
    ),
    "amount": _field(
        Rung.L4,
        "step 2 answers yes (an amount tied to this account identifies the "
        "account) and step 3 also answers yes (it carries the category the "
        "household's finances are). Both together put it at L4 — matching "
        "`packs/credit_card.py`'s `amount`, including its sign convention: "
        "a charge to the loan is negative, a payment is positive, and the "
        "balance is reported as owed.",
        derived_by_sign={
            "-": "a charge is on file",
            "+": "a payment or credit is on file",
        },
    ),
    "account_number": _field(
        Rung.L5,
        "step 4 — key material, resolving this account to its lender-issued "
        "loan number. L5 has no override anywhere (I-13): served on no "
        "surface, in any form, the same posture custody gives an SSN."
        " ~~Written once per transaction.~~ Since 2026-09-11 (bite "
        "G2b-account-instances, provisional I-43) books.py writes three "
        "fields and never this one: the number lives on the account "
        "instance (packs/accounts.py's number). The declaration stays "
        "because rows imported before that change are still on disk — "
        "there is no migration — and this is where the repo says what "
        "rung such a row carries.",
    ),
    "principal": _field(
        Rung.L4,
        "step 2 answers yes (identifies this account's balance) and step 3 "
        "answers yes (the money category `amount` itself carries) — the "
        "principal portion of a split payment is exactly as sensitive as the "
        "payment it is a portion of, so it takes `amount`'s own rung rather "
        "than a lesser one. Declared for a servicer's statement that splits "
        "a payment; not written by this bite's `books.import_transaction` "
        "(see the module docstring).",
        derived="a principal amount is on file",
    ),
    "interest": _field(
        Rung.L4,
        "the same step 2 / step 3 reasoning as `principal` — the interest "
        "portion of a split payment identifies this account and carries the "
        "money category, so it takes L4 too. Declared for a servicer's "
        "statement that splits a payment; not written by this bite's "
        "`books.import_transaction`.",
        derived="an interest amount is on file",
    ),
}

#: Classified at import (I-11). Removing any field's rung above dies here,
#: naming the field, before this module can be imported by anything else.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
