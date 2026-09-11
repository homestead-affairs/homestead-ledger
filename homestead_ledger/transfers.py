"""Transfers between the household's own accounts (decision 9).

A transfer posts twice on the real books — a debit leaving one account, a
credit landing in another — and without a way to say "these two rows are one
movement", every aggregate over the books sees them as two unrelated facts:
`recurring.detect_recurring` can mistake a monthly savings sweep for a
subscription, and a running balance would count money that never actually
left the household. This module lets an operator (or `suggest()`, on its
behalf) say the two rows are one transfer — never automatically, and never
by editing either row: `pair()` writes one **sidecar** record
(`packs/transfers.py`'s schema), keyed by the **outgoing** leg's fingerprint,
naming the incoming leg's fingerprint and both accounts' labels. Nothing
here ever touches `CANONICAL` (mirror, not judge stays books.py's alone).

**What this module does not own.** It does not decide what an aggregate
does with a pairing — `paired_fingerprints()` is the one seam this module
exposes for that, and a caller (an aggregate, or a future orchestrator) is
expected to union it with whatever else it excludes (`overlay.py`'s
`do_not_use`, on the sibling bite that grows alongside this one) rather than
this module reaching into that concern or that one reaching into this one.

**The boundary reach.** `amount` is `L4` on every account pack and derives
on `S1_LIST` (`"a debit is on file"`, never the number) — so whether two
legs are equal-and-opposite cannot be read through the ordinary gate the way
`date` (`L2`) can. `_compatible()` is the one place beyond `books.py`/
`balance.py` this package reads a real `.payload` (an addition to
`tests/test_invariants_chokepoint.py`'s allow-list, with its own scope test
holding it to exactly two rows and two fields — see that module). It hands
back only a bool and a day count, never the amounts or the dates, so every
refusal built from it can name the two fingerprints and never an amount
(I-15).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from homestead.keep.logs import Event, VisibleLog
from homestead.keep.rungs import Classified, Disposition, Rung, Surface, serve

from homestead_ledger import accounts
from homestead_ledger.packs import transfers as pack
from homestead_ledger.store import Canonical, RecordExists, Ref, Replaced, Sidecar, key

__all__ = [
    "MATTER", "FIELDS", "WINDOW_DAYS",
    "pair", "suggest", "paired_fingerprints", "counterpart_of", "other_label",
    "exclude_from",
]

MATTER = pack.MATTER
FIELDS = pack.FIELDS

#: The one record type this pack declares — named once so `pair()` and the
#: readers below cannot drift from each other or from `packs/transfers.py`.
_PAIR = "pair"

#: How many days apart a transfer's two legs may post and still count as one
#: movement — decision 9's own number, not a per-call knob on `pair()`
#: (`suggest()` alone takes a `window_days` override, for exploring a wider
#: net without changing what `pair()` itself will accept).
WINDOW_DAYS = 5


def _locate(canonical: Canonical, sidecar: Sidecar, fp: str) -> str | None:
    """The account label `fp`'s transaction is filed under, or `None`.

    A reference lookup, never a payload: `Reader.has()` reads the adapter's
    raw blob only to say whether a key exists, and never hydrates it into a
    `Classified` — the same reach `cli.py`'s own `--gaps` makes against a
    row's `ref`, one level down. `date` is the field every transaction has
    (`books.py`'s own de-duplication gate), so it is the one checked here.
    """
    for label in accounts.instances(sidecar):
        if canonical.has(label, "date", fp):
            return label
    return None


def _compatible(
    canonical: Canonical, label_out: str, fp_out: str, label_in: str, fp_in: str,
) -> tuple[bool, int]:
    """Whether two transactions could be one transfer's two legs.

    Reads exactly the `amount` and `date` payload of exactly the two rows
    named — one `get()` per field per row, four in all, nothing else on
    either account — and returns only whether the amounts are
    equal-and-opposite and how many days apart the two dates fall. See the
    module docstring on why this, and only this, function reaches a raw
    payload; `tests/test_transfers.py` holds this exact read footprint
    against a spy on `Canonical.get`.
    """
    try:
        amount_out = canonical.get(label_out, "amount", fp_out).payload
        date_out = canonical.get(label_out, "date", fp_out).payload
        amount_in = canonical.get(label_in, "amount", fp_in).payload
        date_in = canonical.get(label_in, "date", fp_in).payload
    except KeyError:
        # A torn transaction (see books.py's own documented limitation) is
        # not a pairable one — refused the same way an incompatible pair is,
        # never distinguished by a message that would need to say why.
        return False, 0
    try:
        equal_and_opposite = (
            Decimal(amount_out) + Decimal(amount_in) == 0 and Decimal(amount_out) != 0
        )
    except InvalidOperation:
        equal_and_opposite = False
    try:
        delta = abs((date.fromisoformat(date_in) - date.fromisoformat(date_out)).days)
    except ValueError:
        delta = 10**6  # an unparseable date never falls inside any window
    return equal_and_opposite, delta


def pair(
    store: Sidecar, fp_out: str, fp_in: str, *, replace: bool = False,
) -> tuple[Ref, Replaced | None]:
    """Record that `fp_out` (an outflow) and `fp_in` (an inflow) are the two
    legs of one transfer. Returns the pair record's ref and, on an explicit
    replace, what it displaced.

    Refuses, before writing anything, and never by echoing an amount (I-15):

    * either fingerprint not found on the books (`_locate`);
    * both on the same account label — a transfer's two legs are two
      *different* accounts;
    * not equal-and-opposite in amount, or more than `WINDOW_DAYS` apart
      (`_compatible`, the one boundary reach this module makes);
    * either fingerprint already part of a pair, on either side, unless
      `replace=True`.

    On success, logs `Event.RECORD_ADDED` with the reference `(MATTER,
    fp_out)` only — never the counterpart, a label, or an amount (I-15).

    **The occupied-key refusal is the store's, not only the precondition's
    (I-9)**, the same posture `accounts.add_account`/`obligations.
    add_obligation` document for their own first field: the write is
    `overwrite=False` unless `replace`, so the adapter's own atomic insert
    is the gate a racing second `pair()` call cannot slip past.
    """
    out_fp = str(fp_out).strip()
    in_fp = str(fp_in).strip()
    if not out_fp or not in_fp:
        raise ValueError("a transfer pairs two transaction fingerprints")

    canonical = Canonical()
    label_out = _locate(canonical, store, out_fp)
    if label_out is None:
        raise ValueError(f"{out_fp!r}: no such transaction fingerprint on the books")
    label_in = _locate(canonical, store, in_fp)
    if label_in is None:
        raise ValueError(f"{in_fp!r}: no such transaction fingerprint on the books")
    if label_out == label_in:
        raise ValueError(
            f"{out_fp!r} and {in_fp!r} are both on {label_out!r} — a "
            "transfer's two legs must be on two different accounts"
        )

    equal_and_opposite, days_apart = _compatible(canonical, label_out, out_fp, label_in, in_fp)
    if not equal_and_opposite:
        raise ValueError(
            f"{out_fp!r} and {in_fp!r} are not a matching pair — a transfer "
            "needs equal-and-opposite amounts on two different accounts"
        )
    if days_apart > WINDOW_DAYS:
        raise ValueError(
            f"{out_fp!r} and {in_fp!r} post {days_apart} day(s) apart — a "
            f"transfer's two legs must fall within {WINDOW_DAYS} days of "
            "each other"
        )

    if not replace:
        already = paired_fingerprints(store)
        clashing = out_fp if out_fp in already else (in_fp if in_fp in already else None)
        if clashing is not None:
            raise RecordExists(
                f"{clashing!r} is already part of a transfer pair. A write "
                "never silently overwrites (I-9): pass --replace (the CLI) "
                'or "replace": true (the UI) to replace it.'
            )

    record = Classified(Rung.L2, {"counterpart": in_fp, "from": label_out, "to": label_in})
    ref = key(MATTER, _PAIR, out_fp)
    if replace:
        replaced = store.put(MATTER, _PAIR, out_fp, record, overwrite=True)
    else:
        try:
            store.put(MATTER, _PAIR, out_fp, record, overwrite=False)
        except RecordExists:
            raise RecordExists(
                f"{out_fp!r} is already part of a transfer pair. A write "
                "never silently overwrites (I-9): pass --replace (the CLI) "
                'or "replace": true (the UI) to replace it.'
            ) from None
        replaced = None
    # Event.RECORD_ADDED, referencing only the matter and the outgoing
    # fingerprint (the same economy `obligations.mark_paid` gives its own
    # `ITEM_RESOLVED` — a reference, never the counterpart or a label, and
    # never an amount, I-15).
    VisibleLog().record(Event.RECORD_ADDED, ref=(MATTER, out_fp))
    return ref, replaced


def _pairs(store: Sidecar) -> dict[str, dict]:
    """Every pair on file, keyed by its outgoing fingerprint, each value
    already read through the gate (`serve()` — never `.payload` here: `pair`
    is `L2`, so `Served.value` on `S1_LIST` *is* the payload for a rung this
    far below the ceiling, and reading it that way is the door
    `accounts.py`/`obligations.py` already use for their own L2 records —
    not a second boundary)."""
    out: dict[str, dict] = {}
    for (_, field, item_id), record in store.records(MATTER):
        if field != _PAIR:
            continue
        served = serve(record, Surface.S1_LIST)
        if served.disposition is Disposition.DENY:
            continue
        if isinstance(served.value, dict):
            out[item_id] = served.value
    return out


def paired_fingerprints(store: Sidecar) -> frozenset[str]:
    """Every fingerprint on either side of a pair — the seam an aggregate
    (`recurring.detect_recurring`, a running balance) unions with whatever
    else it excludes (`overlay.py`'s `do_not_use`) before it sums or scans;
    this module defines no exclusion mechanism of its own beyond this set."""
    pairs = _pairs(store)
    out: set[str] = set(pairs)
    for value in pairs.values():
        counterpart = value.get("counterpart")
        if isinstance(counterpart, str):
            out.add(counterpart)
    return frozenset(out)


def counterpart_of(store: Sidecar, fp: str) -> str | None:
    """The other leg's fingerprint, from either side of a pair, or `None`."""
    pairs = _pairs(store)
    value = pairs.get(fp)
    if value is not None:
        counterpart = value.get("counterpart")
        return counterpart if isinstance(counterpart, str) else None
    for out_fp, value in pairs.items():
        if value.get("counterpart") == fp:
            return out_fp
    return None


def other_label(store: Sidecar, fp: str) -> str | None:
    """The account label of `fp`'s *counterpart* leg, or `None` if `fp` is
    not paired — what `transaction list`/`/api/transactions` annotate a
    paired row with ("transfer → visa-chase"), by reference only."""
    pairs = _pairs(store)
    value = pairs.get(fp)
    if value is not None:
        to_label = value.get("to")
        return to_label if isinstance(to_label, str) else None
    for value in pairs.values():
        if value.get("counterpart") == fp:
            from_label = value.get("from")
            return from_label if isinstance(from_label, str) else None
    return None


def suggest(store: Sidecar, *, window_days: int = WINDOW_DAYS) -> list[tuple[str, str]]:
    """Candidate transfer pairs among transactions not already paired —
    equal-and-opposite amounts, on two different accounts, posted within
    `window_days` of each other. Proposes; **writes nothing** — an operator
    (or a caller acting on their behalf) still calls `pair()` to record one.

    Deterministic: candidates are matched oldest-first and each fingerprint
    is used in at most one proposed pair, so the same books always suggest
    the same pairs in the same order.
    """
    canonical = Canonical()
    excluded = paired_fingerprints(store)
    outflows: list[tuple[str, str, Decimal, date]] = []
    inflows: list[tuple[str, str, Decimal, date]] = []
    for label in accounts.instances(store):
        amounts: dict[str, str] = {}
        dates: dict[str, str] = {}
        for ref, record in canonical.records(label):
            _, field, item_id = ref
            if item_id in excluded:
                continue
            if field == "amount":
                amounts[item_id] = record.payload
            elif field == "date":
                dates[item_id] = record.payload
        for item_id, raw_amount in amounts.items():
            raw_date = dates.get(item_id)
            if raw_date is None:
                continue
            try:
                amount = Decimal(raw_amount)
                when = date.fromisoformat(raw_date)
            except (InvalidOperation, ValueError):
                continue
            entry = (label, item_id, amount, when)
            if amount < 0:
                outflows.append(entry)
            elif amount > 0:
                inflows.append(entry)

    used: set[str] = set()
    found: list[tuple[str, str]] = []
    for label_out, fp_out, amount_out, date_out in sorted(outflows, key=lambda e: (e[3], e[1])):
        if fp_out in used:
            continue
        for label_in, fp_in, amount_in, date_in in sorted(inflows, key=lambda e: (e[3], e[1])):
            if fp_in in used or label_in == label_out:
                continue
            if amount_out + amount_in != 0:
                continue
            if abs((date_in - date_out).days) > window_days:
                continue
            found.append((fp_out, fp_in))
            used.add(fp_out)
            used.add(fp_in)
            break
    return found


def exclude_from(
    canonical: Canonical, sidecar: Sidecar, label: str,
    tuples: list[tuple[str, float, str]],
) -> list[tuple[str, float, str]]:
    """`tuples` (as `balance.transaction_tuples(canonical, label)` returns
    them) with every transfer leg on `label` dropped — the exclusion an
    aggregate over the real books (`recurring.detect_recurring`; a running
    balance, when one is drawn) applies **at the caller**, never inside
    `balance.py` itself, which stays every transaction, paired or not.

    Matched by content rather than by fingerprint: `transaction_tuples`
    carries no item id, but a transaction is already unique by `(date,
    amount, description)` within one account — its own fingerprint folds in
    the account number too, so two rows sharing those three fields on the
    same account would already have collided at import and never both
    exist. This is the one other place besides `_compatible` that this
    module reads a raw `date`/`amount`/`description` payload, over exactly
    the fingerprints `paired_fingerprints` names for this account.
    """
    excluded_fps = {
        fp for fp in paired_fingerprints(sidecar) if canonical.has(label, "date", fp)
    }
    if not excluded_fps:
        return list(tuples)
    drop: set[tuple[str, float, str]] = set()
    for fp in excluded_fps:
        try:
            when = canonical.get(label, "date", fp).payload
            amount = float(canonical.get(label, "amount", fp).payload)
            description = canonical.get(label, "description", fp).payload
        except (KeyError, TypeError, ValueError):
            continue
        drop.add((when, amount, description))
    return [t for t in tuples if t not in drop]
