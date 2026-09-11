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

from homestead_ledger.cadence import CADENCES, UnknownCadence, roll_forward


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
