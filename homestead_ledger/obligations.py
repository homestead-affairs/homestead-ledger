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

from homestead_ledger import accounts, money
from homestead_ledger.cadence import CADENCES, UnknownCadence, previous_due, roll_forward
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

#: The **anchor**: the day of month the obligation's *first* due date fell
#: on, kept as its own record (`(obligations, "due_day", <id>)`, L2) rather
#: than re-derived from `due_date` every time.
#:
#: Without it a month-end obligation drifts and never comes back. Rent due
#: the 31st, paid on time, rolls to Feb 28 — and next month `mark_paid` is
#: handed *that* Feb 28 as the only day it knows, so it rolls to Mar 28, Apr
#: 28, … and the household's rent day has quietly become the 28th forever.
#: `cadence.roll_forward`'s clamp is anchored on this record instead, so the
#: sequence is Jan 31 → Feb 28 → Mar 31 → Apr 30 → May 31: the month that
#: has a 31st gets it back.
#:
#: It is *not* one of `_ORDER`'s pack fields — it is bookkeeping this module
#: keeps for its own arithmetic, not a field the household typed — so
#: `rows()` skips it the way it skips `paid_by` and `resolved`, and a torn
#: write that loses it is harmless for a fresh obligation (see
#: `add_obligation`).
_ANCHOR = "due_day"

#: The paid-by record's own field name, and the resolved marker's. Named
#: once here because three functions key on them.
_PAID_BY = "paid_by"
_RESOLVED = "resolved"

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
    still lists here (this is not the queue, which drops it), only marked.

    **`paid_current` is the one a surface may draw a ✓ from**, and it is a
    narrower claim than `paid_on is not None`. Two ways a payment on file
    fails to say "this is paid up", both of which a bare `paid ✓ <date>`
    would say anyway:

    * The payment is older than the period now open. A due date of
      2026-08-01 with the latest payment on 2026-05-15 is an obligation that
      lapsed two periods ago, not one that is paid. The mark is shown only
      when the latest payment falls on or after the previous due date
      (`cadence.previous_due`) — inside the period that ended at the due
      date now on file.
    * The due date has arrived. `mark_paid` always rolls past the payment
      that triggered it, so every paid obligation shows a due date in its
      own future; once *today* reaches it, the open period is unpaid again
      and last month's receipt stops being an answer. A caller that passes
      `today` gets that second test too — `paid ✓ 2026-07-01` beside
      `due 2026-08-01` is honest on 20 July and a lie on 15 August, and
      only the caller knows which day it is. Omit `today` and only the
      first test applies.

    A `resolved` obligation is always marked: a `once` obligation that has
    been paid has no next period to fall behind on. Where the due date or
    cadence cannot be read (sealed, missing, corrupt) there is no period to
    test against and the answer is `False`: no claim beats a wrong one
    (I-11).

    `paid_on` itself is left as it is either way, so a surface that wants to
    say "last paid …" without claiming the period still can."""

    item_id: str
    name: str
    due_date: str
    cadence: str
    amount: str
    rung: Rung
    gap: bool
    paid_on: str | None = None
    resolved: bool = False
    paid_current: bool = False


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

    **The torn-write gap.** The four fields — and the anchor day written
    behind the gate, five writes in all — are separate writes and the
    adapter exposes no multi-key transaction, so a crash (or a kill) between
    them leaves a partial obligation on file — the same limitation `books.py`
    documents for a transaction's three fields, for the same reason. Nothing
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
        raise ValueError(
            "an obligation says how often it recurs — one of: "
            f"{', '.join(CADENCES)}"
        )
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
    gate = Classified(FIELDS["due_date"], values["due_date"], DERIVED.get("due_date"))
    if replace:
        replaced = store.put(KIND, "due_date", ident, gate, overwrite=True)
    else:
        try:
            store.put(KIND, "due_date", ident, gate, overwrite=False)
        except RecordExists:
            raise RecordExists(
                f"{KIND}/{ident} already exists. A write never silently "
                "overwrites (I-9): pass --replace (the CLI) or "
                '"replace": true (the UI) to replace it.'
            ) from None
    # The anchor, written immediately behind the gate and before any other
    # field, so the ordinary add path cannot produce an obligation that has a
    # due date and no day to clamp against. It is the one write whose torn
    # absence is *not* a gap: for an obligation that has never rolled,
    # `due_date.day` is the anchor, which is exactly what `mark_paid` falls
    # back to — so a crash here costs nothing until the first month-end roll,
    # and `--replace` (which resets the due date) rewrites it.
    store.put(
        KIND, _ANCHOR, ident,
        Classified(Rung.L2, str(date.fromisoformat(values["due_date"]).day)),
        overwrite=True,
    )
    for field in _ORDER[1:]:
        store.put(
            KIND, field, ident,
            Classified(FIELDS[field], values[field], DERIVED.get(field)),
            overwrite=True,
        )
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
    act that moves a date instead of overwriting a whole record.

    `rolled` is `False` for the one case where the payment is recorded and
    the schedule deliberately stands still: a **back-dated** entry, a
    payment for a period a later payment already closed. `new_due` is then
    the unchanged due date, not a new one — see `mark_paid`."""

    old_due: str
    new_due: str | None
    rolled: bool = True


