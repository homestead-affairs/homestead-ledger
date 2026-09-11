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
import re
import threading
import time

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

        def raw(self, method, path, body=None, content_length=None):
            """A request built by hand — a body that is not JSON, a
            `Content-Length` that is not a number, or no body header at all.
            `http.client` will not build these, so the request goes down the
            socket as written."""
            import socket as _socket

            lines = [f"{method} {path} HTTP/1.1", f"Host: {self.host}:{self.port}",
                     "Content-Type: application/json"]
            payload = b"" if body is None else body.encode()
            if body is not None or content_length is not None:
                length = content_length if content_length is not None else str(len(payload))
                lines.append(f"Content-Length: {length}")
            lines.append("Connection: close")
            request = ("\r\n".join(lines) + "\r\n\r\n").encode() + payload
            sock = _socket.create_connection((self.host, self.port), timeout=5)
            try:
                sock.sendall(request)
                chunks = []
                while True:
                    piece = sock.recv(65536)
                    if not piece:
                        break
                    chunks.append(piece)
            finally:
                sock.close()
            response = b"".join(chunks)
            head, _, rest = response.partition(b"\r\n\r\n")
            status = int(head.split(b" ")[1]) if head else 0
            return status, rest

        def json_raw(self, method, path, body, content_length=None):
            status, rest = self.raw(method, path, body, content_length)
            return status, rest

    try:
        client = _Client()
        client.add_account = lambda label="chk-t", kind="checking", number="9821", **extra: client.json(
            "/api/account", {"label": label, "kind": kind, "number": number, **extra},
        )
        yield client
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_page_serves_and_carries_both_forms(ui):
    status, body = ui.get("/")
    assert status == 200
    page = body.decode()
    for field in (
        "oid", "oname", "oamount", "odue", "ocadence",
        "alabel", "akind", "anumber", "ainstitution",
        "tdate", "tamount", "tdesc",
    ):
        assert f'id="{field}"' in page
    assert "/api/obligation" in page and "/api/transaction" in page and "/api/account" in page
    assert "/api/store" not in page


def test_obligation_round_trip_through_the_gate(ui):
    status, data = ui.json("/api/obligation", {"id": "rent", "name": "Sunrise", "amount": "1450",
                                               "due_date": "2099-10-01", "cadence": "monthly"})
    assert status == 200 and data == {"ok": True, "id": "rent", "replaced": False}

    status, data = ui.json("/api/obligations")
    assert data["rows"] == [{"id": "rent", "name": "Sunrise", "due_date": "2099-10-01",
                             "cadence": "monthly", "amount": "a payment is due", "rung": "L4",
                             "gap": False, "paid_on": None, "resolved": False,
                             "paid_current": False}]

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


def test_account_round_trip_and_the_number_never_shows(ui):
    status, data = ui.add_account(label="chk-main", kind="checking", number="9821")
    assert status == 200 and data == {"ok": True, "label": "chk-main", "replaced": False}
    assert "9821" not in json.dumps(data)

    status, data = ui.json("/api/status")
    assert status == 200
    assert data["accounts"] == [{"label": "chk-main", "kind": "checking"}]
    assert "9821" not in json.dumps(data)

    status, data = ui.add_account(label="chk-main", kind="savings", number="1")
    assert status == 400 and "replace" in data["error"]
    status, data = ui.add_account(label="chk-main", kind="savings", number="1", replace=True)
    assert status == 200 and data["replaced"] is True


def test_account_label_cannot_be_a_kind_name(ui):
    status, data = ui.add_account(label="checking", kind="checking", number="1")
    assert status == 400 and data["ok"] is False
    assert "kind" in data["error"]


