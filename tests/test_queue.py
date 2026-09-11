"""The "what's due" queue — money analog of homestead-law's `tests/test_queue.py`.

BUG-6 was the urgent queue: it hardcoded its matter list and workers' comp fell
out of it, never iterated. The load-bearing test here is that the queue
iterates `all_obligations()` and nothing else, so an obligation kind that
exists is a kind the queue reaches. The rest holds the rung model at the
queue: an L5 due date is not in it, and an unparseable date is a surfaced gap
(I-8), never a silent drop.
"""
from __future__ import annotations

import types

import pytest

from homestead.keep.rungs import Classified, Rung
from homestead_ledger import queue as queue_mod
from homestead_ledger import registry as registry_mod
from homestead_ledger.queue import counts, cover, queue
from homestead_ledger.store import Sidecar

TODAY = "2026-08-10"


def _obligation(store: Sidecar, kind: str, item_id: str, rung: Rung, due_date: str, derived: str | None = None):
    store.put(kind, "due_date", item_id, Classified(rung, due_date, derived=derived))


def _register_second_obligation_kind(monkeypatch, name: str = "subscriptions") -> None:
    """Add a second obligation kind to the registry the way test_registry_
    obligations does — a real module, keyed by its own OBLIGATION, injected
    for the test."""
    fake = types.ModuleType(f"homestead_ledger.packs._fake_{name}")
    fake.OBLIGATION = name
    fake.FIELDS = {"due_date": Rung.L2}
    fake.SCHEMA = {"due_date": {"rung": Rung.L2, "obligation": name}}
    monkeypatch.setitem(
        registry_mod.OBLIGATION_REGISTRY, name, registry_mod._obligation_entry(fake)
    )


# ── the BUG-6 fix — the queue iterates the registry ──────────────────────────

def test_the_queue_iterates_the_registry_not_a_hardcoded_list(tmp_path, monkeypatch):
    """A newly registered obligation kind's due dates appear in the queue
    with no change to the queue itself."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _obligation(store, "obligations", "rent", Rung.L2, "2026-09-15", "a payment is due")
    _register_second_obligation_kind(monkeypatch, "subscriptions")
    _obligation(store, "subscriptions", "netflix", Rung.L2, "2026-08-20", "a payment is due")

    kinds_in_queue = {it.kind for it in queue(store, today=TODAY)}
    assert kinds_in_queue == {"obligations", "subscriptions"}


# ── ordering ─────────────────────────────────────────────────────────────────

def test_overdue_comes_before_upcoming(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _obligation(store, "obligations", "insurance", Rung.L2, "2026-09-15", "a payment is due")  # +36
    _obligation(store, "obligations", "rent", Rung.L2, "2026-08-05", "a payment is due")       # -5

    order = [it.ref[2] for it in queue(store, today=TODAY)]
    assert order.index("rent") < order.index("insurance")


def test_a_gap_is_surfaced_first_never_dropped(tmp_path, monkeypatch):
    """I-8: a due date whose stored value will not parse is not dropped — it
    is a gap, surfaced at the top, flagged, for a human to fix."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _obligation(store, "obligations", "insurance", Rung.L2, "2026-09-15", "a payment is due")
    _obligation(store, "obligations", "broken", Rung.L2, "sometime soon", "a payment is due")

    q = queue(store, today=TODAY)
    assert q[0].ref[2] == "broken"
    assert q[0].gap is True and q[0].days_until is None
    assert "broken" in {it.ref[2] for it in q}, "the gap is present, not dropped"


# ── the rung model, at the queue ─────────────────────────────────────────────

def test_a_sealed_obligation_is_not_in_the_queue(tmp_path, monkeypatch):
    """An L5 due date is dropped without a trace — the queue may not reveal,
    or count, what L5 forbids."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _obligation(store, "obligations", "insurance", Rung.L2, "2026-09-15", "a payment is due")
    store.put("obligations", "due_date", "sealed", Classified(Rung.L5, "2026-08-11"))

    refs = {it.ref[2] for it in queue(store, today=TODAY)}
    assert "sealed" not in refs
    assert "insurance" in refs


def test_a_resolved_obligation_is_dropped_not_shown(tmp_path, monkeypatch):
    """G3-cadence-paidby: `mark_paid` marks a `once` obligation done by
    writing a `resolved` record rather than deleting anything (there is no
    delete on `Sidecar`) — the queue is where that record takes effect."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _obligation(store, "obligations", "insurance", Rung.L2, "2026-09-15", "a payment is due")
    _obligation(store, "obligations", "dmv", Rung.L2, "2026-08-01", "a payment is due")
    store.put("obligations", "resolved", "dmv", Classified(Rung.L2, "resolved"))

    refs = {it.ref[2] for it in queue(store, today=TODAY)}
    assert "dmv" not in refs
    assert "insurance" in refs