def _anchor_day(store: Sidecar, ident: str, due_date: date) -> int:
    """The obligation's anchor day of month.

    **The fallback is the documented one.** An obligation written before
    this module kept an anchor — or one whose add was torn between the
    due-date gate and the anchor write — has no `due_day` record, and there
    is nothing to recover it from: the *original* day is gone the moment a
    month-end due date has clamped. So it falls back to the day the due date
    currently holds, which is the old behaviour exactly (I-11: the fallback
    is named and bounded, not a guess at what the day "probably" was), and
    `obligation add --replace` is how an operator restores a drifted
    anchor. A stored value that is not a day of month is treated the same
    way: refusing to mark a payment because a bookkeeping record is
    corrupt would be worse than rolling by the date on file, and the
    corruption is visible in the detail pane.
    """
    try:
        record = store.get(KIND, _ANCHOR, ident)
    except KeyError:
        return due_date.day
    shown = _served(record, Surface.S1_LIST)
    if shown is None or not shown.strip().isdigit():
        return due_date.day
    day = int(shown.strip())
    return day if 1 <= day <= 31 else due_date.day


def _paid_dates(store: Sidecar, ident: str) -> list[date]:
    """Every `paid_by` date on file for `ident`, parsed, oldest first.

    Read by reference — the *key* each paid-by record is filed under, never
    its `{account, fingerprint}` payload (I-15) — so this function never
    needs the gate and never touches a value.
    """
    out: list[date] = []
    prefix = f"{ident}."
    for (_, field, item_id), _record in store.records(KIND):
        if field != _PAID_BY or not item_id.startswith(prefix):
            continue
        try:
            out.append(date.fromisoformat(item_id[len(prefix):]))
        except ValueError:
            continue
    out.sort()
    return out


def _latest_paid(
    store: Sidecar, ident: str, *, excluding: date | None = None
) -> date | None:
    """The most recent payment on file for `ident`, ignoring `excluding`."""
    dates = [d for d in _paid_dates(store, ident) if d != excluding]
    return dates[-1] if dates else None


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

    Then advances `due_date` via `cadence.roll_forward`, clamped against
    the obligation's persisted anchor day (`due_day`) so a month-end
    schedule does not drift — or, for a `once` obligation, which has no next
    date, writes `(obligations, "resolved", "<id>")` at `Rung.L2` instead,
    so `queue()` stops surfacing it. Logs `Event.ITEM_RESOLVED` with the
    reference `(obligations, id)` only — never the account, the
    fingerprint, or either date (I-15).

    **It advances only for the newest payment.** A back-dated entry — a
    `paid_on` older than a payment already on file, or a `--replace` of a
    date already recorded — writes its paid-by record and leaves `due_date`
    alone (`DueRolled.rolled is False`). The alternative is a due date that
    walks forward once per *receipt* rather than once per *period*, so
    entering last December's payment in January would skip February.

    Refuses, before writing anything:
    * `obligation_id` unknown (no `due_date`/`cadence` on file for it).
    * `account` not a registered account *instance*'s label
      (`accounts.label_exists`, `ValueError`) — validated exactly the way
      `books.import_transaction` validates a transaction's own account, so
      the two doors cannot disagree about what an account is (bite 2b).
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

    # Bite 2b: the label of a registered account *instance*, not a kind
    # name. `mark_paid` and `books.import_transaction` are the two doors an
    # account name comes through, and they must agree about what one is —
    # otherwise the browser's paid form, whose select is built from the same
    # `/api/status` instances the transaction form uses, would offer labels
    # this function refuses.
    if not account or not accounts.label_exists(store, account):
        raise ValueError(accounts.unknown_label(account))
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

    anchor_day = _anchor_day(store, ident, due_date)

    # Everything the schedule decision needs, read *before* this call's own
    # write lands, so "is there already a later payment on file?" is asked of
    # the store as it was, not of the record we are about to add.
    latest_other = _latest_paid(store, ident, excluding=paid_date)
    already_recorded = store.has(KIND, _PAID_BY, f"{ident}.{paid_date.isoformat()}")

    paid_item_id = f"{ident}.{paid_date.isoformat()}"
    paid_ref = key(KIND, _PAID_BY, paid_item_id)
    paid_record = Classified(Rung.L2, {"account": account, "fingerprint": fp})
    if replace:
        store.put(KIND, _PAID_BY, paid_item_id, paid_record, overwrite=True)
    else:
        try:
            store.put(KIND, _PAID_BY, paid_item_id, paid_record, overwrite=False)
        except RecordExists:
            raise RecordExists(
                f"{paid_item_id}: this obligation is already marked paid for "
                f"{paid_date.isoformat()}. A write never silently overwrites "
                "(I-9): pass --replace (the CLI) or \"replace\": true (the "
                "UI) to record it again."
            ) from None

    # A back-dated entry — a receipt for a period a later payment already
    # closed — is a *fact*, recorded above, and not an instruction to move
    # the schedule. `due_date` on file is already the date that later
    # payment rolled it to; advancing again from there would skip a period
    # the household still owes (rent due Jan 1, paid Jan 1 → Feb 1; then
    # last December's receipt entered → Mar 1, and February silently
    # vanishes). Re-recording a date already on file (`--replace`) does not
    # advance either: the original write already did.
    advance = not already_recorded and (latest_other is None or paid_date > latest_other)
    if not advance:
        rolled = DueRolled(
            old_due=due_date.isoformat(), new_due=due_date.isoformat(), rolled=False
        )
    else:
        next_due = roll_forward(
            due_date, cadence_value, paid_date, anchor_day=anchor_day
        )
        if next_due is None:
            store.put(
                KIND, _RESOLVED, ident, Classified(Rung.L2, "resolved"), overwrite=True
            )
            rolled = DueRolled(old_due=due_date.isoformat(), new_due=None)
        else:
            store.put(
                KIND, "due_date", ident,
                Classified(Rung.L2, next_due.isoformat()), overwrite=True,
            )
            rolled = DueRolled(old_due=due_date.isoformat(), new_due=next_due.isoformat())

    VisibleLog().record(Event.ITEM_RESOLVED, ref=(KIND, ident))
    return paid_ref, rolled


