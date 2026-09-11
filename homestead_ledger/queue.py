"""The "what's due" queue — money analog of homestead-law's `queue.py`.

*A homesteader knows what the season owes.* This is that, for the household's
recurring obligations: rent, insurance, property tax, registration,
subscriptions. It is also the module BUG-6 was about — the predecessor's
urgent queue hardcoded its matter list and workers' comp fell out of it,
never iterated. This one calls `all_obligations()` (the registry, I-23) and
nothing else, so an obligation kind that exists is a kind the queue reaches.

**It reaches no payload.** Unlike homestead-law's queue, this repo's engine
version does not ship a `Reader.deadlines()` keyed to our own field name
(`due_date`, not the engine's literal `"deadline"` item type), so this module
re-derives that read here rather than adding this file to the chokepoint's
`ALLOWED_PAYLOAD` (`docs/build-plan.md`'s "prefer not to"). It reads each
`due_date` record through `serve()` — the same gate `window.py` and the
engine's own `Reader.deadlines()` use — and parses the **served** value, never
`record.payload` directly.

**Why parsing the served value is safe here, and would not be for an
arbitrary field.** `packs/obligations.py` fixes `due_date` at `Rung.L2` for
every real obligation, and `L2` **renders** (never derives) on `S1_LIST` — so
`serve(record, Surface.S1_LIST).value` *is* the stored date string for every
legitimately-classified obligation, byte for byte the same thing
`record.payload` would give. The only way `served.value` ever differs from
the payload is a record hydrated at `L4` (derives) or denied at `L5` — an
`L5` due date is dropped below before urgency is ever computed, and an `L4`
one (not a shape this pack's schema produces, only reachable by writing a
record directly, off the classified path) degrades to a **gap**: its derived
text will not parse as a date, so it is surfaced rather than silently wrong.
That degrade is intentional — never guessing at a date is I-8's whole point
— and is why this module can stay off the payload boundary.

**Urgency is operational; the specifics are gated.** `days_until` and
`overdue` are computed from the parsed date so the queue can order and count.
What the operator *sees* for each item is `shown` — already through the
gate. A sealed (`L5`) due date is not in the queue at all. And a due date
whose stored value will not parse is a **gap** (I-8): surfaced at the top,
flagged, never silently dropped.

The **cover** counts (I-31) are the queue's aggregate passed through the
re-identification check, so the resting screen shows a number only where it
reveals nothing about which obligation it came from.

**A resolved obligation drops out here, not out of the store.** There is no
delete on `Sidecar` (I-9's append-only posture holds for obligations too), so
`mark_paid` (`obligations.py`) marking a `once` obligation done writes a
`(kind, "resolved", id)` record rather than removing anything, and this is
where that record takes effect: an item with one on file is skipped before
it is ever scored for urgency, the same way an `L5` due date is dropped
without a trace.
"""
from __future__ import annotations

from dataclasses import dataclass

from homestead.keep.dates import UnparseableDate, parse_deadline
from homestead.keep.rungs import Disposition, Rung, Surface, serve

from homestead_ledger.app.cover import cover_counts
from homestead_ledger.registry import all_obligations
from homestead_ledger.store import Ref, Sidecar

__all__ = ["QueueItem", "queue", "counts", "cover"]

#: The field this module reads. Every obligation's other fields (`name`,
#: `amount`, `cadence`) live under the same item id but are not the queue's
#: business — a due-date row references its item id, and a future detail
#: pane (bite 3) is what opens the sibling fields.
_DUE_DATE = "due_date"


@dataclass(frozen=True)
class QueueItem:
    """One line of the queue: which obligation kind, the reference to open
    it, the gated display, and the urgency. `days_until` is `None` for a gap
    (an unparseable due date), and `gap` says why."""

    kind: str
    ref: Ref
    rung: Rung
    shown: str
    overdue: bool
    days_until: int | None
    gap: bool


def _urgency(shown: str, today: str) -> tuple[int | None, bool, bool]:
    """`(days_until, overdue, gap)` from the gated display text. See the
    module docstring for why parsing `shown` rather than a raw payload is
    the correct read for this field."""
    try:
        deadline = parse_deadline(shown, today)
    except UnparseableDate:
        return None, False, True
    return deadline.days_until, deadline.overdue, False