def test_transaction_round_trip_and_the_l5_never_shows(ui):
    ui.add_account(label="chk-main")
    status, data = ui.json("/api/transaction", {"date": "2026-08-01", "amount": "-84.23",
                                                "description": "Whole Foods Market",
                                                "account": "chk-main"})
    assert status == 200 and data["ok"] is True and len(data["id"]) == 64

    status, data = ui.json("/api/transactions?account=chk-main")
    by_field = {r["field"]: r for r in data["rows"]}
    assert by_field["description"]["text"] == "Whole Foods Market"
    assert by_field["amount"]["text"] == "a debit is on file"
    assert "account_number" not in by_field
    assert "9821" not in json.dumps(data) and "84.23" not in json.dumps(data)

    status, data = ui.json("/api/transaction", {"date": "2026-08-01", "amount": "-84.23",
                                                "description": "Whole Foods Market",
                                                "account": "chk-main"})
    assert status == 409


def test_transaction_refusals_at_entry(ui):
    ui.add_account(label="chk-main")
    base = {"date": "2026-08-01", "amount": "-84.23", "description": "x", "account": "chk-main"}
    for key, value in (("date", "yesterday"), ("amount", "lots"), ("description", ""),
                       ("account", ""), ("account", "brokerage")):
        status, data = ui.json("/api/transaction", {**base, key: value})
        assert status == 400, (key, value)
    status, data = ui.json("/api/transactions?account=chk-main")
    assert data["rows"] == []
    status, data = ui.json("/api/transactions?account=brokerage")
    assert status == 400


def test_the_account_select_is_the_registry_and_drives_the_list(ui):
    """The transaction pane names one account in its `<select>` and lists the
    rows of one account below it; if picking an account in the select does
    not redraw the list, the pane shows one account's rows under another's
    label — the two halves of one pane disagreeing about which account the
    operator is looking at. The options come from `/api/status`, and the
    list is drawn only once they exist."""
    ui.add_account(label="chk-main")

    status, data = ui.json("/api/status")
    assert status == 200
    assert data["accounts"] == [{"label": "chk-main", "kind": "checking"}]

    page = server._PAGE
    assert "<select id=\"taccount\"" in page
    assert "sel.onchange=loadTransactions" in page
    # the list is drawn from inside loadAccounts' resolution, not next to the
    # call, so it cannot read an empty select and fall back to something.
    assert "loadAccounts();loadObligations();" in page
    assert "loadAccounts();loadObligations();loadTransactions();" not in page


def test_no_account_name_is_hardcoded_as_a_default_in_the_page(ui):
    """I-23 on this surface, and I-11's fail-closed: the page must not carry
    a literal account kind to fall back on when `/api/status` has not
    answered — a hardcoded `||'checking'` posts a transaction to, and lists,
    an account the operator never chose."""
    from homestead_ledger import registry

    page = server._PAGE
    for name in registry.all_accounts():
        for literal in (f"'{name}'", f'"{name}"'):
            assert literal not in page, (
                f"{literal} is hardcoded in the page — read the account from "
                "currentAccount() (the /api/status-filled select) instead."
            )
    assert "function currentAccount()" in page


def test_subscriptions_run_over_the_real_books(ui):
    ui.add_account(label="chk-main")
    for date in ("2026-05-15", "2026-06-15", "2026-07-15", "2026-08-15"):
        ui.json("/api/transaction", {"date": date, "amount": "-15.99", "description": "Netflix",
                                     "account": "chk-main"})
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
    ui.add_account(label="chk-main")
    status, data = ui.json("/api/status")
    assert status == 200 and isinstance(data["nestor"], bool)
    assert {"label": "chk-main", "kind": "checking"} in data["accounts"]
    assert "checking" in data["kinds"]
    assert ui.host == "127.0.0.1"


# ── the page's own structure ───────────────────────────────────────────────
#
# The Records tab renders on load and, until this bite, no nav button reached
# it: one click on any other tab and the household's only entry forms were
# gone for the rest of the session, with no way back but a reload. That is a
# whole surface orphaned by a missing button, and it passed every test the
# suite had — because every test drove the API and none read the page. These
# two scans are structural for that reason: they hold *every* section against
# the nav, so no future tab can be added and left unreachable.

def _sections(page: str) -> set[str]:
    return set(re.findall(r'<section id="t-([a-z0-9_-]+)"', page))


def _nav_targets(page: str) -> set[str]:
    return set(re.findall(r"show\('([a-z0-9_-]+)'", page))


