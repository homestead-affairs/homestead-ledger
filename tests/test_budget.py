"""Bite G4-budget — per-category, per-month spending limits, and the
derived envelope state a household reads them through.

`budget.set_limit` writes `(budget, "limit", "<category>.<YYYY-MM>")`,
never a figure the books produced themselves. `packs/budget.py` is not a
discovered account or obligation pack (the same posture `packs/overlay.py`
and `packs/accounts.py` hold). `budget.envelopes` is arithmetic over the
books and the limits on file — recomputed on every call, stored nowhere —
and never leaves a spend or a limit figure on `S1_LIST`: only the derived
states and the boolean `over`.
"""
from __future__ import annotations

import ast
import http.client
import json
import re
import threading
from pathlib import Path

import pytest

from homestead.keep import paths
from homestead.keep.logs import Event
from homestead.keep.rungs import Rung
from homestead.keep.store import RecordExists

from homestead_ledger import accounts, budget, overlay, registry, server, transfers
from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.packs import budget as pack
from homestead_ledger.store import Canonical, Sidecar

PKG = Path(__file__).resolve().parent.parent / "homestead_ledger"
LABEL = "chk-b"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    return Sidecar()


def _txn(monkeypatch, tmp_path, make_account, *, date, amount, description, label=LABEL):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    sidecar = Sidecar()
    if not accounts.label_exists(sidecar, label):
        make_account("checking", label=label, number="9821")
    kind = accounts.kind_of(sidecar, label)
    return import_transaction(Transaction(
        account=label, kind=kind, date=date, amount=amount, description=description,
    ))


# ── the pack is not a discovered account or obligation kind (I-23/I-43) ────

def test_the_budget_sidecar_is_not_a_discovered_pack():
    """Mirrors `test_overlay.py`'s own guard, extended to `packs/budget.py`."""
    assert not hasattr(pack, "ACCOUNT")
    assert not hasattr(pack, "OBLIGATION")
    assert "budget" not in registry.all_accounts()
    assert "budget" not in registry.all_obligations()
    assert pack not in registry._discover_packs().values()
    assert pack not in registry._discover_obligation_packs().values()


def test_the_pack_declares_one_field_and_it_is_l4():
    """`limit` is the whole schema — the pack carried a second `note` field
    that nothing ever wrote, and a declared field with no writer is a rung
    kept true for a value that never arrives."""
    assert pack.FIELDS == {"limit": Rung.L4}
    derived = pack.SCHEMA["limit"]["derived"]
    assert derived and not any(ch.isdigit() for ch in derived)
    assert "note" not in pack.SCHEMA


# ── set_limit: shape validation, refused before anything is written ───────

@pytest.mark.parametrize("category", ["Has Spaces", "", "   ", "<img onerror=alert(1)>"])
def test_a_bad_category_is_refused_before_anything_is_written_and_never_echoed(store, category):
    with pytest.raises(ValueError) as exc:
        budget.set_limit(store, category, "2026-09", "100.00")
    if category.strip():
        assert category not in str(exc.value)
    assert list(store.records(budget.MATTER)) == []


@pytest.mark.parametrize("month", ["2026-13", "2026-00", "2026-1", "26-09", "2026/09", "", "2026-09-01"])
def test_a_bad_month_shape_is_refused(store, month):
    with pytest.raises(ValueError):
        budget.set_limit(store, "groceries", month, "100.00")
    assert list(store.records(budget.MATTER)) == []


@pytest.mark.parametrize("amount", [
    "-50", "-50.00",       # negative
    "10.999", "1.234",     # more than two decimal places
    "1e3", "1E3",          # scientific notation
    "nan", "inf", "-inf",  # non-finite
    "", "  ", "abc",       # empty or not a number
    "0", "0.00",           # not strictly positive
])
def test_bad_amounts_are_refused_before_anything_is_written(store, amount):
    with pytest.raises(ValueError):
        budget.set_limit(store, "groceries", "2026-09", amount)
    assert list(store.records(budget.MATTER)) == []


def test_a_refused_amount_is_never_echoed(store):
    with pytest.raises(ValueError) as exc:
        budget.set_limit(store, "groceries", "2026-09", "13371337.999")
    assert "13371337" not in str(exc.value)


# ── set_limit: I-9, the occupied-key refusal is the store's ───────────────

