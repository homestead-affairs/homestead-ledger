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
from datetime import date

from homestead_ledger.store import Canonical

__all__ = ["BalancePoint", "is_iso_date", "running_balance", "transaction_tuples"]


def is_iso_date(value: str) -> bool:
    """True if `value` is a calendar day `date.fromisoformat` accepts.

    This is the one check both the sort below and `transaction list --gaps`
    (`cli.py`) use to tell a genuinely-ordered row from a **pre-existing
    unparsed one** — a transaction the importer wrote before fix:
    G2c-importer-dates, back when a row's date column was stored verbatim
    (`08/11/2026`, say). There is no migration for such a row (v1 is
    synthetic-only); this is how it stays *findable* instead of silently
    misplaced. A caller may hand this a value already served through the
    gate (an L2 payload) without reaching `.payload` of its own.
    """
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True


def _sort_key(raw: str, item_id: str) -> tuple:
    """Order by the real calendar day when `raw` is ISO; a row whose date
    predates this fix and will not parse sorts after every real date, by its
    own raw text (the only ordering left available for it) — "falling back
    to lexical only for a row whose date will not parse", never for the rest.
    The leading `0`/`1` keeps the two groups from ever comparing a `date`
    against a `str` (Python cannot order those against each other).

    **This moves a pre-ISO row relative to where the old lexical sort put
    it.** `"08/11/2026"` used to sort *before* every `"2026-…"` row (`'0'` <
    `'2'`) and now sorts after all of them, so the running total each ISO row
    carries changes by that row's amount. That is a deliberate consequence of
    ordering by the calendar instead of by ASCII, and it is safe to make here
    because no surface in this package draws a `BalancePoint`: the only
    consumer of either sort is `recurring.detect_recurring`, through
    `transaction_tuples`, where an unparseable date joined no honest cadence
    under either ordering. `transaction list --gaps` is how the operator
    finds the rows this applies to; there is no migration (v1 is
    synthetic-only).

    The fallback key is `str(raw)`, not `raw`: a corrupt record whose stored
    payload is `null` hydrates to `None`, and two unparseable rows — one
    `None`, one a string — would otherwise make `sorted` itself raise
    `TypeError: '<' not supported between 'str' and 'NoneType'`, taking down
    the whole running balance rather than sorting the bad row last (I-11 —
    corruption is refused *by name*, never allowed to poison the read of
    every other row). `str(None)` is `'None'`, which `is_iso_date` still
    reports as a gap for `transaction list --gaps` to show."""
    try:
        return (0, date.fromisoformat(raw), item_id)
    except (TypeError, ValueError):
        return (1, str(raw), item_id)


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
        key=lambda i: _sort_key(dates[i], i),
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


def transaction_tuples(canonical: Canonical, account: str) -> list[tuple[str, float, str]]:
    """Every complete transaction in `account` as the plain `(date, amount,
    description)` tuples `recurring.detect_recurring` takes — oldest first.

    The recurring-charge pass needs the real amount and the real payee, so
    this read sits here at the payload boundary beside `running_balance`,
    and the detector stays a pure function over what it is handed. What the
    detector returns (a merchant, a cadence, an amount) is the household's own
    arithmetic over its own books — reflected, never authored — and a surface
    still receives it only as that summary, never as a `Classified`.
    """
    amounts: dict[str, str] = {}
    dates: dict[str, str] = {}
    descriptions: dict[str, str] = {}
    for ref, record in canonical.records(account):
        _, field, item_id = ref
        if field == "amount":
            amounts[item_id] = record.payload
        elif field == "date":
            dates[item_id] = record.payload
        elif field == "description":
            descriptions[item_id] = record.payload

    complete = sorted(
        (i for i in amounts if i in dates and i in descriptions),
        key=lambda i: _sort_key(dates[i], i),
    )
    out: list[tuple[str, float, str]] = []
    for item_id in complete:
        try:
            amount = float(amounts[item_id])
        except (TypeError, ValueError):
            continue   # an unreadable amount joins no pattern (I-8)
        out.append((str(dates[item_id]), amount, str(descriptions[item_id])))
    return out
