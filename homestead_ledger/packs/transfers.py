"""The transfer-pairing pack — decision 9's schema for the sidecar matter
`transfers`, one record type: `pair`, keyed by the **outgoing** leg's
transaction fingerprint.

A transfer between two of the household's own accounts posts twice — a
debit on the account money left, a credit on the account it landed in — and
without a pairing record each leg reads as ordinary income or an ordinary
outflow: `recurring.detect_recurring` can call a recurring transfer a
subscription, and a running balance would double-count money the household
never actually spent. `transfers.py` is the writer and reader; this module
is only the schema.

    pair (counterpart fp, from label, to label)  →  L2  (references only)

The value is a mapping, not a bare rung, for the reason every other pack's
is: `classify_schema` reads the `"rung"` key and ignores the rest, so the
matter and the justifying sentence travel with the rung as a reviewable
record (step 5 of the classification procedure).

**This is not an account-*kind* pack.** It declares no `ACCOUNT` (the
attribute `registry._discover_packs` scans for) and no `OBLIGATION` (the
attribute `registry._discover_obligation_packs` scans for), so neither
registry ever finds it and a household's chosen transfer label can never be
mistaken for a registered kind — the same posture `packs/accounts.py`
documents for the `accounts` sidecar, held here by
`tests/test_transfers.py`.

**Why `pair` is one record, not one-per-field like `packs/accounts.py`.**
`{counterpart, from, to}` are three references that only ever mean anything
together — a `to` with no `counterpart` is not a smaller fact, it is not a
transfer at all — so it is written and read as one L2 record, the same
shape `obligations.py`'s own `paid_by` record already uses for
`{account, fingerprint}`.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["MATTER", "SCHEMA", "FIELDS"]

#: The sidecar matter every pairing record is filed under — never a pack
#: name in `all_accounts()`/`all_obligations()` (see the module docstring).
MATTER = "transfers"


def _field(rung: Rung, why: str) -> dict[str, Any]:
    return {"rung": rung, "matter": MATTER, "why": why}


#: The closed schema for a pairing record.
SCHEMA: dict[str, dict[str, Any]] = {
    "pair": _field(
        Rung.L2,
        "step 1 (public in this matter's own forum?) answers no and step 2 "
        "(identity or protected category?) also answers no — a pairing "
        "record is references only: a counterpart fingerprint and two "
        "account labels, every one of them a key this household already "
        "holds elsewhere on the books. The same posture packs/accounts.py "
        "gives kind, and packs/obligations.py gives its own paid_by record.",
    ),
}

#: Classified at import (I-11). Removing the field's rung above dies here,
#: naming it, before this module can be imported by anything else.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
