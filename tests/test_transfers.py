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

    # --replace is the explicit override, and it retires the *old* pairing
    # rather than leaving fp_in claimed by two pairs at once.
    ref, replaced = transfers.pair(sidecar, fp_third, fp_in, replace=True)
    assert ref[2] == fp_third
    assert replaced is not None, "replacing displaced a pairing and did not say so"
    assert transfers.counterpart_of(sidecar, fp_third) == fp_in
    assert transfers.counterpart_of(sidecar, fp_in) == fp_third
    assert transfers.other_label(sidecar, fp_in) == "sav-t"
    assert fp_out not in transfers.paired_fingerprints(sidecar), (
        "the replaced pairing's old outgoing leg is still paired — a --replace "
        "that leaves the old pair on file makes counterpart_of answer by dict order"
    )
    assert transfers.paired_fingerprints(sidecar) == frozenset({fp_third, fp_in})
    assert transfers.counterpart_of(sidecar, fp_out) is None
    assert transfers.other_label(sidecar, fp_out) is None


# ── suggest — proposes, never writes ────────────────────────────────────────


def test_suggest_finds_the_pair_and_writes_nothing(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-42.00", description="to card")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="42.00", description="from checking")
    # an unrelated ordinary transaction should not be proposed as anyone's pair
    _txn(checking, "checking", date="2026-08-01", amount="-9.99", description="Coffee")

    found = transfers.suggest(sidecar)
    assert found == [transfers.Suggestion(fp_out, fp_in, False)]

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


def test_the_boundary_file_is_the_allow_list_entry_and_transfers_is_not():
    """The chokepoint admits the smallest unit. `transfers_boundary.py` is
    three reads and no policy; `transfers.py` — every refusal, every reader,
    everything either grows into — is held by the scan like any surface."""
    from tests import test_invariants_chokepoint as chk

    assert chk.PKG / "transfers_boundary.py" in chk.ALLOWED_PAYLOAD
    assert chk.PKG / "transfers.py" not in chk.ALLOWED_PAYLOAD


def test_the_boundary_entry_is_not_vacuous_and_transfers_reaches_nothing():
    """Two halves of the same claim: the allow-listed file really does hold a
    `.payload` reach the scan can see (so the entry means something), and the
    module beside it holds none (so the narrowing is real and not a comment)."""
    from tests import test_invariants_chokepoint as chk

    boundary_tree = ast.parse((chk.PKG / "transfers_boundary.py").read_text("utf-8"))
    assert chk._payload_reaches(boundary_tree)
    transfers_tree = ast.parse((chk.PKG / "transfers.py").read_text("utf-8"))
    assert chk._payload_reaches(transfers_tree) == []
    assert chk._reflection_reaches(transfers_tree) == []


def test_the_boundary_file_is_exactly_three_reads_and_no_policy():
    """A file on the allow-list grows by accident unless something holds it
    shut. Every `.payload` in it sits inside one of the three named reads,
    and nothing else public lives there — a fourth function, or the pairing
    logic drifting in, fails here before it is allow-listed by inheritance."""
    from tests import test_invariants_chokepoint as chk

    from homestead_ledger import transfers_boundary as tb

    source = (chk.PKG / "transfers_boundary.py").read_text("utf-8")
    tree = ast.parse(source)
    readers = {"compatibility", "signed_rows", "content_rows"}
    assert set(tb.__all__) - {"Compatibility", "SignedRow"} == readers
    top_level_defs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert top_level_defs == readers | {"_amount_of", "_day_of"}
    reaches = set(chk._payload_reaches(tree))
    assert reaches, "the allow-list entry would be vacuous"
    inside = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in readers:
            inside |= set(chk._payload_reaches(node))
    assert reaches == inside, "a payload is reached outside the three named reads"
    # no policy: the window and the pack's matter belong to transfers.py.
    # Read as code, not as text — the docstring may (and does) explain them.
    named = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert not named & {"WINDOW_DAYS", "MATTER", "FIELDS", "Sidecar"}


def test_compatibility_reads_exactly_two_rows_two_fields_and_returns_no_values(
    two_accounts, monkeypatch,
):
    """`compatibility` is the one place beyond `books.py`/`balance.py` this
    package reaches `.payload` for a pairing — held here to exactly what the
    module docstring promises: one `get()` per field per named row, four
    calls in all, and a return value that is only booleans and a day count."""
    from homestead_ledger import transfers_boundary as tb

    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-64.10", description="a")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="64.10", description="b")

    seen: list[tuple[str, str, str]] = []
    real_get = Canonical.get

    def _spy(self, matter, item_type, item_id):
        seen.append((matter, item_type, item_id))
        return real_get(self, matter, item_type, item_id)

    monkeypatch.setattr(Canonical, "get", _spy)

    result = tb.compatibility(Canonical(), checking, fp_out, card, fp_in)

    assert result == tb.Compatibility(
        readable=True, equal_and_opposite=True, outgoing_first=True, days_apart=1,
    )
    assert sorted(seen) == sorted([
        (checking, "amount", fp_out), (checking, "date", fp_out),
        (card, "amount", fp_in), (card, "date", fp_in),
    ])
    assert len(seen) == 4, "reached more than two rows / two fields"
    # never the raw strings, anywhere in what came back
    assert "64.10" not in repr(result)


def test_compatibility_returns_unreadable_for_a_torn_row(two_accounts):
    """A row that is missing its `amount` (a torn import; `books.py`'s own
    documented limitation) is not a pairable one — reported as unreadable and
    refused by name at the `pair()` level, never by this boundary function
    raising."""
    from homestead_ledger import transfers_boundary as tb

    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-1.00")
    fit = tb.compatibility(Canonical(), checking, fp_out, checking, "no-such-fp")
    assert fit.readable is False and fit.days_apart is None


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
    assert transfers.suggest(sidecar) == [transfers.Suggestion(fp_out, fp_in, False)]


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
    assert data["pairs"] == [{"fp_out": fp_out, "fp_in": fp_in, "ambiguous": False}]

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


# ── the pair says what happened: the first fingerprint is the outgoing leg ──


def test_the_incoming_leg_first_is_refused_rather_than_swapped(two_accounts):
    """`pair(fp_out, fp_in)` with the two the other way round would write a
    record whose `from` names the account the money *arrived* in — true of
    nothing. Refused by name, and not quietly normalized: the operator asked
    for something that is not so, and silently reinterpreting it teaches them
    nothing about which way the record reads."""
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount=f"-{_PLANTED_AMOUNT}")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount=_PLANTED_AMOUNT)

    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_in, fp_out)          # swapped
    assert "outgoing" in str(caught.value)
    assert fp_in in str(caught.value)
    _assert_never_echoes_amount(caught.value)
    assert Sidecar().records(transfers.MATTER) == [], "a refusal wrote a record"

    # and the right way round still works
    ref, _ = transfers.pair(sidecar, fp_out, fp_in)
    assert ref[2] == fp_out
    assert transfers.other_label(sidecar, fp_out) == card


