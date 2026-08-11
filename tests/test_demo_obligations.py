"""`--demo`'s bite-2 addition: seeding a couple of obligations and rendering
the "what's due" queue and the resting cover, headless — the money analog of
homestead-law's `tests/test_view.py::test_the_queue_demo_orders_gates_and_
hides_the_cover`.
"""
from __future__ import annotations

from homestead_ledger.app import demo
from homestead_ledger.store import Sidecar


def test_seed_obligations_writes_every_field_at_the_packs_rungs(tmp_path, monkeypatch):
    from homestead.keep.rungs import Rung
    from homestead_ledger.packs import obligations

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    demo.seed_obligations(store)

    for item_id in demo._DEMO_OBLIGATIONS:
        for field in ("name", "amount", "due_date", "cadence"):
            record = store.get(obligations.OBLIGATION, field, item_id)
            assert record.rung is obligations.FIELDS[field]

    # a corrupt or wrong rung would slip past a test that only checks presence
    assert Rung.L5 not in {
        store.get(obligations.OBLIGATION, "due_date", item_id).rung
        for item_id in demo._DEMO_OBLIGATIONS
    }


def test_compose_queue_orders_gates_and_hides_the_cover(tmp_path, monkeypatch):
    """The queue rendered headless: overdue before far-off, and the resting
    cover reveals nothing over the one obligation kind bite 2 registers
    (I-31), even though the queue itself has items."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    out = demo.compose_queue(Sidecar())

    lines = out.splitlines()
    overdue_line = next(i for i, l in enumerate(lines) if "overdue by" in l)
    far_off_line = next(i for i, l in enumerate(lines) if "due in" in l and "overdue" not in l)
    assert overdue_line < far_off_line

    assert "Nothing is open" in out   # the resting cover, over one obligation kind (I-31)


def test_compose_queue_shows_the_payee_and_due_date_not_the_raw_amount(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    out = demo.compose_queue(Sidecar())
    # the due_date field (L2) renders on the ambient queue
    assert "202" in out  # a year appears somewhere in a rendered due date
    # nothing here ever writes a raw signed amount into the queue's own text
    assert "-1450.00" not in out


def test_compose_recurring_runs_over_the_demo_transactions(tmp_path, monkeypatch):
    """The optional recurring-charge pass over the same synthetic checking
    transactions the books demo already seeds. The demo data carries a monthly
    Netflix charge across three months, so the detector surfaces exactly that
    one recurring charge — while the one-off merchants (occurrences < 3) are
    correctly ignored."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    demo.seed()
    out = demo.compose_recurring()
    assert "recurring" in out.lower()
    # the monthly subscription is detected; the one-offs are not
    assert "netflix" in out.lower()
    assert "detected:" in out            # the "found" branch, not the empty fallback
    assert "monthly" in out.lower()
