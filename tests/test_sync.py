"""`sync.py` — a consented scope of the household's own books, composed and
delivered on an explicit act. Mirrors `test_schedules.py`'s own shape for
the planted-number section: a distinctive number, read on every ceiling
this bite touches, asserted absent everywhere but the one write that put it
there.
"""
from __future__ import annotations

import json
import socket

import pytest
from homestead.keep import paths
from homestead.keep.egress import EgressRefused
from homestead.keep.rungs import Disposition, Rung, Served
from homestead.keep import sync as engine_sync

from homestead_ledger import accounts, books, overlay, sync, transfers
from homestead_ledger.store import Sidecar

# ── the floor this bite raises: 0.11.0, where homestead.keep.sync landed ────


def test_the_engine_floor_carries_sync_core():
    """`homestead.keep.sync.SyncScope`/`Envelope` are what `sync.py` is
    built on (E4-sync-core) — a floor below 0.11.0 would install an engine
    with no `keep/sync.py` at all, and this bite would fail at import
    rather than at `pip install`. `pyproject.toml`'s own floor is
    `homestead-affairs>=0.11.0,<1.0` (see the dependency line's comment)."""
    from homestead.keep.sync import Envelope, SyncScope

    assert SyncScope is not None and Envelope is not None


pytestmark = pytest.mark.usefixtures("_home")


@pytest.fixture
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))


@pytest.fixture
def store():
    return Sidecar()


def _import(account, date, amount, description):
    return books.import_transaction(
        books.Transaction(
            account=account, date=date, amount=amount, description=description,
            kind=accounts.kind_of(Sidecar(), account),
        )
    )


# ── I-40: matters are held against what the household actually has ─────────


