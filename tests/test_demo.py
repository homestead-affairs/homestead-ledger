"""`--demo` — the store → serve → surface pipeline, headless, on a throwaway
account. Mirrors homestead-law's `tests/test_advise_ui.py`-adjacent demo
coverage in spirit: the values are invented, the rungs are the checking
pack's real ones, so what renders where is the real crossing.
"""
from __future__ import annotations

import pytest

from homestead_ledger.app import demo
from homestead_ledger.books import RecordExists
from homestead_ledger.store import Canonical


def test_seed_imports_the_demo_transactions(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    item_ids = demo.seed()
    assert len(item_ids) == len(demo._DEMO_TRANSACTIONS)
    assert len(set(item_ids)) == len(item_ids), "each demo transaction has a distinct fingerprint"

    canonical = Canonical()
    for item_id in item_ids:
        assert canonical.get(demo.ACCOUNT, "amount", item_id).payload  # exists, readable


def test_seed_is_not_idempotent_against_a_second_call(tmp_path, monkeypatch):
    """seed() re-imports the same fixed transactions; a second call against
    the same store must be refused by the same identity rule books.py
    enforces everywhere else — this is not special-cased for the demo."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    demo.seed()
    with pytest.raises(RecordExists):
        demo.seed()


def test_compose_demo_starts_and_ends_on_the_resting_cover(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    text = demo.compose_demo()
    lines = text.splitlines()
    assert "cover (resting)" in lines[0]
    assert "Nothing is open" in lines[0]
    assert "cover (resting)" in lines[-1]
    assert "Nothing is open" in lines[-1]


def test_compose_demo_list_shows_dates_and_payees_derives_amounts_denies_numbers(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    text = demo.compose_demo()

    assert "[L2] 2026-08-01" in text
    assert "[L3] Whole Foods Market" in text
    assert "[L4] a debit is on file" in text
    assert "[L4] a credit is on file" in text
    # no raw account number, and no raw amount, anywhere in the LIST section
    list_section = text.split("S1_LIST):", 1)[1].split("detail amount", 1)[0]
    assert "9821" not in list_section
    assert "84.23" not in list_section
    assert "account_number" not in list_section  # the field itself never becomes a row


def test_compose_demo_opens_amount_detail_and_denies_account_number(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    text = demo.compose_demo()

    assert "detail amount (S1_DETAIL): [L4] -84.23" in text
    assert "detail account_number (S1_DETAIL): deny" in text
    assert "value=None" in text
    assert "9821" not in text, "the sealed account number must never appear in the demo output"


def test_open_account_composes_through_the_real_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    demo.seed()
    window = demo.open_account(Canonical())
    rungs_shown = {row.rung for row in window.rows}
    assert "L5" not in {r.value for r in rungs_shown}