def test_the_same_fingerprint_twice_is_refused(two_accounts):
    """One row is not two legs. It is caught by the two-different-accounts
    rule — a fingerprint is on exactly one account — and pinned here so the
    case cannot quietly become allowed."""
    checking, _card = two_accounts
    sidecar = Sidecar()
    fp = _txn(checking, "checking", date="2026-08-01", amount="-20.00")
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp, fp)
    assert "different accounts" in str(caught.value)
    assert transfers.paired_fingerprints(sidecar) == frozenset()


# ── --replace retires the old pairing entirely ─────────────────────────────


def test_an_incoming_leg_can_never_become_an_outgoing_one(two_accounts):
    """Why there is no third clash case to retire. A counterpart is always
    the *incoming* leg, so it is always a positive amount, and the outgoing
    check refuses it as a first fingerprint before any occupied-key question
    arises: one fingerprint can never be an inflow in one record and an
    outflow in another."""
    checking, card = two_accounts
    sidecar = Sidecar()
    accounts.add_account(sidecar, "sav-t", kind="savings", number="4444")
    fp_a = _txn(checking, "checking", date="2026-08-01", amount="-30.00")
    fp_b = _txn(card, "credit_card", date="2026-08-02", amount="30.00")
    transfers.pair(sidecar, fp_a, fp_b)

    fp_d = _txn("sav-t", "savings", date="2026-08-04", amount="-30.00")
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_b, fp_d)
    assert "outgoing" in str(caught.value)
    # and with --replace, which skips the occupied-key precondition entirely
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_b, fp_d, replace=True)
    assert "outgoing" in str(caught.value)
    assert transfers.paired_fingerprints(sidecar) == frozenset({fp_a, fp_b})


