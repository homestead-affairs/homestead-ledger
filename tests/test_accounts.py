"""Account instances (`accounts.py`, decision 9) — the sidecar matter
`accounts`, one record per field per operator-chosen label.

Mirrors `obligations.py`'s own test shape: a label-shape table, the I-9
occupied-write refusal, and the gate (`serve()`, never `.payload`) for every
read. The invariant this bite adds, I-43 ("an account number lives in
exactly one record"), gets its own section — a planted, distinctive number,
read on every surface this bite touches, asserted absent everywhere but the
one write that put it there.
"""
from __future__ import annotations

import pytest
from homestead.keep.rungs import Disposition, Rung, Surface, serve
from homestead.keep.store import InvalidKey, RecordExists

from homestead_ledger import accounts, registry
from homestead_ledger.app.cover import K
from homestead_ledger.store import Sidecar

pytestmark = pytest.mark.usefixtures("_home")


@pytest.fixture
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))


# ── the label shape — accept/refuse table ───────────────────────────────────

@pytest.mark.parametrize("label", [
    "chk-main", "a", "a1", "visa-chase", "9", "checking-2", "x" * 40,
])
def test_valid_labels_are_accepted(label):
    accounts.add_account(Sidecar(), label, kind="checking", number="9821")
    assert accounts.label_exists(Sidecar(), label)


@pytest.mark.parametrize("label", [
    "", "  ", "-leading-hyphen", "Chk-Main", "chk main", "chk_main",
    "chk/main", "../etc", "chk.main", "x" * 41, "chk'main",
])
def test_invalid_labels_are_refused(label):
    with pytest.raises(InvalidKey):
        accounts.add_account(Sidecar(), label, kind="checking", number="9821")


@pytest.mark.parametrize("kind", sorted(registry.all_accounts()))
def test_a_label_equal_to_a_registered_kind_name_is_refused_by_name(kind):
    """I-43: a label could otherwise be mistaken for a kind — every
    registered kind name is refused as a label, not only "checking". A kind
    with an underscore (`credit_card`) fails the id-*shape* check first
    (underscores are not in it) and never reaches the collision check at
    all — still refused, by a different sentence; only a shape-legal kind
    name's own message is held to naming it."""
    with pytest.raises(InvalidKey) as exc:
        accounts.add_account(Sidecar(), kind, kind=kind, number="1")
    if accounts._ID.match(kind):
        assert kind in str(exc.value)
    assert not accounts.label_exists(Sidecar(), kind)


def test_an_unregistered_kind_is_refused_by_name():
    with pytest.raises(ValueError) as exc:
        accounts.add_account(Sidecar(), "chk-main", kind="brokerage", number="1")
    assert "brokerage" in str(exc.value)
    for name in registry.all_accounts():
        assert name in str(exc.value)


def test_a_missing_number_is_refused():
    with pytest.raises(ValueError, match="number"):
        accounts.add_account(Sidecar(), "chk-main", kind="checking", number="")


# ── writing, reading back, and the I-9 occupied-write refusal ──────────────

def test_add_account_round_trips_every_optional_field():
    sidecar = Sidecar()
    accounts.add_account(
        sidecar, "chk-main", kind="checking", number="9821",
        institution="Wells Fargo", opened="2020-01-15", payment_due_day="15",
    )
    fields = accounts.detail(sidecar, "chk-main")
    assert fields["kind"] == ("L2", "checking")
    assert fields["institution"] == ("L3", "Wells Fargo")
    assert fields["opened"] == ("L2", "2020-01-15")
    assert fields["payment_due_day"] == ("L2", "15")
    assert fields["number"] == ("L5", None)     # I-13: never served, anywhere


def test_add_account_writes_only_the_fields_given():
    sidecar = Sidecar()
    accounts.add_account(sidecar, "chk-main", kind="checking", number="9821")
    fields = accounts.detail(sidecar, "chk-main")
    assert set(fields) == {"kind", "number"}    # no placeholder for the rest