def test_scope_from_refuses_all(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    with pytest.raises(sync.UnnamedScope, match="not a matter"):
        sync.scope_from(["all"], None, Rung.L3, ["sidecar"], sidecar=store)


def test_scope_from_refuses_an_unknown_matter(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    with pytest.raises(sync.UnnamedScope, match="unknown matter"):
        sync.scope_from(["nope"], None, Rung.L3, ["sidecar"], sidecar=store)


def test_scope_from_refuses_empty_matters(store):
    with pytest.raises(sync.UnnamedScope):
        sync.scope_from([], None, Rung.L3, ["sidecar"], sidecar=store)


def test_scope_from_refuses_an_l5_ceiling(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    with pytest.raises(sync.UnnamedScope):
        sync.scope_from(["chk-main"], None, Rung.L5, ["sidecar"], sidecar=store)


def test_scope_from_refuses_an_unknown_table(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    with pytest.raises(sync.UnnamedScope):
        sync.scope_from(["chk-main"], None, Rung.L3, ["ledger"], sidecar=store)


def test_known_matters_is_read_off_the_registry_not_hardcoded(store):
    """I-23: the union changes as the household's own accounts do, read off
    `accounts.instances` rather than typed out a second time here."""
    before = sync.known_matters(store)
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    after = sync.known_matters(store)
    assert "chk-main" not in before
    assert "chk-main" in after
    assert {"accounts", "overlay", "transfers", "obligations"} <= set(after)


# ── do_not_use never crosses; a tagged-but-not-excluded row does ───────────


def test_do_not_use_rows_absent_a_tagged_row_present(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    excluded_fp = _import("chk-main", "2026-01-01", "-50.00", "Excluded")
    kept_fp = _import("chk-main", "2026-01-02", "-20.00", "Kept")
    overlay.tag(store, excluded_fp, do_not_use=True)
    overlay.tag(store, kept_fp, category="groceries")

    scope = sync.scope_from(
        ["chk-main", "overlay"], None, Rung.L4, ["sidecar", "canonical"], sidecar=store,
    )
    envelope = sync.preview(scope, sidecar=store)

    item_ids = {row["item_id"] for row in envelope.rows}
    assert excluded_fp not in item_ids
    assert kept_fp in item_ids
    # the do_not_use tag record itself is gone too (decision (b)) — syncing
    # it would still name the very fingerprint it excludes
    assert not any(
        row["matter"] == overlay.MATTER and row["item_type"] == "do_not_use"
        for row in envelope.rows
    )
    assert any(
        row["matter"] == overlay.MATTER and row["item_id"] == kept_fp
        for row in envelope.rows
    )


def test_transfer_pairs_are_kept_even_when_one_leg_is_do_not_use(store):
    """Decision (c): a pair is a reference to two of the household's own
    accounts, not the excluded transaction's own data — filed under
    `transfers`, a matter the do_not_use filter never touches."""
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    accounts.add_account(store, "sav-main", kind="savings", number="2")
    fp_out = _import("chk-main", "2026-01-01", "-40.00", "to savings")
    fp_in = _import("sav-main", "2026-01-02", "40.00", "from checking")
    transfers.pair(store, fp_out, fp_in)
    overlay.tag(store, fp_out, do_not_use=True)

    scope = sync.scope_from(["transfers"], None, Rung.L2, ["sidecar"], sidecar=store)
    envelope = sync.preview(scope, sidecar=store)

    assert len(envelope.rows) == 1
    assert envelope.rows[0]["matter"] == transfers.MATTER
    assert envelope.rows[0]["item_id"] == fp_out


# ── canonical rows are labelled so the fleet inserts, never upserts ────────


def test_canonical_rows_are_labelled_canonical(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    _import("chk-main", "2026-01-01", "-10.00", "Coffee")
    scope = sync.scope_from(["chk-main"], None, Rung.L4, ["canonical"], sidecar=store)
    envelope = sync.preview(scope, sidecar=store)
    assert envelope.rows
    assert all(row["table"] == "canonical" for row in envelope.rows)


# ── the number never crosses, at any ceiling — and the structural belt ─────

_PLANTED_NUMBER = "PLANTED-9821-NEVER-SYNCED"


def _plant(store):
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number=_PLANTED_NUMBER,
        balance_as_of="1200.00",
    )


@pytest.mark.parametrize("ceiling", [Rung.L1, Rung.L2, Rung.L3, Rung.L4])
def test_the_planted_number_never_appears_at_any_ceiling(store, ceiling):
    _plant(store)
    scope = sync.scope_from(["accounts"], None, ceiling, ["sidecar"], sidecar=store)
    envelope = sync.preview(scope, sidecar=store)
    assert _PLANTED_NUMBER not in json.dumps(envelope.to_dict())
    assert not any(row["item_type"] == "number" for row in envelope.rows)


def test_the_structural_belt_refuses_a_number_that_leaked_past_a_corrupted_ceiling(
    store, monkeypatch,
):
    """Plants the failure the belt exists for: a `serve()` that reports
    every rung as `L1`/`RENDER`, the shape a corrupted or monkeypatched
    rung table would leave behind, so the engine's own ceiling drop no
    longer stops `number`. `sync.preview` still refuses (I-13)."""
    _plant(store)

    def _fake_serve(classified, surface, *, purpose=None):
        return Served(
            surface=surface, rung=Rung.L1, disposition=Disposition.RENDER,
            value=classified.payload,
        )

    monkeypatch.setattr(engine_sync, "serve", _fake_serve)
    scope = sync.scope_from(["accounts"], None, Rung.L4, ["sidecar"], sidecar=store)
    with pytest.raises(sync.NumberNeverCrosses):
        sync.preview(scope, sidecar=store)


def test_the_belt_is_quiet_when_nothing_leaked(store):
    """The regression the belt guard needs: a green result means "nothing
    leaked", not "the check cannot see anything" — the ordinary
    (uncorrupted) path composes fine."""
    _plant(store)
    scope = sync.scope_from(["accounts"], None, Rung.L4, ["sidecar"], sidecar=store)
    envelope = sync.preview(scope, sidecar=store)  # must not raise
    assert envelope.count >= 1


# ── a destination is never a permission (I-37) ──────────────────────────


def _one_row_envelope(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Test Bank")
    scope = sync.scope_from(["accounts"], None, Rung.L3, ["sidecar"], sidecar=store)
    return sync.preview(scope, sidecar=store)


def test_env_url_set_and_declined_confirm_writes_nothing_and_ledgers_nothing(store, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_FLEET_URL", "https://fleet.example.invalid/ingest")
    envelope = _one_row_envelope(store)
    integrity_path = paths.logs_dir() / "integrity.jsonl"
    visible_path = paths.logs_dir() / "visible.jsonl"
    before_integrity = integrity_path.read_bytes() if integrity_path.exists() else b""
    before_visible = visible_path.read_bytes() if visible_path.exists() else b""

    with pytest.raises(EgressRefused):
        sync.send(envelope, confirm=lambda wire: False)

    after_integrity = integrity_path.read_bytes() if integrity_path.exists() else b""
    after_visible = visible_path.read_bytes() if visible_path.exists() else b""
    assert after_integrity == before_integrity
    assert after_visible == before_visible


def test_a_declined_file_confirm_writes_nothing_and_ledgers_nothing(store):
    envelope = _one_row_envelope(store)
    drop_dir = sync.default_drop_dir()

    with pytest.raises(EgressRefused):
        sync.send(envelope, drop_dir=drop_dir, confirm=lambda wire: False)

    assert not drop_dir.exists()
    integrity_path = paths.logs_dir() / "integrity.jsonl"
    assert not integrity_path.exists() or not integrity_path.read_text("utf-8").strip()


def test_file_delivery_is_o_excl_one_integrity_row_one_visible_line(store):
    envelope = _one_row_envelope(store)
    drop_dir = sync.default_drop_dir()

    receipt = sync.send(envelope, drop_dir=drop_dir, confirm=lambda wire: True)

    target = drop_dir / f"{envelope.envelope_id}.json"
    assert target.exists()
    assert receipt.destination == str(target)
    on_disk = json.loads(target.read_text("utf-8"))
    assert on_disk["envelope_id"] == envelope.envelope_id

    integrity_lines = (paths.logs_dir() / "integrity.jsonl").read_text("utf-8").splitlines()
    synced = [json.loads(l) for l in integrity_lines if json.loads(l).get("act") == "record_synced"]
    assert len(synced) == 1
    assert synced[0]["envelope"] == envelope.envelope_id
    assert synced[0]["household"] == envelope.household

    visible_lines = (paths.logs_dir() / "visible.jsonl").read_text("utf-8").splitlines()
    assert sum(1 for l in visible_lines if '"record_synced"' in l) == 1

    # I-38 — an envelope is delivered once; the O_EXCL create is the backstop.
    with pytest.raises(sync.AlreadyDelivered):
        sync.send(envelope, drop_dir=drop_dir, confirm=lambda wire: True)


def test_url_delivery_is_mocked_at_egress_send_never_a_socket(store, monkeypatch):
    """Never a real socket, on a money ledger's own outbound seam
    (I-17/I-30) — `homestead.keep.egress.send` is mocked, and every
    socket-construction entry point is separately poisoned so a slip past
    the mock fails loudly rather than hanging or dialing out for real."""
    import homestead.keep.egress as engine_egress

    def _boom(*args, **kwargs):
        raise AssertionError("a real socket call was attempted")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)

    calls = []

    def fake_send(url, payload, *, confirm=None, transport=None, method="POST"):
        wire = engine_egress.Wire(
            method=method, url=url, body=json.dumps(payload, sort_keys=True, ensure_ascii=False),
        )
        calls.append(wire)
        if confirm is None or confirm(wire) is not True:
            raise EgressRefused("declined at the mock")
        return b"ok"

    monkeypatch.setattr(engine_egress, "send", fake_send)

    envelope = _one_row_envelope(store)
    receipt = sync.send(
        envelope, url="https://fleet.example.invalid/ingest", confirm=lambda wire: True,
    )

    assert len(calls) == 1
    assert calls[0].url == "https://fleet.example.invalid/ingest"
    assert receipt.destination == "https://fleet.example.invalid/ingest"
    integrity_lines = (paths.logs_dir() / "integrity.jsonl").read_text("utf-8").splitlines()
    assert any('"record_synced"' in l for l in integrity_lines)


def test_destination_preview_reads_the_env_var_or_falls_back_to_the_drop_dir(store, monkeypatch):
    monkeypatch.delenv("HOMESTEAD_FLEET_URL", raising=False)
    assert sync.destination_preview() == str(sync.default_drop_dir())

    monkeypatch.setenv("HOMESTEAD_FLEET_URL", "https://fleet.example.invalid/ingest")
    assert sync.destination_preview() == "https://fleet.example.invalid/ingest"
