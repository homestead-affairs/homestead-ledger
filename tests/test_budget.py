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

from homestead_ledger import accounts, budget, overlay, registry, server
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
    if not accounts.label_exists(Sidecar(), label):
        make_account("checking", label=label, number="9821")
    return import_transaction(Transaction(
        account=label, kind="checking", date=date, amount=amount, description=description,
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


def test_the_pack_classifies_at_import_and_both_fields_are_l4():
    assert pack.FIELDS == {"limit": Rung.L4, "note": Rung.L4}
    for name in ("limit", "note"):
        derived = pack.SCHEMA[name]["derived"]
        assert derived and not any(ch.isdigit() for ch in derived)


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
    budget.set_limit(store, "groceries", "2026-09", "12345.67")
    log_path = paths.logs_dir() / "visible.jsonl"
    lines = [json.loads(line) for line in log_path.read_text("utf-8").splitlines() if line.strip()]
    assert lines, "set_limit logged nothing"
    for line in lines:
        assert line["event"] == Event.RECORD_ADDED.value
        assert line["ref"] == f"{budget.MATTER}/groceries.2026-09"
        blob = json.dumps(line)
        assert "12345" not in blob


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

    rows, uncategorised = budget.envelopes(canonical, sidecar, "2026-09")
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

    assert uncategorised == 1

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


def test_a_transaction_in_another_month_does_not_count(tmp_path, monkeypatch, make_account):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    sidecar, canonical = Sidecar(), Canonical()

    fp_august = _txn(monkeypatch, tmp_path, make_account, date="2026-08-15", amount="-999.00",
                      description="August groceries")
    overlay.tag(sidecar, fp_august, category="groceries")
    budget.set_limit(sidecar, "groceries", "2026-09", "50.00")

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
