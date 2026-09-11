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

* **k ≥ 2 *contributing* obligation kinds**, when the caller can state its
  own spread (`by_kind`). The gate above reads the roster's *shape*; this
  one reads the household's actual distribution, and they are not the same
  question. Two registered kinds with a `(2, 0)` spread — both overdue bills
  under one kind — clears the roster gate and still resolves to that one
  kind the instant it is read. `(1, 1)` is the spread that genuinely has no
  answer to "which one?". This is the leak homestead-law's L2c audit found
  and E4-cover-distribution closed in the engine.

**Absence, not zero.** A dropped count leaves *no key* — never a `0` in its
place.

## Why this file is now an adapter and not an implementation

**X7-drift correction, 2026-09-11.** This file used to carry its own copy of
the arithmetic, ported from homestead-law before either hardening existed.
The engine has since fixed the copy it was ported from **twice** — the
roster is read as a *set* (two spellings of one kind are still one kind, so
`["obligations", "obligations"]` no longer satisfies the roster gate), and
`by_matter` closes the `(2, 0)` leak above — and this copy inherited
neither: a duplicated gate that drifts is worse than no duplication, which
is the same finding this sweep recorded about the protected-category word
list. So the arithmetic is the engine's one copy (`homestead.app.cover`,
floored at `homestead-affairs>=0.13.0`, far past the 0.7.0 that shipped
`by_matter`), and what stays here is the domain translation: "matter"
becomes "obligation kind", which is the only thing this module ever added.

## I-29 — the surface calculates nothing beyond this arithmetic

`cover_counts` compares integers and copies obligation-kind names. It
computes no deadline (that is `homestead.keep.dates`, driven from
`queue.py`), reads no rung, reaches no `.payload`, and reflects over nothing.
`tests/test_invariants_chokepoint.py` scans this file with the rest of
`homestead_ledger/app/`.
"""
from __future__ import annotations

#: `K` is the anonymity floor — the engine's own, re-exported rather than
#: restated, so this module cannot come to disagree with the arithmetic it
#: delegates to about what "at least two" means. Two is the smallest set in
#: which "which one?" has no answer.
from homestead.app.cover import K, cover_counts as _engine_cover_counts

__all__ = ["cover_counts", "K"]


def cover_counts(
    kinds: list[str],
    *,
    by_kind: dict[str, dict[str, int]] | None = None,
    **counts: int,
) -> dict[str, int]:
    """The counts the resting cover may show, and no more (I-31).

    `kinds` is the roster of registered obligation kinds — context for the
    check, never itself emitted. Each keyword is a per-category aggregate
    (`overdue=1`, `due_soon=4`, …). Returns a dict of only the categories
    that survive the re-identification check, each mapped to its real count.
    A category that does not survive is **absent** from the result.

    `by_kind` (obligation kind → category → count) is the distribution behind
    those aggregates, for a caller that has one — `queue.cover` does. With it
    supplied, a category survives only when at least `K` *distinct kinds*
    each contribute at least one to it, so a `(2, 0)` spread is dropped where
    the roster gate alone would have shown it. Omitting it (the default) is
    byte-identical to every call this function answered before the parameter
    existed.

    Fails closed on a stranger, exactly as the engine's does: a count that is
    not a plain integer at or above `K` is dropped rather than coerced, and a
    distribution that disagrees with its own totals is **refused** by name
    rather than repaired (I-11) — a caller that cannot state its spread does
    not get a softer gate than one that states none.

    The arithmetic itself is `homestead.app.cover.cover_counts`; this is the
    domain translation and nothing else (I-29). The engine's parameter is
    called `by_matter` because its roster is matters; here the roster is
    obligation kinds, and the name says so.
    """
    return _engine_cover_counts(list(kinds), by_matter=by_kind, **counts)