def test_a_retired_key_is_free_to_pair_again_without_replace(two_accounts):
    """A retired record still occupies its key (the store has no delete), so
    re-pairing that outgoing leg must not be refused as an occupied key — the
    key names no pairing any more."""
    checking, card = two_accounts
    sidecar = Sidecar()
    accounts.add_account(sidecar, "sav-t", kind="savings", number="5555")
    fp_a = _txn(checking, "checking", date="2026-08-01", amount="-30.00")
    fp_b = _txn(card, "credit_card", date="2026-08-02", amount="30.00")
    fp_c = _txn("sav-t", "savings", date="2026-08-03", amount="-30.00")
    transfers.pair(sidecar, fp_a, fp_b)
    transfers.pair(sidecar, fp_c, fp_b, replace=True)   # retires fp_a's pairing
    assert fp_a not in transfers.paired_fingerprints(sidecar)

    fp_d = _txn(card, "credit_card", date="2026-08-04", amount="30.00", description="another")
    ref, _ = transfers.pair(sidecar, fp_a, fp_d)        # no --replace needed
    assert ref[2] == fp_a
    assert transfers.counterpart_of(sidecar, fp_a) == fp_d


# ── exclusion is one row per paired fingerprint, not every row like it ─────


def test_exclude_from_drops_one_row_per_paired_fingerprint(two_accounts):
    """A genuine duplicate purchase. `-100.00` and `-100.0` are two different
    transactions (different fingerprints — the fingerprint is over the exact
    strings), and `transaction_tuples` reads both as the same `(date, amount,
    description)` triple. Pairing one of them must drop one row, not both:
    dropping both hides a real charge from the recurring detector."""
    checking, card = two_accounts
    sidecar = Sidecar()
    canonical = Canonical()
    fp_a = _txn(checking, "checking", date="2026-08-01", amount="-100.00", description="Hardware")
    fp_b = _txn(checking, "checking", date="2026-08-01", amount="-100.0", description="Hardware")
    assert fp_a != fp_b, "the two rows are one transaction; the case does not exist"
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="100.00", description="Hardware")
    transfers.pair(sidecar, fp_a, fp_in)

    before = balance.transaction_tuples(canonical, checking)
    assert len(before) == 2
    after = transfers.exclude_from(canonical, sidecar, checking, before)
    assert after == [("2026-08-01", -100.0, "Hardware")], (
        "the unpaired duplicate was dropped with the paired one — a real "
        "charge that never reaches the recurring pass"
    )


# ── corruption refuses by name; it never crashes a door ────────────────────


def _plant_null_amount(label: str, fp: str) -> None:
    """A `null` payload — the corruption shape `balance.py`'s own sort key
    documents — written straight past the classified path."""
    from homestead.keep.store import CANONICAL, key as _key

    from homestead_ledger.store import _adapter

    _adapter().write(CANONICAL, _key(label, "amount", fp),
                     json.dumps({"rung": "L4", "payload": None, "derived": "on file"}))


def test_a_corrupt_amount_refuses_by_name_and_never_raises_typeerror(two_accounts):
    """`Decimal(None)` raises `TypeError`, which is a traceback on the
    terminal and a 500 in the browser. I-11: corruption is refused by name."""
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-5.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="5.00")
    _plant_null_amount(card, fp_in)

    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_out, fp_in)
    assert "readable" in str(caught.value)
    assert fp_in in str(caught.value)
    # and the same corruption does not take the whole suggest pass down
    assert transfers.suggest(sidecar) == []


