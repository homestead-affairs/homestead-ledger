"""The payload reach transfers need — and nothing else.

`transfers.py` pairs two transactions, and deciding whether two rows *are*
one transfer needs their real `amount` and their real `date`: `amount` is
`L4` on every account pack and derives on `S1_LIST` ("a debit is on file",
never the number), so equal-and-opposite cannot be read through the ordinary
gate the way `date` (`L2`) can.

That reach is the reason this module exists **as its own file**. The
chokepoint allow-list in `tests/test_invariants_chokepoint.py` is per file,
so allow-listing `transfers.py` itself would put the whole feature — every
refusal, every reader, and everything either grows into later — outside the
one scan that holds the package's surfaces to the gate. The rule is that the
chokepoint admits the *smallest* unit, so the three reads live here, alone,
and `transfers.py` is a surface like any other: it is held by the scan, and
`tests/test_transfers.py` holds this file to exactly these three functions.

**Reads, never policy.** Nothing here knows what `WINDOW_DAYS` is, what a
"transfer" is, or what to do about any answer it gives. `compatibility()`
hands back three booleans and a day count — never an amount, never a date —
so every refusal built on it can name two fingerprints and nothing else
(I-15). `signed_rows()` and `content_rows()` hand back the same derived
readings `balance.py` already hands `recurring.detect_recurring`, for
callers that are doing arithmetic rather than rendering.

**Corruption refuses, it never raises.** A `null` payload (the shape
`balance.py`'s own sort key documents) hydrates to `None`, and `Decimal(None)`
/ `date.fromisoformat(None)` raise `TypeError` — which, unhandled, is a
traceback on the operator's terminal and a 500 in the browser. Every read
here reports an unreadable row as unreadable (I-11: corruption is refused by
name upstream, never allowed to poison the read of every other row).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from homestead_ledger.money import decimal_amount
from homestead_ledger.store import Canonical

__all__ = ["Compatibility", "SignedRow", "compatibility", "signed_rows", "content_rows"]

#: The three canonical fields a transaction carries (`books._FIELD_ORDER`),
#: named once here so the reads below cannot drift from each other.
_AMOUNT = "amount"
_DATE = "date"
_DESCRIPTION = "description"


@dataclass(frozen=True)
class Compatibility:
    """What two rows are to each other — booleans and a day count, no values.

    `readable` is false when either row is missing a field or carries one
    that will not parse; the other three are then meaningless and the caller
    refuses on `readable` alone. `outgoing_first` says the *first* row named
    is the one money left (a negative amount), which is what makes a pair
    record's `from`/`to` honest rather than whichever way round the operator
    happened to type the two fingerprints.
    """

    readable: bool
    equal_and_opposite: bool
    outgoing_first: bool
    days_apart: int | None


@dataclass(frozen=True)
class SignedRow:
    """One complete, readable transaction: its id, its exact amount, its day."""

    item_id: str
    amount: Decimal
    day: date


def _amount_of(raw: object) -> Decimal | None:
    """`raw` as this package's one reading of money (`money.decimal_amount` —
    exact, and refusing `nan`/`inf`), or `None` if it will not read.

    `Decimal` and not `float`: two legs a cent apart at a magnitude binary
    floating point cannot resolve (`float("99999999999999999.01") +
    float("-99999999999999999.02") == 0.0`) would otherwise pair as
    equal-and-opposite. `tests/test_transfers.py` plants exactly that.
    """
    try:
        return decimal_amount(raw)
    except ValueError:
        return None


def _day_of(raw: object) -> date | None:
    """`raw` as a calendar day, or `None` — a pre-ISO row (`transaction list
    --gaps`) and a corrupt one both land here."""
    try:
        return date.fromisoformat(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def compatibility(
    canonical: Canonical, label_out: str, fp_out: str, label_in: str, fp_in: str,
) -> Compatibility:
    """Whether two transactions could be one transfer's two legs.

    Reads exactly the `amount` and `date` of exactly the two rows named —
    one `get()` per field per row, four in all, nothing else on either
    account — and returns only booleans and a day count.
    `tests/test_transfers.py` holds this exact read footprint against a spy
    on `Canonical.get`.
    """
    try:
        amount_out = _amount_of(canonical.get(label_out, _AMOUNT, fp_out).payload)
        date_out = _day_of(canonical.get(label_out, _DATE, fp_out).payload)
        amount_in = _amount_of(canonical.get(label_in, _AMOUNT, fp_in).payload)
        date_in = _day_of(canonical.get(label_in, _DATE, fp_in).payload)
    except KeyError:
        # A torn transaction (books.py's own documented limitation) is not a
        # pairable one, and is reported as unreadable rather than as a pair
        # that happens not to match.
        return Compatibility(False, False, False, None)
    if amount_out is None or amount_in is None or date_out is None or date_in is None:
        return Compatibility(False, False, False, None)
    return Compatibility(
        readable=True,
        equal_and_opposite=(amount_out + amount_in == 0 and amount_out != 0),
        outgoing_first=amount_out < 0,
        days_apart=abs((date_in - date_out).days),
    )


def signed_rows(
    canonical: Canonical, label: str, *, skip: frozenset[str] = frozenset(),
) -> list[SignedRow]:
    """Every complete, readable, non-zero transaction on `label`, by id.

    The scan `suggest()` runs its candidate matching over. A row missing
    either field, carrying an amount or a date that will not read, or
    amounting to zero (no sign, so no side of a transfer) is left out rather
    than guessed at; `skip` drops the fingerprints the caller has already
    spoken for.
    """
    amounts: dict[str, object] = {}
    dates: dict[str, object] = {}
    for (_, field, item_id), record in canonical.records(label):
        if item_id in skip:
            continue
        if field == _AMOUNT:
            amounts[item_id] = record.payload
        elif field == _DATE:
            dates[item_id] = record.payload
    rows: list[SignedRow] = []
    for item_id in sorted(amounts):
        amount = _amount_of(amounts[item_id])
        day = _day_of(dates.get(item_id))
        if amount is None or day is None or amount == 0:
            continue
        rows.append(SignedRow(item_id=item_id, amount=amount, day=day))
    return rows


def content_rows(
    canonical: Canonical, label: str, fingerprints: frozenset[str] | set[str],
) -> list[tuple[str, float, str]]:
    """The `(date, amount, description)` triples of exactly `fingerprints`,
    for the ones that are on `label` — the shape, and deliberately the same
    `float()` reading, `balance.transaction_tuples` returns, so a caller can
    compare the two directly. A fingerprint that is not on this account, or
    whose row is torn or unreadable, contributes nothing.
    """
    out: list[tuple[str, float, str]] = []
    for fp in sorted(fingerprints):
        if not canonical.has(label, _DATE, fp):
            continue
        try:
            when = canonical.get(label, _DATE, fp).payload
            amount = canonical.get(label, _AMOUNT, fp).payload
            description = canonical.get(label, _DESCRIPTION, fp).payload
        except KeyError:
            continue
        try:
            out.append((str(when), float(amount), str(description)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return out