def test_set_limit_i9_replace(store):
    ref, replaced = budget.set_limit(store, "groceries", "2026-09", "100.00")
    assert replaced is None
    assert ref == ("budget", "limit", "groceries.2026-09")

    with pytest.raises(RecordExists):
        budget.set_limit(store, "groceries", "2026-09", "50.00")
    assert budget.limit_detail(store, "groceries", "2026-09") == "100.00"

    ref2, replaced2 = budget.set_limit(store, "groceries", "2026-09", "50.00", replace=True)
    assert replaced2 is not None
    assert budget.limit_detail(store, "groceries", "2026-09") == "50.00"

    # a different month for the same category needs no replace — an
    # independent key, not the same record.
    budget.set_limit(store, "groceries", "2026-10", "75.00")
    assert budget.limit_detail(store, "groceries", "2026-10") == "75.00"


def test_limits_derive_on_s1_list_and_render_on_s1_detail(store):
    budget.set_limit(store, "groceries", "2026-09", "400.00")
    on_list = budget.limits(store, "2026-09")
    assert on_list == {"groceries": pack.SCHEMA["limit"]["derived"]}
    assert "400" not in " ".join(on_list.values())
    assert budget.limit_detail(store, "groceries", "2026-09") == "400.00"
    assert budget.limit_detail(store, "dining", "2026-09") is None


# ── the visible log carries a reference only (I-15) ────────────────────────

def test_the_visible_log_never_carries_the_amount(store):
    """One line per accepted write — `RECORD_ADDED` and the reference the
    plan names, `(budget, "<category>.<month>")`. A replace logs the same
    line and no figure from either the new limit or the one it displaced; a
    refused write logs nothing at all."""
    log_path = paths.logs_dir() / "visible.jsonl"

    def lines():
        return [json.loads(line) for line in log_path.read_text("utf-8").splitlines() if line.strip()]

    budget.set_limit(store, "groceries", "2026-09", "12345.67")
    assert len(lines()) == 1

    with pytest.raises(RecordExists):
        budget.set_limit(store, "groceries", "2026-09", "76543.21")
    assert len(lines()) == 1, "a refused write logged a line"

    budget.set_limit(store, "groceries", "2026-09", "76543.21", replace=True)
    assert len(lines()) == 2

    for line in lines():
        assert line["event"] == Event.RECORD_ADDED.value
        assert line["ref"] == f"{budget.MATTER}/groceries.2026-09"
        blob = json.dumps(line)
        assert "12345" not in blob and "76543" not in blob


# ── envelopes: within / over / no-limit / no-spend, on a planted month ────

def test_envelopes_states_on_a_planted_month(tmp_path, monkeypatch, make_account):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar = Sidecar()
    canonical = Canonical()

    def spend(date, amount, description, category):
        fp = _txn(monkeypatch, tmp_path, make_account, date=date, amount=amount, description=description)
        overlay.tag(sidecar, fp, category=category)
        return fp

    spend("2026-09-05", "-30.00", "Groceries A", "groceries")   # spend 30, limit 100 -> within
    budget.set_limit(sidecar, "groceries", "2026-09", "100.00")

    spend("2026-09-06", "-60.00", "Dining A", "dining")         # spend 150 (two charges), limit
    spend("2026-09-07", "-90.00", "Dining B", "dining")         # 100 -> over
    budget.set_limit(sidecar, "dining", "2026-09", "100.00")

    spend("2026-09-08", "-40.00", "Fuel A", "fuel")             # no limit set

    budget.set_limit(sidecar, "subscription", "2026-09", "20.00")   # no spend this month

    _txn(monkeypatch, tmp_path, make_account, date="2026-09-09", amount="-12.00",
         description="Unknown vendor")   # untagged -> "needs a category" only

    spend("2026-08-05", "-500.00", "Groceries August", "groceries")   # another month, must not count

    rows, gaps = budget.envelopes(canonical, sidecar, "2026-09")
    by_category = {row.category: row for row in rows}

    assert by_category["groceries"].spent_state == budget.HAS_SPEND
    assert by_category["groceries"].limit_state == budget.LIMIT_SET
    assert by_category["groceries"].over is False   # 500 in August never joined September
    assert budget.state_text(by_category["groceries"]) == "within limit"

    assert by_category["dining"].over is True
    assert budget.state_text(by_category["dining"]) == "over limit"

    assert by_category["fuel"].limit_state == budget.NO_LIMIT
    assert budget.state_text(by_category["fuel"]) == budget.NO_LIMIT

    assert by_category["subscription"].spent_state == budget.NO_SPEND
    assert budget.state_text(by_category["subscription"]) == budget.NO_SPEND

    assert gaps == budget.Gaps(uncategorised=1, undated=0)

    blob = json.dumps([
        {"category": r.category, "spent_state": r.spent_state,
         "limit_state": r.limit_state, "over": r.over}
        for r in rows
    ])
    for digits in ("30.00", "150.00", "60.00", "90.00", "40.00", "100.00", "20.00", "500.00"):
        assert digits not in blob


