"""The account-**instance** pack — bite 2b's schema for the sidecar matter
`accounts`, one record per field per operator-chosen label (`chk-main`,
`visa-chase`). This is not an account *kind* pack: it declares no `ACCOUNT`
(the name `registry._discover_packs`/`_discover_obligation_packs` scan for),
so `registry.py` never finds it and it never joins `all_accounts()` —
`tests/test_registry.py::test_the_accounts_sidecar_is_not_a_discovered_pack`
guards that directly. A *kind* (`checking`, `credit_card`, …) says which
pack classifies a transaction's four fields; an *instance* of this pack says
which real-world account (`chk-main` at Wells Fargo, `visa-chase` at Chase)
a household actually holds one of a kind under — decision 9's "account
instances (label ≠ L5 number)".

Each field is a mapping, not a bare rung, for the same reason every other
pack's are: `classify_schema` reads the `"rung"` key and ignores the rest, so
the matter and the justifying sentence travel with the rung as a reviewable
record (step 5 of the classification procedure).

    kind (checking, savings, …)        → L2  (household metadata, no party)
    institution (Wells Fargo, Chase)   → L3  (resolves to a party)
    number (the bank-issued identifier)→ L5  (key material — I-43, I-13)
    opened (the date the account began)→ L2  (household schedule)
    balance_as_of                      → L4  (money category)
    rate (an interest rate)            → L4  (money category)
    limit (a credit limit)             → L4  (money category)
    payment_due_day                    → L2  (household schedule)
    min_payment                        → L4  (money category)

**Why `number` is here at all, given the pack that classifies a
*transaction's* own `account_number` already exists.** Before this bite, a
bank-issued number was written once per transaction (`packs/checking.py`'s
`account_number` field) — the same digits repeated on every row of a
statement. Provisional **I-43**, "an account number lives in exactly one
record," retires that per-transaction write; this pack's `number` is the one
place it is recorded from now on, and `books.py` reads it back from here
(the one allowed payload boundary, `accounts._account_number`) to keep the
transaction fingerprint working exactly as before.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["MATTER", "SCHEMA", "FIELDS"]

#: The sidecar matter every account instance's records are filed under —
#: never a pack name in `all_accounts()` (see the module docstring).
MATTER = "accounts"


def _field(rung: Rung, why: str, *, derived: str | None = None) -> dict[str, Any]:
    decl: dict[str, Any] = {"rung": rung, "matter": MATTER, "why": why}
    if derived is not None:
        decl["derived"] = derived
    return decl


#: The closed schema for one account instance. Ordered by rung, matching the
#: layout every other pack in this package uses.
SCHEMA: dict[str, dict[str, Any]] = {
    "kind": _field(
        Rung.L2,
        "step 1 (public in this account's own forum?) answers no and step 2 "
        "(identity or protected category?) also answers no — which registered "
        "kind an instance is filed under is household metadata, the same "
        "posture packs/obligations.py gives cadence.",
    ),
    "institution": _field(
        Rung.L3,
        "step 2 answers yes: the bank or lender an account is held with "
        "resolves to a party, the same posture packs/checking.py gives a "
        "transaction's description. Step 3 finds no protected category of "
        "its own, so it climbs no higher.",
        derived="an institution is on file",
    ),
    "number": _field(
        Rung.L5,
        "step 4 — key material, the bank- or issuer-assigned identifier this "
        "instance resolves to. L5 has no override anywhere (I-13): served on "
        "no surface, in any form, the same posture packs/checking.py gives a "
        "transaction's account_number — I-43 makes this the one record it "
        "lives in.",
    ),
    "opened": _field(
        Rung.L2,
        "step 1 and step 2 both answer no, the same reasoning "
        "packs/checking.py gives a transaction's posting date — a household "
        "schedule fact, never a public record and never itself an identity "
        "or a protected category.",
    ),
    "balance_as_of": _field(
        Rung.L4,
        "step 2 answers yes (identifies this account) and step 3 answers "
        "yes too (the money category the household's finances are) — the "
        "same two answers packs/checking.py gives amount.",
        derived="a balance is on file",
    ),
    "rate": _field(
        Rung.L4,
        "an interest rate tied to an account identifies it (step 2) and "
        "carries the money category (step 3), exactly as an amount does.",
        derived="a rate is on file",
    ),
    "limit": _field(
        Rung.L4,
        "a credit limit tied to an account identifies it (step 2) and "
        "carries the money category (step 3), exactly as an amount does.",
        derived="a limit is on file",
    ),
    "payment_due_day": _field(
        Rung.L2,
        "which day of the month a payment is due is a household schedule "
        "fact — step 1 and step 2 both answer no, the same reasoning "
        "packs/obligations.py gives due_date.",
    ),
    "min_payment": _field(
        Rung.L4,
        "a minimum payment tied to an account identifies it (step 2) and "
        "carries the money category (step 3), exactly as an amount does.",
        derived="a minimum payment is on file",
    ),
}

#: Classified at import (I-11). Removing any field's rung above dies here,
#: naming the field, before this module can be imported by anything else.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
