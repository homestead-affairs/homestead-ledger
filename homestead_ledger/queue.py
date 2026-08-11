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


def counts(store: Sidecar, *, today: str, soon_days: int = 14) -> dict[str, int]:
    """The raw aggregate — `overdue` and `due_soon` across all obligation
    kinds — before re-identification. `due_soon` is a not-yet-overdue due
    date falling within `soon_days`. Gaps count as neither; an unassessable
    due date is surfaced in `queue()`, not folded into a number."""
    overdue = 0
    due_soon = 0
    for item in queue(store, today=today):
        if item.gap:
            continue
        if item.overdue:
            overdue += 1
        elif item.days_until is not None and item.days_until <= soon_days:
            due_soon += 1
    return {"overdue": overdue, "due_soon": due_soon}


def cover(store: Sidecar, *, today: str, soon_days: int = 14) -> dict[str, int]:
    """The counts the resting cover may show — the aggregate passed through
    the re-identification check (I-31), so a number appears only where it
    reveals nothing about which obligation it came from. Over the single
    obligation kind bite 2 registers, this is empty, and the cover rests on
    'Nothing is open'."""
    return cover_counts(
        list(all_obligations()), **counts(store, today=today, soon_days=soon_days)
    )