def test_do_not_use_changes_over_from_true_to_false(tmp_path, monkeypatch, make_account):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    fp_small = _txn(monkeypatch, tmp_path, make_account, date="2026-09-06", amount="-60.00", description="Dining A")
    fp_big = _txn(monkeypatch, tmp_path, make_account, date="2026-09-07", amount="-90.00", description="Dining B")
    overlay.tag(sidecar, fp_small, category="dining")
    overlay.tag(sidecar, fp_big, category="dining")
    budget.set_limit(sidecar, "dining", "2026-09", "100.00")

    rows, _ = budget.envelopes(canonical, sidecar, "2026-09")
    assert {r.category: r.over for r in rows}["dining"] is True

    overlay.tag(sidecar, fp_big, do_not_use=True)
    rows, _ = budget.envelopes(canonical, sidecar, "2026-09")
    assert {r.category: r.over for r in rows}["dining"] is False


def test_a_paired_transfer_leg_never_counts_as_spend(tmp_path, monkeypatch, make_account):
    """G4-transfers' own exclusion, unioned in alongside `do_not_use`: a
    transfer's outgoing leg is not spending, even when it is tagged with a
    category (a household can tag either)."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    make_account("savings", label="sav-b", number="1234")
    sidecar, canonical = Sidecar(), Canonical()

    fp_out = _txn(monkeypatch, tmp_path, make_account, date="2026-09-05", amount="-50.00",
                  description="To savings", label=LABEL)
    fp_in = _txn(monkeypatch, tmp_path, make_account, date="2026-09-05", amount="50.00",
                 description="From checking", label="sav-b")
    overlay.tag(sidecar, fp_out, category="groceries")
    transfers.pair(sidecar, fp_out, fp_in)
    budget.set_limit(sidecar, "groceries", "2026-09", "10.00")

    rows, _ = budget.envelopes(canonical, sidecar, "2026-09")
    row = {r.category: r for r in rows}["groceries"]
    assert row.spent_state == budget.NO_SPEND
    assert row.over is False


def test_a_protected_categorys_state_still_shows_but_the_name_derives(tmp_path, monkeypatch, make_account):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    fp = _txn(monkeypatch, tmp_path, make_account, date="2026-09-10", amount="-45.00", description="Pharmacy run")
    overlay.tag(sidecar, fp, category="medical-copay")
    budget.set_limit(sidecar, "medical-copay", "2026-09", "40.00")

    rows, _ = budget.envelopes(canonical, sidecar, "2026-09")
    assert len(rows) == 1
    row = rows[0]
    # the real word never reaches this surface; the derived stand-in does —
    # the identical string overlay.tags_of gives its own protected category.
    assert row.category == "a category is on file"
    # but the envelope's own state is still the real comparison
    assert row.over is True
    assert budget.state_text(row) == "over limit"


def test_envelopes_stores_nothing(tmp_path, monkeypatch, make_account):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    fp = _txn(monkeypatch, tmp_path, make_account, date="2026-09-05", amount="-30.00", description="Groceries A")
    overlay.tag(sidecar, fp, category="groceries")
    budget.set_limit(sidecar, "groceries", "2026-09", "100.00")

    before = list(sidecar.records(budget.MATTER))
    budget.envelopes(canonical, sidecar, "2026-09")
    budget.envelopes(canonical, sidecar, "2026-09")
    assert list(sidecar.records(budget.MATTER)) == before


def test_envelopes_refuses_a_bad_month(tmp_path, monkeypatch, make_account):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    with pytest.raises(ValueError):
        budget.envelopes(Canonical(), Sidecar(), "not-a-month")


# ── the chokepoint scan, run directly against this bite's own files ───────

def test_chokepoint_scan_is_clean_on_the_budget_module():
    """`budget.py`/`packs/budget.py` reach no `.payload` and name no
    `CANONICAL` — the I-16/"mirror, not judge" guard, run directly against
    this bite's own files rather than only inferred from
    `tests/test_invariants_chokepoint.py` staying green."""
    for relative in ("budget.py", "packs/budget.py"):
        tree = ast.parse((PKG / relative).read_text("utf-8"))
        payload_hits = [n.lineno for n in ast.walk(tree)
                        if isinstance(n, ast.Attribute) and n.attr == "payload"]
        canonical_hits = [n.lineno for n in ast.walk(tree)
                          if (isinstance(n, ast.Name) and n.id == "CANONICAL")
                          or (isinstance(n, ast.Attribute) and n.attr == "CANONICAL")]
        assert not payload_hits, f"{relative} reaches .payload at {payload_hits}"
        assert not canonical_hits, f"{relative} names CANONICAL at {canonical_hits}"


def test_smoke_imports_budget_and_its_pack(tmp_path, monkeypatch):
    import sys

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead_ledger.__main__ import main

    assert main(["--smoke"]) == 0
    assert "homestead_ledger.budget" in sys.modules
    assert "homestead_ledger.packs.budget" in sys.modules


# ── the server: POST /api/budget/limit, GET /api/budget ────────────────────

@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    srv = server.build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address

    def call(method, path, payload=None):
        conn = http.client.HTTPConnection(host, port, timeout=5)
        if payload is None:
            conn.request(method, path)
        else:
            conn.request(method, path, body=json.dumps(payload),
                         headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        if method == "GET" and path == "/":
            return resp.status, body.decode()
        return resp.status, json.loads(body)

    try:
        yield call
    finally:
        srv.shutdown()
        srv.server_close()


def _seed_transaction(ui, *, amount="-30.00"):
    """One tagged `groceries` transaction on a fresh `chk-b`. Returns its
    fingerprint — the shared setup every server test below builds on."""
    ui("POST", "/api/account", {"label": "chk-b", "kind": "checking", "number": "9821"})
    status, data = ui("POST", "/api/transaction", {
        "date": "2026-09-05", "amount": amount, "description": "Groceries run", "account": "chk-b",
    })
    assert status == 200
    ui("POST", "/api/transaction/tag", {"fingerprint": data["id"], "category": "groceries"})
    return data["id"]


def test_budget_limit_round_trip_through_the_gate(ui):
    status, page = ui("GET", "/")
    assert status == 200 and "/api/budget" in page
    for field in ("bcategory", "bmonth", "bamount", "bviewmonth"):
        assert f'id="{field}"' in page
    # the empty month says so once, instead of a bare "needs a category: 0"
    assert "No limits and no spending on file yet." in page

    _seed_transaction(ui)
    status, data = ui("POST", "/api/budget/limit", {
        "category": "groceries", "month": "2026-09", "amount": "100.00",
    })
    assert status == 200 and data == {"ok": True, "category": "groceries", "month": "2026-09", "replaced": False}

    status, data = ui("GET", "/api/budget?month=2026-09")
    assert status == 200
    assert data["envelopes"] == [{
        "category": "groceries", "spent_state": budget.HAS_SPEND,
        "limit_state": budget.LIMIT_SET, "over": False, "state": "within limit",
    }]
    assert data["uncategorised"] == 0

    status, data = ui("POST", "/api/budget/limit", {
        "category": "groceries", "month": "2026-09", "amount": "1.00",
    })
    assert status == 400 and "replace" in data["error"]
    status, data = ui("POST", "/api/budget/limit", {
        "category": "groceries", "month": "2026-09", "amount": "1.00", "replace": True,
    })
    assert data["replaced"] is True


def test_api_budget_never_carries_a_planted_digit_run(ui):
    _seed_transaction(ui)
    planted = "133713370"
    status, data = ui("POST", "/api/budget/limit", {
        "category": "groceries", "month": "2026-09", "amount": f"{planted}.00",
    })
    assert status == 200

    status, data = ui("GET", "/api/budget?month=2026-09")
    assert status == 200
    blob = json.dumps(data)
    assert not any(run == planted for run in re.findall(r"\d+", blob))
    assert "30.00" not in blob


def test_budget_limit_refusals_never_echo_the_amount_or_category(ui):
    for body in (
        {"category": "<img onerror=alert(1)>", "month": "2026-09", "amount": "10"},
        {"category": "groceries", "month": "2026-13", "amount": "10"},
        {"category": "", "month": "2026-09", "amount": "10"},
        {"category": "groceries", "month": "2026-09", "amount": "13371337.999"},
        {"category": "groceries", "month": "2026-09", "amount": "-50"},
    ):
        status, data = ui("POST", "/api/budget/limit", body)
        assert status == 400 and data["ok"] is False, body
        assert "13371337" not in json.dumps(data)
        assert "<img" not in json.dumps(data)

    status, data = ui("GET", "/api/budget?month=not-a-month")
    assert status == 400


# ── the refund rule: a month's spend is net of what came back ─────────────

def test_a_refund_nets_against_the_months_spend(tmp_path, monkeypatch, make_account):
    """An inflow on a *categorised* row is a refund, and a refund is not
    spending — it is spending undone. Counting only outflows made the
    envelope answer a question nobody asked: a 120.00 purchase with a 40.00
    refund against a 100.00 limit read "over limit" while the household was
    20.00 under it. The state flips back the moment the money returns."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    bought = _txn(monkeypatch, tmp_path, make_account, date="2026-09-05", amount="-120.00",
                  description="Grocery haul")
    overlay.tag(sidecar, bought, category="groceries")
    budget.set_limit(sidecar, "groceries", "2026-09", "100.00")

    rows, _gaps = budget.envelopes(canonical, sidecar, "2026-09")
    assert {r.category: r for r in rows}["groceries"].over is True

    returned = _txn(monkeypatch, tmp_path, make_account, date="2026-09-09", amount="40.00",
                    description="Grocery return")
    overlay.tag(sidecar, returned, category="groceries")

    rows, gaps = budget.envelopes(canonical, sidecar, "2026-09")
    row = {r.category: r for r in rows}["groceries"]
    assert row.over is False
    assert row.spent_state == budget.HAS_SPEND
    assert budget.state_text(row) == "within limit"
    assert gaps == budget.Gaps(uncategorised=0, undated=0)


