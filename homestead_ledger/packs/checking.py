"""The checking-account pack — bite 1's one schema, classified at **import**.

A transaction's four fields, each declared and classified here rather than
inferred from its name — `docs/build-plan.md`'s money-classification table is
the source, not this file's invention:

    amount tied to an account         → L4  (money category)
    account number / SSN              → L5  (key material)
    posting date                      → L1/L2
    payee / merchant name             → L3

**Why `date` lands on L2 and not L1.** homestead-law's `hearing_date` is L1
because it is posted on a public court calendar — public *in that matter's
forum* is step 1 of the classification procedure. A checking account's
posting date has no such forum: it is household activity, not a public
record, so it carries no identity and no protected category (`Rung.L2`'s own
definition) without ever being public the way a court date is. L1 would be
the wrong analogy transplanted from the wrong domain.

**Why `amount` needs its own rung rather than inheriting `date`'s.** An
amount is tied to *this* account (identifies) and is the category the
household's finances are — homestead-rungs.md's money table calls that L4
outright, and `docs/build-plan.md` restates it as this bite's own worked
example. It is not merely "sensitive text" the way a note is; it is the
domain's `L4` datum the way a diagnosis is law's.

Each field is a mapping, not a bare rung, for the same reason custody's are:
`classify_schema` reads the `"rung"` key and ignores the rest, so the account
kind and the justifying sentence travel with the rung as a reviewable record.

**What this pack does not catch.** `classify_schema` checks that a rung was
*declared*, not that it fits its content — it would accept `L1` for
`account_number` without complaint. Content-shape advisories (declared L2,
shaped like an account number → flag) are out of this bite's scope.

**The sign convention (bite 2a).** An amount is signed from the household's
own side, not the bank's: money leaving the household is negative, money
coming in is positive. Checking is an asset kind, so that reads the ordinary
way — a debit is negative, a credit is positive — and `amount`'s
`derived_by_sign` below names those two forms directly. `LIABILITY = False`
records that this pack is on the asset side of that convention;
`registry.AccountType.liability` reads it live. A liability pack (`credit_card`,
`loan`) keeps the same signs (a charge negative, a payment/credit positive)
but reports its running balance as *owed* — see those packs' own docstrings
and `balance.running_balance`.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["ACCOUNT", "LIABILITY", "SCHEMA", "FIELDS"]

ACCOUNT = "checking"

#: An asset kind: money in the account is the household's, not owed to
#: anyone else. `registry.AccountType.liability` reads this live, and
#: `registry._validate` requires every account pack declare it as a bool.
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


#: The closed transaction schema for a checking account. Ordered by rung so
#: the ladder reads down the page, exactly as custody's does.
SCHEMA: dict[str, dict[str, Any]] = {
    "date": _field(
        Rung.L2,
        "a posting date alone carries no identity and no protected category "
        "(step 2 answers no, Rung.L2's own definition) — household activity, "
        "never a public record the way a court calendar is (step 1 answers "
        "no), so L2 rather than L1.",
    ),
    "description": _field(
        Rung.L3,
        "the payee/merchant name as imported — step 2 answers yes: it "
        "resolves to a party (who was paid), and step 3 finds no protected "
        "category of its own, so it climbs no higher. The household's "
        "*confirmed* merchant name is a separate, sidecar concept "
        "(build-plan.md); this field is the raw imported text.",
        derived="a payee is on file",
    ),
    "amount": _field(
        Rung.L4,
        "an amount tied to an account is the money category: step 2 answers "
        "yes (it identifies this account) and step 3 answers yes too (it "
        "carries the category the household's finances are, the way a "
        "diagnosis carries law's medical category). "
        "docs/homestead-rungs.md's money table classifies this L4 directly; "
        "this is this bite's worked example of that table.",
        derived_by_sign={"-": "a debit is on file", "+": "a credit is on file"},
    ),
    "account_number": _field(
        Rung.L5,
        "step 4 — key material, resolving an account to its bank-issued "
        "identifier. L5 has no override anywhere (I-13): served on no "
        "surface, in any form, the same posture custody gives an SSN."
        " ~~Written once per transaction.~~ Since 2026-09-11 (bite "
        "G2b-account-instances, provisional I-43) books.py writes three "
        "fields and never this one: the number lives on the account "
        "instance (packs/accounts.py's number). The declaration stays "
        "because rows imported before that change are still on disk — "
        "there is no migration — and this is where the repo says what "
        "rung such a row carries.",
    ),
}

#: Classified at import (I-11). Removing any field's rung above dies here,
#: naming the field, before this module can be imported by anything else.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
