"""The browser UI — the door a household keeps its own books through.

`server.build_server()` binds the real handlers on an ephemeral port without
serving, so this suite drives them end to end with `http.client`. No Nestor is
needed. The invariants hold at the browser exactly as on the window: an amount
lists as its derived form and renders in the detail; the account number is never
a row; a re-entered transaction is refused; a bad date is refused at entry.
"""
from __future__ import annotations

import http.client
import json
import threading

import pytest

from homestead_ledger import server


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    srv = server.build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    class _Client:
        host, port = srv.server_address[0], srv.server_address[1]

        def get(self, path):
            conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
            conn.request("GET", path)
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            return resp.status, body

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


def test_the_page_serves_and_carries_both_forms(ui):
    status, body = ui.get("/")
    assert status == 200
    page = body.decode()
    for field in ("oid", "oname", "oamount", "odue", "ocadence", "tdate", "tamount", "tdesc", "tacct"):
        assert f'id="{field}"' in page
    assert "/api/obligation" in page and "/api/transaction" in page
    assert "/api/store" not in page


def test_obligation_round_trip_through_the_gate(ui):
    status, data = ui.json("/api/obligation", {"id": "rent", "name": "Sunrise", "amount": "1450",
                                               "due_date": "2099-10-01", "cadence": "monthly"})
    assert status == 200 and data == {"ok": True, "id": "rent", "replaced": False}

    status, data = ui.json("/api/obligations")
    assert data["rows"] == [{"id": "rent", "name": "Sunrise", "due_date": "2099-10-01",
                             "cadence": "monthly", "amount": "a payment is due", "rung": "L4"}]

    status, data = ui.json("/api/obligation?id=rent")
    assert data["fields"]["amount"] == {"rung": "L4", "value": "1450.00"}

    status, data = ui.json("/api/queue")
    assert data["items"][0]["id"] == "rent" and data["items"][0]["shown"] == "2099-10-01"

    status, data = ui.json("/api/obligation", {"id": "rent", "name": "x", "amount": "1",
                                               "due_date": "2099-10-01", "cadence": "monthly"})
    assert status == 400 and "replace" in data["error"]
    status, data = ui.json("/api/obligation", {"id": "rent", "name": "x", "amount": "1",
                                               "due_date": "2099-10-01", "cadence": "monthly",
                                               "replace": True})
    assert data["replaced"] is True


def test_obligation_refusals_at_entry(ui):
    for bad in (
        {"id": "", "name": "a", "amount": "1", "due_date": "2099-10-01", "cadence": "monthly"},
        {"id": "rent", "name": "", "amount": "1", "due_date": "2099-10-01", "cadence": "monthly"},
        {"id": "rent", "name": "a", "amount": "lots", "due_date": "2099-10-01", "cadence": "monthly"},
        {"id": "rent", "name": "a", "amount": "1", "due_date": "someday", "cadence": "monthly"},
        {"id": "../x", "name": "a", "amount": "1", "due_date": "2099-10-01", "cadence": "monthly"},
    ):
        status, data = ui.json("/api/obligation", bad)
        assert status == 400 and data["ok"] is False, bad
    status, data = ui.json("/api/obligations")
    assert data["rows"] == []
    status, data = ui.json("/api/obligation?id=rent")
    assert status == 404


def test_transaction_round_trip_and_the_l5_never_shows(ui):
    status, data = ui.json("/api/transaction", {"date": "2026-08-01", "amount": "-84.23",
                                                "description": "Whole Foods Market",
                                                "account_number": "9821"})
    assert status == 200 and data["ok"] is True and len(data["id"]) == 64

    status, data = ui.json("/api/transactions?account=checking")
    by_field = {r["field"]: r for r in data["rows"]}
    assert by_field["description"]["text"] == "Whole Foods Market"
    assert by_field["amount"]["text"] == "a debit is on file"
    assert "account_number" not in by_field
    assert "9821" not in json.dumps(data) and "84.23" not in json.dumps(data)

    status, data = ui.json("/api/transaction", {"date": "2026-08-01", "amount": "-84.23",
                                                "description": "Whole Foods Market",
                                                "account_number": "9821"})
    assert status == 409


def test_transaction_refusals_at_entry(ui):
    base = {"date": "2026-08-01", "amount": "-84.23", "description": "x", "account_number": "1"}
    for key, value in (("date", "yesterday"), ("amount", "lots"), ("description", ""),
                       ("account_number", ""), ("account", "savings")):
        status, data = ui.json("/api/transaction", {**base, key: value})
        assert status == 400, (key, value)
    status, data = ui.json("/api/transactions")
    assert data["rows"] == []
    status, data = ui.json("/api/transactions?account=savings")
    assert status == 400


def test_subscriptions_run_over_the_real_books(ui):
    for date in ("2026-05-15", "2026-06-15", "2026-07-15", "2026-08-15"):
        ui.json("/api/transaction", {"date": date, "amount": "-15.99", "description": "Netflix",
                                     "account_number": "9821"})
    status, data = ui.json("/api/subscriptions")
    assert status == 200
    assert [s["merchant"] for s in data["subscriptions"]] == ["netflix"]
    assert data["subscriptions"][0]["cadence"] == "monthly"


def test_intake_extracts_without_storing(ui):
    status, data = ui.json("/api/extract", {"text": "Total: $45.99  Due: 10/01/2026"})
    kinds = {i["kind"] for i in data["items"]}
    assert "amount" in kinds and "due_date" in kinds
    status, data = ui.json("/api/obligations")
    assert data["rows"] == []


def test_status_and_localhost(ui):
    status, data = ui.json("/api/status")
    assert status == 200 and isinstance(data["nestor"], bool) and "checking" in data["accounts"]
    assert ui.host == "127.0.0.1"
