"""I-17, made runtime-explicit — bite 4, piece 2.

`test_no_egress.py` is the static half: an AST sweep proving no network
module is imported anywhere in this package (`importer.py` included — its
discovery already walks every `*.py` under `homestead_ledger`, recursively,
via `PKG.rglob("*.py")`; nothing needed fixing there). This file is the
runtime half: `socket.socket`, `socket.getaddrinfo`, and
`socket.create_connection` are monkeypatched to raise on any call, and a real
CSV import — plus the real-store app-compose path bite 4's piece 1 wires up —
is proven to run to completion over a tmp `HOMESTEAD_HOME` without ever
tripping one. A money ledger is the canonical "must not egress" case; this
makes that a runtime assertion, not only a static one.
"""
from __future__ import annotations

import socket

import pytest

from homestead_ledger import importer
from homestead_ledger.app import view
from homestead_ledger.store import Canonical

_CSV = (
    "Date,Description,Amount\n"
    "2026-08-01,Whole Foods Market,-84.23\n"
    "2026-08-03,Employer Payroll,1500.00\n"
)


class EgressAttempt(AssertionError):
    """Raised in place of a real network call. Any instance escaping a test
    below means something on the import (or app-compose) path tried to dial
    out — a merely-absent network would just hang or raise `OSError`, which
    would prove nothing; this makes the attempt itself the failure."""


@pytest.fixture
def no_egress(monkeypatch):
    """Poison every socket-construction and DNS-resolution entry point
    stdlib networking goes through. `socket.socket` alone would miss a
    caller that goes through `socket.create_connection` (which can resolve
    via `getaddrinfo` and build its own socket internally), so all three are
    covered."""
    def _boom(name):
        def _raise(*args, **kwargs):
            raise EgressAttempt(f"socket.{name} called: args={args!r} kwargs={kwargs!r}")
        return _raise

    monkeypatch.setattr(socket, "socket", _boom("socket"))
    monkeypatch.setattr(socket, "getaddrinfo", _boom("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", _boom("create_connection"))


def test_import_csv_completes_with_no_network_egress(tmp_path, monkeypatch, no_egress):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = tmp_path / "statement.csv"
    path.write_text(_CSV, encoding="utf-8")

    result = importer.import_csv(path, account_number="9821")

    assert result.imported == 2
    assert result.errors == 0
    # the import really landed — this is a real run, not a no-op the guard
    # would pass trivially.
    canonical = Canonical()
    assert len(canonical.records("checking")) == 8  # 2 transactions * 4 fields


def test_reimport_dedup_path_completes_with_no_network_egress(tmp_path, monkeypatch, no_egress):
    """The `RecordExists`-catching dedup path is its own set of calls
    (insert, refuse, catch, tally) — proven separately rather than assumed
    to be as clean as the first import just because the happy path is."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = tmp_path / "statement.csv"
    path.write_text(_CSV, encoding="utf-8")
    importer.import_csv(path, account_number="9821")

    result = importer.import_csv(path, account_number="9821")

    assert result.imported == 0
    assert result.skipped == 2


def test_dry_run_completes_with_no_network_egress(tmp_path, monkeypatch, no_egress):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = tmp_path / "statement.csv"
    path.write_text(_CSV, encoding="utf-8")

    result = importer.import_csv(path, account_number="9821", dry_run=True)

    assert result.imported == 2


def test_compose_store_over_a_real_import_completes_with_no_network_egress(
    tmp_path, monkeypatch, no_egress
):
    """Bite 4's piece 1 — the real-store app-compose path — reading the
    imported rows back through `view.compose_store()`, also never dials out."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    path = tmp_path / "statement.csv"
    path.write_text(_CSV, encoding="utf-8")
    importer.import_csv(path, account_number="9821")

    ledger = view.compose_store()

    assert ledger.demo is False
    assert ledger.canonical.records(view.checking.ACCOUNT) != []


def test_compose_store_demo_fallback_completes_with_no_network_egress(
    tmp_path, monkeypatch, no_egress
):
    """The empty-store demo fallback — its own tmpdir, seeded from
    in-process data only — is exercised too, not just the real-store path."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    ledger = view.compose_store()

    assert ledger.demo is True
