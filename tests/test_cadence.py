"""`cadence.roll_forward` — the closed set of recurrence words, and the
arithmetic that advances a due date once it has been paid.

The load-bearing behaviour: `roll_forward` walks forward from the *due*
date, never from `paid_on`, and month-length cadences anchor every step on
the *original* day of month rather than compounding a previous clamp (a
January 31st due date must reach March 31st, not drift to the 28th
permanently).
"""
from __future__ import annotations

from datetime import date

import pytest

from homestead_ledger.cadence import (
    CADENCES,
    UnknownCadence,
    previous_due,
    roll_forward,
)


def test_cadences_is_the_closed_set_the_plan_names():
    assert CADENCES == ("weekly", "biweekly", "monthly", "quarterly", "yearly", "once")


# ── the roll-forward table ───────────────────────────────────────────────────

def test_weekly_advances_seven_days():
    assert roll_forward(date(2026, 8, 5), "weekly", date(2026, 8, 6)) == date(2026, 8, 12)


def test_biweekly_advances_fourteen_days():
    assert roll_forward(date(2026, 8, 5), "biweekly", date(2026, 8, 6)) == date(2026, 8, 19)


def test_biweekly_across_a_year_boundary():
    assert roll_forward(date(2026, 12, 25), "biweekly", date(2026, 12, 26)) == date(2027, 1, 8)


def test_monthly_clamps_at_a_short_month_when_paid_promptly():
    """Paid within the first period: Jan 31 -> Feb 28 (2026 is not a leap
    year) — the ordinary, single-period case."""
    assert roll_forward(date(2026, 1, 31), "monthly", date(2026, 2, 1)) == date(2026, 2, 28)


def test_monthly_does_not_compound_the_clamp_across_periods():
    """Jan 31 -> Feb 28 -> Mar 31, never Mar 28: `paid_on` falls after the
    clamped February date, so this needs the *second* period — and the
    second period is computed from the original Jan 31, not from the Feb 28
    the first period clamped to. A "recompute from the last result" bug (the
    module docstring names the dateutil-style predecessor) would answer
    Mar 28 here instead."""
    assert roll_forward(date(2026, 1, 31), "monthly", date(2026, 3, 1)) == date(2026, 3, 31)


def test_monthly_clamps_to_29_in_a_leap_year():
    jan31 = date(2028, 1, 31)   # 2028 is a leap year
    assert roll_forward(jan31, "monthly", date(2028, 2, 1)) == date(2028, 2, 29)


def test_quarterly_from_nov_30():
    # Nov 30 + 3 months = Feb (28 or 29) — clamped, no 31 to anchor on here.
    assert roll_forward(date(2026, 11, 30), "quarterly", date(2027, 1, 1)) == date(2027, 2, 28)


def test_yearly_from_feb_29_in_a_non_leap_target_year():
    assert roll_forward(date(2028, 2, 29), "yearly", date(2029, 1, 1)) == date(2029, 2, 28)


def test_yearly_from_feb_29_back_to_a_leap_target_year():
    assert roll_forward(date(2028, 2, 29), "yearly", date(2031, 6, 1)) == date(2032, 2, 29)


def test_paid_on_before_due_rolls_exactly_one_period():
    """Paying early does not skip ahead — it still advances by one cadence
    length from the due date, never zero and never two."""
    assert roll_forward(date(2026, 10, 1), "monthly", date(2026, 9, 20)) == date(2026, 11, 1)


def test_paid_on_far_past_due_rolls_multiple_periods():
    """A due date lapsed for months advances however many periods separate
    it from `paid_on` — never just one, and never guessed."""
    assert roll_forward(date(2026, 1, 1), "monthly", date(2026, 6, 15)) == date(2026, 7, 1)


def test_once_has_no_next_date():
    assert roll_forward(date(2026, 9, 1), "once", date(2026, 9, 1)) is None
    assert roll_forward(date(2026, 9, 1), "once", date(2030, 1, 1)) is None