def test_a_refund_that_covers_the_whole_month_leaves_no_spend(tmp_path, monkeypatch, make_account):
    """Net zero or less is "no spend" — the category is square for the
    month, and no figure says by how much."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    bought = _txn(monkeypatch, tmp_path, make_account, date="2026-09-05", amount="-60.00",
                  description="Dining out")
    refund = _txn(monkeypatch, tmp_path, make_account, date="2026-09-06", amount="60.00",
                  description="Dining refunded")
    overlay.tag(sidecar, bought, category="dining")
    overlay.tag(sidecar, refund, category="dining")
    budget.set_limit(sidecar, "dining", "2026-09", "10.00")

    rows, _gaps = budget.envelopes(canonical, sidecar, "2026-09")
    row = {r.category: r for r in rows}["dining"]
    assert row.spent_state == budget.NO_SPEND
    assert row.over is False
    assert budget.state_text(row) == budget.NO_SPEND


def test_an_inflow_alone_makes_no_envelope_and_an_untagged_one_is_no_gap(tmp_path, monkeypatch, make_account):
    """A paycheck is not a negative grocery bill. An untagged inflow is
    ignored outright — not counted as a category gap — and a *tagged*
    inflow in a category with no outflow of its own this month creates no
    envelope: a refund alone is not spending."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    _txn(monkeypatch, tmp_path, make_account, date="2026-09-01", amount="250.00",
         description="Employer payroll")
    lonely = _txn(monkeypatch, tmp_path, make_account, date="2026-09-02", amount="15.00",
                  description="Late refund for August")
    overlay.tag(sidecar, lonely, category="groceries")

    rows, gaps = budget.envelopes(canonical, sidecar, "2026-09")
    assert rows == []
    assert gaps == budget.Gaps(uncategorised=0, undated=0)


