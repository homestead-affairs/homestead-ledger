"""`obligations.mark_paid` — recording a payment and rolling the schedule.

Load-bearing claims: the write is exactly one L2 record above the gate
(`{account, fingerprint}`, no amount, ever), the visible log carries a
reference and nothing else (I-15), a second call for the same `(id,
paid_on)` is refused by the store's own atomic insert rather than a
`has()`-then-write race (I-9), and `once` resolves instead of rescheduling.
"""
from __future__ import annotations

import json

import pytest

from homestead.keep.logs import Event, VisibleLog
from homestead.keep.rungs import Classified, Rung, Surface, serve
from homestead.keep.store import RecordExists
from homestead.keep import paths

from homestead_ledger import obligations, queue
from homestead_ledger.cadence import UnknownCadence
from homestead_ledger.store import Sidecar

AMOUNT = "1450.00"
ACCOUNT_NUMBER_PLANT = "9821"     # a bank account number, to grep the log for


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    return Sidecar()


def _pre_anchor_obligation(store, item_id, *, due_date, cadence):
    """An obligation as bite G3 first wrote them: four pack fields and no
    `due_day` record. `Sidecar` has no delete (I-9's append-only posture), so
    the only way to stand up a pre-anchor record is to write it the way the
    old code did — which is also exactly what is on a household's disk.
    """
    for field, value, derived in (
        ("due_date", due_date, None),
        ("name", "Old Record", obligations.DERIVED["name"]),
        ("amount", AMOUNT, obligations.DERIVED["amount"]),
        ("cadence", cadence, None),
    ):
        store.put(obligations.KIND, field, item_id,
                  Classified(obligations.FIELDS[field], value, derived), overwrite=True)


def _add_rent(store, due_date="2026-08-05", cadence="monthly"):
    obligations.add_obligation(
        store, item_id="rent", name="Sunrise Properties LLC", amount=AMOUNT,
        due_date=due_date, cadence=cadence,
    )


# ── the happy path ────────────────────────────────────────────────────────

def test_mark_paid_rolls_the_due_date_forward(store):
    _add_rent(store)
    ref, rolled = obligations.mark_paid(
        store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-07",
    )
    assert ref == ("obligations", "paid_by", "rent.2026-08-07")
    assert rolled.old_due == "2026-08-05" and rolled.new_due == "2026-09-05"
    detail = obligations.detail(store, "rent")
    assert detail["due_date"] == ("L2", "2026-09-05")


def test_once_resolves_instead_of_rescheduling(store):
    _add_rent(store, due_date="2026-08-05", cadence="once")
    ref, rolled = obligations.mark_paid(
        store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-05",
    )
    assert rolled.new_due is None and rolled.old_due == "2026-08-05"
    # the due date itself is left as-is; a "resolved" record is what changes
    detail = obligations.detail(store, "rent")
    assert detail["due_date"] == ("L2", "2026-08-05")
    assert store.has("obligations", "resolved", "rent")


def test_a_resolved_once_obligation_drops_out_of_the_queue(store):
    _add_rent(store, due_date="2026-08-05", cadence="once")
    obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-05")
    items = queue.queue(store, today="2026-08-06")
    assert items == []


def test_the_list_shows_paid_by_reference_next_to_the_row(store):
    _add_rent(store)
    obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-07")
    rows = {r.item_id: r for r in obligations.rows(store)}
    assert rows["rent"].paid_on == "2026-08-07"
    assert rows["rent"].resolved is False


def test_the_list_flags_a_resolved_once_obligation(store):
    _add_rent(store, due_date="2026-08-05", cadence="once")
    obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-05")
    rows = {r.item_id: r for r in obligations.rows(store)}
    assert rows["rent"].resolved is True


# ── I-9: the write is exactly one L2 record, and nothing above it ───────────