def test_a_second_add_under_the_same_label_is_refused_without_replace():
    sidecar = Sidecar()
    accounts.add_account(sidecar, "chk-main", kind="checking", number="9821")
    with pytest.raises(RecordExists):
        accounts.add_account(sidecar, "chk-main", kind="savings", number="1")
    # untouched
    assert accounts.kind_of(sidecar, "chk-main") == "checking"


def test_replace_true_overwrites_and_reports_what_it_displaced():
    sidecar = Sidecar()
    accounts.add_account(sidecar, "chk-main", kind="checking", number="9821")
    ref, replaced = accounts.add_account(
        sidecar, "chk-main", kind="savings", number="1", replace=True,
    )
    assert replaced is not None
    assert accounts.kind_of(sidecar, "chk-main") == "savings"


def test_payment_due_day_out_of_range_is_refused():
    with pytest.raises(ValueError):
        accounts.add_account(Sidecar(), "chk-main", kind="checking", number="1", payment_due_day="32")
    with pytest.raises(ValueError):
        accounts.add_account(Sidecar(), "chk-main", kind="checking", number="1", payment_due_day="0")


def test_a_non_finite_money_field_is_refused():
    with pytest.raises(ValueError):
        accounts.add_account(Sidecar(), "chk-main", kind="checking", number="1", rate="nan")


# ── instances / kind_of / label_exists ──────────────────────────────────────

def test_instances_lists_every_label_sorted():
    sidecar = Sidecar()
    accounts.add_account(sidecar, "visa-chase", kind="credit_card", number="1")
    accounts.add_account(sidecar, "chk-main", kind="checking", number="2")
    assert accounts.instances(sidecar) == ["chk-main", "visa-chase"]


def test_kind_of_an_unknown_label_is_refused_by_name_with_no_echo():
    sidecar = Sidecar()
    with pytest.raises(ValueError) as exc:
        accounts.kind_of(sidecar, "no-such-label")
    assert "no-such-label" in str(exc.value)   # the label is a reference, not a secret
    assert not accounts.label_exists(sidecar, "no-such-label")


# ── I-13: the number is never served, on any surface, in any form ─────────

def test_the_number_denies_on_every_surface():
    """`number` is L5 — `decide()` returns `DENY` for every surface member,
    with or without a purpose declared (I-13: no override anywhere)."""
    sidecar = Sidecar()
    accounts.add_account(sidecar, "chk-main", kind="checking", number="9821-secret")
    record = sidecar.get(accounts.MATTER, "number", "chk-main")
    assert record.rung is Rung.L5
    for surface in Surface:
        served = serve(record, surface)
        assert served.disposition is Disposition.DENY
        assert served.value is None


def test_rows_rung_reflects_what_is_shown_not_the_sealed_number():
    """`number` (L5) is always present on an instance but never rendered by
    `rows()` — composing it in anyway would badge every row `L5` and say
    nothing about what the row actually shows. The row's rung is the max of
    only `kind` (L2) and `institution` (L3, when on file)."""
    sidecar = Sidecar()
    accounts.add_account(sidecar, "chk-main", kind="checking", number="9821")
    (bare,) = accounts.rows(sidecar)
    assert bare.rung is Rung.L2

    accounts.add_account(
        sidecar, "visa-chase", kind="credit_card", number="4242", institution="Chase",
    )
    by_label = {r.label: r for r in accounts.rows(sidecar)}
    assert by_label["visa-chase"].rung is Rung.L3


def test_rows_and_detail_never_carry_the_number(capsys):
    """The two read surfaces this module exposes — `rows()` (S1_LIST) and
    `detail()` (S1_DETAIL) — never render the number, and `rows()` does not
    even have a place to put it (no `number` column at all)."""
    sidecar = Sidecar()
    accounts.add_account(
        sidecar, "chk-main", kind="checking", number="4111-secret",
        institution="Credit Union",
    )
    for row in accounts.rows(sidecar):
        assert "4111-secret" not in repr(row)
    fields = accounts.detail(sidecar, "chk-main")
    assert fields["number"] == ("L5", None)
    assert "4111-secret" not in repr(fields)