def _orphans(page: str) -> list[str]:
    return sorted(_sections(page) - _nav_targets(page))


def test_every_section_has_a_nav_button():
    """Every `<section id="t-X">` has a `show('X')` button. The bug this
    catches is not "Records is missing" — it is "a tab exists that nothing can
    open", which is the general shape."""
    page = server._PAGE
    assert _sections(page), "no tabs found — the scan is reading the wrong thing"
    assert _orphans(page) == [], (
        "these tabs render but no nav button opens them; once another tab is "
        "clicked they are unreachable for the rest of the session."
    )
    assert "records" in _nav_targets(page)


def test_the_tab_that_opens_is_the_tab_the_nav_marks():
    """Exactly one section starts `on`, exactly one button starts `on`, and
    they are the same tab — otherwise the page opens on one tab with another
    underlined, and the first click 'moves' to where the user already was."""
    page = server._PAGE
    on_sections = re.findall(r'<section id="t-([a-z0-9_-]+)" class="tab on"', page)
    on_buttons = re.findall(r'<button class="tb on" onclick="show\(\'([a-z0-9_-]+)\'', page)
    assert on_sections == on_buttons == ["records"]


def test_the_orphan_scan_catches_a_planted_orphan():
    """A scan that has never fired has not been shown to check anything."""
    planted = """
    <nav><button class="tb on" onclick="show('records',this)">Records</button></nav>
    <section id="t-records" class="tab on">a</section>
    <section id="t-ledgers" class="tab">b</section>
    """
    assert _orphans(planted) == ["ledgers"]
    assert _orphans(planted.replace(
        "</nav>", "<button onclick=\"show('ledgers',this)\">L</button></nav>")) == []


# ── the door itself ────────────────────────────────────────────────────────

def test_a_malformed_body_is_answered_not_crashed(ui):
    """Every one of these used to be an unhandled exception inside the
    handler: no response at all, a traceback on the operator's terminal, and a
    browser left spinning. A door answers."""
    status, body = ui.raw("POST", "/api/obligation", body="{not json")
    assert status == 400 and b"JSON" in body

    status, body = ui.raw("POST", "/api/obligation", body="[1, 2, 3]")
    assert status == 400

    status, body = ui.raw("POST", "/api/obligation", body="{}", content_length="banana")
    assert status == 400

    # no Content-Length at all
    status, body = ui.raw("POST", "/api/obligation", body=None)
    assert status in (400, 411)


def test_an_oversized_body_is_refused_before_it_is_read(ui):
    """`rfile.read(Content-Length)` is an instruction from the client to
    allocate whatever number it names, in the process that holds the books."""
    status, data = ui.json_raw("POST", "/api/extract", json.dumps({"text": "x" * 8}),
                               content_length=str(64 * 1024 * 1024))
    assert status == 413


def test_a_non_string_field_is_refused_not_stringified(ui):
    """`str({"a": 1})` is `"{'a': 1}"` — a dict quietly becoming the payee's
    name. JSON carries shapes a form field is not; they are refused by name."""
    for value in ({"a": 1}, [1, 2], True):
        status, data = ui.json("/api/obligation", {
            "id": "rent", "name": value, "amount": "1",
            "due_date": "2099-10-01", "cadence": "monthly"})
        assert status == 400 and data["ok"] is False, value
    status, data = ui.json("/api/obligations")
    assert data["rows"] == []


def test_replace_is_json_true_and_nothing_else(ui):
    """`bool("false")` is `True`. A checkbox serialized as the *string*
    `"false"` — which several form encoders send — would have read as "yes,
    replace it" and silently overwritten the obligation (I-9)."""
    first = {"id": "rent", "name": "Sunrise", "amount": "1450",
             "due_date": "2099-10-01", "cadence": "monthly"}
    assert ui.json("/api/obligation", first)[0] == 200

    for sneaky in ("false", "0", "no", 1, [], {}):
        status, data = ui.json("/api/obligation", {**first, "name": "Interloper",
                                                   "replace": sneaky})
        assert status == 400, sneaky
    status, data = ui.json("/api/obligation?id=rent")
    assert data["fields"]["name"]["value"] == "Sunrise"

    status, data = ui.json("/api/obligation", {**first, "name": "Deliberate", "replace": True})
    assert status == 200 and data["replaced"] is True