def test_an_unparseable_date_refuses_by_name_not_by_a_day_count(two_accounts):
    """A pre-ISO row (`transaction list --gaps`) used to come back as "post
    1000000 day(s) apart" — a sentinel read out loud as though it were a
    fact about the household's books."""
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="08/01/2026", amount="-5.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="5.00")
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_out, fp_in)
    assert "--gaps" in str(caught.value)
    assert "1000000" not in str(caught.value)


def test_amounts_compare_as_decimals_not_floats(two_accounts):
    """Two legs one cent apart, at a magnitude binary floating point cannot
    resolve: `float(a) + float(b) == 0.0` is true and they are still not a
    matching pair. The exact reading (`money.decimal_amount`) is what makes
    the refusal right."""
    checking, card = two_accounts
    sidecar = Sidecar()
    out_amount, in_amount = "-99999999999999999.02", "99999999999999999.01"
    assert float(out_amount) + float(in_amount) == 0.0, "the float trap is not set"
    fp_out = _txn(checking, "checking", date="2026-08-01", amount=out_amount)
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount=in_amount)
    with pytest.raises(ValueError) as caught:
        transfers.pair(sidecar, fp_out, fp_in)
    assert "matching pair" in str(caught.value)


# ── suggest reports ambiguity; it never resolves one ───────────────────────


def test_suggest_lists_every_candidate_of_an_ambiguous_match_and_marks_it(two_accounts):
    """One `-40.00` outflow, two `+40.00` inflows on two other accounts the
    next day. Picking one would be wrong half the time and silently wrong
    every time."""
    checking, card = two_accounts
    sidecar = Sidecar()
    accounts.add_account(sidecar, "sav-t", kind="savings", number="6666")
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-40.00", description="sweep")
    fp_card = _txn(card, "credit_card", date="2026-08-02", amount="40.00", description="a")
    fp_sav = _txn("sav-t", "savings", date="2026-08-02", amount="40.00", description="b")

    found = transfers.suggest(sidecar)
    assert {(s.fp_out, s.fp_in) for s in found} == {(fp_out, fp_card), (fp_out, fp_sav)}
    assert all(s.ambiguous for s in found), "an ambiguous match was proposed as settled"
    assert transfers.paired_fingerprints(sidecar) == frozenset(), "suggest wrote something"


def test_suggest_marks_two_outflows_competing_for_one_inflow(two_accounts):
    """The mirror case: one inflow that two outflows both fit. Neither is the
    obvious answer, so neither is proposed as one."""
    checking, card = two_accounts
    sidecar = Sidecar()
    accounts.add_account(sidecar, "sav-t", kind="savings", number="7777")
    fp_a = _txn(checking, "checking", date="2026-08-01", amount="-40.00", description="a")
    fp_b = _txn("sav-t", "savings", date="2026-08-01", amount="-40.00", description="b")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="40.00")

    found = transfers.suggest(sidecar)
    assert {(s.fp_out, s.fp_in) for s in found} == {(fp_a, fp_in), (fp_b, fp_in)}
    assert all(s.ambiguous for s in found)


# ── I-15: a planted amount and description reach no surface ────────────────


def test_no_surface_of_this_feature_echoes_an_amount_or_a_payee(two_accounts, capsys):
    """One sweep with a distinctive amount and a distinctive description,
    paired, then every door this bite opens is read back: the visible log,
    the CLI list annotation, the CLI suggest output and the server's JSON.
    The annotation names the *other account's label* and nothing else."""
    from homestead.keep.logs import VisibleLog

    checking, card = two_accounts
    sidecar = Sidecar()
    payee = "ZZQPLANTEDPAYEE"
    fp_out = _txn(checking, "checking", date="2026-08-01",
                  amount=f"-{_PLANTED_AMOUNT}", description=payee)
    fp_in = _txn(card, "credit_card", date="2026-08-02",
                 amount=_PLANTED_AMOUNT, description=payee)
    transfers.pair(sidecar, fp_out, fp_in)
    capsys.readouterr()

    seen = str(VisibleLog().read())
    assert run_cli(["transaction", "transfer", "--suggest"]) == 0
    assert run_cli(["transaction", "list", "--account", checking]) == 0
    captured = capsys.readouterr()
    annotation = captured.out
    assert f"(transfer → {card})" in annotation
    for text, where in ((seen, "the visible log"), (annotation, "the CLI")):
        assert _PLANTED_AMOUNT not in text, f"{where} echoed the amount"
    # the description is L4 and derives on the list; the *counterpart's* one
    # never crosses at all, on either side of the pair.
    assert payee not in seen
    assert fp_in not in seen


