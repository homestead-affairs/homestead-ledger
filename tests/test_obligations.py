"""Obligations the household enters itself — the writer the queue was waiting for.

The pack declared the fields and the queue read their due dates, but the only
writers were the demo's seed and a `put` that filed one field, under a random id,
in the wrong matter. `obligations.add_obligation` writes exactly the shape the
demo seeds and the queue and window read: one record per field, at the pack's
rungs, under the household's own short id.
"""
from __future__ import annotations

import pytest

from homestead.keep.dates import UnparseableDate
from homestead.keep.rungs import Rung
from homestead.keep.store import InvalidKey, RecordExists

from homestead_ledger import obligations, queue
from homestead_ledger.app.window import Window
from homestead_ledger.store import Sidecar


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    return Sidecar()


def test_an_obligation_is_one_record_per_field_at_the_packs_rungs(store):
    ref, replaced = obligations.add_obligation(
        store, item_id="rent", name="Sunrise Properties LLC", amount="1,450",
        due_date="2026-10-01", cadence="monthly",
    )
    assert ref == ("obligations", "due_date", "rent") and replaced is None
    assert store.get("obligations", "name", "rent").rung is Rung.L3
    assert store.get("obligations", "amount", "rent").rung is Rung.L4
    assert store.get("obligations", "due_date", "rent").rung is Rung.L2
    assert store.get("obligations", "cadence", "rent").rung is Rung.L2
    assert store.get("obligations", "amount", "rent").derived == "a payment is due"


def test_the_queue_and_the_window_read_it(store):
    obligations.add_obligation(store, item_id="rent", name="Sunrise", amount="1450",
                               due_date="2026-10-01", cadence="monthly")
    items = queue.queue(store, today="2026-09-25")
    assert [(i.ref[2], i.shown, i.days_until) for i in items] == [("rent", "2026-10-01", 6)]

    window = Window()
    texts = [row.text for row in window.open_list(store.records("obligations"))]
    assert "Sunrise" in texts and "a payment is due" in texts
    assert "1450.00" not in texts


def test_rows_and_detail_go_through_the_gate(store):
    obligations.add_obligation(store, item_id="rent", name="Sunrise", amount="1450",
                               due_date="2026-10-01", cadence="monthly")
    obligations.add_obligation(store, item_id="car", name="County DMV", amount="180",
                               due_date="2026-11-01", cadence="annual")
    rows = obligations.rows(store)
    assert [r.item_id for r in rows] == ["car", "rent"]
    rent = rows[1]
    assert (rent.name, rent.due_date, rent.cadence, rent.amount) == \
        ("Sunrise", "2026-10-01", "monthly", "a payment is due")
    assert rent.rung is Rung.L4

    detail = obligations.detail(store, "rent")
    assert detail["amount"] == ("L4", "1450.00")
    assert detail["name"] == ("L3", "Sunrise")
    assert obligations.detail(store, "nope") == {}


def test_a_second_write_is_refused_unless_replace_is_explicit(store):
    obligations.add_obligation(store, item_id="rent", name="Sunrise", amount="1450",
                               due_date="2026-10-01", cadence="monthly")
    with pytest.raises(RecordExists):
        obligations.add_obligation(store, item_id="rent", name="Other", amount="1",
                                   due_date="2026-10-02", cadence="monthly")
    assert obligations.detail(store, "rent")["name"][1] == "Sunrise"

    ref, replaced = obligations.add_obligation(store, item_id="rent", name="Other", amount="1",
                                               due_date="2026-10-02", cadence="monthly", replace=True)
    assert replaced is not None and replaced.previous.payload == "2026-10-01"
    assert obligations.detail(store, "rent")["name"][1] == "Other"


def test_refusals_happen_before_any_write(store):
    with pytest.raises(InvalidKey):
        obligations.add_obligation(store, item_id="../x", name="a", amount="1",
                                   due_date="2026-10-01", cadence="monthly")
    with pytest.raises(ValueError, match="names who is owed"):
        obligations.add_obligation(store, item_id="rent", name="  ", amount="1",
                                   due_date="2026-10-01", cadence="monthly")
    with pytest.raises(ValueError, match="not a number"):
        obligations.add_obligation(store, item_id="rent", name="a", amount="lots",
                                   due_date="2026-10-01", cadence="monthly")
    with pytest.raises(UnparseableDate):
        obligations.add_obligation(store, item_id="rent", name="a", amount="1",
                                   due_date="first of the month", cadence="monthly")
    with pytest.raises(ValueError, match="how often"):
        obligations.add_obligation(store, item_id="rent", name="a", amount="1",
                                   due_date="2026-10-01", cadence="")
    assert store.records("obligations") == []


def test_amounts_and_dates_are_normalised(store):
    obligations.add_obligation(store, item_id="rent", name="a", amount="$1,450",
                               due_date="Oct 1 2026", cadence="monthly")
    detail = obligations.detail(store, "rent")
    assert detail["amount"][1] == "1450.00" and detail["due_date"][1] == "2026-10-01"