def test_an_amount_that_is_not_a_number_never_reaches_the_books(ui):
    """`float("nan")` and `float("1e400")` both succeed and `f"{…:.2f}"` writes
    the words. An amount on the books that is not finite makes every balance
    after it `nan`."""
    ui.add_account(label="chk-main")
    base = {"date": "2026-08-01", "description": "x", "account": "chk-main"}
    for bad in ("nan", "inf", "-inf", "Infinity"):
        status, data = ui.json("/api/transaction", {**base, "amount": bad})
        assert status == 400, bad
    status, data = ui.json("/api/transactions?account=chk-main")
    assert data["rows"] == []

    # a real exponent is a real number, and `Decimal` keeps it finite where
    # `float("1e400")` would have overflowed to `inf` and been written as one.
    status, data = ui.json("/api/transaction", {**base, "amount": "1e3"})
    assert status == 200


def test_no_error_text_echoes_the_account_number_or_the_amount(ui):
    """I-15: an error may name a field, never repeat an L3+ value — and an
    error crosses to the browser exactly as a rendered record does. The
    account number, set once on the instance (bite 2b), and the amount must
    never leak through a later transaction door refusal. The one fingerprint
    in `books`'s re-import refusal is a *reference*, not content."""
    ui.add_account(label="chk-main", number="4111111111111111")
    good = {"date": "2026-08-01", "amount": "-73.61", "description": "Whole Foods",
            "account": "chk-main"}
    assert ui.json("/api/transaction", good)[0] == 200

    probes = [
        {**good, "date": "someday"},
        {**good, "amount": "8675.309lots"},
        {**good, "description": ""},
        {**good, "account": "offshore"},
        good,                                     # the re-import refusal (409)
    ]
    for probe in probes:
        status, data = ui.json("/api/transaction", probe)
        text = json.dumps(data)
        assert "4111111111111111" not in text, probe
        assert "73.61" not in text and "8675.309" not in text, probe
        assert "offshore" not in text, probe


def test_an_unknown_account_is_refused_on_both_doors(ui):
    """Bite 2b: an unregistered label would grow a phantom matter in the
    canonical books that nothing iterating `accounts.instances()` ever reads
    back."""
    status, data = ui.json("/api/transaction", {
        "date": "2026-08-01", "amount": "-1.00", "description": "x",
        "account": "mattress"})
    assert status == 400
    status, data = ui.json("/api/transactions?account=mattress")
    assert status == 400


def test_a_handler_that_fails_answers_with_a_type_not_a_record(ui, monkeypatch):
    """The subscription pass used to swallow every exception and answer
    `{"subscriptions": []}` — a silent "you have none" that is indistinguishable
    from the truth. It must surface; and what surfaces must be the *class* of
    what broke, never an exception's text, which can carry the record it was
    handed (I-15)."""
    from homestead_ledger import balance

    ui.add_account(label="chk-main")

    def boom(*a, **k):
        raise RuntimeError("account 4111111111111111 balance -84.23")

    monkeypatch.setattr(balance, "transaction_tuples", boom)
    status, data = ui.json("/api/subscriptions")
    assert status == 500
    assert data["ok"] is False
    assert "RuntimeError" in data["error"]
    assert "4111111111111111" not in json.dumps(data)
    assert "84.23" not in json.dumps(data)


def test_an_id_is_never_spliced_into_javascript(ui):
    """`esc()` escapes `&`, `<` and `>` — a text-node escape, not a
    JavaScript-string one. An id carrying an apostrophe, built into
    `onclick="openObligation('…')"`, closes the string and runs what follows.
    The id travels as data and the click is bound in code; and the id shape is
    closed upstream so the quote never gets this far either."""
    page = server._PAGE
    assert "openObligation(\\'" not in page
    assert "data-oid=" in page and "getAttribute('data-oid')" in page
    assert "function attr(" in page

    status, data = ui.json("/api/obligation", {
        "id": "a'-alert(1)-'b", "name": "x", "amount": "1",
        "due_date": "2099-10-01", "cadence": "monthly"})
    assert status == 400