# ── month arithmetic: the boundary days, and a date no calendar can read ──

def test_the_last_day_counts_and_the_first_of_the_next_month_does_not(tmp_path, monkeypatch, make_account):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    last = _txn(monkeypatch, tmp_path, make_account, date="2026-09-30", amount="-80.00",
                description="Last day of September")
    first = _txn(monkeypatch, tmp_path, make_account, date="2026-10-01", amount="-80.00",
                 description="First of October")
    overlay.tag(sidecar, last, category="groceries")
    overlay.tag(sidecar, first, category="groceries")
    budget.set_limit(sidecar, "groceries", "2026-09", "100.00")
    budget.set_limit(sidecar, "groceries", "2026-10", "100.00")

    september = {r.category: r for r in budget.envelopes(canonical, sidecar, "2026-09")[0]}
    october = {r.category: r for r in budget.envelopes(canonical, sidecar, "2026-10")[0]}
    # one charge each side of midnight, each under its own month's limit
    assert september["groceries"].spent_state == budget.HAS_SPEND
    assert september["groceries"].over is False
    assert october["groceries"].spent_state == budget.HAS_SPEND
    # and both together would have been over either limit
    assert budget.state_text(september["groceries"]) == "within limit"


def test_a_row_whose_date_is_not_iso_joins_no_month_and_is_counted(tmp_path, monkeypatch, make_account):
    """`importer.py` writes ISO, but a row imported before that fix carries
    a slashed statement date, and `balance.dated_transactions` hands back
    what is stored. Such a row cannot be placed on a calendar: it joins no
    month's arithmetic (its 500.00 never reaches the comparison), it does
    not crash the month, and it is not silently dropped either — it shows
    as "needs a date", by count (I-11)."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    legacy = _txn(monkeypatch, tmp_path, make_account, date="09/15/2026", amount="-500.00",
                  description="Pre-ISO row")
    overlay.tag(sidecar, legacy, category="groceries")
    real = _txn(monkeypatch, tmp_path, make_account, date="2026-09-05", amount="-10.00",
                description="A real September charge")
    overlay.tag(sidecar, real, category="groceries")
    budget.set_limit(sidecar, "groceries", "2026-09", "100.00")

    rows, gaps = budget.envelopes(canonical, sidecar, "2026-09")
    row = {r.category: r for r in rows}["groceries"]
    assert row.over is False            # the 500.00 joined nothing
    assert gaps.undated == 1
    assert gaps.uncategorised == 0
    # and it is not quietly folded into the next month either
    assert budget.envelopes(canonical, sidecar, "2026-10")[1].undated == 1

    # a `do_not_use` row is excluded before the date is ever read — an
    # excluded row is not a gap waiting on a hand.
    overlay.tag(sidecar, legacy, do_not_use=True)
    assert budget.envelopes(canonical, sidecar, "2026-09")[1].undated == 0


def test_whitespace_around_a_category_month_and_amount_is_stripped(store):
    """The ruling, pinned: surrounding whitespace is stripped, not refused —
    `overlay._category`'s own posture for the identical field, so a pasted
    value behaves the same at both doors."""
    ref, _replaced = budget.set_limit(store, " groceries ", " 2026-09 ", " 12.00 ")
    assert ref == ("budget", "limit", "groceries.2026-09")
    assert budget.limit_detail(store, "groceries", "2026-09") == "12.00"
    # inner whitespace is still a bad shape
    with pytest.raises(ValueError):
        budget.set_limit(store, "groceries", "2026-09", "1 2.00")


# ── one category validator, not two ───────────────────────────────────────

#: The character class `overlay._CATEGORY_RE` is spelled with. A second copy
#: of it anywhere else is a rule that can drift from the one that is enforced,
#: which is the same finding this sweep recorded about the protected-category
#: word list — one copy, re-exported, never restated.
_CATEGORY_SHAPE = "a-z0-9-"


def _holds_a_second_category_shape(module: Path) -> bool:
    """True if `module`'s source spells the category character class itself
    rather than calling `overlay._category`."""
    return _CATEGORY_SHAPE in module.read_text("utf-8")


def test_the_second_copy_guard_fires_on_a_planted_regex(tmp_path):
    """A scan that has never fired has not been shown to check anything. The
    guard above reads `budget.py` and finds nothing, which is what a guard
    reading the wrong path would also find. Planted: a module that does spell
    the class out, in the shape a hand-rolled copy would take."""
    planted = tmp_path / "budget.py"
    planted.write_text(
        (PKG / "budget.py").read_text("utf-8")
        + '\n\n_PLANTED_CATEGORY_RE = re.compile(r"^[a-z0-9-]{1,40}$")\n',
        encoding="utf-8",
    )
    assert _holds_a_second_category_shape(planted), "the plant did not apply"
    assert not _holds_a_second_category_shape(PKG / "budget.py")


@pytest.mark.parametrize("candidate", [
    "groceries", "medical-copay", "a", "a" * 40, "a" * 41, "Groceries", "9lives",
    "with space", "", "  ", "dash-", "-dash", "under_score", "a.b",
])
def test_the_category_rule_is_overlays_own_not_a_second_copy(candidate):
    """`budget` and `overlay` must not be able to drift: the shape is
    `overlay._category` itself, called, and this module holds no regex of
    its own to fall out of step with it."""
    def result(fn):
        try:
            return fn(candidate)
        except ValueError:
            return "refused"

    assert result(budget._category) == result(overlay._category)
    assert not _holds_a_second_category_shape(PKG / "budget.py"), (
        "budget.py carries a second copy of the category shape"
    )


# ── I-23: the discovery attribute is what keeps this pack out (planted) ────

def test_the_registry_would_find_this_pack_if_it_declared_one(monkeypatch):
    """The absence asserted above is only load-bearing if `ACCOUNT`/
    `OBLIGATION` is what the scan actually reads — the same plant
    `tests/test_overlay.py` makes for its own sidecar pack."""
    monkeypatch.setattr(pack, "ACCOUNT", "budget", raising=False)
    assert registry._discover_packs().get("budget") is pack
    monkeypatch.delattr(pack, "ACCOUNT")

    monkeypatch.setattr(pack, "OBLIGATION", "budget", raising=False)
    assert registry._discover_obligation_packs().get("budget") is pack
    monkeypatch.delattr(pack, "OBLIGATION")

    assert "budget" not in registry._discover_packs()
    assert "budget" not in registry._discover_obligation_packs()


# ── the server: what `replace` accepts, and what a missing month does ──────

def test_replace_is_json_true_and_nothing_else(ui):
    _seed_transaction(ui)
    ok = {"category": "groceries", "month": "2026-09", "amount": "100.00"}
    assert ui("POST", "/api/budget/limit", ok)[0] == 200
    for impostor in ("yes", "true", 1, ["true"], {"replace": True}):
        body = dict(ok, amount="1.00", replace=impostor)
        status, data = ui("POST", "/api/budget/limit", body)
        assert status == 400 and "replace" in data["error"], impostor
    status, data = ui("POST", "/api/budget/limit", dict(ok, amount="1.00", replace=True))
    assert status == 200 and data["replaced"] is True


def test_the_server_never_defaults_a_month_and_reports_both_gaps(ui):
    _seed_transaction(ui)
    for path in ("/api/budget", "/api/budget?month=", "/api/budget?month=2026-1"):
        status, data = ui("GET", path)
        assert status == 400 and "YYYY-MM" in data["error"], path

    status, data = ui("GET", "/api/budget?month=2026-09")
    assert status == 200
    assert data["uncategorised"] == 0 and data["undated"] == 0


def test_a_budget_tab_load_writes_nothing_to_either_store(ui):
    """Item 7: a Budget tab load is a read. Sidecar and canonical row counts
    are identical before and after, and the visible log gains no line."""
    _seed_transaction(ui)
    assert ui("POST", "/api/budget/limit",
              {"category": "groceries", "month": "2026-09", "amount": "100.00"})[0] == 200

    sidecar, canonical = Sidecar(), Canonical()
    log = paths.logs_dir() / "visible.jsonl"
    before = (
        sorted(str(r) for r, _ in sidecar.records(budget.MATTER)),
        sorted(str(r) for r, _ in sidecar.records(overlay.MATTER)),
        sorted(str(r) for r, _ in canonical.records("chk-b")),
        log.read_text("utf-8"),
    )
    for _ in range(3):
        assert ui("GET", "/api/budget?month=2026-09")[0] == 200
    after = (
        sorted(str(r) for r, _ in sidecar.records(budget.MATTER)),
        sorted(str(r) for r, _ in sidecar.records(overlay.MATTER)),
        sorted(str(r) for r, _ in canonical.records("chk-b")),
        log.read_text("utf-8"),
    )
    assert before == after
