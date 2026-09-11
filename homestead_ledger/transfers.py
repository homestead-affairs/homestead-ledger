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

**The first fingerprint is the outgoing one, and that is checked.** A pair
record says money went *from* one account *to* another. An operator who
types the two fingerprints the other way round would otherwise get a record
that names the receiving account as the source — true of nothing — so
`pair()` refuses a first fingerprint whose amount is not negative and says
which way round the pair goes, rather than quietly normalizing it: the
operator asked for something that is not so, and a tool that silently
reinterprets that has taught them nothing.

**What this module does not own.** It does not decide what an aggregate
does with a pairing — `paired_fingerprints()` is the one seam this module
exposes for that, and a caller (an aggregate, or a future orchestrator) is
expected to union it with whatever else it excludes (`overlay.py`'s
`do_not_use`, on the sibling bite that grows alongside this one) rather than
this module reaching into that concern or that one reaching into this one.

**The boundary reach lives next door.** Reading whether two legs are
equal-and-opposite needs a real `amount` payload, and that read — with the
two others this module needs — is `transfers_boundary.py`, which is the file
on `tests/test_invariants_chokepoint.py`'s allow-list. This module is not:
it is held by the scan exactly like a surface, so the pairing logic, the
refusals and everything they grow into stay on the ordinary side of the one
door. See that module's docstring for why the smallest unit is the file.
"""
from __future__ import annotations

from collections import Counter
from typing import NamedTuple

from homestead.keep.logs import Event, VisibleLog
from homestead.keep.rungs import Classified, Disposition, Rung, Surface, serve

from homestead_ledger import accounts, transfers_boundary as boundary
from homestead_ledger.packs import transfers as pack
from homestead_ledger.store import Canonical, RecordExists, Ref, Replaced, Sidecar, key

__all__ = [
    "MATTER", "FIELDS", "WINDOW_DAYS", "Suggestion",
    "pair", "suggest", "paired_fingerprints", "counterpart_of", "other_label",
    "exclude_from", "is_commingled", "commingling_count",
]

MATTER = pack.MATTER
FIELDS = pack.FIELDS

#: The one record type this pack declares — named once so `pair()` and the
#: readers below cannot drift from each other or from `packs/transfers.py`.
_PAIR = "pair"

#: How many days apart a transfer's two legs may post and still count as one
#: movement — decision 9's own number, not a per-call knob on `pair()`
#: (`suggest()` alone takes a `window_days` override, for exploring a wider
#: net without changing what `pair()` itself will accept). The window is
#: **inclusive of both endpoints**: `abs(days_apart) <= WINDOW_DAYS`.
WINDOW_DAYS = 5

#: A pair record whose `counterpart` names nothing is a **retired** pairing —
#: the two legs it used to join are unpaired again, and every reader below
#: skips it. `homestead.keep.store`'s adapter seam is `read`/`read_matter`/
#: `insert`/`write`: there is no delete, by design (a record is never removed,
#: only superseded), so `--replace` says "this pairing is over" the only way
#: the store offers — by writing a record that names no counterpart and no
#: accounts. A retired key is re-usable: `pair()` treats it as free.
_RETIRED = ""


class Suggestion(NamedTuple):
    """One candidate pair `suggest()` proposes. `ambiguous` is true when the
    outgoing leg fits more than one incoming leg, or its one candidate fits
    more than one outgoing leg — every candidate of an ambiguous match is
    listed and marked, and none of them is ever paired automatically."""

    fp_out: str
    fp_in: str
    ambiguous: bool


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


def _retire(store: Sidecar, out_fp: str) -> Replaced | None:
    """Mark the pairing keyed by `out_fp` as over — see `_RETIRED`."""
    record = Classified(Rung.L2, {"counterpart": _RETIRED, "from": _RETIRED, "to": _RETIRED})
    return store.put(MATTER, _PAIR, out_fp, record, overwrite=True)


def pair(
    store: Sidecar, fp_out: str, fp_in: str, *, replace: bool = False,
) -> tuple[Ref, Replaced | None]:
    """Record that `fp_out` (an outflow) and `fp_in` (an inflow) are the two
    legs of one transfer. Returns the pair record's ref and, on an explicit
    replace, what it displaced.

    Refuses, before writing anything, and never by echoing an amount (I-15):

    * either fingerprint not found on the books (`_locate`);
    * both on the same account label — a transfer's two legs are two
      *different* accounts, and the same fingerprint twice is that case;
    * either row unreadable — a torn import, a `null` payload, a pre-ISO
      date (`transaction list --gaps`): refused by name, never guessed (I-11);
    * not equal-and-opposite in amount, or more than `WINDOW_DAYS` apart
      (inclusive of both endpoints);
    * `fp_out` not the outgoing leg (see the module docstring);
    * either fingerprint already part of a pair, on either side, unless
      `replace=True`.

    With `replace=True`, **every** pairing either fingerprint is part of is
    retired first, whichever key it is filed under, so an incoming leg
    re-pointed at a new outgoing leg leaves its old partner genuinely
    unpaired rather than half-joined to two pairs at once (which would make
    `counterpart_of`/`other_label` answer by dict order).

    On success, logs `Event.RECORD_ADDED` with the reference `(MATTER,
    fp_out)` only — never the counterpart, a label, or an amount (I-15).

    **The occupied-key refusal is the store's, not only the precondition's
    (I-9)**, the same posture `accounts.add_account`/`obligations.
    add_obligation` document for their own first field: the write is
    `overwrite=False` unless `replace`, so the adapter's own atomic insert
    is the gate a racing second `pair()` call cannot slip past. (The one
    exception is a *retired* key, which has to be written over to be
    re-used; a racing pair() on that same key is a window this single-
    operator tool accepts, as the precondition scan below already does.)
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

    fit = boundary.compatibility(canonical, label_out, out_fp, label_in, in_fp)
    if not fit.readable:
        raise ValueError(
            f"{out_fp!r} and {in_fp!r}: one of these two rows has no readable "
            "amount and date on file — a pairing is refused rather than "
            "guessed at (`transaction list --gaps` shows a row whose date "
            "will not parse)"
        )
    if not fit.equal_and_opposite:
        raise ValueError(
            f"{out_fp!r} and {in_fp!r} are not a matching pair — a transfer "
            "needs equal-and-opposite amounts on two different accounts"
        )
    if not fit.outgoing_first:
        raise ValueError(
            f"{out_fp!r} is the incoming leg of this pair — the first "
            "fingerprint must be the outgoing side, the account the money "
            "left, so the record's from/to say what actually happened. Swap "
            "the two."
        )
    if fit.days_apart is not None and fit.days_apart > WINDOW_DAYS:
        raise ValueError(
            f"{out_fp!r} and {in_fp!r} post {fit.days_apart} day(s) apart — a "
            f"transfer's two legs must fall within {WINDOW_DAYS} days of "
            "each other"
        )

    pairs = _pairs(store)
    if not replace:
        already = _fingerprints(pairs)
        clashing = out_fp if out_fp in already else (in_fp if in_fp in already else None)
        if clashing is not None:
            raise RecordExists(
                f"{clashing!r} is already part of a transfer pair. A write "
                "never silently overwrites (I-9): pass --replace (the CLI) "
                'or "replace": true (the UI) to replace it.'
            )

    # G8-business-books: a transfer whose two legs sit on accounts with
    # different owners crosses the household/business line — visible by
    # reference (I-15: never an amount), never refused, so a founder who
    # does pay a business expense personally still shows up on the books.
    commingling = accounts.owner_of(store, label_out) != accounts.owner_of(store, label_in)
    record = Classified(
        Rung.L2,
        {"counterpart": in_fp, "from": label_out, "to": label_in, "commingling": commingling},
    )
    ref = key(MATTER, _PAIR, out_fp)
    replaced: Replaced | None = None
    if replace:
        for stale_fp, value in pairs.items():
            if stale_fp == out_fp:
                continue          # about to be written over by this call anyway
            if stale_fp in (out_fp, in_fp) or value.get("counterpart") in (out_fp, in_fp):
                replaced = _retire(store, stale_fp) or replaced
        replaced = store.put(MATTER, _PAIR, out_fp, record, overwrite=True) or replaced
    elif out_fp in _retired(store):
        # The key is on file but names no pairing: re-using it is not a
        # clobber, so it is not the occupied-key refusal's business.
        store.put(MATTER, _PAIR, out_fp, record, overwrite=True)
    else:
        try:
            store.put(MATTER, _PAIR, out_fp, record, overwrite=False)
        except RecordExists:
            raise RecordExists(
                f"{out_fp!r} is already part of a transfer pair. A write "
                "never silently overwrites (I-9): pass --replace (the CLI) "
                'or "replace": true (the UI) to replace it.'
            ) from None
    # Event.RECORD_ADDED, referencing only the matter and the outgoing
    # fingerprint (the same economy `obligations.mark_paid` gives its own
    # `ITEM_RESOLVED` — a reference, never the counterpart or a label, and
    # never an amount, I-15).
    VisibleLog().record(Event.RECORD_ADDED, ref=(MATTER, out_fp))
    return ref, replaced