class _Sock:
    """A socket that hands out the chunks it was given, honouring the size
    asked for, then whatever `then` is — `b""` for a peer that closed, or an
    exception to raise."""

    def __init__(self, chunks, then=b""):
        self.chunks = list(chunks)
        self.then = then
        self.timeout = None
        self.asked = []

    def settimeout(self, t):
        self.timeout = t

    def recv(self, n):
        self.asked.append(n)
        if self.chunks:
            head, rest = self.chunks[0][:n], self.chunks[0][n:]
            if rest:
                self.chunks[0] = rest
            else:
                self.chunks.pop(0)
            return head
        if isinstance(self.then, BaseException):
            raise self.then
        return self.then


def test_a_refused_body_is_drained_before_the_socket_closes():
    """Closing a socket with unread bytes in its receive buffer turns the
    close into a reset, and on Windows a reset discards the 400 the client
    has not read yet (`WinError 10053`, seen on the law module's release PR
    for its bad-Content-Length test).  The drain reads what arrived, waits
    only `DRAIN_TIMEOUT_SECONDS` for more, is bounded by the cap, and
    swallows the socket's own errors — the answer is already sent."""
    sock = _Sock([b"{}", b"more"])
    assert server._drain(sock) == 6
    assert sock.timeout == server.DRAIN_TIMEOUT_SECONDS
    sock = _Sock([b"{}"], then=TimeoutError())
    assert server._drain(sock) == 2
    sock = _Sock([b"x" * 65536] * 40)
    assert server._drain(sock, limit=100_000) == 100_000
    assert max(sock.asked) <= 65536 and sum(sock.asked) >= 100_000
    sock = _Sock([], then=OSError())
    assert server._drain(sock) == 0


def test_a_refused_content_length_reaches_the_drain(ui, monkeypatch):
    """The refusal path must actually call the drain on the live connection —
    the unit test above proves what draining does, this proves it happens,
    once, after the answer is on the wire (the client read a 400).  The client
    can hold its 400 before the handler thread reaches the drain, so the check
    waits for the call rather than asserting the instant the answer lands."""
    calls = []
    real = server._drain

    def _spy(sock, **kw):
        calls.append(sock)
        return real(sock, **kw)

    monkeypatch.setattr(server, "_drain", _spy)
    status, rest = ui.raw("POST", "/api/obligation", body="{}", content_length="abc")
    assert status == 400 and json.loads(rest)["error"]
    deadline = time.monotonic() + 5
    while not calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(calls) == 1 and hasattr(calls[0], "recv")


# ── the cadence select equals cadence.CADENCES structurally ─────────────────

def test_the_cadence_select_options_equal_cadences(ui):
    """The `<select id="ocadence">` on the page is generated from
    `cadence.CADENCES` (`server._CADENCE_OPTIONS`), never a second, hand-kept
    literal — parsed out of the real served page, not the module's private
    string, so this fails the moment the two drift apart."""
    from homestead_ledger.cadence import CADENCES

    status, body = ui.get("/")
    page = body.decode()
    m = re.search(r'<select id="ocadence">(.*?)</select>', page, re.S)
    assert m is not None
    options = re.findall(r'<option value="([^"]+)">', m.group(1))
    assert tuple(options) == CADENCES


# ── /api/obligation/paid ─────────────────────────────────────────────────────

#: Bite 2b: `/api/obligation/paid` takes an account *instance*'s label — the
#: same string `/api/transaction` files a transaction under and the same one
#: the form's select is filled with from `/api/status`. `_add_rent` registers
#: it, so every paid test below posts a label that door actually knows.
PAID_ACCOUNT = "chk-t"


