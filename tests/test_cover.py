"""I-31 — the resting state reveals nothing (`homestead_ledger.app.cover`),
ported from homestead-law's `tests/test_cover.py`. Same mechanism, same
worked cases, "matter" read as "obligation kind".
"""
from __future__ import annotations

from homestead_ledger.app.cover import K, cover_counts


def test_i31_the_cover_survives_re_identification():
    """'1 overdue' over a household where one obligation kind has due dates
    identifies that kind. The L2 check is not theoretical at three kinds."""
    counts = cover_counts(kinds=["obligations"], overdue=1)
    assert "overdue" not in counts


def test_a_count_of_one_is_dropped_even_across_many_kinds():
    counts = cover_counts(
        kinds=["obligations", "subscriptions", "utilities", "insurance"], overdue=1
    )
    assert "overdue" not in counts


def test_a_count_of_two_or_more_survives_when_kinds_survive():
    counts = cover_counts(kinds=["obligations", "subscriptions"], overdue=2)
    assert counts == {"overdue": 2}


def test_a_single_kind_drops_every_count_however_large():
    counts = cover_counts(kinds=["obligations"], overdue=5, due_soon=9)
    assert counts == {}


def test_no_kinds_shows_nothing():
    assert cover_counts(kinds=[]) == {}
    assert cover_counts(kinds=[], overdue=3) == {}


def test_a_zero_count_is_absent_never_rendered():
    counts = cover_counts(kinds=["obligations", "subscriptions"], overdue=0, due_soon=3)
    assert "overdue" not in counts
    assert counts == {"due_soon": 3}


def test_an_unpassed_category_is_simply_absent():
    counts = cover_counts(kinds=["obligations", "subscriptions"], due_soon=4)
    assert set(counts) == {"due_soon"}
    assert "overdue" not in counts


def test_survivors_render_as_their_real_counts():
    counts = cover_counts(
        kinds=["obligations", "subscriptions", "utilities"],
        due_soon=4,
        overdue=1,
        drafts_unsent=2,
    )
    assert counts == {"due_soon": 4, "drafts_unsent": 2}


def test_both_gates_are_needed_at_the_pinned_case():
    assert cover_counts(kinds=["obligations"], overdue=1) == {}
    assert cover_counts(kinds=["obligations"], overdue=5) == {}          # kinds gate
    assert cover_counts(kinds=["a", "b", "c"], overdue=1) == {}          # count gate


def test_a_non_integer_count_fails_closed():
    assert cover_counts(kinds=["a", "b"], overdue="2") == {}
    assert cover_counts(kinds=["a", "b"], overdue=None) == {}
    assert cover_counts(kinds=["a", "b"], overdue=True) == {}
    assert cover_counts(kinds=["a", "b"], overdue=3.0) == {}


def test_the_anonymity_floor_is_two():
    assert K == 2