def _served_pairs(store: Sidecar) -> dict[str, dict]:
    """Every pair record on file, retired ones included, keyed by its
    outgoing fingerprint and each value already read through the gate
    (`serve()` — never `.payload` here: `pair` is `L2`, so `Served.value` on
    `S1_LIST` *is* the payload for a rung this far below the ceiling, and
    reading it that way is the door `accounts.py`/`obligations.py` already
    use for their own L2 records — not a second boundary)."""
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


def _is_live(value: dict) -> bool:
    """A pairing names a counterpart; a retired record (`_RETIRED`) does not."""
    counterpart = value.get("counterpart")
    return isinstance(counterpart, str) and counterpart != _RETIRED


def _pairs(store: Sidecar) -> dict[str, dict]:
    """Every *live* pairing, keyed by its outgoing fingerprint."""
    return {
        item_id: value for item_id, value in _served_pairs(store).items()
        if _is_live(value)
    }


def _retired(store: Sidecar) -> frozenset[str]:
    """Every key holding a retired pairing — a key `pair()` may write over."""
    return frozenset(
        item_id for item_id, value in _served_pairs(store).items() if not _is_live(value)
    )


def _fingerprints(pairs: dict[str, dict]) -> frozenset[str]:
    out: set[str] = set(pairs)
    for value in pairs.values():
        counterpart = value.get("counterpart")
        if isinstance(counterpart, str):
            out.add(counterpart)
    return frozenset(out)