def test_an_unknown_cadence_is_refused_by_name():
    with pytest.raises(UnknownCadence):
        roll_forward(date(2026, 9, 1), "fortnightly", date(2026, 9, 2))


def test_roll_forward_takes_dates_not_text():
    with pytest.raises(TypeError):
        roll_forward("2026-09-01", "monthly", date(2026, 9, 2))
    with pytest.raises(TypeError):
        roll_forward(date(2026, 9, 1), "monthly", "2026-09-02")


# ── an independent table, written out by hand ─────────────────────────────
#
# Not a re-parametrisation of the cases above: each row was reasoned from a
# calendar rather than from the implementation, and the awkward corners were
# picked deliberately — the two US daylight-saving switches (which a
# `timedelta(days=…)` walk must ignore, because these are calendar dates and
# not instants), a leap day landed on and stepped over, the three month-end
# days through February in both a common year (2027) and a leap year (2028),
# a quarter from August 31, and February 29 2028 rolled yearly into the next
# leap year.

_TABLE: tuple[tuple[date, str, date, date | None], ...] = (
    # weekly straddling the 2027 spring-forward (Mar 14) and fall-back (Nov 7)
    (date(2027, 3, 10), "weekly", date(2027, 3, 10), date(2027, 3, 17)),
    (date(2027, 11, 3), "weekly", date(2027, 11, 3), date(2027, 11, 10)),
    # biweekly over and onto the 2028 leap day
    (date(2028, 2, 20), "biweekly", date(2028, 2, 20), date(2028, 3, 5)),
    (date(2028, 2, 15), "biweekly", date(2028, 2, 15), date(2028, 2, 29)),
    # the 29th / 30th / 31st through a February with 28 days
    (date(2027, 1, 29), "monthly", date(2027, 1, 29), date(2027, 2, 28)),
    (date(2027, 1, 30), "monthly", date(2027, 1, 30), date(2027, 2, 28)),
    (date(2027, 1, 31), "monthly", date(2027, 1, 31), date(2027, 2, 28)),
    # …and through a February with 29
    (date(2028, 1, 29), "monthly", date(2028, 1, 29), date(2028, 2, 29)),
    (date(2028, 1, 30), "monthly", date(2028, 1, 30), date(2028, 2, 29)),
    (date(2028, 1, 31), "monthly", date(2028, 1, 31), date(2028, 2, 29)),
    # quarterly from a 31-day month into a 30-day one, and on into February
    (date(2026, 8, 31), "quarterly", date(2026, 8, 31), date(2026, 11, 30)),
    (date(2026, 11, 30), "quarterly", date(2026, 11, 30), date(2027, 2, 28)),
    # yearly out of a leap day and back into one, four periods late
    (date(2028, 2, 29), "yearly", date(2028, 2, 29), date(2029, 2, 28)),
    (date(2029, 2, 28), "yearly", date(2029, 2, 28), date(2030, 2, 28)),
    (date(2028, 2, 29), "yearly", date(2032, 2, 1), date(2032, 2, 29)),
    # paid exactly on the due date, and one day early: one period either way
    (date(2026, 6, 15), "monthly", date(2026, 6, 15), date(2026, 7, 15)),
    (date(2026, 6, 15), "monthly", date(2026, 6, 14), date(2026, 7, 15)),
    # three periods late: every skipped period is stepped, not one and hope
    (date(2026, 1, 31), "monthly", date(2026, 5, 2), date(2026, 5, 31)),
    (date(2026, 1, 1), "weekly", date(2026, 1, 20), date(2026, 1, 22)),
    # and the one with no next date at all
    (date(2026, 1, 1), "once", date(2026, 1, 1), None),
)


@pytest.mark.parametrize("due,cadence,paid_on,expected", _TABLE)
def test_roll_forward_against_a_hand_written_table(due, cadence, paid_on, expected):
    assert roll_forward(due, cadence, paid_on) == expected


