"""Transfers between the household's own accounts (decision 9).

`pair()` needs a `books.import_transaction` for each leg and a registered
account instance for each label — `make_account` (conftest.py) plus a small
local helper for posting a transaction under a given label build every
fixture below.
"""
from __future__ import annotations

import ast
import json
from datetime import date as _date

import pytest
from homestead.keep.store import RecordExists

from homestead_ledger import accounts, balance, registry, transfers
from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.cli import run_cli
from homestead_ledger.recurring import detect_recurring
from homestead_ledger.store import Canonical, Sidecar


def _txn(label: str, kind: str, *, date: str, amount: str, description: str = "x") -> str:
    return import_transaction(
        Transaction(account=label, kind=kind, date=date, amount=amount, description=description)
    )


@pytest.fixture
def two_accounts(tmp_path, monkeypatch, make_account):
    """`chk-t` (checking) and `card-t` (credit_card) — every test below pairs
    a leg on one against a leg on the other."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    checking = make_account("checking", label="chk-t", number="1111")
    card = make_account("credit_card", label="card-t", number="2222")
    return checking, card


# ── the pack — not discovered as an account or obligation kind ─────────────


def test_the_transfers_sidecar_is_not_a_discovered_pack():
    """Mirrors `test_registry.py`'s own guard for `packs/accounts.py` — a
    transfer pairing has nothing to do with account *kinds* and must never
    be mistaken for one."""
    from homestead_ledger.packs import transfers as transfers_pack

    assert not hasattr(transfers_pack, "ACCOUNT")
    assert not hasattr(transfers_pack, "OBLIGATION")
    assert "transfers" not in registry.all_accounts()
    assert "transfers" not in registry.all_obligations()
    assert transfers_pack not in registry._discover_packs().values()
    assert transfers_pack not in registry._discover_obligation_packs().values()


def test_the_pair_field_is_l2_and_names_its_step():
    from homestead_ledger.packs import transfers as transfers_pack

    assert transfers_pack.FIELDS["pair"].value == "L2"
    assert "step" in transfers_pack.SCHEMA["pair"]["why"].lower()


# ── the canonical pairing case: a card payment, checking -> credit card ────


def test_a_card_payment_from_checking_pairs(two_accounts):
    """The plan's own canonical case: money leaving checking as a negative
    debit and landing on the card as a positive payment — an asset-to-
    liability transfer, not two same-sign amounts."""
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-100.00", description="to card")
    fp_in = _txn(card, "credit_card", date="2026-08-03", amount="100.00", description="from checking")

    ref, replaced = transfers.pair(sidecar, fp_out, fp_in)
    assert ref == (transfers.MATTER, "pair", fp_out)
    assert replaced is None
    assert transfers.counterpart_of(sidecar, fp_out) == fp_in
    assert transfers.counterpart_of(sidecar, fp_in) == fp_out
    assert transfers.other_label(sidecar, fp_out) == card
    assert transfers.other_label(sidecar, fp_in) == checking
    assert transfers.paired_fingerprints(sidecar) == frozenset({fp_out, fp_in})


# ── refusals, each named and none echoing the planted amount ───────────────

_PLANTED_AMOUNT = "417.63"


def _assert_never_echoes_amount(exc: Exception) -> None:
    assert _PLANTED_AMOUNT not in str(exc)


def test_unknown_fingerprint_is_refused_by_name(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount=f"-{_PLANTED_AMOUNT}")
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_out, "not-a-real-fingerprint")
    assert "not-a-real-fingerprint" in str(caught.value)
    _assert_never_echoes_amount(caught.value)


def test_same_account_both_legs_is_refused(two_accounts):
    checking, _card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount=f"-{_PLANTED_AMOUNT}")
    fp_in = _txn(checking, "checking", date="2026-08-02", amount=_PLANTED_AMOUNT, description="y")
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_out, fp_in)
    assert checking in str(caught.value)
    assert "different accounts" in str(caught.value)
    _assert_never_echoes_amount(caught.value)


def test_unequal_amounts_are_refused(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount=f"-{_PLANTED_AMOUNT}")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="1.23")
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_out, fp_in)
    assert "matching pair" in str(caught.value)
    _assert_never_echoes_amount(caught.value)


def test_opposite_sign_missing_is_refused(two_accounts):
    """Both legs negative — a household paying two bills, not a transfer —
    must refuse exactly as an unequal amount does, and just as silently."""
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount=f"-{_PLANTED_AMOUNT}")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount=f"-{_PLANTED_AMOUNT}")
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_out, fp_in)
    assert "matching pair" in str(caught.value)
    _assert_never_echoes_amount(caught.value)


def test_six_days_apart_is_refused_five_is_accepted(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()

    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-50.00")
    fp_in = _txn(card, "credit_card", date="2026-08-07", amount="50.00")  # 6 days
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_out, fp_in)
    assert "5 days" in str(caught.value)

    fp_out2 = _txn(checking, "checking", date="2026-09-01", amount="-60.00")
    fp_in2 = _txn(card, "credit_card", date="2026-09-06", amount="60.00")  # 5 days
    ref, replaced = transfers.pair(sidecar, fp_out2, fp_in2)
    assert ref[2] == fp_out2 and replaced is None


def test_a_fingerprint_already_paired_is_refused_without_replace(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-70.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="70.00")
    transfers.pair(sidecar, fp_out, fp_in)

    # a third transaction, equal-and-opposite with the already-paired *incoming*
    # leg, on a different label again — fp_in is already spoken for.
    accounts.add_account(sidecar, "sav-t", kind="savings", number="3333")
    fp_third = _txn("sav-t", "savings", date="2026-08-03", amount="-70.00")
    with pytest.raises(RecordExists) as caught:
        transfers.pair(sidecar, fp_third, fp_in)
    assert fp_in in str(caught.value)
    assert "--replace" in str(caught.value)

    # --replace is the explicit override
    ref, replaced = transfers.pair(sidecar, fp_third, fp_in, replace=True)
    assert ref[2] == fp_third
    assert transfers.counterpart_of(sidecar, fp_third) == fp_in


# ── suggest — proposes, never writes ────────────────────────────────────────


def test_suggest_finds_the_pair_and_writes_nothing(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-42.00", description="to card")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="42.00", description="from checking")
    # an unrelated ordinary transaction should not be proposed as anyone's pair
    _txn(checking, "checking", date="2026-08-01", amount="-9.99", description="Coffee")

    found = transfers.suggest(sidecar)
    assert found == [(fp_out, fp_in)]

    # nothing written
    assert Sidecar().records(transfers.MATTER) == []
    assert transfers.paired_fingerprints(sidecar) == frozenset()


def test_suggest_never_proposes_the_same_account_twice(two_accounts):
    checking, _card = two_accounts
    sidecar = Sidecar()
    _txn(checking, "checking", date="2026-08-01", amount="-30.00", description="a")
    _txn(checking, "checking", date="2026-08-02", amount="30.00", description="b")
    assert transfers.suggest(sidecar) == []


def test_suggest_excludes_already_paired_fingerprints(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-10.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="10.00")
    transfers.pair(sidecar, fp_out, fp_in)
    assert transfers.suggest(sidecar) == []


# ── aggregates exclude both sides ───────────────────────────────────────────


def test_recurring_detection_excludes_a_paired_transfer(two_accounts):
    """Three monthly, equal-and-opposite legs between two accounts would
    otherwise look exactly like a recurring subscription to
    `recurring.detect_recurring` (same merchant text, same amount, monthly
    gap) — pairing every occurrence must drop all of them from the pass."""
    checking, card = two_accounts
    sidecar = Sidecar()
    canonical = Canonical()
    months = ["2026-06-01", "2026-07-01", "2026-08-01"]
    for month in months:
        fp_out = _txn(checking, "checking", date=month, amount="-25.00", description="Sweep")
        card_date = month[:-2] + "02"
        fp_in = _txn(card, "credit_card", date=card_date, amount="25.00", description="Sweep")
        transfers.pair(sidecar, fp_out, fp_in)

    for label in (checking, card):
        txns = balance.transaction_tuples(canonical, label)
        txns = transfers.exclude_from(canonical, sidecar, label, txns)
        assert detect_recurring(txns, today=_date(2026, 9, 1)) == []


def test_exclude_from_leaves_unpaired_transactions_alone(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    canonical = Canonical()

    _txn(checking, "checking", date="2026-08-01", amount="-9.99", description="Coffee")
    fp_out = _txn(checking, "checking", date="2026-08-05", amount="-40.00", description="Sweep")
    fp_in = _txn(card, "credit_card", date="2026-08-06", amount="40.00", description="Sweep")
    transfers.pair(sidecar, fp_out, fp_in)

    txns = balance.transaction_tuples(canonical, checking)
    filtered = transfers.exclude_from(canonical, sidecar, checking, txns)
    assert ("2026-08-01", -9.99, "Coffee") in filtered
    assert not any(t[1] == -40.00 for t in filtered)


# ── the list annotation ─────────────────────────────────────────────────────


def test_other_label_annotates_both_legs(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-15.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="15.00")
    transfers.pair(sidecar, fp_out, fp_in)
    assert transfers.other_label(sidecar, fp_out) == card
    assert transfers.other_label(sidecar, fp_in) == checking
    # an ordinary, unpaired transaction annotates with nothing
    fp_plain = _txn(checking, "checking", date="2026-08-10", amount="-3.00", description="z")
    assert transfers.other_label(sidecar, fp_plain) is None


# ── the boundary reach: allow-listed, and scoped to exactly two rows ───────


def test_transfers_is_on_the_chokepoint_allow_list():
    from tests import test_invariants_chokepoint as chk

    assert chk.PKG / "transfers.py" in chk.ALLOWED_PAYLOAD


def test_transfers_actually_has_a_payload_reach_to_allow_list():
    """The allow-list entry above is not vacuous: the scan's own reach
    finder really does find a `.payload` access in this file."""
    from tests import test_invariants_chokepoint as chk

    tree = ast.parse((chk.PKG / "transfers.py").read_text("utf-8"))
    assert chk._payload_reaches(tree)


def test_compatible_reads_exactly_two_rows_two_fields_and_returns_no_values(
    two_accounts, monkeypatch,
):
    """`_compatible` is the one place beyond `books.py`/`balance.py` this
    package reaches `.payload` — held here to exactly what the module
    docstring promises: one `get()` per field per named row, four calls in
    all, and a return value that is only a bool and a day count."""
    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-64.10", description="a")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="64.10", description="b")

    seen: list[tuple[str, str, str]] = []
    real_get = Canonical.get

    def _spy(self, matter, item_type, item_id):
        seen.append((matter, item_type, item_id))
        return real_get(self, matter, item_type, item_id)

    monkeypatch.setattr(Canonical, "get", _spy)

    result = transfers._compatible(Canonical(), checking, fp_out, card, fp_in)

    assert result == (True, 1)
    assert isinstance(result[0], bool) and isinstance(result[1], int)
    assert sorted(seen) == sorted([
        (checking, "amount", fp_out), (checking, "date", fp_out),
        (card, "amount", fp_in), (card, "date", fp_in),
    ])
    assert len(seen) == 4, "reached more than two rows / two fields"
    # never the raw strings, anywhere in what came back
    assert "64.10" not in repr(result)


def test_compatible_returns_false_for_a_torn_row(two_accounts):
    """A row that is missing its `amount` (a torn import; `books.py`'s own
    documented limitation) is not a pairable one — refused the same way an
    incompatible pair is, and by name at the `pair()` level, not by this
    boundary function ever raising."""
    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-1.00")
    assert transfers._compatible(Canonical(), checking, fp_out, checking, "no-such-fp") == (False, 0)


# ── I-23 groundwork: nothing here iterates a hand-kept matter/account list ──


def test_pair_and_suggest_use_the_registry_for_account_labels(two_accounts):
    """`suggest()` scans `accounts.instances()`, never a list of its own —
    proof: a third, unrelated account registered after the fixture still
    gets scanned."""
    checking, card = two_accounts
    sidecar = Sidecar()
    accounts.add_account(sidecar, "sav-t", kind="savings", number="9999")
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-5.00")
    fp_in = _txn("sav-t", "savings", date="2026-08-02", amount="5.00")
    assert transfers.suggest(sidecar) == [(fp_out, fp_in)]


# ── the visible log — references only ───────────────────────────────────


def test_pair_logs_a_reference_never_an_amount(two_accounts):
    from homestead.keep.logs import VisibleLog

    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount=f"-{_PLANTED_AMOUNT}")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount=_PLANTED_AMOUNT)
    transfers.pair(sidecar, fp_out, fp_in)

    entries = VisibleLog().read()
    assert entries, "pair() logged nothing"
    last = entries[-1]
    assert last["event"] == "record_added"
    assert last["ref"] == f"{transfers.MATTER}/{fp_out}"
    assert _PLANTED_AMOUNT not in str(last)
    assert fp_in not in str(last)  # a reference to the pair, not its payload


# ── the CLI door ─────────────────────────────────────────────────────────


def test_cli_transfer_round_trip_and_the_list_annotation(two_accounts, capsys):
    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-88.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="88.00")
    capsys.readouterr()

    assert run_cli(["transaction", "transfer", fp_out, fp_in]) == 0
    out = capsys.readouterr().out
    assert "paired" in out and "88.00" not in out

    assert run_cli(["transaction", "list", "--account", checking]) == 0
    out = capsys.readouterr().out
    assert f"(transfer → {card})" in out

    # already paired, refused without --replace
    assert run_cli(["transaction", "transfer", fp_out, fp_in]) == 1
    err = capsys.readouterr().err
    assert "--replace" in err and "88.00" not in err


def test_cli_transfer_suggest_proposes_without_writing(two_accounts, capsys):
    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-12.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="12.00")
    capsys.readouterr()

    assert run_cli(["transaction", "transfer", "--suggest"]) == 0
    out = capsys.readouterr().out
    assert fp_out[:12] in out and fp_in[:12] in out
    assert transfers.paired_fingerprints(Sidecar()) == frozenset()


# ── the server door ──────────────────────────────────────────────────────


@pytest.fixture
def ui_client(tmp_path, monkeypatch):
    import http.client
    import threading

    from homestead_ledger import server as server_mod

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    srv = server_mod.build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    class _Client:
        host, port = srv.server_address[0], srv.server_address[1]

        def json(self, path, payload=None):
            conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
            if payload is None:
                conn.request("GET", path)
            else:
                conn.request("POST", path, body=json.dumps(payload),
                             headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
            return resp.status, data

    try:
        yield _Client()
    finally:
        srv.shutdown()
        srv.server_close()


def test_server_transfer_round_trip_and_suggest(ui_client, two_accounts):
    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-55.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="55.00")

    status, data = ui_client.json("/api/transaction/transfers/suggest")
    assert status == 200
    assert data["pairs"] == [{"fp_out": fp_out, "fp_in": fp_in}]

    status, data = ui_client.json(
        "/api/transaction/transfer", {"fp_out": fp_out, "fp_in": fp_in}
    )
    assert status == 200 and data["ok"] is True
    assert "55.00" not in json.dumps(data)

    status, data = ui_client.json(f"/api/transactions?account={checking}")
    by_field = {r["field"]: r for r in data["rows"]}
    assert by_field["date"]["transfer_to"] == card

    status, data = ui_client.json(
        "/api/transaction/transfer", {"fp_out": fp_out, "fp_in": fp_in}
    )
    assert status == 400 and "replace" in data["error"]
    assert "55.00" not in data["error"]
