"""The overlay pack — bite 4's schema for the sidecar matter `overlay`, one
record per field per transaction **fingerprint** (`books.fingerprint`, the
same content hash `books.import_transaction` keys the canonical books
under). Not an account pack: it declares no `ACCOUNT`/`OBLIGATION` (the
attributes `registry._discover_packs`/`_discover_obligation_packs` scan
for), so neither registry ever finds it and it never joins `all_accounts()`/
`all_obligations()` — `tests/test_overlay.py::test_the_overlay_sidecar_is_
not_a_discovered_pack` guards that directly, the posture `packs/accounts.py`
already holds for the account-instance sidecar.

The household's own layer over its read-only books ("mirror, not judge"): a
category, a free-text note, a confirmed merchant name, and a "do not use"
flag that excludes one transaction from recurring detection, budget
envelopes and every export (`overlay.excluded_fingerprints`).

    category (a closed-shape word)          → L3, raised to L4 by
                                               PROTECTED_CATEGORY_WORDS
    confirmed_merchant (a resolved name)    → L3
    do_not_use (excluded from aggregates)   → L2
    note (free text)                        → L4

**Why `category` is L3 and not L4 outright — and why the advisory only ever
argues up.** An ordinary category (`groceries`) identifies a kind of
spending (step 2) but is not yet a protected category (step 3) — the floor
every ordinary category sits at, the pack's own declaration. `overlay.tag`
composes a category *containing* a word from `PROTECTED_CATEGORY_WORDS` up
to L4 instead, reusing this schema's own `derived` string for the L4 case;
there is no path anywhere that composes an already-flagged category back
down to L3 — `homestead.keep.advise`'s "argue up, never down" rule, applied
here to one closed word list rather than a whole matter.

**Why `note` has no floor to raise from.** Open text can name anything —
step 3 cannot be ruled out the way it can for a closed category word — so
`note` is classified at the ceiling from the start rather than composed up
later.

**Why `confirmed_merchant` mirrors `checking.py`'s `description`, and
`do_not_use` mirrors `obligations.py`'s `cadence`.** A confirmed merchant
name resolves to a party with no protected category of its own; a flag
about how a row is *used* (not what it is) is household metadata, the same
two postures those packs already state.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["MATTER", "SCHEMA", "FIELDS", "PROTECTED_CATEGORY_WORDS"]

#: The sidecar matter every overlay record is filed under — never a pack
#: name in `all_accounts()`/`all_obligations()` (see the module docstring).
MATTER = "overlay"

#: The closed, hand-reviewed list a category is held against. Substring
#: containment (`overlay._is_protected`), not an exact match: `medical-copay`
#: contains `medical`, and a category that merely *contains* a protected
#: word is exactly the case the advisory must not talk itself out of
#: raising — the false-negative direction is the one that costs someone the
#: L4 they needed.
PROTECTED_CATEGORY_WORDS: frozenset[str] = frozenset({
    "medical", "therapy", "pharmacy", "attorney", "legal", "court",
    "bankruptcy", "child-support", "union", "church", "donation", "political",
})


def _field(rung: Rung, why: str, *, derived: str | None = None) -> dict[str, Any]:
    decl: dict[str, Any] = {"rung": rung, "matter": MATTER, "why": why}
    if derived is not None:
        decl["derived"] = derived
    return decl


#: The closed schema for one transaction's overlay. Ordered by rung, matching
#: the layout every other pack in this package uses.
SCHEMA: dict[str, dict[str, Any]] = {
    "category": _field(
        Rung.L3,
        "step 1 answers no; step 2 answers 'identifies a kind of spending' "
        "but not yet a protected category — the floor every ordinary "
        "category sits at. `overlay.tag` composes a category containing a "
        "PROTECTED_CATEGORY_WORDS word up to L4 instead — the pack declares "
        "only the floor; the advisory argues up, never down.",
        derived="a category is on file",
    ),
    "confirmed_merchant": _field(
        Rung.L3,
        "step 2 answers yes: a confirmed merchant name resolves to a party, "
        "the same posture packs/checking.py gives description. Step 3 finds "
        "no protected category of its own, so it climbs no higher.",
        derived="a merchant is confirmed",
    ),
    "do_not_use": _field(
        Rung.L2,
        "step 1 and step 2 both answer no: a flag that a transaction is "
        "excluded from recurring detection, budget envelopes and every "
        "export says how the row is used, not what it is — the same "
        "posture packs/obligations.py gives cadence.",
    ),
    "note": _field(
        Rung.L4,
        "step 3: free text can name anything, including a protected "
        "category — unlike a closed category word it cannot be held to a "
        "floor and composed up only when needed, so it is classified at "
        "the ceiling from the start.",
        derived="a note is on file",
    ),
}

#: Classified at import (I-11). Removing any field's rung above dies here,
#: naming the field, before this module can be imported by anything else.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
