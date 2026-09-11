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
from homestead.keep.rungs import Classified, Rung, compose
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
                               due_date="2026-11-01", cadence="yearly")
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


def test_a_racing_second_add_is_refused_by_the_store_not_by_a_check(store, monkeypatch):
    """I-9, against the check-then-act shape.

    `store.has()` followed by `put(..., overwrite=True)` reads correctly and is
    wrong: between the two statements another writer — a second browser tab, a
    CLI run beside the open UI — can take the id, and the `has()` answer the
    loser is holding is then stale. Both callers see "free" and the second
    silently overwrites the first, which is the clobber I-9 exists to prevent.

    So: poison `has()` to answer the way a lost race answers it — always
    "free" — and the refusal must arrive anyway, out of the adapter's atomic
    insert, with nothing of the first obligation touched.
    """
    obligations.add_obligation(store, item_id="rent", name="Sunrise", amount="1450",
                               due_date="2026-10-01", cadence="monthly")

    monkeypatch.setattr(type(store), "has", lambda *a, **k: False)

    with pytest.raises(RecordExists):
        obligations.add_obligation(store, item_id="rent", name="Interloper", amount="9999",
                                   due_date="2026-12-25", cadence="weekly")

    detail = obligations.detail(store, "rent")
    assert detail["name"][1] == "Sunrise"          # not clobbered
    assert detail["amount"][1] == "1450.00"
    assert detail["due_date"][1] == "2026-10-01"
    assert detail["cadence"][1] == "monthly"


def test_an_explicit_replace_still_goes_through_with_has_poisoned(store, monkeypatch):
    """The complement: `replace=True` is the one path that overwrites, and it
    does not consult `has()` either — so the same poisoning changes nothing
    about it. A refusal that only a stale read could produce would be as wrong
    as a clobber it could produce."""
    obligations.add_obligation(store, item_id="rent", name="Sunrise", amount="1450",
                               due_date="2026-10-01", cadence="monthly")
    monkeypatch.setattr(type(store), "has", lambda *a, **k: False)
    _, replaced = obligations.add_obligation(store, item_id="rent", name="Other", amount="1",
                                             due_date="2026-10-02", cadence="monthly",
                                             replace=True)
    assert replaced is not None
    assert obligations.detail(store, "rent")["name"][1] == "Other"


def test_a_torn_obligation_is_surfaced_not_hidden(store):
    """A crash between the four per-field writes leaves a partial obligation on
    file. `rows()` must show the tear — each absent field as `MISSING`, the row
    flagged as a gap — and never a row that reads whole because the blanks were
    filled in with "" (I-8: a gap is surfaced, never guessed at)."""
    obligations.add_obligation(store, item_id="rent", name="Sunrise", amount="1450",
                               due_date="2026-10-01", cadence="monthly")
    # what an interrupted add leaves: the gate field and one more, no amount,
    # no cadence.
    store.put("obligations", "due_date", "torn", Classified(Rung.L2, "2026-11-01", None))
    store.put("obligations", "name", "torn",
              Classified(Rung.L3, "County DMV", "a payee is on file"))

    by_id = {r.item_id: r for r in obligations.rows(store)}
    torn = by_id["torn"]
    assert torn.gap is True
    assert torn.amount == obligations.MISSING and torn.cadence == obligations.MISSING
    assert torn.name == "County DMV" and torn.due_date == "2026-11-01"
    assert by_id["rent"].gap is False


def test_the_row_rung_comes_from_compose_not_from_string_order(store, monkeypatch):
    """I-14/I-12: a rung is a string, never a sortable one, and composition is
    the engine's `compose()`.

    `max(rungs, key=lambda r: r.value)` gives the right answer today only
    because `"L1" < "L2" < … < "L5"` happens to hold in the alphabet — a rung
    read as an ordered string, which is the exact shape I-14 names. Plant an
    order in which the top is `L1` and the row must follow it: whatever the
    engine's composition says is the row's rung, because that is the one place
    the ladder's order is written down.
    """
    obligations.add_obligation(store, item_id="rent", name="Sunrise", amount="1450",
                               due_date="2026-10-01", cadence="monthly")

    seen: list[tuple] = []

    def planted(*rungs):
        seen.append(tuple(rungs))
        return Rung.L1

    monkeypatch.setattr(obligations, "compose", planted)
    assert obligations.rows(store)[0].rung is Rung.L1
    assert sorted(r.value for r in seen[0]) == ["L2", "L2", "L3", "L4"]

    # and the engine's real composition over those same four rungs is L4 — the
    # max, not the first and not the last written. (`test_rows_and_detail_go_
    # through_the_gate` above asserts the unpatched row carries it.)
    assert compose(Rung.L2, Rung.L2, Rung.L3, Rung.L4) is Rung.L4


def test_an_id_is_one_closed_shape(store):
    """The id is a key segment *and* a string this app renders back into a
    browser. `homestead.keep.store.key` would accept `a'-alert(1)-'b` — no
    separator, no NUL — and that is a quote inside whatever the surface builds
    around it. One closed shape, refused before anything is written."""
    for bad in ("../x", "", "  ", "Rent", "rent account", "a'-alert(1)-'b",
                "rent.primary", "-rent", "x" * 41):
        with pytest.raises(InvalidKey):
            obligations.add_obligation(store, item_id=bad, name="a", amount="1",
                                       due_date="2026-10-01", cadence="monthly")
    assert store.records("obligations") == []

    for good in ("rent", "car-insurance", "x", "9", "x" * 40):
        obligations.add_obligation(store, item_id=good, name="a", amount="1",
                                   due_date="2026-10-01", cadence="monthly")
    assert {r.item_id for r in obligations.rows(store)} == {
        "rent", "car-insurance", "x", "9", "x" * 40
    }


def test_a_refusal_never_echoes_the_amount(store):
    """I-15: an error may name a field, never repeat an L3+ value — and a
    *rejected* amount reaches the same stderr and the same browser as an
    accepted one."""
    with pytest.raises(ValueError) as caught:
        obligations.add_obligation(store, item_id="rent", name="a", amount="4242.42lots",
                                   due_date="2026-10-01", cadence="monthly")
    assert "4242" not in str(caught.value)
    assert "amount" in str(caught.value)


def test_a_cadence_outside_cadences_is_refused_by_name(store):
    """I-23's reasoning applied to the household-typed `cadence` word:
    `cadence.CADENCES` is the one enumeration `mark_paid`'s `roll_forward`
    reads, so nothing may land in the field that arithmetic does not also
    recognise. Plant `"fortnightly"` — a word an operator might reasonably
    type for `biweekly` — and it must be refused, not silently accepted."""
    with pytest.raises(ValueError, match="cadence must be one of"):
        obligations.add_obligation(store, item_id="rent", name="a", amount="1",
                                   due_date="2026-10-01", cadence="fortnightly")
    assert store.records("obligations") == []


def test_a_non_finite_amount_is_not_an_amount(store):
    """`float("nan")` and `float("inf")` both succeed, and `f"{float('nan'):.2f}"`
    is the string "nan" — an amount on the books that makes every sum it joins
    `nan` and compares false to itself. Refused by name (I-11)."""
    for bad in ("nan", "NaN", "inf", "-inf", "Infinity"):
        with pytest.raises(ValueError, match="finite"):
            obligations.add_obligation(store, item_id="rent", name="a", amount=bad,
                                       due_date="2026-10-01", cadence="monthly")
    assert store.records("obligations") == []