def test_the_annotation_names_a_label_never_the_counterpart_fingerprint(two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-15.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="15.00")
    transfers.pair(sidecar, fp_out, fp_in)
    assert transfers.other_label(sidecar, fp_out) == card
    assert transfers.other_label(sidecar, fp_out) != fp_in


# ── the doors carry the ambiguity and refuse an unhonoured flag ────────────


def test_cli_suggest_marks_an_ambiguous_candidate(two_accounts, capsys):
    checking, card = two_accounts
    sidecar = Sidecar()
    accounts.add_account(sidecar, "sav-t", kind="savings", number="8888")
    _txn(checking, "checking", date="2026-08-01", amount="-40.00", description="sweep")
    _txn(card, "credit_card", date="2026-08-02", amount="40.00", description="a")
    _txn("sav-t", "savings", date="2026-08-02", amount="40.00", description="b")
    capsys.readouterr()

    assert run_cli(["transaction", "transfer", "--suggest"]) == 0
    out = capsys.readouterr().out
    assert out.count("ambiguous") == 2
    assert "40.00" not in out


def test_cli_suggest_refuses_an_argument_it_would_not_honour(two_accounts, capsys):
    """`--suggest` proposes over the whole books. A fingerprint beside it
    describes a write this branch does not do; accepting and ignoring it
    reads as though it had been honoured."""
    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-11.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="11.00")
    capsys.readouterr()

    assert run_cli(["transaction", "transfer", "--suggest", fp_out, fp_in]) == 2
    assert "--suggest takes no other argument" in capsys.readouterr().err
    assert transfers.paired_fingerprints(Sidecar()) == frozenset()


def test_server_suggest_says_when_a_candidate_is_ambiguous(ui_client, two_accounts):
    checking, card = two_accounts
    sidecar = Sidecar()
    accounts.add_account(sidecar, "sav-t", kind="savings", number="9191")
    _txn(checking, "checking", date="2026-08-01", amount="-40.00", description="sweep")
    _txn(card, "credit_card", date="2026-08-02", amount="40.00", description="a")
    _txn("sav-t", "savings", date="2026-08-02", amount="40.00", description="b")

    status, data = ui_client.json("/api/transaction/transfers/suggest")
    assert status == 200
    assert len(data["pairs"]) == 2
    assert all(p["ambiguous"] is True for p in data["pairs"])
    assert "40.00" not in json.dumps(data), "an amount crossed the suggest door"


def test_server_refuses_a_swapped_pair_and_a_corrupt_row_without_a_500(
    ui_client, two_accounts,
):
    checking, card = two_accounts
    fp_out = _txn(checking, "checking", date="2026-08-01", amount="-55.00")
    fp_in = _txn(card, "credit_card", date="2026-08-02", amount="55.00")

    status, data = ui_client.json(
        "/api/transaction/transfer", {"fp_out": fp_in, "fp_in": fp_out}
    )
    assert status == 400 and data["ok"] is False
    assert "outgoing" in data["error"]
    assert "55.00" not in json.dumps(data)

    _plant_null_amount(card, fp_in)
    status, data = ui_client.json(
        "/api/transaction/transfer", {"fp_out": fp_out, "fp_in": fp_in}
    )
    assert status == 400, "a corrupt row answered with a 500, not a refusal"
    assert "readable" in data["error"]