# ── the planted number: read every surface this bite touches ──────────────

_PLANTED_NUMBER = "4242-4242-PLANTED"


def _plant(label: str = "chk-plant") -> str:
    accounts.add_account(Sidecar(), label, kind="checking", number=_PLANTED_NUMBER)
    return label


def test_the_planted_number_never_appears_in_cli_output(capsys):
    from homestead_ledger.cli import run_cli

    label = _plant()
    capsys.readouterr()

    run_cli(["account", "list"])
    run_cli(["account", "show", label])
    run_cli(["transaction", "add", "2026-08-01", "-10.00", "x", "--account", label])
    run_cli(["transaction", "list", "--account", label])
    transcript = capsys.readouterr()  # stdout + stderr — the operator's own "visible log"
    assert _PLANTED_NUMBER not in transcript.out
    assert _PLANTED_NUMBER not in transcript.err


def test_the_planted_number_never_appears_over_the_browser(capsys):
    """`/api/status`, `/api/accounts`-shaped reads (`/api/transactions`), and
    the served page markup — none of them ever carry the number back."""
    import json

    from homestead_ledger import server

    label = _plant()
    srv = server.build_server(host="127.0.0.1", port=0)
    import http.client
    import threading

    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = srv.server_address

        def get(path):
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("GET", path)
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            return body

        status_body = get("/api/status")
        assert _PLANTED_NUMBER.encode() not in status_body
        assert _PLANTED_NUMBER not in json.loads(status_body).__repr__()

        transactions_body = get(f"/api/transactions?account={label}")
        assert _PLANTED_NUMBER.encode() not in transactions_body

        page_body = get("/")
        assert _PLANTED_NUMBER.encode() not in page_body
    finally:
        srv.shutdown()
        srv.server_close()


def test_fingerprint_is_identical_to_the_pre_instance_path():
    """Dedup continuity: the transaction fingerprint is still computed over
    the raw number, exactly as it was before account instances existed — a
    row imported under the old shape and the same row imported under this
    one land on the same id."""
    from homestead_ledger.books import Transaction, import_transaction
    from homestead_ledger.fingerprint import fingerprint

    label = _plant("chk-fp")
    txn = Transaction(
        account=label, kind="checking", date="2026-08-01", amount="-84.23",
        description="Whole Foods Market",
    )
    item_id = import_transaction(txn)
    old_style_id = fingerprint(
        date="2026-08-01", amount="-84.23", description="Whole Foods Market",
        account=_PLANTED_NUMBER,
    )
    assert item_id == old_style_id


def test_the_account_number_record_is_not_written_by_import_transaction():
    """I-43: the per-transaction `account_number` record this pack used to
    write is gone — assert the key is simply absent, not sealed."""
    from homestead.keep.store import CANONICAL, SQLiteAdapter, key
    from homestead.keep import paths
    from homestead_ledger.books import Transaction, import_transaction

    label = _plant("chk-noan")
    txn = Transaction(
        account=label, kind="checking", date="2026-08-01", amount="-10.00",
        description="x",
    )
    item_id = import_transaction(txn)
    adapter = SQLiteAdapter(paths.home() / "homestead-ledger.db")
    assert adapter.read(CANONICAL, key(label, "account_number", item_id)) is None


# ── the cover (I-31) ─────────────────────────────────────────────────────

def test_cover_shows_nothing_with_fewer_than_two_instances():
    sidecar = Sidecar()
    assert accounts.cover(sidecar) == {}
    accounts.add_account(sidecar, "chk-main", kind="checking", number="1")
    assert accounts.cover(sidecar) == {}      # one instance: still absence


def test_cover_shows_a_count_once_two_instances_exist():
    sidecar = Sidecar()
    accounts.add_account(sidecar, "chk-main", kind="checking", number="1")
    accounts.add_account(sidecar, "visa-chase", kind="credit_card", number="2")
    assert accounts.cover(sidecar) == {"instances": 2}
    assert K == 2