def _covers_current_period(
    *,
    paid: str | None,
    due: str | None,
    cadence: str | None,
    anchor: Classified | None,
    resolved: bool,
    today: date | None,
) -> bool:
    """Whether the latest payment closes the period the due date now on file
    ends — the one question a `paid ✓` mark is allowed to answer.

    See `ObligationRow.paid_current`. Every unreadable input answers `False`:
    a mark that might be a month stale is worse than no mark at all.
    """
    if paid is None:
        return False
    if resolved:
        return True
    if due is None or cadence is None or cadence.strip() not in CADENCES:
        return False
    try:
        due_date = date.fromisoformat(parse_deadline(due).iso)
        paid_date = date.fromisoformat(paid)
    except (UnparseableDate, ValueError):
        return False
    anchor_day = None
    if anchor is not None:
        text = _served(anchor, Surface.S1_LIST)
        if text is not None and text.strip().isdigit():
            day = int(text.strip())
            anchor_day = day if 1 <= day <= 31 else None
    if today is not None and today >= due_date:
        # The due date has arrived: whatever was paid for the last period,
        # this one is open and unpaid.
        return False
    start = previous_due(due_date, cadence.strip(), anchor_day=anchor_day)
    if start is None:
        # `once`, and not resolved — nothing has closed its single period.
        return False
    return paid_date >= start


def rows(store: Sidecar, *, today: str | None = None) -> list[ObligationRow]:
    """Every obligation on file, as the list pane shows it, by id.

    A row's rung is `compose()` — the engine's one composition (I-12), and the
    one place the ladder's order is written down. `max(..., key=lambda r:
    r.value)` gives the same answer today only because `L1 < L2 < … < L5`
    happens to hold in the alphabet; that is a rung being read as a sortable
    string, which is the shape I-14 names outright.

    `today` (ISO) is optional and only sharpens `paid_current`; see
    `ObligationRow`. Nothing else on a row depends on the date, so a caller
    with no clock still gets every field.

    `paid_by`, `resolved` and `due_day` records are not obligation *fields*
    — `paid_by`'s are keyed under `<id>.<date>`, the other two under `<id>`
    itself but a different field name — so they are read out into
    `last_paid`/`resolved`/`anchors` here rather than folded into `by_id`'s
    per-field map, which would otherwise mint a bogus row for every
    `<id>.<date>` pseudo-id `paid_by` writes under and count the anchor as a
    fifth field the row must show.
    """
    now: date | None = None
    if today is not None:
        try:
            now = date.fromisoformat(str(today).strip())
        except ValueError:
            # A caller's own clock string it could not spell is not a reason
            # to refuse to list the household's obligations; it is a reason
            # to make the weaker claim (I-11).
            now = None
    by_id: dict[str, dict[str, Classified]] = {}
    last_paid: dict[str, str] = {}
    resolved_ids: set[str] = set()
    anchors: dict[str, Classified] = {}
    for (_, field, item_id), record in store.records(KIND):
        if field == _PAID_BY:
            ident, _dot, paid = item_id.partition(".")
            if paid and paid > last_paid.get(ident, ""):
                last_paid[ident] = paid
            continue
        if field == _RESOLVED:
            resolved_ids.add(item_id)
            continue
        if field == _ANCHOR:
            anchors[item_id] = record
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
            paid_current=_covers_current_period(
                paid=last_paid.get(item_id),
                due=shown.get("due_date"),
                cadence=shown.get("cadence"),
                anchor=anchors.get(item_id),
                resolved=item_id in resolved_ids,
                today=now,
            ),
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