def _sort_key(item: QueueItem) -> tuple[int, int]:
    """Gaps first — a due date that cannot be assessed needs a hand before
    any that can (I-8). Then by `days_until` ascending: the most overdue
    (most negative) first, then the soonest upcoming."""
    if item.gap:
        return (0, 0)
    return (1, item.days_until if item.days_until is not None else 0)


def queue(store: Sidecar, *, today: str) -> list[QueueItem]:
    """Every obligation kind's due dates, in one list, ordered by what needs
    acting on first. Iterates `all_obligations()` — so a newly registered
    obligation kind's due dates appear here with no change to this function
    (the BUG-6 fix)."""
    items: list[QueueItem] = []
    for kind in all_obligations():
        for ref, record in store.records(kind):
            if ref[1] != _DUE_DATE:
                continue
            if store.has(kind, "resolved", ref[2]):
                continue
            served = serve(record, Surface.S1_LIST)
            if served.disposition is Disposition.DENY:
                continue
            shown = str(served.value)
            days_until, overdue, gap = _urgency(shown, today)
            items.append(
                QueueItem(
                    kind=kind, ref=ref, rung=served.rung, shown=shown,
                    overdue=overdue, days_until=days_until, gap=gap,
                )
            )
    items.sort(key=_sort_key)
    return items


#: The categories the cover counts. Named once so the aggregate and its own
#: distribution cannot come to disagree about which keys exist — the engine
#: refuses a distribution that names a category the aggregate does not.
_CATEGORIES = ("overdue", "due_soon")


def counts_by_kind(
    store: Sidecar, *, today: str, soon_days: int = 14
) -> dict[str, dict[str, int]]:
    """The raw aggregate **spread over the obligation kind each item belongs
    to** — `{kind: {"overdue": n, "due_soon": m}}`, one entry per registered
    kind whether or not it contributes, so the roster and the distribution
    are the same set of names.

    This is the household's real distribution, and it is what makes the
    cover's second gate mean something: `(2, 0)` across two registered kinds
    is two bills under one kind, and a count that resolves to one kind is
    that kind's news, not the household's (I-31)."""
    spread = {kind: {c: 0 for c in _CATEGORIES} for kind in all_obligations()}
    for item in queue(store, today=today):
        if item.gap:
            continue
        if item.overdue:
            spread[item.kind]["overdue"] += 1
        elif item.days_until is not None and item.days_until <= soon_days:
            spread[item.kind]["due_soon"] += 1
    return spread


def counts(store: Sidecar, *, today: str, soon_days: int = 14) -> dict[str, int]:
    """The raw aggregate — `overdue` and `due_soon` across all obligation
    kinds — before re-identification. `due_soon` is a not-yet-overdue due
    date falling within `soon_days`. Gaps count as neither; an unassessable
    due date is surfaced in `queue()`, not folded into a number.

    Summed from `counts_by_kind` rather than counted again alongside it: two
    passes over the same queue is two chances to disagree, and a total that
    disagrees with its own distribution is refused outright at the cover
    (I-11), which would take the resting screen down over an arithmetic slip
    nobody would otherwise see."""
    spread = counts_by_kind(store, today=today, soon_days=soon_days)
    return {
        category: sum(per[category] for per in spread.values())
        for category in _CATEGORIES
    }


def cover(store: Sidecar, *, today: str, soon_days: int = 14) -> dict[str, int]:
    """The counts the resting cover may show — the aggregate passed through
    the re-identification check (I-31), so a number appears only where it
    reveals nothing about which obligation it came from. Over the single
    obligation kind bite 2 registers, this is empty, and the cover rests on
    'Nothing is open'.

    **X7-drift fix.** The distribution goes with the aggregate. Without it
    the check reads only the roster's *shape* — how many obligation kinds are
    registered — and a second registered kind that contributes nothing was
    enough to show a count that came entirely from the first. That is the
    leak homestead-law's L2c audit found and the engine closed in 0.7.0
    (`by_matter`); this module carried the pre-fix port until now. It shows
    nothing over today's single-kind registry either way — the fix is for the
    day a second kind is registered, which is what `all_obligations()` exists
    to make a non-event."""
    spread = counts_by_kind(store, today=today, soon_days=soon_days)
    totals = {
        category: sum(per[category] for per in spread.values())
        for category in _CATEGORIES
    }
    return cover_counts(list(all_obligations()), by_kind=spread, **totals)
