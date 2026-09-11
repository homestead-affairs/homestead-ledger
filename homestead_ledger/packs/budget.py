"""The budget pack — bite G4-budget's schema for the sidecar matter
`budget`, one record per field per `<category>.<YYYY-MM>` — a household's
own spending limit for one category in one calendar month (decision 9).

Not an account or obligation pack: it declares no `ACCOUNT`/`OBLIGATION`
(the attributes `registry._discover_packs`/`_discover_obligation_packs`
scan for), so neither registry ever finds it and it never joins
`all_accounts()`/`all_obligations()` — the same posture `packs/overlay.py`
and `packs/accounts.py` already hold for their own sidecar matters
(`tests/test_budget.py::test_the_budget_sidecar_is_not_a_discovered_pack`).

    limit (a spending limit, money)         → L4

**Why `limit` is `L4` outright, unlike `overlay`'s `category`.** A category
word can be ordinary or protected, so it has a floor to compose up from
(step 2, then step 3 only for a closed word list). A dollar figure has no
such floor: whichever category it governs, it is money tied to what the
household spends on that category (step 3), the same reason
`packs/obligations.py` gives its own `amount` — classified at the ceiling
from the start, the same posture `overlay`'s `note` takes for open text.

**One field, not two.** An earlier draft carried a `note` here as well,
mirroring `packs/overlay.py`'s own free-text note — with nothing that ever
wrote one. A declared field no writer fills is a rung to keep true for a
value that never arrives, so it is gone; a household that wants to say *why*
a limit is what it is says it on the transaction (`transaction tag --note`),
and a budget note can be added here the day a door exists to write one.

`budget.py`'s `envelopes()` never stores what it derives — a category's
spend-versus-limit state for a month is arithmetic over the books and the
limits on file, computed fresh on every call, the "mirror, not judge"
posture `balance.py` documents for a running total.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["MATTER", "SCHEMA", "FIELDS"]

#: The sidecar matter every budget-limit record is filed under — never a
#: pack name in `all_accounts()`/`all_obligations()` (see the module
#: docstring).
MATTER = "budget"


def _field(rung: Rung, why: str, *, derived: str | None = None) -> dict[str, Any]:
    decl: dict[str, Any] = {"rung": rung, "matter": MATTER, "why": why}
    if derived is not None:
        decl["derived"] = derived
    return decl


#: The closed schema for one category-month's budget entry. Ordered by
#: rung, matching the layout every other pack in this package uses.
SCHEMA: dict[str, Any] = {
    "limit": _field(
        Rung.L4,
        "step 3: a spending limit is money tied to the category it "
        "governs — the same reason packs/obligations.py gives its own "
        "amount. A dollar figure has no lower floor to compose up from, "
        "so it is classified at the ceiling outright.",
        derived="a limit is set",
    ),
}

#: Classified at import (I-11). Removing any field's rung above dies here,
#: naming the field, before this module can be imported by anything else.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
