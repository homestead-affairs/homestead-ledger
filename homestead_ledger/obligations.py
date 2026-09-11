"""Obligations the household enters itself — rent, insurance, a subscription.

The obligations pack (`packs/obligations.py`) declared the fields and the queue
(`queue.py`) reads their due dates, but until now the only writer was `app.demo`'s
synthetic seed and a `put` that filed one field under a random id in the wrong
matter, where the queue never looked. This module is the writer, in exactly the
shape the demo seeds and the queue and window read: **one record per field**,
keyed `(obligations, <field>, <item id>)`, each at the pack's declared rung —
`name` L3 (a payee), `amount` L4 (money tied to a bill; the list shows only
*"a payment is due"*), `due_date` and `cadence` L2.

The **item id** is the household's own short name for the bill — `rent`,
`car-insurance` — and is the reference the queue carries (I-15). It is validated
against one closed shape (`^[a-z0-9][a-z0-9-]{0,39}$`, the id shape the build
plan fixes for every matter instance) before anything is written: a key segment
the engine would accept can still carry a quote, and this id is rendered back
into the browser. A first write refuses an occupied id (I-9); replacing an
obligation is an explicit act (`replace=True`) that reports what it displaced.

Reading back goes through the gate, field by field, on the list surface: the
payee, the due date and the cadence render; the amount derives. Opening one
(`S1_DETAIL`) is the purpose declaration, and the amount renders there. Nothing
in this module reaches a `.payload`.

**`mark_paid` is the fourth writer this module carries** (`cadence.py`'s
`roll_forward` does the arithmetic; this is where a payment becomes a
record). It writes a `paid_by` record — `{account, fingerprint}`, references
to a labeled account and a transaction fingerprint, never an amount — keyed
`<id>.<paid_on ISO>` so a second `mark_paid` for the same obligation on the
same day is the same TOCTOU-safe gate `add_obligation` already uses (I-9: the
first write is `overwrite=False` unless `--replace`), then advances
`due_date` (or, for a `once` obligation, marks it `resolved` instead — there
is no next due date to advance to). `Event.ITEM_RESOLVED` is logged with a
reference only — `(obligations, id)` — never the account, the fingerprint, or
the date (I-15: a visible-log entry says *that* something happened, not what).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from homestead.keep.dates import UnparseableDate, parse_deadline
from homestead.keep.logs import Event, VisibleLog
from homestead.keep.rungs import Classified, Disposition, Rung, Surface, compose, serve

from homestead_ledger import money, registry
from homestead_ledger.cadence import CADENCES, UnknownCadence, roll_forward
from homestead_ledger.packs import obligations as pack
from homestead_ledger.store import InvalidKey, RecordExists, Ref, Replaced, Sidecar, key

__all__ = [
    "KIND", "FIELDS", "DERIVED", "MISSING", "SEALED", "ObligationRow",
    "DueRolled", "add_obligation", "mark_paid", "rows", "detail",
]

KIND = pack.OBLIGATION
FIELDS = pack.FIELDS

#: The stand-in text for the L3/L4 fields — the same sentences `app.demo`
#: seeds, so an entered obligation and a demonstrated one read alike. The
#: amount's derived form names neither the number nor its sign.
DERIVED: dict[str, str] = {"name": "a payee is on file", "amount": "a payment is due"}

#: What a field that is *not on file* reads as on the list. Never "" and never
#: a plausible-looking blank: a torn obligation is a gap (I-8), and a gap is
#: shown, not filled in.
MISSING = "(missing)"

#: What a field the gate refused reads as — present, classified, and not for
#: this surface. Distinct from `MISSING`, because "sealed" and "not there" are
#: different facts and only one of them wants an operator's hand.
SEALED = "(sealed)"

#: Write order. `due_date` first: it is the field the queue keys on, so it is
#: the de-duplication gate (the same posture `books.py` gives `date`).
_ORDER = ("due_date", "name", "amount", "cadence")

#: The closed id shape. Lowercase because the id is a key segment and a
#: reference an operator retypes; hyphens because `car-insurance` is how a
#: household names a bill; no dot, so a future `<instance>.<sub>` id stays
#: unambiguous (the build plan's decision 2).
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


@dataclass(frozen=True)
class ObligationRow:
    """One obligation as the list pane shows it: its id, each field's served
    text (the amount is its derived form here), the composed rung, and whether
    any field is missing — a torn write, surfaced rather than smoothed over.

    `paid_on` is the most recent `paid_by` record on file for this id — shown
    by reference (the date the record is keyed under, not its `{account,
    fingerprint}` payload) — or `None` if the obligation has never been
    marked paid. `resolved` is `True` once a `once` obligation has been paid
    (a `(obligations, "resolved", id)` record exists); a resolved obligation
    still lists here (this is not the queue, which drops it), only marked."""

    item_id: str
    name: str
    due_date: str
    cadence: str
    amount: str
    rung: Rung
    gap: bool
    paid_on: str | None = None
    resolved: bool = False


def _identifier(item_id: object) -> str:
    """The id, or `InvalidKey`. Refuses without echoing what was given: the id
    is a reference, but it is also rendered back into a browser, and a refusal
    that repeats it is a refusal that carries it onward."""
    ident = str(item_id).strip()
    if not _ID.match(ident):
        raise InvalidKey(
            "an obligation id is the household's own short name for the bill: "
            "lowercase letters, digits and hyphens, 1-40 characters, starting "
            "with a letter or digit (rent, car-insurance)"
        )
    return ident


def add_obligation(
    store: Sidecar,
    *,
    item_id: str,
    name: str,
    amount: object,
    due_date: str,
    cadence: str,
    replace: bool = False,
) -> tuple[Ref, Replaced | None]:
    """Record one recurring obligation. Returns its due-date ref and, on an
    explicit replace, what the due date displaced.

    Refuses — before writing — a bad id, an empty payee or cadence, an amount
    that is not a finite number, and a due date the engine will not read.

    **The occupied-id refusal is the store's, not a check's (I-9).** An earlier
    shape asked `store.has()` and then wrote every field with `overwrite=True`.
    Between those two statements another writer — a second `ui` tab, a CLI run
    beside the browser — can land the same id, and the `has()` answer is then
    stale: both callers see "free" and the second silently overwrites the
    first, which is exactly the clobber I-9 exists to prevent. Here the first
    field (`due_date`) is written with `overwrite=False`, so the adapter's own
    atomic insert is the gate: it either takes the key or refuses it, with no
    window in between. `replace=True` is the one path that overwrites, and it
    is an explicit act that reports what it displaced.

    **The torn-write gap.** The four fields are four separate writes and the
    adapter exposes no multi-key transaction, so a crash (or a kill) between
    them leaves a partial obligation on file — the same limitation `books.py`
    documents for a transaction's four fields, for the same reason. Nothing
    here guesses the rest afterwards: `rows()` shows each absent field as
    `MISSING` and flags the row as a gap, so a tear is something an operator
    sees rather than an obligation that reads whole and is not (I-8/I-11).
    """
    ident = _identifier(item_id)
    ref = key(KIND, "due_date", ident)
    payee = str(name).strip()
    if not payee:
        raise ValueError("an obligation names who is owed")
    how_often = str(cadence).strip()
    if not how_often:
        raise ValueError("an obligation says how often it recurs (monthly, annual, …)")
    if how_often not in CADENCES:
        # I-23's reasoning applied to a household-typed word rather than a
        # matter/account name: `cadence.CADENCES` is the one enumeration
        # `mark_paid`'s `roll_forward` reads, so nothing may land in the
        # field that arithmetic does not also recognise (I-11 — fail closed
        # on a rule outside the closed set, never guess the nearest bucket).
        raise ValueError(f"cadence must be one of: {', '.join(CADENCES)}")
    values = {
        "due_date": parse_deadline(due_date).iso,
        "name": payee,
        "amount": money.amount_text(amount),
        "cadence": how_often,
    }
    replaced: Replaced | None = None
    for index, field in enumerate(_ORDER):
        record = Classified(FIELDS[field], values[field], DERIVED.get(field))
        first = index == 0
        if first and not replace:
            try:
                store.put(KIND, field, ident, record, overwrite=False)
            except RecordExists:
                raise RecordExists(
                    f"{KIND}/{ident} already exists. A write never silently "
                    "overwrites (I-9): pass --replace (the CLI) or "
                    '"replace": true (the UI) to replace it.'
                ) from None
            continue
        result = store.put(KIND, field, ident, record, overwrite=True)
        if first:
            replaced = result
    return ref, replaced


@dataclass(frozen=True)
class DueRolled:
    """What `mark_paid` did to the schedule: the due date it advanced from,
    and the due date it advanced to. `new_due` is `None` for a `once`
    obligation — there is nothing to advance to; it is resolved instead (see
    `mark_paid`'s own docstring). Both dates are plain ISO strings this
    module already read through the gate (`_served`) before computing
    `roll_forward` — never a `.payload` reach, and this pair is what
    `add_obligation`'s `Replaced` reports for `--replace`, restated for an
    act that moves a date instead of overwriting a whole record."""

    old_due: str
    new_due: str | None


def _served(record: Classified, surface: Surface) -> str | None:
    served = serve(record, surface)
    return None if served.disposition is Disposition.DENY else str(served.value)


def mark_paid(
    store: Sidecar,
    obligation_id: str,
    *,
    account: str,
    fingerprint: str,
    paid_on: str,
    replace: bool = False,
) -> tuple[Ref, DueRolled]:
    """Record that `obligation_id` was paid, and advance its schedule.

    Writes `(obligations, "paid_by", "<id>.<paid_on>")` at `Rung.L2` with
    `{"account": account, "fingerprint": fingerprint}` — a labeled account
    and a transaction fingerprint, both **references**, never an amount or
    an account number. That write is the TOCTOU-safe gate, exactly the shape
    `add_obligation` gives its own first field: with `replace=False` (the
    default) it is `overwrite=False`, so a second `mark_paid` for the same
    `(id, paid_on)` is refused by the store's atomic insert, not by a
    `has()` check a second racing caller could see stale (I-9).

    Then advances `due_date` via `cadence.roll_forward`, or — for a `once`
    obligation, which has no next date — writes `(obligations, "resolved",
    "<id>")` at `Rung.L2` instead, so `queue()` stops surfacing it. Logs
    `Event.ITEM_RESOLVED` with the reference `(obligations, id)` only — never
    the account, the fingerprint, or either date (I-15).

    Refuses, before writing anything:
    * `obligation_id` unknown (no `due_date`/`cadence` on file for it).
    * `account` not one `registry.all_accounts()` knows (`ValueError`,
      registry-validated the way `transaction add --account` already is).
    * an empty `fingerprint`.
    * `paid_on` that is not a bare ISO date (`YYYY-MM-DD`) — this is a
      record key's own suffix, not a household-typed deadline, so it takes
      no month-name or slashed form the way `due_date` does.
    * a `due_date`/`cadence` on file that the gate denies (sealed) or that
      will not parse/is outside `CADENCES` — an obligation this module
      cannot itself compute a next date for is not silently left as-is.
    """
    ident = _identifier(obligation_id)
    # `store.get` (a direct adapter read), never `store.has` — this is the
    # precondition check, not the TOCTOU write gate below, and it must not
    # share a mechanism a racing writer could poison the same way (I-9's
    # own test for `add_obligation` poisons `has()` globally; this call
    # stays correct regardless).
    try:
        due_record = store.get(KIND, "due_date", ident)
        cadence_record = store.get(KIND, "cadence", ident)
    except KeyError:
        raise KeyError(f"{ident}: no such obligation on file") from None

    if account not in registry.all_accounts():
        raise ValueError(
            f"unknown account {account!r} — one of: "
            f"{', '.join(registry.all_accounts())}"
        )
    fp = str(fingerprint).strip()
    if not fp:
        raise ValueError("a paid-by record names the transaction fingerprint")

    paid_text = str(paid_on).strip()
    try:
        paid_date = date.fromisoformat(paid_text)
    except ValueError:
        raise ValueError(
            "paid_on must be an ISO date (YYYY-MM-DD) — it keys the paid-by "
            "record, so it takes no other spelling"
        ) from None

    due_shown = _served(due_record, Surface.S1_LIST)
    cadence_shown = _served(cadence_record, Surface.S1_LIST)
    if due_shown is None or cadence_shown is None:
        raise ValueError(f"{ident}: due date or cadence is sealed; cannot mark paid")
    try:
        due_date = date.fromisoformat(parse_deadline(due_shown).iso)
    except UnparseableDate:
        raise ValueError(
            f"{ident}: the due date on file will not parse — fix it (obligation "
            "add --replace) before marking this obligation paid"
        ) from None
    cadence_value = cadence_shown.strip()
    if cadence_value not in CADENCES:
        raise UnknownCadence(
            f"{ident}: cadence {cadence_value!r} on file is not one of: "
            f"{', '.join(CADENCES)} — fix the obligation before marking it paid"
        )

    paid_item_id = f"{ident}.{paid_date.isoformat()}"
    paid_ref = key(KIND, "paid_by", paid_item_id)
    paid_record = Classified(Rung.L2, {"account": account, "fingerprint": fp})
    if replace:
        store.put(KIND, "paid_by", paid_item_id, paid_record, overwrite=True)
    else:
        try:
            store.put(KIND, "paid_by", paid_item_id, paid_record, overwrite=False)
        except RecordExists:
            raise RecordExists(
                f"{paid_item_id}: this obligation is already marked paid for "
                f"{paid_date.isoformat()}. A write never silently overwrites "
                "(I-9): pass --replace (the CLI) or \"replace\": true (the "
                "UI) to record it again."
            ) from None

    next_due = roll_forward(due_date, cadence_value, paid_date)
    if next_due is None:
        store.put(KIND, "resolved", ident, Classified(Rung.L2, "resolved"), overwrite=True)
        rolled = DueRolled(old_due=due_date.isoformat(), new_due=None)
    else:
        store.put(
            KIND, "due_date", ident, Classified(Rung.L2, next_due.isoformat()), overwrite=True
        )
        rolled = DueRolled(old_due=due_date.isoformat(), new_due=next_due.isoformat())

    VisibleLog().record(Event.ITEM_RESOLVED, ref=(KIND, ident))
    return paid_ref, rolled


def rows(store: Sidecar) -> list[ObligationRow]:
    """Every obligation on file, as the list pane shows it, by id.

    A row's rung is `compose()` — the engine's one composition (I-12), and the
    one place the ladder's order is written down. `max(..., key=lambda r:
    r.value)` gives the same answer today only because `L1 < L2 < … < L5`
    happens to hold in the alphabet; that is a rung being read as a sortable
    string, which is the shape I-14 names outright.

    `paid_by` and `resolved` records are not obligation *fields* — they are
    keyed under their own item ids (`paid_by`'s under `<id>.<date>`,
    `resolved`'s under `<id>` itself but a different field name) — so they
    are read out into `last_paid`/`resolved` here rather than folded into
    `by_id`'s per-field map, which would otherwise mint a bogus row for
    every `<id>.<date>` pseudo-id `paid_by` writes under.
    """
    by_id: dict[str, dict[str, Classified]] = {}
    last_paid: dict[str, str] = {}
    resolved_ids: set[str] = set()
    for (_, field, item_id), record in store.records(KIND):
        if field == "paid_by":
            ident, _dot, paid = item_id.partition(".")
            if paid and paid > last_paid.get(ident, ""):
                last_paid[ident] = paid
            continue
        if field == "resolved":
            resolved_ids.add(item_id)
            continue
        by_id.setdefault(item_id, {})[field] = record
    out: list[ObligationRow] = []
    for item_id in sorted(by_id):
        fields = by_id[item_id]
        shown = {f: _served(r, Surface.S1_LIST) for f, r in fields.items()}

        def text(field: str) -> str:
            if field not in fields:
                return MISSING
            value = shown[field]
            return SEALED if value is None else value

        out.append(ObligationRow(
            item_id=item_id,
            name=text("name"),
            due_date=text("due_date"),
            cadence=text("cadence"),
            amount=text("amount"),
            rung=compose(*(r.rung for r in fields.values())),
            gap=any(f not in fields for f in _ORDER),
            paid_on=last_paid.get(item_id),
            resolved=item_id in resolved_ids,
        ))
    return out


def detail(store: Sidecar, item_id: str) -> dict[str, tuple[str, str | None]]:
    """One obligation opened in the detail pane: field → (rung, rendered value
    or `None` where the gate refused). Empty if there is no such obligation."""
    out: dict[str, tuple[str, str | None]] = {}
    for (_, field, found), record in store.records(KIND):
        if found == item_id:
            out[field] = (record.rung.value, _served(record, Surface.S1_DETAIL))
    return out