def paired_fingerprints(store: Sidecar) -> frozenset[str]:
    """Every fingerprint on either side of a live pair — the seam an
    aggregate (`recurring.detect_recurring`, a running balance) unions with
    whatever else it excludes (`overlay.py`'s `do_not_use`) before it sums or
    scans; this module defines no exclusion mechanism of its own beyond this
    set."""
    return _fingerprints(_pairs(store))


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


def is_commingled(store: Sidecar, fp: str) -> bool:
    """Whether `fp`'s pair — from either side — crosses the household/
    business line (G8-business-books). `False` for an unpaired fingerprint,
    the same "absence is a decision, not a gap" posture `counterpart_of`
    already takes."""
    pairs = _pairs(store)
    value = pairs.get(fp)
    if value is not None:
        return bool(value.get("commingling"))
    for value in pairs.values():
        if value.get("counterpart") == fp:
            return bool(value.get("commingling"))
    return False


def commingling_count(store: Sidecar) -> int:
    """How many live pairs cross the household/business line — a count only
    (I-15/I-8: never which pair, never an amount), what `budget show`/
    `/api/budget` carry as `commingling: N`."""
    return sum(1 for value in _pairs(store).values() if value.get("commingling"))


def suggest(store: Sidecar, *, window_days: int = WINDOW_DAYS) -> list[Suggestion]:
    """Candidate transfer pairs among transactions not already paired —
    equal-and-opposite amounts, on two different accounts, posted within
    `window_days` of each other. Proposes; **writes nothing** — an operator
    (or a caller acting on their behalf) still calls `pair()` to record one.

    **Ambiguity is reported, never resolved.** A candidate is unambiguous
    only when the two legs fit each other and nothing else: one compatible
    inflow for that outflow, and one compatible outflow for that inflow.
    Anything else lists *every* candidate, each marked `ambiguous`, so the
    operator sees that there is a choice to make instead of a guess this
    module made for them — two `-40.00` sweeps landing in two accounts the
    same day are exactly a case where picking one would be wrong half the
    time, and silently wrong every time.

    Deterministic and order-independent: candidates are found by fit rather
    than by a first-come claim, and are listed oldest outflow first.
    """
    canonical = Canonical()
    excluded = paired_fingerprints(store)
    outflows: list[tuple[str, boundary.SignedRow]] = []
    inflows: list[tuple[str, boundary.SignedRow]] = []
    for label in accounts.instances(store):
        for row in boundary.signed_rows(canonical, label, skip=excluded):
            (outflows if row.amount < 0 else inflows).append((label, row))
    outflows.sort(key=lambda e: (e[1].day, e[1].item_id))
    inflows.sort(key=lambda e: (e[1].day, e[1].item_id))

    def _fits(out: tuple[str, boundary.SignedRow], inn: tuple[str, boundary.SignedRow]) -> bool:
        return (
            out[0] != inn[0]
            and out[1].amount + inn[1].amount == 0
            and abs((inn[1].day - out[1].day).days) <= window_days
        )

    candidates = [[inn for inn in inflows if _fits(out, inn)] for out in outflows]
    fits_per_inflow: Counter[str] = Counter()
    for matches in candidates:
        fits_per_inflow.update(inn[1].item_id for inn in matches)

    found: list[Suggestion] = []
    for (_, out), matches in zip(outflows, candidates):
        if not matches:
            continue
        ambiguous = len(matches) > 1 or fits_per_inflow[matches[0][1].item_id] > 1
        found.extend(Suggestion(out.item_id, inn.item_id, ambiguous) for _, inn in matches)
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

    **One paired row drops one tuple, not every tuple that looks like it.**
    `transaction_tuples` carries no item id, so the match has to be by
    content — and two *different* transactions can share one `(date, amount,
    description)` triple even though their fingerprints differ, because the
    fingerprint is over the exact strings (`-100.00` and `-100.0` are two
    rows; `float()` makes them one tuple). Dropping by content alone would
    take the unpaired one with it and hide a real charge from the recurring
    detector. So the drop is counted: as many tuples go as there are paired
    fingerprints on this account with that content, and the rest stay. Which
    of two identical tuples survives does not matter — they are identical to
    every caller of this function.

    **X7-drift correction: the overlay bite landed, and the honest filter
    is what every real caller now uses instead of this function.**
    `overlay.py` added `balance.dated_transactions` — `transaction_tuples`
    with the item id still attached — and every aggregate that reads through
    it (`budget.envelopes`, `grant_report.by_use`, `server.py`'s
    subscriptions pass) filters by fingerprint directly:
    `overlay.excluded_fingerprints(sidecar) | paired_fingerprints(sidecar)`,
    the union this module's seam was always for. None of them call
    `exclude_from` any more. This function's content-counting stays — tested
    below, not dead code deleted out from under a caller that might still
    reach it — for the one seam that still only has plain `(date, amount,
    description)` tuples with no item id attached, the shape
    `transaction_tuples` (not `dated_transactions`) still returns.
    """
    paired = paired_fingerprints(sidecar)
    if not paired:
        return list(tuples)
    budget = Counter(boundary.content_rows(canonical, label, paired))
    if not budget:
        return list(tuples)
    kept: list[tuple[str, float, str]] = []
    for item in tuples:
        if budget[item] > 0:
            budget[item] -= 1
            continue
        kept.append(item)
    return kept
