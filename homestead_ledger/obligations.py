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
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from homestead.keep.dates import parse_deadline
from homestead.keep.rungs import Classified, Disposition, Rung, Surface, compose, serve

from homestead_ledger import money
from homestead_ledger.packs import obligations as pack
from homestead_ledger.store import InvalidKey, RecordExists, Ref, Replaced, Sidecar, key

__all__ = [
    "KIND", "FIELDS", "DERIVED", "MISSING", "SEALED", "ObligationRow",
    "add_obligation", "rows", "detail",
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
    any field is missing — a torn write, surfaced rather than smoothed over."""

    item_id: str
    name: str
    due_date: str
    cadence: str
    amount: str
    rung: Rung
    gap: bool


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


def _served(record: Classified, surface: Surface) -> str | None:
    served = serve(record, surface)
    return None if served.disposition is Disposition.DENY else str(served.value)


def rows(store: Sidecar) -> list[ObligationRow]:
    """Every obligation on file, as the list pane shows it, by id.

    A row's rung is `compose()` — the engine's one composition (I-12), and the
    one place the ladder's order is written down. `max(..., key=lambda r:
    r.value)` gives the same answer today only because `L1 < L2 < … < L5`
    happens to hold in the alphabet; that is a rung being read as a sortable
    string, which is the shape I-14 names outright.
    """
    by_id: dict[str, dict[str, Classified]] = {}
    for (_, field, item_id), record in store.records(KIND):
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
