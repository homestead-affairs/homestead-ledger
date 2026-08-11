"""Running balance — derived over the books, never stored (I-25: the ledger
never authors a fact of its own; it only reflects what is already on record).

A running balance is arithmetic over `date` and `amount`, computed fresh on
every call. There is no `balance` field on any canonical record and no
sidecar record either — persisting one would be exactly the failure "mirror,
not judge" forbids: the ledger inventing and then storing its own financial
claim, rather than reflecting the transactions that are already there.

**This module reads `.payload` directly**, which is the one thing a rendering
surface must never do (I-16's shape, as homestead-law's chokepoint test
states it for its own package). That is deliberate and narrow: arithmetic
over an amount needs the actual number, the same way the engine's own
`Reader.deadlines()` (in `homestead.keep.store`) parses a raw payload to
compute urgency before anything is served. This module is the ledger's
analogous case — a computation over canonical content, not a rendering of it
— and *what it returns* (a running total) still has to cross the gate before
any surface shows it; that crossing is bite 3's, when a total is first drawn
on screen. Nothing in this bite serves a `BalancePoint` to a surface.
"""
from __future__ import annotations

from dataclasses import dataclass

from homestead_ledger.store import Canonical

__all__ = ["BalancePoint", "running_balance"]


@dataclass(frozen=True)
class BalancePoint:
    """One transaction's contribution to the running total, in posting-date
    order. `amount` and `running` are floats derived from the canonical
    strings — never written back anywhere."""

    item_id: str
    date: str
    amount: float
    running: float


def running_balance(canonical: Canonical, account: str) -> list[BalancePoint]:
    """Every transaction in `account`, oldest posting date first, each paired
    with the running total through that point.

    Reads the canonical `date` and `amount` fields for every transaction
    fingerprint under `account` and orders by the parsed date (not by
    fingerprint or import order, neither of which is chronological). A
    transaction missing either field (a torn import; see `books.py`'s
    documented limitation) is skipped rather than guessed at — an incomplete
    transaction contributes nothing to a total it cannot honestly join.
    """
    amounts: dict[str, str] = {}
    dates: dict[str, str] = {}
    for ref, record in canonical.records(account):
        _, field, item_id = ref
        if field == "amount":
            amounts[item_id] = record.payload
        elif field == "date":
            dates[item_id] = record.payload

    complete_ids = sorted(
        (i for i in amounts if i in dates),
        key=lambda i: (dates[i], i),
    )

    points: list[BalancePoint] = []
    total = 0.0
    for item_id in complete_ids:
        amount = float(amounts[item_id])
        total += amount
        points.append(
            BalancePoint(item_id=item_id, date=dates[item_id], amount=amount, running=round(total, 2))
        )
    return points
