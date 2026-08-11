"""A synthetic checking account, for seeing the surfaces work end to end.

**Synthetic data only** — this writes to a throwaway store (a fresh
`HOMESTEAD_HOME`, set up by `__main__.py`), never a real household root. It
imports a few invented transactions through the same path bite 4's CSV
importer will use (`books.import_transaction`), then composes the list and
two details through the gate — store → serve → surface, headless:
`python -m homestead_ledger --demo`.

The values are invented; the rungs are the checking pack's real ones, so
what renders where is the real crossing, not a mock. `date` and
`description` (L2/L3) render as themselves; `amount` (L4) shows only its
derived debit/credit form on the list and its real value once the detail
pane is opened (opening it *is* the purpose declaration — I-13); the
`account_number` (L5) never becomes a row at all, and its detail is denied
outright, with no override anywhere.
"""
from __future__ import annotations

from homestead.keep.rungs import Disposition

from homestead_ledger.app.window import Ref, Window
from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.store import Canonical

ACCOUNT = "checking"

#: Three invented transactions, one account. Fixed so the demo's output is
#: stable across runs — the running app uses real imports (bite 4).
_DEMO_TRANSACTIONS: list[Transaction] = [
    Transaction(
        account=ACCOUNT, date="2026-08-01", amount="-84.23",
        description="Whole Foods Market", account_number="9821",
    ),
    Transaction(
        account=ACCOUNT, date="2026-08-03", amount="1500.00",
        description="Employer Payroll", account_number="9821",
    ),
    Transaction(
        account=ACCOUNT, date="2026-08-05", amount="-64.10",
        description="Electric Co", account_number="9821",
    ),
]


def seed() -> list[str]:
    """Import the demo transactions, returning their fingerprints in seed
    order. Not idempotent against itself on purpose: a second `seed()` call
    against the same store raises `RecordExists`, the same re-import refusal
    every real import gets — the demo does not special-case its own data."""
    return [import_transaction(txn) for txn in _DEMO_TRANSACTIONS]


def open_account(canonical: Canonical) -> Window:
    """Load the account from the books into a `Window`'s list pane."""
    window = Window()
    window.open_list(canonical.records(ACCOUNT))
    return window


def compose_demo() -> str:
    """Seed, list, and open two details — a headless proof of the whole
    pipeline, returning the text a view would draw so it can be read without
    a display.

    Starts and ends on the resting cover (I-21: nothing before a human asks;
    I-32: closing lets go of what was held). In between: the list — dates and
    the payee render, the amount shows its derived debit/credit form, the
    account number is silently absent (L5, dropped without a trace) — then
    the first transaction's amount opened in detail (renders, L4, opening the
    pane *is* the purpose declaration) and the same transaction's account
    number opened in detail (denied — L5 has no override anywhere).
    """
    item_ids = seed()
    canonical = Canonical()

    lines = [f"{ACCOUNT} — cover (resting): Nothing is open (I-21)"]

    window = open_account(canonical)
    lines.append(f"{ACCOUNT} — list (S1_LIST):")
    for row in window.rows:
        lines.append(f"  [{row.rung.value}] {row.text}")

    first_id = item_ids[0]
    amount_ref: Ref = (ACCOUNT, "amount", first_id)
    served = window.open_detail(amount_ref)
    shown = served.value if served.disposition is Disposition.RENDER else "(withheld)"
    lines.append(f"detail amount (S1_DETAIL): [{served.rung.value}] {shown}")

    number_ref: Ref = (ACCOUNT, "account_number", first_id)
    sealed = window.open_detail(number_ref)
    lines.append(
        f"detail account_number (S1_DETAIL): {sealed.disposition.value} (value={sealed.value!r})"
    )

    window.close()
    lines.append(f"{ACCOUNT} — cover (resting): {window.state} — Nothing is open (I-21/I-32)")
    return "\n".join(lines)
