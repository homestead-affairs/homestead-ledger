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

from homestead.keep.rungs import Classified, Disposition

from homestead_ledger import queue as queue_mod
from homestead_ledger import recurring
from homestead_ledger.app.window import Ref, Window
from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.packs import obligations
from homestead_ledger.store import Canonical, Sidecar

ACCOUNT = "checking"

#: A fixed reference date, so the seeded obligations have stable urgency in
#: the demo — the running app uses the real today (mirrors homestead-law's
#: `app/demo.py::TODAY`).
TODAY = "2026-08-10"

#: Invented transactions, one account. Fixed so the demo's output is stable
#: across runs — the running app uses real imports (bite 4). Three one-off
#: merchants, plus a **recurring** monthly charge (Netflix, three months) so the
#: recurring-charge pass has a real pattern to find, the way a real statement
#: would — a subscription is just a checking transaction.
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
    # A monthly subscription, three months running — the recurring pattern.
    Transaction(
        account=ACCOUNT, date="2026-05-15", amount="-15.99",
        description="Netflix", account_number="9821",
    ),
    Transaction(
        account=ACCOUNT, date="2026-06-15", amount="-15.99",
        description="Netflix", account_number="9821",
    ),
    Transaction(
        account=ACCOUNT, date="2026-07-15", amount="-15.99",
        description="Netflix", account_number="9821",
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


# ── bite 2 — "what's due": obligations, the queue, and recurring charges ────

#: item id → (name, amount, due_date, cadence). Invented content; real rungs
#: (`packs.obligations.FIELDS`). Urgency is reckoned against `TODAY`
#: (2026-08-10): rent is overdue, insurance is due soon, registration is far
#: off — the same overdue/soon/far-off spread homestead-law's demo deadlines
#: give its own queue.
_DEMO_OBLIGATIONS: dict[str, tuple[str, str, str, str]] = {
    "rent": ("Sunrise Properties LLC", "-1450.00", "2026-08-05", "monthly"),        # overdue by 5
    "insurance": ("Homestead Mutual Auto", "-96.40", "2026-08-12", "monthly"),      # due in 2
    "registration": ("County DMV", "-180.00", "2026-11-01", "annual"),              # due in 83
}

#: field → the stand-in text for its L3/L4 rungs (`Classified` requires one).
#: `due_date`/`cadence` (L2) need none.
_DERIVED = {"name": "a payee is on file", "amount": "a payment is due"}


def seed_obligations(store: Sidecar) -> None:
    """Write the synthetic obligations into the sidecar — the household's
    own overlay, not the bank-imported canonical books (`books.py`'s
    concern). Each field becomes one record keyed `(obligations, <field>,
    <item id>)`, classified at the pack's declared rung, mirroring
    `packs.checking`'s one-record-per-field shape."""
    kind = obligations.OBLIGATION
    for item_id, (name, amount, due_date, cadence) in _DEMO_OBLIGATIONS.items():
        values = {"name": name, "amount": amount, "due_date": due_date, "cadence": cadence}
        for field, value in values.items():
            rung = obligations.FIELDS[field]
            classified = Classified(rung, value, _DERIVED.get(field))
            store.put(kind, field, item_id, classified, overwrite=True)


def compose_queue(store: Sidecar, today: str = TODAY) -> str:
    """Seed the obligations and render the queue — the store→dates→gate
    pipeline for *what is due*, headless. Overdue first, then soonest; the
    resting cover shows nothing over the single obligation kind bite 2
    registers (I-31), even though the queue itself has items."""
    seed_obligations(store)
    lines = [f"{obligations.OBLIGATION} — what's due, as of {today}:"]
    for item in queue_mod.queue(store, today=today):
        if item.gap:
            mark = "date unreadable"
        elif item.overdue:
            mark = f"overdue by {abs(item.days_until)} days"
        else:
            mark = f"due in {item.days_until} days"
        lines.append(f"  [{item.rung.value}] {item.ref[2]}: {item.shown} — {mark}")

    resting = queue_mod.cover(store, today=today)
    lines.append(
        f"cover (resting): {resting or 'Nothing is open — one obligation kind (I-31)'}"
    )
    return "\n".join(lines)


def compose_recurring(today: str = TODAY) -> str:
    """The recurring-charge detector run over the same synthetic checking
    transactions the books demo seeds — headless, no store involved
    (`recurring.py` takes plain transaction data, never a handle). The demo
    data carries a monthly Netflix charge across three months, so the detector
    surfaces it (cadence, next-expected); the one-off merchants fall below the
    minimum-occurrence bar and are correctly ignored. The `if not found`
    branch stays as an honest fallback if the demo data ever loses its
    pattern."""
    from datetime import date as _date

    txns = [(t.date, float(t.amount), t.description) for t in _DEMO_TRANSACTIONS]
    found = recurring.detect_recurring(txns, today=_date.fromisoformat(today))
    if not found:
        return (
            f"recurring — 0 recurring charge(s) detected among {len(txns)} demo "
            "transactions (each merchant appears once; too few for a pattern)"
        )
    lines = [f"recurring — {len(found)} recurring charge(s) detected:"]
    for charge in found:
        lines.append(f"  {charge.merchant} — {charge.cadence}, next expected {charge.next_expected}")
    return "\n".join(lines)
