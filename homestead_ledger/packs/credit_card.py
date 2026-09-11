"""The credit-card pack — bite 2a's first **liability** account kind.

Same four fields, same rungs, as `packs/checking.py` and `packs/savings.py` —
a card statement's date, merchant/description, amount and account number
resolve to the same steps of the classification procedure a bank account's
do (`docs/homestead-rungs-procedure.md`). What differs is `LIABILITY = True`
and, downstream of it, the sign convention below and how `amount`'s value is
read back as a balance.

**The sign convention.** An amount is signed from the household's own side on
every account kind: money leaving the household is negative, money coming in
is positive. On an **asset** kind (checking, savings) that reads the ordinary
way — a debit negative, a credit positive. On a **liability** kind it still
follows the same household-side rule, just phrased in the card's own words: a
**charge** is negative (the household committed to pay it — money leaving,
the same sign a debit gets) and a **payment or credit** is positive (money
reducing what is owed, the same sign a credit gets). The magnitude is never
restated in a derived form (`amount`'s `derived_by_sign` below names only
which of the two happened).

**Why the balance is reported as owed, not summed raw.** Summing signed
amounts the way an asset account's running total works would leave a card
with three charges and no payments reading *negative* — technically correct
arithmetic, but the wrong word for a debt: nobody says their card balance is
"minus three hundred dollars," they say they owe three hundred. `balance.
running_balance(..., liability=True)` negates the running total for exactly
that reason (see `books.owed`); this pack does not compute that itself; it
only supplies the sign a charge or a payment carries on the books.

**A bank's own "Debit"/"Credit" column headers do not answer which is which
here.** A checking account's bank calls the column that reduces your balance
"Debit"; nothing requires a card issuer's export to use the same word for the
same direction — some list a charge under "Debit," others under "Credit,"
because the *card's* balance moves the opposite way a checking balance does
for the same customer action. `importer.import_csv` refuses a debit/credit
header shape on a liability kind unless the caller states which column means
a charge and which means a payment (`--liability-columns`) — guessing would
misstate a debt, silently, in the direction that matters most.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["ACCOUNT", "LIABILITY", "SCHEMA", "FIELDS"]

ACCOUNT = "credit_card"

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


#: The closed transaction schema for a credit-card account. Ordered by rung
#: so the ladder reads down the page, matching `checking.py`'s layout.
SCHEMA: dict[str, dict[str, Any]] = {
    "date": _field(
        Rung.L2,
        "step 1 (public in this account's own forum?) answers no — a card "
        "statement's posting date is posted nowhere public. Step 2 (identity "
        "or protected category?) also answers no: household activity, never "
        "a public record. L2, the same answer `checking.py`'s `date` gives "
        "for the same two steps.",
    ),
    "description": _field(
        Rung.L3,
        "step 2 answers yes — the merchant name as imported resolves to a "
        "party (who was charged, or who issued a credit). Step 3 (a "
        "protected category of its own?) answers no, so it climbs no "
        "higher — the same posture `checking.py`'s `description` takes.",
        derived="a payee is on file",
    ),
    "amount": _field(
        Rung.L4,
        "step 2 answers yes (an amount tied to this account identifies the "
        "account) and step 3 also answers yes (it carries the category the "
        "household's finances are, the way a diagnosis carries law's medical "
        "category). Both together put it at L4 — matching `checking.py`'s "
        "`amount` exactly, though the sign it derives names a charge or a "
        "payment/credit rather than a debit or a credit (see the module "
        "docstring's sign convention).",
        derived_by_sign={
            "-": "a charge is on file",
            "+": "a payment or credit is on file",
        },
    ),
    "account_number": _field(
        Rung.L5,
        "step 4 — key material, resolving this account to its issuer-issued "
        "card number. L5 has no override anywhere (I-13): served on no "
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
