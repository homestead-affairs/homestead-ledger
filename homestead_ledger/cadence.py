"""How often a recurring obligation recurs, and what "next" means.

`packs/obligations.py` classifies `cadence` at `Rung.L2` — "monthly" is
descriptive metadata about the household's own schedule, no different in
posture from `due_date` — but until now nothing held the *word* itself to a
closed set: an operator (or the browser's `<select>`, or a CLI typo) could
write `"fortnightly"` into the field and nothing would ever notice, because
nothing rolled an obligation forward by it. `mark_paid` (`obligations.py`) is
that consumer now, and a consumer that reads a household-typed word to decide
how far to advance a date is exactly the shape I-23 already applies to a
matter or account *name*: **the set the household may choose from is one
enumeration, not a string nothing holds against anything.**

`CADENCES` is that enumeration. It **replaces** the residual note
`server.py`'s `_post_obligation` carried since bite 2 — "cadence is not held
against anything because nothing yet rolls an obligation forward by it" — now
that something does.

## `roll_forward`

The one piece of arithmetic this module has an opinion about: given an
obligation's current due date, its cadence, and the date it was actually
paid, what due date replaces it.

**It walks forward from the *due* date, never from `paid_on`.** A rent due
the 1st of the month, paid on the 3rd, is still due the 1st next month — the
schedule is the due date's own cadence, not a clock restarted from whenever
the household got around to paying. Paying early does not owe two periods
early either: `paid_on` only decides *how many* cadence-lengths to advance
before the answer lands strictly after the day paid, so a due date reached
before it is due still advances by exactly one period, and a due date paid
long after it lapsed advances by however many periods separate it from
`paid_on` — never fewer (I-11: a lapsed obligation's next due date is
computed, never guessed at by advancing once and hoping).

**Month-length cadences (`monthly`/`quarterly`/`yearly`) clamp to the target
month's real length, anchored on the *original* day of month, not on
whatever the previous roll clamped down to.** `dateutil`-style "add N months"
libraries that recompute from the last clamped result drift a January 31st
due date down to the 28th and never back up: Jan 31 → Feb 28 → Mar 28 → …,
permanently losing three days of a household's own schedule to February
having fewer of them. This module instead computes every step from the
*same* original due date — `_add_months(due, k)` for the target `k`, never
`_add_months(_add_months(due, 1), 1)` — so, **within one call** that must
step past several lapsed periods to clear `paid_on`, Jan 31 → Feb 28 → **Mar
31**: the month that has a 31st gets it back.

**What this does not fix, stated because the gap is the useful part.** This
function has no memory beyond its own arguments. Across *separate* calls —
an obligation's ordinary month-by-month life: pay January, the store now
holds Feb 28; pay February a month later and `roll_forward` is handed that
Feb 28, not the original Jan 31 — the anchor really has been lost by the
time the next call runs, and the next result is Mar 28: the exact drift
this function refuses *within* one call. Recovering the day-of-month across
separate months would need the obligation to persist it somewhere this
function never touches (an anchor field this bite does not add); until
then, a month-end due date that has ever clamped stays clamped on its
ordinary cadence, and only a lapsed multi-period catch-up — one call,
several periods, exactly the shape this function was written for — restores
it.

**`once` has no next date.** A one-time obligation paid is not due again;
`roll_forward` returns `None` for it, and the caller (`mark_paid`) reads that
as "resolved," not "advance to `None`."

**An unknown cadence is refused by name, not guessed at as the nearest
bucket.** `recurring.py`'s *detector* infers a cadence from observed gaps and
tolerates whatever bucket the data falls into; this module is the opposite
direction — an operator's own declared word, held to the closed set that
declaration must come from — and I-11 says a rule outside that set fails
closed.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

__all__ = ["CADENCES", "UnknownCadence", "roll_forward"]

#: The closed set of words an obligation's `cadence` field may hold. Ordered
#: shortest-interval first, purely for anything that prints them (the CLI
#: usage line, the server's `<select>`) — order carries no meaning to
#: `roll_forward`.
CADENCES: tuple[str, ...] = ("weekly", "biweekly", "monthly", "quarterly", "yearly", "once")


class UnknownCadence(ValueError):
    """A cadence outside `CADENCES` — refused by name (I-11), never treated
    as the nearest bucket or silently defaulted to `monthly`."""


def _add_months(base: date, months: int) -> date:
    """`base` advanced by exactly `months` calendar months, clamped to the
    target month's real length. Always computed from `base` directly — a
    caller that needs several steps calls this once per step with the
    cumulative month count, never by chaining this function's own output
    back through itself, which is what would let the clamp compound (see the
    module docstring's Jan 31 → Feb 28 → Mar 28 failure this avoids)."""
    total = base.month - 1 + months
    year = base.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(base.day, last_day))


#: One step function per month-length cadence: `(due, k) -> due advanced by
#: k periods`, anchored on `due` itself every time (see `_add_months`).
_MONTH_STEPS: dict[str, int] = {"monthly": 1, "quarterly": 3, "yearly": 12}

#: One step size (days) per fixed-length cadence.
_DAY_STEPS: dict[str, int] = {"weekly": 7, "biweekly": 14}


def _advance(due: date, cadence: str, periods: int) -> date:
    if cadence in _MONTH_STEPS:
        return _add_months(due, _MONTH_STEPS[cadence] * periods)
    return due + timedelta(days=_DAY_STEPS[cadence] * periods)


def roll_forward(due: date, cadence: str, paid_on: date) -> date | None:
    """The due date that replaces `due` once it has been paid on `paid_on`.

    Advances from `due` — never from `paid_on` — one cadence period at a
    time, until the result falls strictly after `paid_on`; see the module
    docstring for why that means a due date paid early still moves by
    exactly one period and a due date paid long after it lapsed moves by
    however many periods separate it from `paid_on`, never fewer.

    Returns `None` for `cadence == "once"` — there is no next date; the
    obligation is resolved, not rescheduled.

    Raises `UnknownCadence` for anything outside `CADENCES`, and `TypeError`
    if `due`/`paid_on` are not `datetime.date` — this function takes parsed
    dates, never date text; parsing (and its own refusal, `UnparseableDate`)
    happens once, at the edge, before this is ever called.
    """
    for name, value in (("due", due), ("paid_on", paid_on)):
        if not isinstance(value, date):
            raise TypeError(
                f"roll_forward's {name!r} argument must be a datetime.date, "
                f"not {type(value).__name__} — parse a date string once, at "
                "the edge, before calling this"
            )
    name = str(cadence).strip()
    if name not in CADENCES:
        raise UnknownCadence(
            f"cadence must be one of: {', '.join(CADENCES)}"
        )
    if name == "once":
        return None

    periods = 1
    while True:
        candidate = _advance(due, name, periods)
        if candidate > paid_on:
            return candidate
        periods += 1