def _add_rent(ui, due_date="2026-08-05", cadence="monthly"):
    status, data = ui.add_account(label=PAID_ACCOUNT)
    assert status == 200 and data["ok"]
    status, data = ui.json("/api/obligation", {"id": "rent", "name": "Sunrise", "amount": "1450",
                                               "due_date": due_date, "cadence": cadence})
    assert status == 200 and data["ok"]


def test_obligation_paid_rolls_the_due_date_and_the_list_shows_the_mark(ui):
    _add_rent(ui)
    status, data = ui.json("/api/obligation/paid", {
        "id": "rent", "account": PAID_ACCOUNT, "fingerprint": "fp-1", "paid_on": "2026-08-07",
    })
    assert status == 200 and data["ok"] is True
    assert data["old_due"] == "2026-08-05" and data["new_due"] == "2026-09-05"

    status, data = ui.json("/api/obligations")
    row = data["rows"][0]
    assert row["due_date"] == "2026-09-05"
    assert row["paid_on"] == "2026-08-07"
    assert row["resolved"] is False


def test_obligation_paid_resolves_a_once_obligation_and_drops_it_from_the_queue(ui):
    _add_rent(ui, due_date="2026-08-05", cadence="once")
    status, data = ui.json("/api/obligation/paid", {
        "id": "rent", "account": PAID_ACCOUNT, "fingerprint": "fp-1", "paid_on": "2026-08-05",
    })
    assert status == 200 and data["new_due"] is None

    status, data = ui.json("/api/obligations")
    assert data["rows"][0]["resolved"] is True

    status, data = ui.json("/api/queue")
    assert data["items"] == []


def test_obligation_paid_refuses_before_writing_and_never_echoes_an_amount(ui):
    _add_rent(ui)
    for bad in (
        {"id": "rent", "account": "mattress", "fingerprint": "fp-1", "paid_on": "2026-08-07"},
        {"id": "rent", "account": PAID_ACCOUNT, "fingerprint": "", "paid_on": "2026-08-07"},
        {"id": "rent", "account": PAID_ACCOUNT, "fingerprint": "fp-1", "paid_on": "08/07/2026"},
        {"id": "nope", "account": PAID_ACCOUNT, "fingerprint": "fp-1", "paid_on": "2026-08-07"},
    ):
        status, data = ui.json("/api/obligation/paid", bad)
        assert status == 400 and data["ok"] is False
        assert "1450" not in data["error"]

    status, data = ui.json("/api/obligations")
    assert data["rows"][0]["due_date"] == "2026-08-05"   # nothing rolled


def test_obligation_paid_replace_true_only_as_a_json_boolean(ui):
    """The same I-9 posture `_post_obligation`'s `replace` already carries:
    the *string* `"false"` must not read as `True` (`bool("false")` is
    `True` in Python)."""
    _add_rent(ui)
    status, data = ui.json("/api/obligation/paid", {
        "id": "rent", "account": PAID_ACCOUNT, "fingerprint": "fp-1", "paid_on": "2026-08-07",
    })
    assert status == 200

    status, data = ui.json("/api/obligation/paid", {
        "id": "rent", "account": PAID_ACCOUNT, "fingerprint": "fp-2", "paid_on": "2026-08-07",
        "replace": "false",
    })
    assert status == 400 and "overwrite" in data["error"]


def test_obligation_paid_reports_a_back_dated_entry_without_rolling(ui):
    """A receipt for a period a later payment already closed is recorded and
    the schedule stands still (`rolled: false`) — otherwise the due date
    walks forward once per receipt and a period the household still owes
    disappears."""
    _add_rent(ui, due_date="2026-08-05")
    status, first = ui.json("/api/obligation/paid", {
        "id": "rent", "account": PAID_ACCOUNT, "fingerprint": "fp-1", "paid_on": "2026-08-05"})
    assert status == 200 and first["new_due"] == "2026-09-05" and first["rolled"] is True

    status, back = ui.json("/api/obligation/paid", {
        "id": "rent", "account": PAID_ACCOUNT, "fingerprint": "fp-0", "paid_on": "2026-07-05"})
    assert status == 200 and back["rolled"] is False
    assert back["old_due"] == back["new_due"] == "2026-09-05"

    status, data = ui.json("/api/obligations")
    assert data["rows"][0]["due_date"] == "2026-09-05"


