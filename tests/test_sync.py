"""`sync.py` — a consented scope of the household's own books, composed and
delivered on an explicit act. Mirrors `test_schedules.py`'s own shape for
the planted-number section: a distinctive number, read on every ceiling
this bite touches, asserted absent everywhere but the one write that put it
there.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from homestead.keep import paths
from homestead.keep.egress import EgressRefused
from homestead.keep.rungs import Disposition, Rung, Served
from homestead.keep import sync as engine_sync

from homestead_ledger import accounts, books, cli, overlay, schedules, sync, transfers
from homestead_ledger.cli import run_cli
from homestead_ledger.store import Sidecar

# ── the floor this bite raises: 0.13.0, where the fleet took structured values ─


def test_the_engine_floor_carries_sync_core():
    """`homestead.keep.sync.SyncScope`/`Envelope` are what `sync.py` is
    built on (E4-sync-core) — a floor below 0.11.0 would install an engine
    with no `keep/sync.py` at all, and this bite would fail at import
    rather than at `pip install`. `pyproject.toml`'s own floor is
    `homestead-affairs>=0.13.0,<1.0` (see the dependency line's comment)."""
    from homestead.keep.sync import Envelope, SyncScope

    assert SyncScope is not None and Envelope is not None


def test_the_engine_floor_carries_fleet_structured_values():
    """`homestead.keep.fleet_cli.MAX_VALUE_DEPTH` and `decode_value` are
    E7b's own additions (2026-09-11) — a floor below 0.13.0 would install an
    engine whose `fleet_cli` still refuses any mapping `value` by name, and
    this bite's `test_the_fleet_accepts_a_structured_pair_value` would fail
    at import rather than at `pip install`. `pyproject.toml`'s own floor is
    `homestead-affairs>=0.13.0,<1.0` (G7b-floor-0.13)."""
    from homestead.keep.fleet_cli import MAX_VALUE_DEPTH, decode_value

    assert MAX_VALUE_DEPTH > 0 and decode_value is not None


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


def test_scope_from_refuses_an_l5_ceiling_naming_the_rung(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    with pytest.raises(sync.UnnamedScope, match="L5"):
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
    assert {"accounts", "overlay", "transfers", "budget", "obligations"} <= set(after)


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


def _paired(store, *, exclude):
    """Two accounts, one paired transfer, and `exclude` ("out"/"in") tagged
    do_not_use. Returns the two fingerprints."""
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    accounts.add_account(store, "sav-main", kind="savings", number="2")
    fp_out = _import("chk-main", "2026-01-01", "-40.00", "to savings")
    fp_in = _import("sav-main", "2026-01-02", "40.00", "from checking")
    transfers.pair(store, fp_out, fp_in)
    overlay.tag(store, fp_out if exclude == "out" else fp_in, do_not_use=True)
    return fp_out, fp_in


@pytest.mark.parametrize("excluded_leg", ["out", "in"])
def test_a_transfer_pair_naming_an_excluded_leg_is_dropped(store, excluded_leg):
    """The builder kept these, reading a pair as "a reference to two of the
    household's own accounts". The record says otherwise: a pair is keyed
    `(transfers, "pair", <fp_out>)` and its value names `counterpart`, so a
    pair with an excluded out-leg carries the excluded transaction's own
    content hash as its `item_id` and one with an excluded in-leg carries it
    in the value. Either way the row the household said must never leave
    leaves by reference. G4-overlay's `do_not_use` excludes a transaction
    from "every S4 envelope"; the reference goes with it (I-11, fail closed
    where two readings disagree)."""
    fp_out, fp_in = _paired(store, exclude=excluded_leg)

    scope = sync.scope_from(["transfers"], None, Rung.L2, ["sidecar"], sidecar=store)
    with pytest.raises(sync.NothingToSync):
        sync.preview(scope, sidecar=store)   # the one pair was the only row


def test_an_excluded_transfer_leg_appears_nowhere_in_a_whole_household_sync(store):
    """The same drop, read the way it matters: grep the envelope bytes of a
    sync over *every* matter the household has. The excluded fingerprint is
    nowhere in them — not as a row of its own, not as a pair's `item_id`,
    and not as a `counterpart` inside one. The counterpart's own rows stay:
    do_not_use excluded one transaction, not the other account's books."""
    fp_out, fp_in = _paired(store, exclude="in")
    envelope = sync.preview(
        sync.scope_from(
            sync.known_matters(store), None, Rung.L4, ["sidecar", "canonical"], sidecar=store,
        ),
        sidecar=store,
    )
    body = envelope.to_bytes().decode("utf-8")
    assert fp_in not in body
    assert not any(row["matter"] == transfers.MATTER for row in envelope.rows)
    assert fp_out in body   # the leg that was not excluded is still the books


def test_a_transfer_pair_with_no_excluded_leg_still_crosses(store):
    """The regression the drop needs: it drops a pair that names an excluded
    fingerprint, not every pair."""
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    accounts.add_account(store, "sav-main", kind="savings", number="2")
    fp_out = _import("chk-main", "2026-01-01", "-40.00", "to savings")
    fp_in = _import("sav-main", "2026-01-02", "40.00", "from checking")
    transfers.pair(store, fp_out, fp_in)
    other = _import("chk-main", "2026-02-01", "-5.00", "unrelated")
    overlay.tag(store, other, do_not_use=True)

    scope = sync.scope_from(["transfers"], None, Rung.L2, ["sidecar"], sidecar=store)
    envelope = sync.preview(scope, sidecar=store)
    assert [row["item_id"] for row in envelope.rows] == [fp_out]


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


@pytest.mark.parametrize("ceiling", [Rung.L2, Rung.L3, Rung.L4])
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




# ── nothing to sync is refused, never delivered as an envelope of nothing ───


def test_a_scope_that_composes_no_rows_is_refused_and_nothing_is_written(store):
    """A zero-row envelope is still a *delivery*: it writes a file, spends
    an envelope id, and writes an `IntegrityLog` row and a visible line that
    read as a sync that happened. Refused at `preview`, before a confirm is
    ever shown one."""
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    scope = sync.scope_from(["budget"], None, Rung.L4, ["sidecar"], sidecar=store)
    with pytest.raises(sync.NothingToSync, match="nothing to sync"):
        sync.preview(scope, sidecar=store)
    assert not sync.default_drop_dir().exists()
    assert not (paths.logs_dir() / "integrity.jsonl").exists()


def test_an_l1_ceiling_composes_nothing_and_says_so(store):
    """Nothing this package classifies sits at `L1` (the packs' lowest rung
    is `L2`), so an `L1` ceiling is a scope that can only compose nothing —
    said by name rather than delivered as an empty envelope."""
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    scope = sync.scope_from(["accounts"], None, Rung.L1, ["sidecar"], sidecar=store)
    with pytest.raises(sync.NothingToSync):
        sync.preview(scope, sidecar=store)


def test_nothing_to_sync_is_caught_by_a_caller_handling_scope_refusals(store):
    """`NothingToSync` is an `UnnamedScope`, so the CLI's and the server's
    one `except ValueError` already answers it as a refusal."""
    assert issubclass(sync.NothingToSync, sync.UnnamedScope)
    assert issubclass(sync.NothingToSync, ValueError)


# ── --types: a name that matches nothing is refused by name ────────────────


def test_an_unknown_item_type_is_refused_by_name(store):
    """The typo that would otherwise ship: `--types` narrows, so a name no
    record carries silently composes an envelope of nothing. Refused naming
    the offending type and what the matters named actually hold."""
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    scope = sync.scope_from(
        ["accounts"], ["instutition"], Rung.L4, ["sidecar"], sidecar=store,
    )
    with pytest.raises(sync.UnnamedScope, match="unknown item type"):
        sync.preview(scope, sidecar=store)


def test_a_known_item_type_still_composes(store):
    """The regression: the type check refuses a name nothing holds, not
    every name."""
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    scope = sync.scope_from(
        ["accounts"], ["institution"], Rung.L4, ["sidecar"], sidecar=store,
    )
    envelope = sync.preview(scope, sidecar=store)
    assert {row["item_type"] for row in envelope.rows} == {"institution"}


def test_the_item_type_check_never_names_an_excluded_row(store):
    """What is "on file" for the purposes of the refusal is what the filter
    already left — an error message is a reference, never a leak (I-15)."""
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    fp = _import("chk-main", "2026-01-01", "-50.00", "Excluded")
    overlay.tag(store, fp, do_not_use=True)
    scope = sync.scope_from(["chk-main"], ["nope"], Rung.L4, ["canonical"], sidecar=store)
    with pytest.raises(sync.UnnamedScope) as caught:
        sync.preview(scope, sidecar=store)
    assert fp not in str(caught.value)


# ── the confirm reads the Wire it is handed (I-37) ─────────────────────────


def _foreign_envelope(store):
    accounts.add_account(store, "sav-other", kind="savings", number="7", institution="Elsewhere")
    scope = sync.scope_from(["accounts"], None, Rung.L3, ["sidecar"], sidecar=store)
    return sync.preview(scope, sidecar=store)


def test_wire_matches_holds_the_file_leg_to_this_envelope(store):
    envelope = _one_row_envelope(store)
    target = sync.default_drop_dir() / f"{envelope.envelope_id}.json"
    good = engine_sync.Wire(
        method="FILE", url=str(target),
        body=f"{len(envelope.to_bytes())} bytes", content_type="text/plain",
    )
    assert sync.wire_matches(envelope, good) is True
    # another envelope's drop, the same directory — the id is the difference
    other = engine_sync.Wire(
        method="FILE", url=str(sync.default_drop_dir() / "deadbeef.json"),
        body=good.body, content_type="text/plain",
    )
    assert sync.wire_matches(envelope, other) is False
    # the right name, a different size: not this envelope's frozen bytes
    resized = engine_sync.Wire(
        method="FILE", url=str(target), body="1 bytes", content_type="text/plain",
    )
    assert sync.wire_matches(envelope, resized) is False


def test_wire_matches_compares_the_url_leg_as_bytes(store):
    envelope = _one_row_envelope(store)
    foreign = _foreign_envelope(store)
    good = engine_sync.Wire(
        method="POST", url="https://fleet.example.invalid/ingest",
        body=json.dumps(envelope.to_dict(), sort_keys=True, ensure_ascii=False),
    )
    assert sync.wire_matches(envelope, good) is True
    swapped = engine_sync.Wire(
        method="POST", url="https://fleet.example.invalid/ingest",
        body=json.dumps(foreign.to_dict(), sort_keys=True, ensure_ascii=False),
    )
    assert sync.wire_matches(envelope, swapped) is False
    assert sync.wire_matches(foreign, swapped) is True
    # not an envelope at all, and an envelope whose id does not hash its own
    # contents (`Envelope.from_bytes` refuses that one, I-11)
    assert sync.wire_matches(envelope, engine_sync.Wire(
        method="POST", url="https://fleet.example.invalid/ingest", body="{}")) is False
    tampered = json.loads(good.body)
    tampered["count"] = 99
    assert sync.wire_matches(envelope, engine_sync.Wire(
        method="POST", url="https://fleet.example.invalid/ingest",
        body=json.dumps(tampered))) is False


def test_a_confirm_that_reads_the_wire_refuses_a_swapped_envelope(store, monkeypatch):
    """The plant behind `wire_matches`: `deliver()` is made to hand the
    confirm a `Wire` for a *different* envelope, the shape a re-composed or
    swapped delivery would arrive in. A `lambda wire: True` sends it; a
    confirm that reads the Wire does not."""
    envelope = _one_row_envelope(store)
    foreign = _foreign_envelope(store)
    sent = []

    def fake_deliver(env, *, confirm, url=None, drop_dir=None, **kw):
        wire = engine_sync.Wire(
            method="FILE", url=str((drop_dir or Path("/tmp")) / f"{foreign.envelope_id}.json"),
            body=f"{len(foreign.to_bytes())} bytes", content_type="text/plain",
        )
        if confirm(wire) is not True:
            raise EgressRefused("declined at the preview")
        sent.append(wire)
        return None

    monkeypatch.setattr(sync, "_engine_deliver", fake_deliver)
    with pytest.raises(EgressRefused):
        sync.send(
            envelope, drop_dir=sync.default_drop_dir(),
            confirm=lambda wire: sync.wire_matches(envelope, wire),
        )
    assert sent == []
    # and the permission-shaped callback the audit replaced would have sent it
    sync.send(envelope, drop_dir=sync.default_drop_dir(), confirm=lambda wire: True)
    assert len(sent) == 1


# ── the destination is resolved once, at preview, and carried ──────────────


def test_resolve_destination_prefers_the_explicit_url_then_env_then_file(store, monkeypatch):
    monkeypatch.delenv("HOMESTEAD_FLEET_URL", raising=False)
    assert sync.resolve_destination() == (None, sync.default_drop_dir())

    (paths.home() / "fleet.url").write_text("  https://from-file.invalid/ingest \n", "utf-8")
    assert sync.resolve_destination() == ("https://from-file.invalid/ingest", None)

    monkeypatch.setenv("HOMESTEAD_FLEET_URL", " https://from-env.invalid/ingest ")
    assert sync.resolve_destination() == ("https://from-env.invalid/ingest", None)

    assert sync.resolve_destination(url="https://explicit.invalid/ingest") == (
        ("https://explicit.invalid/ingest", None)
    )
    # `destination_preview` is that same resolution as the one string a
    # preview shows — the CLI and the Sync tab both print it.
    assert sync.destination_preview() == "https://from-env.invalid/ingest"
    monkeypatch.delenv("HOMESTEAD_FLEET_URL")
    (paths.home() / "fleet.url").unlink()
    assert sync.destination_preview() == str(sync.default_drop_dir())


def test_a_fleet_url_written_after_the_resolve_does_not_redirect_the_delivery(store, monkeypatch):
    """A destination resolved at preview and carried is a destination the
    operator saw. Resolving again inside `send()` would let this file —
    written between the two — turn a previewed file drop into a network POST
    nobody was asked about (the shape the L5-sync audit found on the law
    side, 2026-09-11)."""
    monkeypatch.delenv("HOMESTEAD_FLEET_URL", raising=False)
    envelope = _one_row_envelope(store)
    dest_url, dest_dir = sync.resolve_destination()
    assert dest_url is None

    (paths.home() / "fleet.url").write_text("https://late.invalid/ingest\n", "utf-8")

    receipt = sync.send(envelope, url=dest_url, drop_dir=dest_dir, confirm=lambda w: True)
    assert receipt.destination == str(dest_dir / f"{envelope.envelope_id}.json")
    assert "late.invalid" not in receipt.destination


# ── the reader wrapper is a whole Reader (I-16: no payload, no reflection) ──


def test_the_excluding_reader_delegates_every_other_reader_method(store):
    """`compose()` reads `records()` today; a wrapper that answers only that
    is one refactor away from an `AttributeError` in the middle of a sync.
    Every other `Reader` method is delegated unchanged."""
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    fp = _import("chk-main", "2026-01-01", "-50.00", "Excluded")
    overlay.tag(store, fp, do_not_use=True)
    wrapped = sync._ExcludingReader(store, excluded={overlay.MATTER: frozenset({fp})})

    assert wrapped.has("accounts", "institution", "chk-main") is True
    assert wrapped.get("accounts", "institution", "chk-main") == store.get(
        "accounts", "institution", "chk-main"
    )
    assert wrapped.advise("accounts", "institution", "chk-main") == store.advise(
        "accounts", "institution", "chk-main"
    )
    assert wrapped.deadlines("accounts") == store.deadlines("accounts")
    # and the filter itself is per matter: `accounts` is untouched
    assert len(wrapped.records("accounts")) == len(store.records("accounts"))
    assert not any(ref[2] == fp for ref, _ in wrapped.records(overlay.MATTER))


def test_the_canonical_table_literal_is_the_engines_own():
    """`sync.py` spells the canonical table as a literal because this
    package's chokepoint scan refuses any module but `books.py` naming the
    engine's `CANONICAL` constant at all. The literal and the constant can
    therefore only be held together from outside the package — here."""
    from homestead.keep.store import CANONICAL

    assert sync._CANONICAL == CANONICAL


# ── I-23: the matters are discovered, never listed ─────────────────────────


def test_sidecar_matters_are_discovered_from_the_packs(store):
    """Every pack that declares a `MATTER`, found the way `registry.py`
    finds an `ACCOUNT` — held against an independent read of the pack
    sources, so a matter added to one and not the other fails here."""
    import re

    pack_dir = Path(sync.packs.__file__).parent
    on_disk = {
        m.group(1)
        for path in pack_dir.glob("*.py")
        for m in re.finditer(r'^MATTER = "([a-z0-9-]+)"$', path.read_text("utf-8"), re.M)
    }
    assert on_disk == set(sync._sidecar_matters())
    assert on_disk <= set(sync.known_matters(store))


def test_known_matters_picks_up_a_planted_sidecar_pack(tmp_path):
    """A guard that has never fired has not been shown to check anything:
    a *new* sidecar pack, written to a package of its own, is discovered
    with no edit to `sync.py`. The hand-kept tuple this replaced would have
    silently refused to sync it."""
    import importlib
    import sys as _sys

    pkg = tmp_path / "planted_packs"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", "utf-8")
    (pkg / "reconciliation.py").write_text('MATTER = "reconciliation"\n', "utf-8")
    (pkg / "chk_like.py").write_text('ACCOUNT = "chk_like"\n', "utf-8")   # not a matter
    _sys.path.insert(0, str(tmp_path))
    try:
        planted = importlib.import_module("planted_packs")
        found = sync._sidecar_matters(planted)
    finally:
        _sys.path.remove(str(tmp_path))
        for name in [n for n in _sys.modules if n.startswith("planted_packs")]:
            del _sys.modules[name]
    assert found == frozenset({"reconciliation"})


# ── the fleet's own end: what it does with an envelope this module produced ─


def _full_envelope(store):
    accounts.add_account(
        store, "chk-main", kind="checking", number="1", institution="Test Bank",
    )
    _import("chk-main", "2026-01-05", "-12.34", "Coffee")
    scope = sync.scope_from(
        ["accounts", "chk-main"], None, Rung.L4, ["sidecar", "canonical"], sidecar=store,
    )
    return sync.preview(scope, sidecar=store)


def test_the_fleet_reads_and_validates_a_produced_envelope_before_it_dials(store):
    """Fleet compatibility, exercised without a database: the fleet's own
    `Envelope.from_bytes` and `_validate_rows` both run *before*
    `PostgresAdapter` is even constructed, so a real envelope can be held to
    them here. Schema, household id shape and the plan's row keys, and the
    canonical rows labelled so `ingest` takes the insert-only branch."""
    import re as _re

    from homestead.keep import fleet_cli
    from homestead.keep.sync import SCHEMA, Envelope

    envelope = _full_envelope(store)
    parsed = Envelope.from_bytes(envelope.to_bytes())

    assert parsed.schema == SCHEMA == "homestead.sync/1"
    assert _re.fullmatch(r"hh-[0-9a-f]{16}", parsed.household)
    assert set(parsed.to_dict()) == {
        "schema", "household", "composed_at", "head", "scope", "rows", "count",
        "envelope_id",
    }
    for row in parsed.rows:
        assert set(row) == {
            "table", "matter", "item_type", "item_id", "rung", "disposition",
            "value", "derived",
        }
    fleet_cli._validate_rows(parsed)          # must not raise

    canonical_rows = [r for r in parsed.rows if r["table"] == "canonical"]
    assert canonical_rows
    # the branch `ingest()` takes for them is the insert-only one
    assert all(row["table"] != "sidecar" for row in canonical_rows)


def test_the_fleet_refuses_a_structured_pair_value_by_name(store):
    """Pinned, not papered over: a `transfers` `pair` is served as a mapping
    (it is `L2`), and the fleet's `value` column is `TEXT`, so
    `_validate_rows` refuses the row — and with it the *whole* envelope
    (I-11). An envelope whose scope names `transfers` therefore composes and
    drops to a file here and is refused at `homestead-fleet ingest`, loudly
    and before a row is written. Settling that is the engine's contract to
    change (a `TEXT` column versus a structured served value), not a
    module's to work around; this test is where it is recorded."""
    from homestead.keep import fleet_cli
    from homestead.keep.sync import Envelope

    accounts.add_account(store, "chk-main", kind="checking", number="1")
    accounts.add_account(store, "sav-main", kind="savings", number="2")
    fp_out = _import("chk-main", "2026-01-01", "-40.00", "to savings")
    fp_in = _import("sav-main", "2026-01-02", "40.00", "from checking")
    transfers.pair(store, fp_out, fp_in)

    scope = sync.scope_from(["transfers"], None, Rung.L2, ["sidecar"], sidecar=store)
    envelope = sync.preview(scope, sidecar=store)
    assert not isinstance(envelope.rows[0]["value"], str)

    with pytest.raises(fleet_cli.IngestRefused, match="not storable text"):
        fleet_cli._validate_rows(Envelope.from_bytes(envelope.to_bytes()))


# ── the CLI: the yes is read after the Wire is printed, and there is no --yes ─


def test_the_cli_refuses_without_a_terminal_and_has_no_yes_flag(store, monkeypatch, capsys):
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert run_cli(["sync", "--matters", "accounts", "--ceiling", "L3",
                    "--init-household"]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and "interactive terminal" in err and "--yes" in err
    assert "--yes" not in cli._SYNC_USAGE
    assert not sync.default_drop_dir().exists()


def test_the_cli_prints_the_wire_it_sends_and_reads_the_yes_after_it(store, monkeypatch, capsys):
    """The preview *is* the request: what the terminal prints before the
    prompt is `Wire.preview()` — the same object `deliver()` hands the
    transport — and `input()` is not called until it has been printed."""
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    seen = {}

    def _input(prompt):
        seen["printed"] = capsys.readouterr().out
        return "y"

    monkeypatch.setattr("builtins.input", _input)
    assert run_cli(["sync", "--matters", "accounts", "--ceiling", "L3",
                    "--init-household"]) == 0

    dropped = sorted(sync.default_drop_dir().glob("*.json"))
    assert len(dropped) == 1
    envelope_id = dropped[0].stem
    wire = engine_sync.Wire(
        method="FILE", url=str(dropped[0]),
        body=f"{dropped[0].stat().st_size} bytes", content_type="text/plain",
    )
    assert wire.preview() in seen["printed"]
    assert envelope_id in seen["printed"]


def test_the_cli_declines_a_wire_that_is_not_the_previewed_envelope(store, monkeypatch, capsys):
    """The confirm refuses before the prompt: `input` is never reached."""
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def _never(prompt):   # pragma: no cover - reaching this is the failure
        raise AssertionError("the operator was asked about a wire that was refused")

    monkeypatch.setattr("builtins.input", _never)

    def fake_deliver(env, *, confirm, url=None, drop_dir=None, **kw):
        confirm(engine_sync.Wire(
            method="FILE", url=str((drop_dir or Path("/tmp")) / "deadbeef.json"),
            body="1 bytes", content_type="text/plain",
        ))
        raise EgressRefused("declined at the preview")

    monkeypatch.setattr(sync, "_engine_deliver", fake_deliver)
    assert run_cli(["sync", "--matters", "accounts", "--ceiling", "L3",
                    "--init-household"]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and "not the envelope previewed" in err


def test_the_cli_says_nothing_to_sync_rather_than_delivering_nothing(store, monkeypatch, capsys):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert run_cli(["sync", "--matters", "budget", "--ceiling", "L4",
                    "--init-household"]) == 1
    assert "nothing to sync" in capsys.readouterr().err
    assert not sync.default_drop_dir().exists()


def test_the_cli_prints_the_notice_verbatim(store, monkeypatch, capsys):
    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    run_cli(["sync", "--matters", "accounts", "--ceiling", "L3", "--init-household"])
    assert schedules.NOTICE in capsys.readouterr().out


def test_a_sealed_ledger_the_cli_cannot_read_is_refused_by_name(store, monkeypatch, capsys):
    """A sealed `IntegrityLog` with no key cannot be read to say whether
    this envelope already went, so the engine refuses by name *before*
    delivering. The terminal answers with one `refused:` line, never a
    traceback (I-11)."""
    from homestead.keep.logs import IntegrityLog, IntegritySealError

    accounts.add_account(store, "chk-main", kind="checking", number="1", institution="Bank")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    # `_already_delivered` only reads a log that exists, so there is one.
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    (paths.logs_dir() / "integrity.jsonl").write_text('{"sealed": 1}\n', "utf-8")

    def _sealed(self, *, decrypt=True):
        raise IntegritySealError(
            "this log is sealed; the key is absent — sealing requires the key"
        )

    monkeypatch.setattr(IntegrityLog, "_entries", _sealed)
    assert run_cli(["sync", "--matters", "accounts", "--ceiling", "L3",
                    "--init-household"]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and "sealed" in err and "Traceback" not in err
    assert not sync.default_drop_dir().exists()


# ── ledgered once, by reference only (I-38, I-15) ──────────────────────────


def test_a_second_delivery_is_refused_by_the_ledger_not_only_by_the_file(store, tmp_path):
    """I-38 has two mechanisms and the O_EXCL create is only the backstop:
    delivered once and then offered a *different* destination, the same
    envelope is still refused — the `IntegrityLog` row is what makes it
    already-delivered."""
    envelope = _one_row_envelope(store)
    sync.send(envelope, drop_dir=sync.default_drop_dir(), confirm=lambda wire: True)

    elsewhere = paths.home() / "second-drop"
    with pytest.raises(sync.AlreadyDelivered):
        sync.send(envelope, drop_dir=elsewhere, confirm=lambda wire: True)
    assert not elsewhere.exists()


def test_the_visible_line_carries_the_household_and_the_envelope_and_nothing_else(store):
    """I-15: the visible log is references. The planted institution — an
    `L3` value that really is in the envelope — must not be in the line that
    records the sync."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number=_PLANTED_NUMBER,
        institution="PLANTED-INSTITUTION-NEVER-LOGGED",
    )
    scope = sync.scope_from(["accounts"], None, Rung.L3, ["sidecar"], sidecar=store)
    envelope = sync.preview(scope, sidecar=store)
    assert "PLANTED-INSTITUTION-NEVER-LOGGED" in envelope.to_bytes().decode("utf-8")

    sync.send(envelope, drop_dir=sync.default_drop_dir(), confirm=lambda wire: True)

    visible = (paths.logs_dir() / "visible.jsonl").read_text("utf-8")
    line = [l for l in visible.splitlines() if "record_synced" in l]
    assert len(line) == 1
    assert envelope.household in line[0] and envelope.envelope_id in line[0]
    assert "PLANTED-INSTITUTION-NEVER-LOGGED" not in visible
    assert _PLANTED_NUMBER not in visible

    integrity = (paths.logs_dir() / "integrity.jsonl").read_text("utf-8")
    assert "PLANTED-INSTITUTION-NEVER-LOGGED" not in integrity
    assert _PLANTED_NUMBER not in integrity
