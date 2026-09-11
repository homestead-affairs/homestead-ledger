"""Chapter 13 debt schedules — composed, never drafted (provisional I-44).

Decision 9's account instances (`accounts.py`) already know which real
accounts a household holds and which are **liabilities**
(`registry.account(kind).liability`, read live off each pack's own
`LIABILITY` — I-23, the registry is the only enumeration). This module
composes them into the one shape the household's Chapter 13 plan payment
sits beside: **a list of what is owed**, never a filing. The court's own
paperwork for secured and unsecured creditors is prepared and submitted by
the debtor's attorney — a separate, human act this package plays no part
in. Provisional **I-44**: no `Purpose.DRAFTING` or `Purpose.FILING` reaches
this package, and no numbered-form or court-submission language appears in
it either (`tests/test_i44_no_drafting.py`). The Chapter 13 **plan payment
stays an ordinary obligation** here (`obligations.py`'s own `L4` amount);
the `NOTICE` on every export says so.

Every read here is `serve()`'s `Served.value`, never `Classified.payload`
or a reflective stand-in for it — this module composes rows for `cli.py`
and `server.py` to draw from, the same relationship `accounts.py` and
`obligations.py` already hold to them, and it keeps to their rule (I-16;
the package-wide `.payload` ban already covers this file too, since it is
neither `books.py` nor `balance.py`).

**Two compositions, two surfaces.** `debts()` serves each field on
`Surface.S4_EGRESS` with `Purpose.EXPORT` declared — the one cell in the
engine's `_CEILING` table (`rungs._CEILING[Surface.S4_EGRESS] == (Rung.L2,
Rung.L4)`, pinned in `tests/test_schedules.py`) where a declared purpose
lifts the ceiling to `L4`, so `balance_as_of`/`rate`/`limit`/`min_payment`
render as themselves rather than as "a balance is on file." `rows()` serves
the same fields on `Surface.S1_LIST` with **no** purpose declared — those
same `L4` fields **derive** there instead: what `schedules show` and `GET
/api/schedules` draw from. `institution` (`L3`) renders on both.
`number` (`L5`) never appears in either composition: it is not in
`_OPTIONAL_FIELDS`, so no code path here ever hands it to `serve()` at all
(I-13, no override anywhere).

**Never zero, never guessed.** A liability instance with no `balance_as_of`
on file gets `None` for that field on every row — absent, not `"0.00"`
(I-31's spirit, applied to a field rather than a count).

`export()` composes `debts()`'s rows into one JSON document and, after a
per-call confirmation shows exactly what would be written, hands it to the
engine's own `homestead.keep.export.export_record` — one artifact under
`exports_dir()` (`O_EXCL`), one `IntegrityLog` row, one `VisibleLog` line,
references and the declared purpose only, never content (I-15). A declined
confirmation never calls `export_record`: nothing is written, nothing is
ledgered — the same posture `homestead.keep.egress.send` takes for a
refused send, reused rather than reinvented.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from homestead.keep.egress import Wire
from homestead.keep.export import ExportReceipt, ExportRefused, export_record
from homestead.keep.rungs import Classified, Purpose, Rung, Surface, compose, serve

from homestead_ledger import accounts, registry
from homestead_ledger.store import Sidecar

__all__ = ["SCHEMA", "NOTICE", "DebtRow", "debts", "rows", "export"]

#: The export document's schema identifier — versioned so a future shape
#: change does not silently reinterpret an old file.
SCHEMA = "homestead-ledger.schedules/1"

#: Quoted verbatim on every export (`export()`'s document), and in the
#: README's own "Exporting your liabilities" section —
#: `tests/test_schedules.py` holds the two equal, so the sentence cannot
#: drift between the artifact and the documentation describing it.
#:
#: **Carries the one permitted mention of that two-word phrase pairing
#: "official" with the word for a court's own paperwork.**
#: `tests/test_i44_no_drafting.py`'s grep guard scans this package and the
#: README for that pairing, among other things, and excludes only this
#: literal sentence — because the sentence exists to say the opposite of
#: what the guard is watching for: this is not a filing.
NOTICE = (
    "A list of the household's liabilities as the ledger holds them, for "
    "the household's own use. It is not a schedule on any official form, "
    "it carries no form number, and the Chapter 13 plan payment is an "
    "ordinary obligation here, not a claim."
)


@dataclass(frozen=True)
class DebtRow:
    """One liability account instance, composed for a schedules pane or an
    export. `institution`/`balance_as_of`/`rate`/`limit`/`min_payment` are
    `None` when nothing is on file for them — never `"0.00"` and never a
    guess — and, on `rows()` (S1_LIST), the `L4` four read as their derived
    stand-in sentence rather than as `None`. `number` never appears here at
    all (L5, I-13)."""

    label: str
    kind: str
    institution: str | None
    balance_as_of: str | None
    rate: str | None
    limit: str | None
    min_payment: str | None
    rung: Rung


#: Every field beyond `kind` (the always-present dedup gate — the same
#: posture `accounts._ROW_FIELDS` takes) this module ever composes.
#: `number` is deliberately absent: nothing below ever iterates this list to
#: decide what to serve, so there is no code path that could hand `number`
#: to `serve()` here at all.
_OPTIONAL_FIELDS = ("institution", "balance_as_of", "rate", "limit", "min_payment")


def _by_label(store: Sidecar) -> dict[str, dict[str, Classified]]:
    """Every account instance's records, grouped by label — the same shape
    `accounts.rows()` reads its own fields from, so this module keeps no
    second copy of what `accounts.py` already knows how to enumerate."""
    grouped: dict[str, dict[str, Classified]] = {}
    for (_, field, item_id), record in store.records(accounts.MATTER):
        grouped.setdefault(item_id, {})[field] = record
    return grouped


def _text(record: Classified, surface: Surface, purpose: Purpose | None) -> str | None:
    """`serve()`'s `Served.value`, as text — never `.payload` (I-16)."""
    served = serve(record, surface, purpose=purpose)
    return None if served.value is None else str(served.value)