def test_only_the_due_date_field_is_read_not_the_others(tmp_path, monkeypatch):
    """`name`, `amount`, and `cadence` are separate records under the same
    item id — the queue reads only `due_date`, never mistaking a sibling
    field for a deadline."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    store.put("obligations", "name", "rent", Classified(Rung.L3, "Landlord LLC", derived="a payee is on file"))
    store.put("obligations", "amount", "rent", Classified(Rung.L4, "-1200.00", derived="a payment is due"))
    store.put("obligations", "cadence", "rent", Classified(Rung.L2, "monthly"))
    _obligation(store, "obligations", "rent", Rung.L2, "2026-08-05", "a payment is due")

    q = queue(store, today=TODAY)
    assert len(q) == 1
    assert q[0].ref == ("obligations", "due_date", "rent")


# ── counts and the cover (I-31) ──────────────────────────────────────────────

def test_counts_aggregate_overdue_and_due_soon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _obligation(store, "obligations", "rent", Rung.L2, "2026-08-05", "overdue")       # -5 overdue
    _obligation(store, "obligations", "insurance", Rung.L2, "2026-08-12", "due soon")  # +2 soon
    _obligation(store, "obligations", "registration", Rung.L2, "2026-09-30", "far off")  # +51 not soon

    assert counts(store, today=TODAY) == {"overdue": 1, "due_soon": 1}


def test_the_cover_hides_counts_over_a_single_obligation_kind(tmp_path, monkeypatch):
    """I-31: '1 overdue' over one obligation kind identifies that kind, so
    the cover shows nothing — it rests on 'Nothing is open'."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _obligation(store, "obligations", "rent", Rung.L2, "2026-08-05", "overdue")

    assert cover(store, today=TODAY) == {}


def test_the_cover_shows_a_count_spread_across_two_kinds(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _register_second_obligation_kind(monkeypatch, "subscriptions")
    _obligation(store, "obligations", "rent", Rung.L2, "2026-08-05", "overdue")
    _obligation(store, "subscriptions", "netflix", Rung.L2, "2026-08-04", "overdue")

    assert cover(store, today=TODAY) == {"overdue": 2}


# ── the distribution gate (X7-drift fix): (2, 0) is not a spread ─────────────


def test_the_cover_hides_a_count_concentrated_in_one_of_two_kinds(tmp_path, monkeypatch):
    """The leak this repo carried until the X7 sweep. Two obligation kinds
    are registered and two bills are overdue, so both the roster gate and
    the count gate pass — but both bills are `obligations`, and "2 overdue"
    is that one kind's news wearing a household number (I-31). The
    distribution the cover now passes is what says so.

    The (1, 1) half of the same law is the test directly above: same
    aggregate, genuinely spread, still shown."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _register_second_obligation_kind(monkeypatch, "subscriptions")
    _obligation(store, "obligations", "rent", Rung.L2, "2026-08-05", "overdue")
    _obligation(store, "obligations", "insurance", Rung.L2, "2026-08-04", "overdue")

    assert counts(store, today=TODAY)["overdue"] == 2, "the aggregate still counts two"
    assert queue_mod.counts_by_kind(store, today=TODAY) == {
        "obligations": {"overdue": 2, "due_soon": 0},
        "subscriptions": {"overdue": 0, "due_soon": 0},
    }
    assert cover(store, today=TODAY) == {}


def test_the_distribution_names_every_registered_kind_even_a_silent_one(tmp_path, monkeypatch):
    """`counts_by_kind` is keyed by the roster, not by what happens to have
    records — the engine refuses a distribution naming a matter outside the
    roster it was given, and a roster entry missing from the distribution
    would quietly read as "contributes nothing" rather than being stated."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _register_second_obligation_kind(monkeypatch, "subscriptions")

    assert set(queue_mod.counts_by_kind(store, today=TODAY)) == {
        "obligations", "subscriptions",
    }


def test_the_aggregate_is_always_its_own_distribution_summed(tmp_path, monkeypatch):
    """`counts` is summed from `counts_by_kind`, never counted a second time
    beside it — a total that disagrees with its distribution is refused
    outright at the cover (I-11), which would take the resting screen down
    over a slip nobody would otherwise see. Held over a household carrying
    every shape the queue scores: overdue, due soon, far off, and a gap."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    _register_second_obligation_kind(monkeypatch, "subscriptions")
    _obligation(store, "obligations", "rent", Rung.L2, "2026-08-05", "overdue")
    _obligation(store, "obligations", "gym", Rung.L2, "2026-08-14", "due soon")
    _obligation(store, "obligations", "tax", Rung.L2, "2026-12-01", "far off")
    _obligation(store, "obligations", "broken", Rung.L2, "not-a-date", "a gap")
    _obligation(store, "subscriptions", "netflix", Rung.L2, "2026-08-04", "overdue")

    spread = queue_mod.counts_by_kind(store, today=TODAY)
    totals = counts(store, today=TODAY)
    for category in ("overdue", "due_soon"):
        assert totals[category] == sum(per[category] for per in spread.values())


# ── the queue reaches no payload (the chokepoint holds it too) ────────────────

def test_queue_module_reaches_no_payload():
    """The queue works over what `serve()` already gated; it never reads a
    `.payload` — pinned here for the module that is most tempted to reach for
    a due date directly. Held package-wide by test_invariants_chokepoint too.

    2026-09-11: this used to re-walk the AST itself; it now calls
    `test_invariants_chokepoint`'s own `_payload_reaches`, the one place that
    scan is owned and planted (G9d-inline-scans, "Duplicated chokepoint
    scans")."""
    import ast
    from pathlib import Path

    from tests import test_invariants_chokepoint as chk

    src = Path(queue_mod.__file__).read_text("utf-8")
    reaches = chk._payload_reaches(ast.parse(src))
    assert not reaches, f"queue.py reaches a payload at {reaches}"
