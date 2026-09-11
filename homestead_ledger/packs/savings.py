"""The savings-account pack — bite 2a's second account kind, the money-domain
proof that a second pack needs no change anywhere else (I-23): register it
here and `all_accounts()`/`registry.account("savings")` pick it up with no
other file touched.

Same four fields as `packs/checking.py`, at the same rungs, for the same
reasons — a savings account is the same shape of fact as a checking one (an
asset the household holds, a posting date, a payee, an amount, a bank-issued
number). Each `why` below walks the classification procedure's five steps
explicitly (`docs/homestead-rungs-procedure.md`), naming the step that
answers the rung — the form `packs/checking.py` and the engine's
`homestead/packs/custody.py` both use, custody's more literally (its own
`"(step 1)"` parentheticals); checking's bite predates that convention and is
left in its own words rather than rewritten to match (bite 2a's scope is new
packs, not restating an existing one).

**The sign convention.** An amount is signed from the household's own side:
money leaving the household is negative, money coming in is positive. Savings
is an asset kind (`LIABILITY = False`) — a withdrawal is negative, a deposit
or interest credit is positive, the same reading `checking.py` gives a debit
and a credit. There is no "owed" reading for an asset account; `balance.
running_balance`'s `liability` flag stays `False` here.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["ACCOUNT", "LIABILITY", "SCHEMA", "FIELDS"]

ACCOUNT = "savings"

#: An asset kind — see the module docstring's sign convention.
LIABILITY = False


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


#: The closed transaction schema for a savings account. Ordered by rung so
#: the ladder reads down the page, matching `checking.py`'s layout.
SCHEMA: dict[str, dict[str, Any]] = {
    "date": _field(
        Rung.L2,
        "step 1 asks whether this is public in the account's own forum — a "
        "savings posting date is posted nowhere public, so step 1 answers no "
        "and L1 is not in play. Step 2 (does it carry identity or a "
        "protected category?) also answers no: a bare date is household "
        "activity, not a public record, the same reasoning "
        "packs/checking.py's `date` gives step for step. L2, not L1.",
    ),
    "description": _field(
        Rung.L3,
        "step 2 asks whether the field resolves to a person — the "
        "payee/merchant name as imported does (who was paid or who paid the "
        "household), which is what L3 is for. Step 3 (a protected category "
        "of its own?) answers no, so it climbs no higher. Same posture "
        "packs/checking.py's `description` takes for a checking transaction.",
        derived="a payee is on file",
    ),
    "amount": _field(
        Rung.L4,
        "step 2 answers yes (an amount tied to this account identifies the "
        "account) and step 3 also answers yes — it carries the category the "
        "household's finances are, the way a diagnosis carries law's medical "
        "category (docs/homestead-rungs.md's money table). Both together are "
        "what puts an amount at L4 rather than L3.",
        derived_by_sign={"-": "a debit is on file", "+": "a credit is on file"},
    ),
    "account_number": _field(
        Rung.L5,
        "step 4 asks whether the field is key material that resolves an "
        "account to its bank-issued identifier — it is, which is L5 outright "
        "regardless of the earlier steps' answers. L5 has no override "
        "anywhere (I-13): served on no surface, in any form, the same "
        "posture custody gives an SSN.",
    ),
}

#: Classified at import (I-11). Removing any field's rung above dies here,
#: naming the field, before this module can be imported by anything else.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