def _compose(
    store: Sidecar, *, surface: Surface, purpose: Purpose | None
) -> list[DebtRow]:
    """`debts()` and `rows()` share this — the only difference between the
    two is which surface (and purpose) every field is served on."""
    out: list[DebtRow] = []
    for label, fields in sorted(_by_label(store).items()):
        if "kind" not in fields:
            continue  # a torn write; add_account's own I-9 gate is the
            # dedup point and nothing here guesses at a missing kind
        kind = _text(fields["kind"], surface, purpose)
        if kind is None:
            continue  # kind is L2 and never denies; defensive only
        try:
            liability = registry.account(kind).liability
        except KeyError:
            continue  # an unregistered kind cannot be on file at all —
            # add_account refuses one before it is ever written (defensive)
        if not liability:
            continue
        values = {
            field: (_text(fields[field], surface, purpose) if field in fields else None)
            for field in _OPTIONAL_FIELDS
        }
        present = ("kind", *(f for f in _OPTIONAL_FIELDS if f in fields))
        rung = compose(*(fields[f].rung for f in present))
        out.append(DebtRow(label=label, kind=kind, rung=rung, **values))
    return out


def debts(store: Sidecar) -> list[DebtRow]:
    """Every liability account instance, composed for **export**: each
    field served on `Surface.S4_EGRESS` with `Purpose.EXPORT` declared, so
    `balance_as_of`/`rate`/`limit`/`min_payment` (`L4`) render as themselves
    — the one cell where a declared purpose lifts S4's ceiling to `L4`
    (`rungs._CEILING[Surface.S4_EGRESS] == (Rung.L2, Rung.L4)`). `number`
    (`L5`) never renders, on any surface, purpose or not (I-13), and is
    never even asked for (`_OPTIONAL_FIELDS`).

    Rows sorted by label. A `checking` or `savings` instance never appears
    — only a kind `registry.account(kind).liability` reads `True` for does.
    """
    return _compose(store, surface=Surface.S4_EGRESS, purpose=Purpose.EXPORT)


