"""The recurring-charge detector — pure, stdlib-only, `today`-injected.

Re-derived from `safe-app-store/apps/private-ledger/src/private_ledger/
subscriptions.py` as knowledge, not copy-pasted: same pipeline (normalize
merchant → group → cluster by amount tolerance → infer cadence from median
gap → require a minimum occurrence count → score confidence → derive
next-expected/monthly-equivalent/annualized/status), adapted to this bite's
plain-tuple interface (no `category` field — housing/rent/mortgage/debt/loan
is excluded by matching the description text instead) and to
`docs/build-plan.md`'s cadence set (weekly/monthly/quarterly/annual, no
biweekly bucket).
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from homestead_ledger import recurring
from homestead_ledger.recurring import RecurringCharge, detect_recurring, normalize_merchant

TODAY = date(2026, 8, 10)


def _monthly(desc, amount, start, count, day=5):
    out = []
    y, m = start
    for _ in range(count):
        out.append((date(y, m, day).isoformat(), amount, desc))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _by_merchant(charges):
    return {c.merchant: c for c in charges}


def test_monthly_subscription_detected():
    txns = _monthly("NETFLIX #1234", -9.99, (2025, 8), 12)
    subs = _by_merchant(detect_recurring(txns, today=TODAY))
    assert "netflix" in subs
    nf = subs["netflix"]
    assert nf.cadence == "monthly"
    assert nf.amount == 9.99
    assert nf.occurrences == 12
    assert nf.status == "active"
    assert nf.confidence > 0.8


def test_weekly_subscription_detected():
    txns = [(date(2026, m, d).isoformat(), -4.50, "COFFEE SUB") for m, d in
            [(7, 6), (7, 13), (7, 20), (7, 27), (8, 3)]]
    subs = _by_merchant(detect_recurring(txns, today=TODAY))
    assert "coffee sub" in subs
    assert subs["coffee sub"].cadence == "weekly"


def test_quarterly_subscription_detected():
    txns = [
        ("2025-11-01", -300.0, "QUARTERLY BOX CLUB"),
        ("2026-02-01", -300.0, "QUARTERLY BOX CLUB"),
        ("2026-05-02", -300.0, "QUARTERLY BOX CLUB"),
    ]
    subs = _by_merchant(detect_recurring(txns, today=TODAY))
    assert "quarterly box club" in subs
    assert subs["quarterly box club"].cadence == "quarterly"


def test_annual_renewal_detected_with_only_two_occurrences():
    txns = [
        ("2024-06-10", -14.99, "NAMECHEAP DOMAIN RENEWAL"),
        ("2025-06-11", -14.99, "NAMECHEAP DOMAIN RENEWAL"),
    ]
    subs = _by_merchant(detect_recurring(txns, today=TODAY))
    assert "namecheap domain renewal" in subs
    dom = subs["namecheap domain renewal"]
    assert dom.cadence == "annual"
    assert dom.occurrences == 2


def test_two_monthly_occurrences_are_not_enough():
    """The default minimum is 3 occurrences except for annual (2) — two
    monthly charges do not yet make a detected subscription."""
    txns = _monthly("NEW STREAMING CO", -12.00, (2026, 6), 2)
    subs = detect_recurring(txns, today=TODAY)
    assert subs == []


def test_variable_usage_bill_reports_a_range_not_a_fixed_amount():
    usage = [-42.10, -58.30, -71.05, -85.60, -96.20, -40.75]
    txns = _monthly("AWS CLOUD SERVICES", None, (2026, 2), 0)  # placeholder, overwritten below
    txns = []
    y, m = 2026, 2
    for amt in usage:
        txns.append((date(y, m, 15).isoformat(), amt, "AWS CLOUD SERVICES"))
        m += 1
    subs = _by_merchant(detect_recurring(txns, today=TODAY))
    assert "aws cloud services" in subs
    aws = subs["aws cloud services"]
    assert aws.cadence == "monthly"
    assert aws.amount is None
    assert aws.amount_range == (40.75, 96.20)


def test_lapsed_subscription_flagged_possibly_cancelled():
    txns = _monthly("SPOTIFY USA", -11.99, (2026, 1), 3)
    subs = _by_merchant(detect_recurring(txns, today=TODAY))
    assert "spotify usa" in subs
    assert subs["spotify usa"].status == "possibly_cancelled"


def test_active_subscription_stays_active():
    txns = _monthly("NETFLIX", -9.99, (2026, 4), 5)
    subs = _by_merchant(detect_recurring(txns, today=TODAY))
    assert subs["netflix"].status == "active"


def test_housing_rent_mortgage_debt_loan_excluded_by_description():
    txns = (
        _monthly("MONTHLY RENT PAYMENT", -1500.0, (2025, 8), 12)
        + _monthly("MORTGAGE PMT 4412", -2100.0, (2025, 8), 12)
        + _monthly("STUDENT LOAN SERVICER", -220.0, (2025, 8), 12)
        + _monthly("CREDIT CARD DEBT PAYOFF", -300.0, (2025, 8), 12)
        + _monthly("HOUSING COOP DUES", -180.0, (2025, 8), 12)
    )
    subs = detect_recurring(txns, today=TODAY)
    assert subs == []


def test_next_expected_is_last_charge_plus_the_median_interval():
    txns = _monthly("NETFLIX", -9.99, (2026, 3), 6)
    nf = _by_merchant(detect_recurring(txns, today=TODAY))["netflix"]
    last = date.fromisoformat(nf.last_charge)
    nxt = date.fromisoformat(nf.next_expected)
    assert 25 <= (nxt - last).days <= 35


def test_normalize_strips_store_numbers_auth_codes_and_dates():
    assert normalize_merchant("NETFLIX #1234") == "netflix"
    assert normalize_merchant("NETFLIX 07/24") == "netflix"
    assert normalize_merchant("Netflix") == "netflix"
    assert normalize_merchant("ACME REF:88213X") == "acme"


def test_price_hike_does_not_split_the_subscription():
    """A cluster tolerance of max(5%, $1) keeps a modest price increase in
    one subscription rather than splitting it into two."""
    txns = _monthly("STREAMING PLUS", -9.99, (2025, 8, ), 6)
    txns += _monthly("STREAMING PLUS", -10.49, (2026, 2), 6)
    subs = _by_merchant(detect_recurring(txns, today=TODAY))
    assert "streaming plus" in subs
    assert subs["streaming plus"].occurrences == 12


def test_determinism():
    txns = _monthly("NETFLIX #1234", -9.99, (2025, 8), 12)
    a = detect_recurring(txns, today=TODAY)
    b = detect_recurring(txns, today=TODAY)
    assert a == b


def test_inflows_are_ignored():
    txns = [(f"2026-0{m}-05", 2000.0, "PAYROLL DEPOSIT") for m in range(1, 6)]
    assert detect_recurring(txns, today=TODAY) == []


def test_min_confidence_filters_irregular_intervals():
    """Wildly irregular gaps between charges score low interval-regularity
    confidence and are dropped at the default threshold."""
    irregular = [
        ("2026-01-03", -20.0, "IRREGULAR CO"),
        ("2026-02-27", -20.0, "IRREGULAR CO"),
        ("2026-03-04", -20.0, "IRREGULAR CO"),
        ("2026-06-19", -20.0, "IRREGULAR CO"),
    ]
    subs = detect_recurring(irregular, today=TODAY, min_confidence=0.5)
    assert all(s.merchant != "irregular co" for s in subs) or subs == []


def test_returns_a_recurring_charge_dataclass():
    txns = _monthly("NETFLIX", -9.99, (2026, 3), 4)
    subs = detect_recurring(txns, today=TODAY)
    assert subs and isinstance(subs[0], RecurringCharge)


# ── the CRITICAL constraint: pure, plain-args, no store/books/balance reach ──

def test_the_module_does_not_import_the_store_books_balance_or_homestead_engine():
    """`recurring.py` takes plain transaction data and `today` — it must not
    reach the store, books, balance, or even the engine, so it stays pure and
    testable with synthetic tuples alone, and the chokepoint/no-egress guards
    need no allow-list change to cover it."""
    src = Path(recurring.__file__).read_text("utf-8")
    tree = ast.parse(src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "homestead" not in imported
    assert "homestead_ledger" not in imported


def test_the_module_reaches_no_payload_and_no_canonical():
    src = Path(recurring.__file__).read_text("utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr != "payload"
        if isinstance(node, ast.Name):
            assert node.id != "CANONICAL"


def test_detect_recurring_takes_plain_tuples_not_a_store():
    """The public signature is `(transactions, *, today, min_confidence=…)` —
    a caller never passes a Canonical/Sidecar/store handle."""
    import inspect

    sig = inspect.signature(detect_recurring)
    params = list(sig.parameters)
    assert params[0] == "transactions"
    assert "today" in sig.parameters
    for name in ("store", "canonical", "sidecar", "books"):
        assert name not in sig.parameters
