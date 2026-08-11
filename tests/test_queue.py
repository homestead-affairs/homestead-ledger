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


# ── the queue reaches no payload (the chokepoint holds it too) ────────────────

def test_queue_module_reaches_no_payload():
    """The queue works over what `serve()` already gated; it never reads a
    `.payload` — pinned here for the module that is most tempted to reach for
    a due date directly. Held package-wide by test_invariants_chokepoint too."""
    import ast
    from pathlib import Path

    src = Path(queue_mod.__file__).read_text("utf-8")
    reaches = [
        n.lineno for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Attribute) and n.attr == "payload"
    ]
    assert not reaches, f"queue.py reaches a payload at {reaches}"