def rows(store: Sidecar) -> list[DebtRow]:
    """The same rows, composed for the household's own screen: each field
    served on `Surface.S1_LIST` with **no** purpose declared, so the `L4`
    fields **derive** — `"a balance is on file"`, never the number. What
    `schedules show` and `GET /api/schedules` draw from; only `export()`
    ever renders them."""
    return _compose(store, surface=Surface.S1_LIST, purpose=None)


def _row_dict(row: DebtRow) -> dict[str, str | None]:
    return {
        "label": row.label,
        "kind": row.kind,
        "institution": row.institution,
        "balance_as_of": row.balance_as_of,
        "rate": row.rate,
        "limit": row.limit,
        "min_payment": row.min_payment,
    }


def _document(store: Sidecar) -> tuple[dict[str, object], list[DebtRow]]:
    """The composed export document, and the rows it was built from (needed
    afterward to compose the whole document's own rung) — one call to
    `debts()`, never two, so the `composed_at` timestamp in the document and
    the rows behind it can never come from two different reads of the
    store."""
    debt_rows = debts(store)
    document = {
        "schema": SCHEMA,
        # Microsecond precision, not seconds: two exports of an unchanged
        # schedule inside the same test run (or the same interactive
        # session) must still compose two distinct documents — see
        # `export()`'s own docstring on why a second export is a new file
        # rather than a refusal.
        "composed_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "rows": [_row_dict(row) for row in debt_rows],
        "count": len(debt_rows),
        "NOTICE": NOTICE,
    }
    return document, debt_rows


def export(
    store: Sidecar,
    *,
    confirm: Callable[[Wire], bool],
    purpose: Purpose = Purpose.EXPORT,
    out_dir: Path | None = None,
) -> ExportReceipt:
    """Compose the household's liability schedule and take it out, through
    the engine's own export machinery — never reimplemented here.

    Builds the document once (`_document`), serializes it once into a
    `Wire` — "the preview is the payload," the same shape
    `homestead.keep.egress.send` uses — and calls `confirm(wire)`. **A
    declined confirmation raises `ExportRefused` before `export_record` is
    ever called**: nothing is written to `exports_dir()`, no
    `IntegrityLog` row, no `VisibleLog` line.

    On confirmation, the whole document becomes one `Classified` — its rung
    is `compose()` over every row's own rung (`L2` when `debts()` is
    empty), carrying `NOTICE` as its derived stand-in — and is handed to
    `export_record()` **once**, under `matter="schedules"`,
    `item_type="debts"`, `item_id="export"`: one artifact, one
    `IntegrityLog` row, one `VisibleLog` line for the whole schedule, not
    one per account. `export_record` re-serves the document on `S4_EGRESS`
    with `purpose` itself (I-16 — this module is not the gate); the default
    `Purpose.EXPORT` is what makes that second gate agree with the one
    `debts()` already cleared while composing the rows.

    **A second export is not refused — it is a new file.**
    `export_record` writes under `exports_dir()` with `O_EXCL`, keyed by a
    timestamp it stamps itself, so two exports of an unchanged schedule
    land as two documents rather than one clobbering the other: a
    household confirming the same export again is still a fact worth
    keeping, not an error.
    """
    document, debt_rows = _document(store)
    body = json.dumps(document, sort_keys=True, ensure_ascii=False)
    wire = Wire(method="FILE", url="schedules/debts", body=body)
    if not confirm(wire):
        raise ExportRefused(
            "declined at the preview: nothing was exported and nothing was "
            "ledgered — the same posture a refused network send takes."
        )
    rung = compose(*(row.rung for row in debt_rows)) if debt_rows else Rung.L2
    item = Classified(rung, document, NOTICE)
    return export_record(
        item, "schedules", "debts", "export", purpose=purpose, exports=out_dir,
    )