def test_mark_paid_writes_exactly_the_l2_record_and_nothing_above(store):
    """Read back through the gate on S1_LIST: the account and fingerprint
    render (L2), and no amount is anywhere in the record — this is the write
    itself, not the log."""
    _add_rent(store)
    obligations.mark_paid(
        store, "rent", account="checking", fingerprint=ACCOUNT_NUMBER_PLANT, paid_on="2026-08-07",
    )
    record = store.get("obligations", "paid_by", "rent.2026-08-07")
    assert record.rung is Rung.L2
    served = serve(record, Surface.S1_LIST)
    assert served.value == {"account": "checking", "fingerprint": ACCOUNT_NUMBER_PLANT}
    # the amount is never in this record, at any rung
    assert AMOUNT not in json.dumps(served.value)
    assert AMOUNT not in json.dumps(record.payload)


def test_the_visible_log_carries_a_reference_only(store, tmp_path):
    """Grep the actual log file — not just the return value — for the
    fingerprint and the account, the plants I-15 forbids in a visible-log
    line."""
    _add_rent(store)
    obligations.mark_paid(
        store, "rent", account="checking", fingerprint=ACCOUNT_NUMBER_PLANT, paid_on="2026-08-07",
    )
    log_path = paths.logs_dir() / "visible.jsonl"
    text = log_path.read_text("utf-8")
    assert ACCOUNT_NUMBER_PLANT not in text
    assert AMOUNT not in text
    entry = json.loads(text.strip().splitlines()[-1])
    assert entry["event"] == Event.ITEM_RESOLVED.value
    assert entry["ref"] == "obligations/rent"


def test_the_log_is_written_through_visiblelog_not_a_free_string(store, monkeypatch):
    """Pinned against a future edit reaching for a free-text `record()` call
    (F-4's shape) instead of the closed `Event` enum."""
    calls = []
    real_record = VisibleLog.record

    def spy(self, event, *, ref):
        calls.append((event, ref))
        return real_record(self, event, ref=ref)

    monkeypatch.setattr(VisibleLog, "record", spy)
    _add_rent(store)
    obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-07")
    assert calls == [(Event.ITEM_RESOLVED, ("obligations", "rent"))]


# ── refusals, before any write ───────────────────────────────────────────────

def test_an_unknown_obligation_id_is_refused(store):
    with pytest.raises(KeyError):
        obligations.mark_paid(store, "nope", account="checking", fingerprint="fp-1", paid_on="2026-08-07")


def test_an_unknown_account_is_refused(store):
    _add_rent(store)
    with pytest.raises(ValueError, match="unknown account"):
        obligations.mark_paid(store, "rent", account="mattress", fingerprint="fp-1", paid_on="2026-08-07")
    # nothing was written
    assert not store.has("obligations", "paid_by", "rent.2026-08-07")


def test_a_non_iso_paid_on_is_refused(store):
    _add_rent(store)
    for bad in ("08/07/2026", "August 7 2026", "not a date", ""):
        with pytest.raises(ValueError, match="ISO"):
            obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on=bad)
    assert not store.has("obligations", "paid_by", "rent.2026-08-07")


def test_an_empty_fingerprint_is_refused(store):
    _add_rent(store)
    with pytest.raises(ValueError, match="fingerprint"):
        obligations.mark_paid(store, "rent", account="checking", fingerprint="  ", paid_on="2026-08-07")


def test_a_cadence_outside_cadences_on_file_is_refused(store):
    """Reaches directly under `add_obligation`'s own new validation — plants
    a bad cadence straight into the store to prove `mark_paid` also checks,
    not just the writer that (now) already refuses it at entry."""
    obligations.add_obligation(store, item_id="rent", name="a", amount="1", due_date="2026-08-05", cadence="monthly")
    store.put("obligations", "cadence", "rent", Classified(Rung.L2, "fortnightly"), overwrite=True)
    with pytest.raises(UnknownCadence):
        obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-07")


def test_a_sealed_due_date_is_refused_not_silently_skipped(store):
    obligations.add_obligation(store, item_id="rent", name="a", amount="1", due_date="2026-08-05", cadence="monthly")
    store.put("obligations", "due_date", "rent", Classified(Rung.L5, "2026-08-05"), overwrite=True)
    with pytest.raises(ValueError, match="sealed"):
        obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-07")