# ── the persisted anchor ──────────────────────────────────────────────────

def test_the_anchor_restores_a_day_a_previous_clamp_took_away():
    """The whole point: handed Feb 28 (already clamped) and told the real
    day is the 31st, March is the 31st — not the 28th it would otherwise
    inherit and keep forever."""
    assert roll_forward(date(2026, 2, 28), "monthly", date(2026, 2, 28),
                        anchor_day=31) == date(2026, 3, 31)
    assert roll_forward(date(2026, 2, 28), "monthly", date(2026, 2, 28)) == date(2026, 3, 28)


def test_the_anchor_still_clamps_where_the_month_is_short():
    """An anchor is a preference, not a promise: April has no 31st."""
    assert roll_forward(date(2026, 3, 31), "monthly", date(2026, 3, 31),
                        anchor_day=31) == date(2026, 4, 30)


def test_the_anchor_is_ignored_by_day_length_cadences():
    """A week has no month-end to clamp against; the argument must not leak
    into the arithmetic that does not use it."""
    assert roll_forward(date(2026, 1, 5), "weekly", date(2026, 1, 5),
                        anchor_day=31) == date(2026, 1, 12)
    assert roll_forward(date(2026, 1, 5), "biweekly", date(2026, 1, 5),
                        anchor_day=31) == date(2026, 1, 19)


# ── previous_due, the window a "paid ✓" mark is allowed to claim ───────────

@pytest.mark.parametrize("due,cadence,expected", [
    (date(2026, 8, 1), "monthly", date(2026, 7, 1)),
    (date(2026, 3, 1), "weekly", date(2026, 2, 22)),
    (date(2026, 3, 1), "biweekly", date(2026, 2, 15)),
    (date(2027, 2, 28), "quarterly", date(2026, 11, 28)),
    (date(2029, 2, 28), "yearly", date(2028, 2, 28)),
    (date(2026, 3, 1), "once", None),
])
def test_previous_due_steps_one_period_back(due, cadence, expected):
    assert previous_due(due, cadence) == expected


def test_previous_due_uses_the_anchor_too():
    """March 31 back one month is February 28, not "February 31"."""
    assert previous_due(date(2026, 3, 31), "monthly", anchor_day=31) == date(2026, 2, 28)


def test_previous_due_refuses_an_unknown_cadence():
    with pytest.raises(UnknownCadence):
        previous_due(date(2026, 1, 1), "fortnightly")


# ── the detector and the form name the same cadences (I-23) ───────────────

def test_every_recurring_bucket_names_a_cadence():
    """`recurring.py` infers a cadence from observed gaps and the obligations
    form takes one the operator declares. They were two vocabularies — the
    detector said `annual` where `CADENCES` says `yearly`, so the
    subscriptions pane could report a word the form beside it would refuse.

    The check lives here rather than as an import in `recurring.py`, which
    deliberately imports nothing from this package
    (`test_recurring.py::test_the_module_does_not_import_the_store_books_balance_or_homestead_engine`).
    """
    from homestead_ledger import recurring
    names = [name for name, _lo, _hi in recurring._CADENCE_BUCKETS]
    assert names and set(names) <= set(CADENCES)
    assert set(recurring._MIN_OCCURRENCES) <= set(CADENCES)
    # the buckets are ordered by interval and do not overlap
    bounds = [(lo, hi) for _n, lo, hi in recurring._CADENCE_BUCKETS]
    assert all(a[1] < b[0] for a, b in zip(bounds, bounds[1:]))


def test_the_bucket_check_catches_a_planted_rogue_cadence():
    """A scan that has never fired has not been shown to check anything: the
    same assertion, over a table carrying a bucket name `CADENCES` does not
    know, must fail."""
    planted = (("weekly", 5, 9), ("fortnightly", 12, 16), ("monthly", 25, 35))
    names = [name for name, _lo, _hi in planted]
    assert not set(names) <= set(CADENCES)
