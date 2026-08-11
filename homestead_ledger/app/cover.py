"""S1 — the cover's counts, and the re-identification check they survive
(I-31). Ported from homestead-law's `app/cover.py` for the money domain: same
mechanism, "matter" becomes "obligation kind" (`all_obligations()`'s roster).

The cover is the resting state of the S1 window (I-21): what the machine
shows with nobody's hand on it, in a room a second person can walk into
(F-1). "Nothing is open" is the answer whenever the check below has no
survivor. This file lets the cover show a **count** in exactly the cases
where the number reveals nothing about *which obligation* it came from, and
drops every count where it does.

**I-31 — the resting state reveals nothing.** A count survives the `L2`
re-identification check and no more. `L2` is not a property a count is born
with: an aggregate inherits the `max` of its inputs and *becomes* `L2` only
after a check that it cannot be resolved to a single obligation (the rung
model, `L2`, and step 2a of the classification procedure). Until it passes,
"1 overdue" over a household is not household news — it is *that one bill's*
news wearing a number.

## The rule, and why it is these two gates

A per-category count (`overdue=…`, `due_soon=…`) is shown only when it
survives **both** of these, and is otherwise absent:

* **k ≥ 2 on the count itself.** A count of `1` is one item, and one item
  lives in exactly one obligation kind — so `overdue=1` *resolves to* that
  obligation the instant it is read, no matter how many obligation kinds the
  household holds.

* **k ≥ 2 on the obligation kinds.** With a single registered obligation
  kind, the household *is* that kind, and every count is a fact asserted
  about it. Bite 2 registers exactly one kind (`packs/obligations.py`), so
  the resting cover shows nothing over the real registry until a second kind
  exists — the same posture homestead-law's demo has with `custody` alone.

**Absence, not zero.** A dropped count leaves *no key* — never a `0` in its
place.

## I-29 — the surface calculates nothing beyond this arithmetic

`cover_counts` compares integers and copies obligation-kind names. It
computes no deadline (that is `homestead.keep.dates`, driven from
`queue.py`), reads no rung, reaches no `.payload`, and reflects over nothing.
`tests/test_invariants_chokepoint.py` scans this file with the rest of
`homestead_ledger/app/`.
"""
from __future__ import annotations

__all__ = ["cover_counts", "K"]

#: The anonymity floor. A count survives only when at least `K` items *and*
#: at least `K` obligation kinds stand behind it — below either, the number
#: resolves to one obligation kind. Two is the smallest set in which "which
#: one?" has no answer.
K = 2


def cover_counts(kinds: list[str], **counts: int) -> dict[str, int]:
    """The counts the resting cover may show, and no more (I-31).

    `kinds` is the roster of registered obligation kinds — context for the
    check, never itself emitted. Each keyword is a per-category aggregate
    (`overdue=1`, `due_soon=4`, …). Returns a dict of only the categories
    that survive the re-identification check, each mapped to its real count.
    A category that does not survive is **absent** from the result.

    Fails closed on a stranger, exactly as homestead-law's does: a count that
    is not a positive integer at or above `K` is dropped rather than coerced.
    """
    n_kinds = len(kinds)
    if n_kinds < K:
        return {}

    shown: dict[str, int] = {}
    for category, count in counts.items():
        # bool is an int subclass; a boolean count is nonsense, and both True
        # (1) and False (0) fall below K anyway.
        if isinstance(count, bool) or not isinstance(count, int):
            continue
        if count >= K:
            shown[category] = count
    return shown