def test_no_obligation_surface_ever_carries_the_account_or_fingerprint(ui):
    """I-15 on the JSON doors: a `paid_by` record holds `{account,
    fingerprint}` and every surface shows it *by reference* — the date the
    record is keyed under — so neither value may appear in a list row, in an
    opened detail, in the queue, or in the served page. Both are planted
    with values nothing else on these surfaces could produce."""
    _add_rent(ui)
    ui.add_account(label="acct-pl4nt")
    status, data = ui.json("/api/obligation/paid", {
        "id": "rent", "account": "acct-pl4nt",
        "fingerprint": "f1nG3rpr1nt-pl4nt", "paid_on": "2026-08-07"})
    assert status == 200

    for path in ("/api/obligations", "/api/obligation?id=rent", "/api/queue"):
        status, data = ui.json(path)
        assert status == 200
        blob = json.dumps(data)
        assert "f1nG3rpr1nt-pl4nt" not in blob, path
        assert "acct-pl4nt" not in blob, path
        assert "paid_by" not in blob, path
    # the row does carry the reference, which is the point
    status, data = ui.json("/api/obligations")
    assert data["rows"][0]["paid_on"] == "2026-08-07"

    status, body = ui.get("/")
    assert b"f1nG3rpr1nt-pl4nt" not in body


def test_the_list_row_ticks_only_a_current_period(ui):
    """`paid_current` is a separate field from `paid_on` and the page's JS
    draws the ✓ from it — "there is a payment on file" and "this period is
    paid" are different claims."""
    _add_rent(ui, due_date="2020-08-05")   # long lapsed on any real clock
    status, _ = ui.json("/api/obligation/paid", {
        "id": "rent", "account": PAID_ACCOUNT, "fingerprint": "fp-1", "paid_on": "2020-08-05"})
    assert status == 200

    status, data = ui.json("/api/obligations")
    row = data["rows"][0]
    assert row["paid_on"] == "2020-08-05" and row["paid_current"] is False

    status, body = ui.get("/")
    page = body.decode()
    assert "if(o.paid_current)" in page
    # and the tick is not drawn from the bare presence of a payment
    assert "if(o.paid_on){paid+='<span class=\"sm s-ok\">paid" not in page


def test_the_mark_paid_form_takes_its_accounts_from_the_status_door(ui):
    """No second hand-kept account list on this surface (I-23): the select is
    empty in the markup and filled from `/api/status`, whose `accounts` is
    the household's registered *instances* (bite 2b) — the same door and the
    same labels the transaction form's select uses, so the two forms can
    never offer different ideas of what an account is. Options are built as
    DOM nodes with `textContent`, so a label is never concatenated into
    HTML."""
    status, body = ui.get("/")
    page = body.decode()
    assert '<select id="paccount"></select>' in page
    m = re.search(r"function loadAccountsForPaid\(\) \{(.*?)\n\}", page, re.S)
    assert m is not None
    fn = m.group(1)
    assert "/api/status" in fn
    assert "createElement('option')" in fn and "textContent" in fn
    assert "innerHTML='<option" not in fn
    # the option's value is the label itself — what `mark_paid` is handed
    assert "opt.value=a.label" in fn

    # no instances on file → no options to offer, and no kind name standing
    # in for one (I-11: absence, never a default).
    status, data = ui.json("/api/status")
    assert data["accounts"] == []

    ui.add_account(label="chk-main", kind="checking")
    status, data = ui.json("/api/status")
    assert data["accounts"] == [{"label": "chk-main", "kind": "checking"}]
    # and that label is exactly what the paid door accepts
    ui.json("/api/obligation", {"id": "rent", "name": "S", "amount": "10",
                                "due_date": "2026-08-05", "cadence": "monthly"})
    status, data = ui.json("/api/obligation/paid", {
        "id": "rent", "account": "chk-main", "fingerprint": "fp-1",
        "paid_on": "2026-08-07"})
    assert status == 200 and data["ok"] is True
