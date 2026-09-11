"""Running balance — derived over the books, never stored.

`running_balance` reads the canonical `date`/`amount` fields and computes a
cumulative total; nothing it returns is written anywhere. That is the whole
of the invariant this file pins: call it twice, get the same answer, and the
store is untouched either time.

Bite 2b: a transaction's matter is a registered account *instance* label
(`make_account`, `conftest.py`), not a bare kind name.
"""
from __future__ import annotations

from homestead.keep import paths
from homestead.keep.store import CANONICAL, SQLiteAdapter

from homestead_ledger.balance import running_balance
from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.store import Canonical

LABEL = "chk-t"


def _seed(monkeypatch, tmp_path, make_account):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    import_transaction(Transaction(
        account=LABEL, kind="checking", date="2026-08-05", amount="-64.10",
        description="Electric Co",
    ))
    import_transaction(Transaction(
        account=LABEL, kind="checking", date="2026-08-01", amount="-84.23",
        description="Whole Foods Market",
    ))
    import_transaction(Transaction(
        account=LABEL, kind="checking", date="2026-08-03", amount="1500.00",
        description="Employer Payroll",
    ))


def test_running_balance_orders_by_posting_date_not_import_order(tmp_path, monkeypatch, make_account):
    _seed(monkeypatch, tmp_path, make_account)
    points = running_balance(Canonical(), LABEL)
    assert [p.date for p in points] == ["2026-08-01", "2026-08-03", "2026-08-05"]


def test_running_balance_accumulates_correctly(tmp_path, monkeypatch, make_account):
    _seed(monkeypatch, tmp_path, make_account)
    points = running_balance(Canonical(), LABEL)
    assert [p.amount for p in points] == [-84.23, 1500.00, -64.10]
    assert [p.running for p in points] == [-84.23, 1415.77, 1351.67]


def test_running_balance_over_an_empty_account_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    assert running_balance(Canonical(), LABEL) == []


def test_running_balance_writes_nothing(tmp_path, monkeypatch, make_account):
    """The derived-not-stored invariant, held behaviourally: calling it twice
    changes no row count in either table."""
    _seed(monkeypatch, tmp_path, make_account)
    running_balance(Canonical(), LABEL)
    running_balance(Canonical(), LABEL)

    adapter = SQLiteAdapter(paths.home() / "homestead-ledger.db")
    canonical_rows = adapter.read_matter(CANONICAL, LABEL)
    # 3 transactions x 3 fields (I-43: no per-transaction account_number) =
    # 9 canonical rows, unmoved by two calls.
    assert len(canonical_rows) == 9


def test_a_liability_balance_is_reported_as_owed(tmp_path, monkeypatch, make_account):
    """A charge is negative on the books (the same sign a debit gets); a
    payment is positive (the same sign a credit gets). Summed raw, that
    reads as a *negative* balance for a household in debt — arithmetically
    correct and not what "owed" means. `liability=True` must report the
    positive amount actually owed at each point instead."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    label = make_account("credit_card", number="4242")
    import_transaction(Transaction(
        account=label, kind="credit_card", date="2026-08-01",
        amount="-50.00", description="Hardware Store",
    ))
    import_transaction(Transaction(
        account=label, kind="credit_card", date="2026-08-05",
        amount="20.00", description="Payment",
    ))

    owed_points = running_balance(Canonical(), label, liability=True)
    assert [p.running for p in owed_points] == [50.00, 30.00]
    # the raw per-transaction amount is never flipped, only the running total
    assert [p.amount for p in owed_points] == [-50.00, 20.00]

    raw_points = running_balance(Canonical(), label)
    assert [p.running for p in raw_points] == [-50.00, -30.00]


def test_transaction_tuples_hand_the_recurring_pass_the_real_numbers(tmp_path, monkeypatch, make_account):
    """The recurring-charge detector takes plain `(date, amount, description)`
    tuples; this read at the payload boundary is what feeds it from the real
    books, oldest first, complete transactions only."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead_ledger.balance import transaction_tuples
    from homestead_ledger.books import Transaction, import_transaction
    from homestead_ledger.store import Canonical

    make_account("checking", label=LABEL, number="9821")
    import_transaction(Transaction(account=LABEL, kind="checking", date="2026-08-03", amount="1500.00",
                                   description="Employer Payroll"))
    import_transaction(Transaction(account=LABEL, kind="checking", date="2026-08-01", amount="-84.23",
                                   description="Whole Foods Market"))

    assert transaction_tuples(Canonical(), LABEL) == [
        ("2026-08-01", -84.23, "Whole Foods Market"),
        ("2026-08-03", 1500.0, "Employer Payroll"),
    ]
    assert transaction_tuples(Canonical(), LABEL) and transaction_tuples(Canonical(), "nothing") == []


# ── fix: G2c-importer-dates — sort by calendar day, not raw text ───────────

def test_running_balance_orders_by_calendar_not_lexically(tmp_path, monkeypatch, make_account):
    """A lexical sort of `["9/2/2026", "2026-10-01"]` puts the September row
    *after* October ('9' > '2' as the first character), which is exactly
    backwards. `9/2/2026` here stands for a pre-existing row from before
    fix: G2c-importer-dates — imported back when a date was stored verbatim
    and never parsed — and there is no migration for it (v1 is
    synthetic-only): it sorts after every real ISO date by the only ordering
    left for it (its own raw text), and `balance.is_iso_date` is what marks
    it as a gap for an operator to find."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    import_transaction(Transaction(
        account=LABEL, kind="checking", date="2026-10-01", amount="-10.00",
        description="October Row",
    ))
    import_transaction(Transaction(
        account=LABEL, kind="checking", date="9/2/2026", amount="-20.00",
        description="Pre-fix September Row",
    ))
    import_transaction(Transaction(
        account=LABEL, kind="checking", date="2026-09-02", amount="-30.00",
        description="ISO September Row",
    ))

    points = running_balance(Canonical(), LABEL)
    # both real calendar dates come first, in true calendar order; the
    # unparsed pre-existing row sorts last, never between them by accident
    # of lexical comparison.
    assert [p.date for p in points] == ["2026-09-02", "2026-10-01", "9/2/2026"]
