"""I-31 — the resting state reveals nothing (`homestead_ledger.app.cover`),
ported from homestead-law's `tests/test_cover.py`. Same mechanism, same
worked cases, "matter" read as "obligation kind".
"""
from __future__ import annotations

import pytest

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


# ── the distribution gate: `(2, 0)` is one kind's news wearing a number ─────
#
# X7-drift audit, 2026-09-11. This module's `cover_counts` was a copy of
# homestead-law's, taken before the L2c audit found that the second gate read
# the roster's *shape* rather than the household's spread. The engine closed
# it in 0.7.0 (`by_matter`); the copy here never did, and the copy is what the
# ledger's two covers call. It is now an adapter over the engine's one copy,
# and these are the cases that say so.


def test_a_two_zero_spread_across_two_kinds_is_dropped():
    """Two overdue bills, both under one of two registered kinds. The roster
    gate passes (two kinds exist) and the count gate passes (two items), and
    the number still resolves to `obligations` the instant it is read."""
    counts = cover_counts(
        kinds=["obligations", "subscriptions"],
        by_kind={"obligations": {"overdue": 2}, "subscriptions": {"overdue": 0}},
        overdue=2,
    )
    assert counts == {}


def test_a_one_one_spread_across_two_kinds_survives():
    """The same aggregate, genuinely spread: one bill under each kind. Now
    "2 overdue" has no answer to "which one?", which is the whole test."""
    counts = cover_counts(
        kinds=["obligations", "subscriptions"],
        by_kind={"obligations": {"overdue": 1}, "subscriptions": {"overdue": 1}},
        overdue=2,
    )
    assert counts == {"overdue": 2}


def test_the_distribution_gates_each_category_on_its_own():
    """One category concentrated, one spread, in a single call — the
    concentrated one is dropped and the spread one survives, so a passing
    category cannot carry a failing one through beside it."""
    counts = cover_counts(
        kinds=["obligations", "subscriptions"],
        by_kind={
            "obligations": {"overdue": 3, "due_soon": 2},
            "subscriptions": {"overdue": 0, "due_soon": 2},
        },
        overdue=3,
        due_soon=4,
    )
    assert counts == {"due_soon": 4}


def test_omitting_the_distribution_is_the_old_answer_exactly():
    """`by_kind=None` is byte-identical to every call made before the
    parameter existed — the tightening is opt-in, so no existing caller's
    cover changed under it."""
    for kinds, counts in (
        (["obligations", "subscriptions"], {"overdue": 2}),
        (["obligations"], {"overdue": 5, "due_soon": 9}),
        (["a", "b", "c"], {"due_soon": 4, "overdue": 1}),
    ):
        assert cover_counts(kinds=kinds, **counts) == cover_counts(
            kinds=kinds, by_kind=None, **counts
        )


def test_a_distribution_that_disagrees_with_its_total_is_refused_by_name():
    """I-11: a caller that cannot state its own spread is refused, never
    given the softer gate. The refusal names the category and no count."""
    with pytest.raises(ValueError) as raised:
        cover_counts(
            kinds=["obligations", "subscriptions"],
            by_kind={"obligations": {"overdue": 1}, "subscriptions": {"overdue": 1}},
            overdue=7,
        )
    assert "overdue" in str(raised.value)


def test_the_roster_is_read_as_a_set_not_a_list():
    """The engine's other hardening this copy had drifted past: two spellings
    of one kind are still one kind, so a duplicated roster entry must not
    satisfy the roster gate."""
    assert cover_counts(kinds=["obligations", "obligations"], overdue=5) == {}