# ── I-9: TOCTOU — the atomic insert is the gate, not a check ────────────────

def test_a_second_mark_paid_for_the_same_id_and_date_is_refused_unless_replace(store):
    _add_rent(store)
    obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-07")
    with pytest.raises(RecordExists):
        obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-2", paid_on="2026-08-07")
    # the due date only rolled once
    assert obligations.detail(store, "rent")["due_date"] == ("L2", "2026-09-05")

    # --replace is the one path that goes through, and rolls again from the
    # (already rolled) due date on file
    _ref, rolled = obligations.mark_paid(
        store, "rent", account="checking", fingerprint="fp-2", paid_on="2026-08-07", replace=True,
    )
    assert rolled.old_due == "2026-09-05"


def test_a_racing_second_mark_paid_is_refused_by_the_store_not_a_check(store, monkeypatch):
    """The same TOCTOU shape `test_obligations.py` proves for `add_obligation`
    (I-9): poison `has()` to always answer "free" — the lost-race answer —
    and the refusal must still arrive out of the adapter's atomic insert."""
    _add_rent(store)
    obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-1", paid_on="2026-08-07")

    monkeypatch.setattr(type(store), "has", lambda *a, **k: False)

    with pytest.raises(RecordExists):
        obligations.mark_paid(store, "rent", account="checking", fingerprint="fp-2", paid_on="2026-08-07")


# ── the CLI and server refusals never echo an amount ────────────────────────

def test_cli_obligation_paid_refusal_never_echoes_an_amount(store, tmp_path, monkeypatch, capsys):
    from homestead_ledger.cli import run_cli

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    run_cli(["obligation", "add", "rent", "Sunrise", AMOUNT, "2026-08-05", "monthly"])
    capsys.readouterr()
    rc = run_cli(["obligation", "paid", "rent", "--account", "mattress",
                  "--fingerprint", "fp-1", "--on", "2026-08-07"])
    assert rc == 1
    err = capsys.readouterr().err
    assert AMOUNT not in err


# The `/api/obligation/paid` door itself is exercised in `tests/test_server.py`
# alongside the rest of the browser UI's own fixture; this file stays over
# `obligations.mark_paid` directly.


# ── --smoke imports cadence ──────────────────────────────────────────────────

def test_smoke_imports_cadence():
    from homestead_ledger.__main__ import main
    assert main(["--smoke"]) == 0


# ── the anchor: a month-end schedule must not drift ───────────────────────
#
# The bug these guard against is a *wrong date*, not a rough edge:
# `roll_forward` anchors its month-end clamp on the day of the due date it
# is handed, and across separate calls that date is whatever the previous
# roll already clamped — so rent due the 31st, paid on time every month,
# went 31 → Feb 28 → Mar 28 → Apr 28 and the household's rent day silently
# became the 28th forever. `add_obligation` now writes the first due date's
# day of month as `(obligations, "due_day", <id>)` and `mark_paid` clamps
# against that.

