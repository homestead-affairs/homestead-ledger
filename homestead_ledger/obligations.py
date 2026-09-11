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
as one key segment before anything is written. A first write refuses an occupied
id (I-9); replacing an obligation is an explicit act (`replace=True`) that
reports what it displaced.

Reading back goes through the gate, field by field, on the list surface: the
payee, the due date and the cadence render; the amount derives. Opening one
(`S1_DETAIL`) is the purpose declaration, and the amount renders there. Nothing
in this module reaches a `.payload`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from homestead.keep.dates import parse_deadline
from homestead.keep.rungs import Classified, Disposition, Rung, Surface, serve

from homestead_ledger.packs import obligations as pack
from homestead_ledger.store import RecordExists, Ref, Replaced, Sidecar, key

__all__ = ["KIND", "FIELDS", "DERIVED", "ObligationRow", "add_obligation", "rows", "detail"]

KIND = pack.OBLIGATION
FIELDS = pack.FIELDS

#: The stand-in text for the L3/L4 fields — the same sentences `app.demo`
#: seeds, so an entered obligation and a demonstrated one read alike. The
#: amount's derived form names neither the number nor its sign.
DERIVED: dict[str, str] = {"name": "a payee is on file", "amount": "a payment is due"}

#: Write order. `due_date` first: it is the field the queue keys on, so it is
#: the de-duplication gate (the same posture `books.py` gives `date`).
_ORDER = ("due_date", "name", "amount", "cadence")


@dataclass(frozen=True)
class ObligationRow:
    """One obligation as the list pane shows it: its id, and each field's served
    text (the amount is its derived form here)."""

    item_id: str
    name: str
    due_date: str
    cadence: str
    amount: str
    rung: Rung


def _amount(text: object) -> str:
    raw = str(text).strip().replace(",", "").replace("$", "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"amount {text!r} is not a number (e.g. 1450.00 or -96.40)")
    if not value.is_finite():
        raise ValueError(f"amount {text!r} is not a number")
    return f"{value:.2f}"


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
    that is not a number, and a due date the engine will not read. Refuses an
    occupied id unless `replace=True` (I-9).
    """
    ref = key(KIND, "due_date", str(item_id).strip())
    payee = str(name).strip()
    if not payee:
        raise ValueError("an obligation names who is owed")
    how_often = str(cadence).strip()
    if not how_often:
        raise ValueError("an obligation says how often it recurs (monthly, annual, …)")
    values = {
        "due_date": parse_deadline(due_date).iso,
        "name": payee,
        "amount": _amount(amount),
        "cadence": how_often,
    }
    if not replace and store.has(*ref):
        raise RecordExists(
            f"{KIND}/{ref[2]} already exists. A write never silently overwrites "
            "(I-9): pass --replace to replace it."
        )
    replaced: Replaced | None = None
    for field in _ORDER:
        rung = FIELDS[field]
        record = Classified(rung, values[field], DERIVED.get(field))
        result = store.put(KIND, field, ref[2], record, overwrite=True)
        if field == "due_date":
            replaced = result
    return ref, replaced


def _served(record: Classified, surface: Surface) -> str | None:
    served = serve(record, surface)
    return None if served.disposition is Disposition.DENY else str(served.value)


def rows(store: Sidecar) -> list[ObligationRow]:
    """Every obligation on file, as the list pane shows it, by id."""
    by_id: dict[str, dict[str, Classified]] = {}
    for (_, field, item_id), record in store.records(KIND):
        by_id.setdefault(item_id, {})[field] = record
    out: list[ObligationRow] = []
    for item_id in sorted(by_id):
        fields = by_id[item_id]
        shown = {f: _served(r, Surface.S1_LIST) for f, r in fields.items()}
        rung = max((r.rung for r in fields.values()), key=lambda r: r.value)
        out.append(ObligationRow(
            item_id=item_id,
            name=shown.get("name") or "",
            due_date=shown.get("due_date") or "",
            cadence=shown.get("cadence") or "",
            amount=shown.get("amount") or "",
            rung=rung,
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
