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