def test_a_month_end_obligation_climbs_back_after_february(store):
    """Five on-time payments, Jan 31 → Feb 28 → Mar 31 → Apr 30 → May 31.

    The failure this guards: Feb 28 → Mar 28, and every later month pinned
    to the 28th — three days of the household's own schedule lost to
    February, permanently, with nothing on any surface saying so.
    """
    obligations.add_obligation(
        store, item_id="rent", name="Sunrise Properties LLC", amount=AMOUNT,
        due_date="2026-01-31", cadence="monthly",
    )
    seen = []
    for paid_on in ("2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"):
        _ref, rolled = obligations.mark_paid(
            store, "rent", account="checking", fingerprint=f"fp-{paid_on}",
            paid_on=paid_on,
        )
        seen.append(rolled.new_due)
    assert seen == ["2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]


def test_a_quarterly_month_end_obligation_keeps_its_anchor(store):
    """Nov 30 → Feb 28 → May 30: the anchor is the **day of month** (30),
    so February clamps and May comes back to the 30th — not the 31st.

    Stated because it is the one place the anchor's semantics are visible
    and a reader could expect otherwise: this is "the 30th of the month",
    not "the last day of the month". A household that means the latter is
    saying something a day-of-month field cannot carry, and inferring it
    from "the first due date happened to be month-end" would guess (Nov 30
    is month-end; so is Feb 28; a rule built on that would move an
    obligation due the 30th onto the 31st without being asked). If the
    household needs last-day-of-month it is a different declared cadence,
    not a clever reading of this one (I-11).
    """
    obligations.add_obligation(
        store, item_id="water", name="City Water", amount=AMOUNT,
        due_date="2026-11-30", cadence="quarterly",
    )
    _ref, first = obligations.mark_paid(
        store, "water", account="checking", fingerprint="f1", paid_on="2026-11-30")
    assert first.new_due == "2027-02-28"
    _ref, second = obligations.mark_paid(
        store, "water", account="checking", fingerprint="f2", paid_on="2027-02-28")
    assert second.new_due == "2027-05-30"


def test_an_obligation_added_mid_month_never_moves(store):
    """The anchor is not a month-end special case — it is *the* day, and a
    15th stays a 15th through February and back."""
    obligations.add_obligation(
        store, item_id="gym", name="Gym", amount=AMOUNT,
        due_date="2026-01-15", cadence="monthly",
    )
    seen = []
    for paid_on in ("2026-01-15", "2026-02-15", "2026-03-15"):
        _ref, rolled = obligations.mark_paid(
            store, "gym", account="checking", fingerprint=f"f-{paid_on}", paid_on=paid_on)
        seen.append(rolled.new_due)
    assert seen == ["2026-02-15", "2026-03-15", "2026-04-15"]


def test_the_anchor_is_written_by_the_ordinary_add_path(store):
    """Not by a migration, not by the first `mark_paid` — by `add_obligation`
    itself, behind the same due-date gate, so an obligation cannot exist with
    a due date and no anchor to clamp against."""
    _add_rent(store, due_date="2026-01-31")
    record = store.get(obligations.KIND, "due_day", "rent")
    assert record.rung is Rung.L2
    assert serve(record, Surface.S1_LIST).value == "31"


def test_replacing_an_obligation_resets_its_anchor(store):
    """`--replace` gives the obligation a new due date, so it gives it a new
    anchor too — otherwise the old month-end day would outlive the schedule
    it belonged to."""
    _add_rent(store, due_date="2026-01-31")
    obligations.add_obligation(
        store, item_id="rent", name="Sunrise Properties LLC", amount=AMOUNT,
        due_date="2026-03-15", cadence="monthly", replace=True,
    )
    assert serve(store.get(obligations.KIND, "due_day", "rent"),
                 Surface.S1_LIST).value == "15"


def test_an_obligation_without_an_anchor_falls_back_to_its_due_date(store):
    """A record written before this module kept an anchor — or an add torn
    between the due-date gate and the anchor write — has no `due_day`. It
    still marks paid: the fallback is the due date's own day, which is the
    behaviour that shipped before the anchor existed, named and bounded
    rather than a guess at what the original day "probably" was (I-11).
    """
    _pre_anchor_obligation(store, "rent", due_date="2026-01-31", cadence="monthly")
    _ref, rolled = obligations.mark_paid(
        store, "rent", account="checking", fingerprint="f1", paid_on="2026-01-31")
    assert rolled.new_due == "2026-02-28"
    # and the next one stays clamped — the anchor is gone, not recoverable
    _ref, again = obligations.mark_paid(
        store, "rent", account="checking", fingerprint="f2", paid_on="2026-02-28")
    assert again.new_due == "2026-03-28"


def test_a_corrupt_anchor_falls_back_rather_than_refusing(store):
    """A `due_day` that is not a day of month is bookkeeping corruption, not
    a reason to refuse to record a payment the household actually made."""
    _add_rent(store, due_date="2026-01-31")
    store.put(obligations.KIND, "due_day", "rent",
              Classified(Rung.L2, "the thirty-first"), overwrite=True)
    _ref, rolled = obligations.mark_paid(
        store, "rent", account="checking", fingerprint="f1", paid_on="2026-01-31")
    assert rolled.new_due == "2026-02-28"


def test_the_anchor_is_not_a_row_field_and_does_not_make_a_row_a_gap(store):
    """`due_day` is this module's own bookkeeping, not a fifth field the
    household typed — so it must not turn up as an obligation of its own, and
    an obligation that has all four pack fields is not `gap` because of it."""
    _add_rent(store)
    row = [r for r in obligations.rows(store) if r.item_id == "rent"][0]
    assert row.gap is False
    assert [r.item_id for r in obligations.rows(store)] == ["rent"]


# ── "paid ✓" is a claim about the *current* period ────────────────────────

def test_a_payment_for_last_period_does_not_tick_the_open_one(store):
    """Paid 1 July, due again 1 August. On 20 July nothing is owed and the
    mark is honest. On 15 August the due date has arrived, the open period
    is unpaid, and a row still reading `paid ✓ 2026-07-01` tells the
    household this month's rent is paid when it is not — the one thing a
    ledger must never say.
    """
    obligations.add_obligation(
        store, item_id="rent", name="Sunrise Properties LLC", amount=AMOUNT,
        due_date="2026-07-01", cadence="monthly",
    )
    obligations.mark_paid(store, "rent", account="checking",
                          fingerprint="f1", paid_on="2026-07-01")

    before = [r for r in obligations.rows(store, today="2026-07-20")
              if r.item_id == "rent"][0]
    assert before.due_date == "2026-08-01" and before.paid_current is True

    after = [r for r in obligations.rows(store, today="2026-08-15")
             if r.item_id == "rent"][0]
    assert after.paid_on == "2026-07-01"    # the fact stays readable
    assert after.paid_current is False      # the claim does not


def test_a_lapsed_obligation_is_not_ticked_by_an_old_payment(store):
    """The other half of the rule, and the one that holds without a clock: a
    payment older than the period now open (here two periods back, the shape
    a back-dated entry or a hand-edited due date leaves behind) is not a
    payment for it."""
    _add_rent(store, due_date="2026-08-01")
    store.put(obligations.KIND, "paid_by", "rent.2026-05-15",
              Classified(Rung.L2, {"account": "checking", "fingerprint": "f1"}),
              overwrite=True)
    row = [r for r in obligations.rows(store) if r.item_id == "rent"][0]
    assert row.paid_on == "2026-05-15" and row.paid_current is False


def test_a_payment_inside_the_current_period_does_tick_it(store):
    """The period that ended at the due date now on file is the one a ✓ is
    about: a payment on or after the previous due date closes it."""
    obligations.add_obligation(
        store, item_id="rent", name="Sunrise Properties LLC", amount=AMOUNT,
        due_date="2026-07-01", cadence="monthly",
    )
    obligations.mark_paid(store, "rent", account="checking",
                          fingerprint="f1", paid_on="2026-07-01")
    # a second, later payment — now the due date is 2026-09-01 and the
    # payment that moved it there (2026-08-01) is inside the closed period.
    obligations.mark_paid(store, "rent", account="checking",
                          fingerprint="f2", paid_on="2026-08-01")
    row = [r for r in obligations.rows(store) if r.item_id == "rent"][0]
    assert (row.due_date, row.paid_on, row.paid_current) == (
        "2026-09-01", "2026-08-01", True)


def test_paid_on_exactly_the_previous_due_date_counts_as_current(store):
    """The boundary is inclusive — a payment *on* the previous due date is
    the payment for the period that started there."""
    obligations.add_obligation(
        store, item_id="gym", name="Gym", amount=AMOUNT,
        due_date="2026-07-15", cadence="monthly")
    obligations.mark_paid(store, "gym", account="checking",
                          fingerprint="f1", paid_on="2026-07-15")
    row = [r for r in obligations.rows(store) if r.item_id == "gym"][0]
    # due is now 2026-08-15; the previous due date is 2026-07-15 exactly.
    assert row.due_date == "2026-08-15" and row.paid_current is True


def test_a_resolved_once_obligation_is_always_marked_paid(store):
    """A `once` obligation has no next period to be behind on: once resolved,
    the mark is simply true."""
    _add_rent(store, cadence="once")
    obligations.mark_paid(store, "rent", account="checking",
                          fingerprint="f1", paid_on="2026-08-06")
    row = [r for r in obligations.rows(store) if r.item_id == "rent"][0]
    assert row.resolved is True and row.paid_current is True


def test_an_unresolved_once_obligation_is_never_marked_current(store):
    """No cadence window, no resolution: no claim."""
    _add_rent(store, cadence="once")
    store.put(obligations.KIND, "paid_by", "rent.2026-08-06",
              Classified(Rung.L2, {"account": "checking", "fingerprint": "f1"}),
              overwrite=True)
    row = [r for r in obligations.rows(store) if r.item_id == "rent"][0]
    assert row.paid_on == "2026-08-06" and row.paid_current is False


def test_an_unreadable_cadence_makes_no_claim_rather_than_a_wrong_one(store):
    """Nothing to compute a period from is `False`, not `True` (I-11)."""
    _add_rent(store)
    store.put(obligations.KIND, "cadence", "rent",
              Classified(Rung.L2, "fortnightly"), overwrite=True)
    store.put(obligations.KIND, "paid_by", "rent.2026-08-06",
              Classified(Rung.L2, {"account": "checking", "fingerprint": "f1"}),
              overwrite=True)
    row = [r for r in obligations.rows(store) if r.item_id == "rent"][0]
    assert row.paid_on == "2026-08-06" and row.paid_current is False


def test_the_cli_list_ticks_only_the_current_period(store, capsys):
    """End to end on the surface an operator actually reads: the CLI passes
    its own clock, so a lapsed obligation reads "last paid", not "paid ✓"."""
    from homestead_ledger.cli import run_cli
    _add_rent(store, due_date="2020-07-01")   # long past, on any real clock
    obligations.mark_paid(store, "rent", account="checking",
                          fingerprint="f1", paid_on="2020-07-01")
    capsys.readouterr()
    assert run_cli(["obligation", "list"]) == 0
    out = capsys.readouterr().out
    assert "paid ✓" not in out
    assert "last paid 2020-07-01" in out


# ── a back-dated entry records the fact and leaves the schedule alone ──────

def test_a_back_dated_payment_does_not_re_roll_the_due_date(store):
    """Rent due Jan 1, paid Jan 1 → due Feb 1. Then December's receipt is
    entered. Rolling again from Feb 1 gives Mar 1 and February silently
    vanishes from the household's schedule: the due date would walk forward
    once per *receipt* instead of once per *period*.
    """
    obligations.add_obligation(
        store, item_id="card", name="Card", amount=AMOUNT,
        due_date="2026-01-01", cadence="monthly")
    _ref, first = obligations.mark_paid(
        store, "card", account="checking", fingerprint="f1", paid_on="2026-01-01")
    assert first.new_due == "2026-02-01" and first.rolled is True

    _ref, back = obligations.mark_paid(
        store, "card", account="checking", fingerprint="f0", paid_on="2025-12-01")
    assert back.rolled is False
    # not forwards, and — the weaker claim, worth stating — not backwards:
    # the date on file is the one the January payment set, unchanged.
    assert back.old_due == back.new_due == "2026-02-01"
    assert serve(store.get(obligations.KIND, "due_date", "card"),
                 Surface.S1_LIST).value == "2026-02-01"
    # and the fact is on file all the same
    assert store.has(obligations.KIND, "paid_by", "card.2025-12-01")


def test_re_recording_the_same_date_with_replace_does_not_advance_twice(store):
    """`--replace` re-writes a paid-by record that already moved the
    schedule. Advancing again would charge the household a second period for
    one correction."""
    _add_rent(store, due_date="2026-08-05")
    _ref, first = obligations.mark_paid(
        store, "rent", account="checking", fingerprint="f1", paid_on="2026-08-06")
    assert first.new_due == "2026-09-05"
    _ref, again = obligations.mark_paid(
        store, "rent", account="savings", fingerprint="f2",
        paid_on="2026-08-06", replace=True)
    assert again.rolled is False and again.new_due == "2026-09-05"
    served = serve(store.get(obligations.KIND, "paid_by", "rent.2026-08-06"),
                   Surface.S1_DETAIL)
    assert served.value == {"account": "savings", "fingerprint": "f2"}


def test_the_cli_says_the_schedule_stood_still(store, capsys):
    from homestead_ledger.cli import run_cli
    obligations.add_obligation(
        store, item_id="card", name="Card", amount=AMOUNT,
        due_date="2026-01-01", cadence="monthly")
    obligations.mark_paid(store, "card", account="checking",
                          fingerprint="f1", paid_on="2026-01-01")
    capsys.readouterr()
    assert run_cli(["obligation", "paid", "card", "--account", "checking",
                    "--fingerprint", "f0", "--on", "2025-12-01"]) == 0
    out = capsys.readouterr().out
    assert "schedule unchanged" in out and "2026-02-01" in out
    assert AMOUNT not in out


# ── a cadence spelling that predates `CADENCES` stays readable ─────────────

def test_an_obligation_stored_as_annual_is_still_readable(store):
    """`annual` was the spelling the browser's `<select>` offered before this
    bite renamed it `yearly`. A household that entered one then must not find
    the obligation unreadable now: it lists, it shows, it queues. Only the
    one act that needs the arithmetic — marking it paid — refuses, **by
    name, with the spelling to fix it to** (I-11: refuse, never guess the
    nearest bucket and roll by it).
    """
    _pre_anchor_obligation(store, "registration", due_date="2026-11-01",
                           cadence="annual")
    row = [r for r in obligations.rows(store) if r.item_id == "registration"][0]
    assert row.cadence == "annual" and row.due_date == "2026-11-01"
    assert obligations.detail(store, "registration")["cadence"] == ("L2", "annual")
    assert any(q.ref[2] == "registration" for q in queue.queue(store, today="2026-10-01"))

    with pytest.raises(UnknownCadence) as caught:
        obligations.mark_paid(store, "registration", account="checking",
                              fingerprint="f1", paid_on="2026-11-01")
    assert "yearly" in str(caught.value)


def test_add_obligation_refuses_annual_by_name(store):
    """Forward, the door is closed — and the refusal names the whole set, so
    the operator is told what to type rather than that they were wrong."""
    with pytest.raises(ValueError) as caught:
        obligations.add_obligation(
            store, item_id="registration", name="County DMV", amount=AMOUNT,
            due_date="2026-11-01", cadence="annual")
    assert "yearly" in str(caught.value)


def test_a_resolved_once_obligation_still_shows(store, capsys):
    """`resolved` is a marker, not a delete (there is no delete on
    `Sidecar`): the obligation drops out of the *queue* and stays readable
    everywhere else, so an operator can still look up what they paid.

    `recurring.detect_recurring` is not in this list because it never sees an
    obligation at all — it takes plain transaction tuples
    (`test_recurring.py::test_detect_recurring_takes_plain_tuples_not_a_store`),
    so a resolved obligation cannot reach it to be ignored.
    """
    from homestead_ledger.cli import run_cli
    _add_rent(store, cadence="once")
    obligations.mark_paid(store, "rent", account="checking",
                          fingerprint="f1", paid_on="2026-08-06")

    assert not queue.queue(store, today="2026-08-20")
    assert [r.item_id for r in obligations.rows(store)] == ["rent"]

    capsys.readouterr()
    assert run_cli(["obligation", "show", "rent"]) == 0
    out = capsys.readouterr().out
    assert "Sunrise Properties LLC" in out and "once" in out
    assert "2026-08-05" in out       # the due date it was resolved at
