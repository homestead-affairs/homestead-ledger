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
or a reflective stand-in for it (I-16 — the package-wide `.payload` ban
covers this file, which is neither `books.py` nor `balance.py`).

**Two compositions, two surfaces** (`debts()` and `rows()`, each documented
on itself). `number` (`L5`) appears in neither: it is not in
`_OPTIONAL_FIELDS`, and every field this module composes is read out of
that one tuple, so no code path here can hand it to `serve()` at all
(I-13, no override anywhere).

**Never zero, never guessed.** A liability instance with no `balance_as_of`
on file gets `None` for that field on every row — absent, not `"0.00"`
(I-31's spirit, applied to a field rather than a count) — and in the
exported document that field's **key is simply not there**, rather than a
`null` a reader could take for a zero balance or an unknown one. A
`DebtRow` keeps the `None`, this package's own in-band "not on file", and
`GET /api/schedules` mirrors the row faithfully; the artifact that leaves
the household does not.

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

from homestead.keep import paths
from homestead.keep.egress import Wire
from homestead.keep.export import ExportReceipt, ExportRefused, export_record
from homestead.keep.rungs import Classified, Purpose, Rung, Surface, compose, serve

from homestead_ledger import accounts, registry
from homestead_ledger.store import Sidecar

__all__ = [
    "SCHEMA", "NOTICE", "BUSINESS_NOTICE", "BUSINESS_NONE_NOTICE",
    "BUSINESS_INCLUDED_NOTICE", "BUSINESS_SENTENCES",
    "DebtRow", "debts", "rows", "export",
]

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

#: **G8-business-books: one of three sentences, and the true one.**
#: Appended to `NOTICE` when the household actually holds a business-owned
#: account and this export left it out.
#:
#: **A notice is a statement of fact, so it may not be constant.** An
#: earlier draft appended this sentence unconditionally, to make two
#: exports byte-identical whether or not a business account was on file —
#: which told a household that holds no business account at all that
#: accounts it does not have were excluded from its own schedule. The
#: byte-identical property the plan asks for is over the **rows** (a
#: business account changes no household row), and it still holds; the
#: notice tells the truth about *this* export instead
#: (`tests/test_business_books.py`).
BUSINESS_NOTICE = "Business-owned accounts are excluded from this schedule."

#: The sentence for a household with no business-owned account on file at
#: all — in either mode, since with none on file the two modes compose the
#: same schedule from the same rows and nothing was left out of it.
BUSINESS_NONE_NOTICE = "No business-owned accounts are on file."

#: `export(..., include_business=True)`'s own sentence, when there is in
#: fact a business-owned account for the flag to have pulled in. Never
#: combined with either sentence above in one document.
BUSINESS_INCLUDED_NOTICE = (
    "Business-owned accounts are included in this schedule at the "
    "operator's own request (--include-business)."
)

#: Every sentence this module can append to `NOTICE` — what
#: `tests/test_i44_no_drafting.py`'s carve-out is anchored to, by value.
BUSINESS_SENTENCES = (BUSINESS_NOTICE, BUSINESS_NONE_NOTICE, BUSINESS_INCLUDED_NOTICE)


@dataclass(frozen=True)
class DebtRow:
    """One liability account instance, composed for a schedules pane or an
    export. Every field but `label` and `kind` is `None` when nothing is on
    file for it — never `"0.00"` and never a guess — and, on `rows()`
    (S1_LIST), the `L4` four read as their derived stand-in sentence rather
    than as `None`. `opened` is `L2` (the pack's own "household schedule"
    reasoning) and so renders on both surfaces, like `kind`: the date a debt
    was taken on is the ordinary companion of what is owed on it, and it
    names no party and no amount. `number` never appears here at all
    (L5, I-13)."""

    label: str
    kind: str
    institution: str | None
    opened: str | None
    balance_as_of: str | None
    rate: str | None
    limit: str | None
    min_payment: str | None
    rung: Rung


#: Every field beyond `kind` (the always-present dedup gate — the same
#: posture `accounts._ROW_FIELDS` takes) this module ever composes.
#: `number` is deliberately absent: nothing below ever iterates this list to
#: decide what to serve, so there is no code path that could hand `number`
#: to `serve()` here at all. `payment_due_day` is left out for the same
#: reason: a schedule says what is owed and to whom, not when this household
#: happens to pay it — out of scope for this bite, not refused.
_OPTIONAL_FIELDS = (
    "institution", "opened", "balance_as_of", "rate", "limit", "min_payment",
)


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
    store: Sidecar, *, surface: Surface, purpose: Purpose | None,
    include_business: bool = False,
) -> list[DebtRow]:
    """`debts()` and `rows()` share this — the only difference between the
    two is which surface (and purpose) every field is served on.

    **G8-business-books.** `include_business=False` (the default) drops a
    business-owned instance before it is ever composed — the household's
    liability schedule excludes the business's own debts unless the caller
    widens the scope."""
    household = None if include_business else set(accounts.household_labels(store))
    out: list[DebtRow] = []
    for label, fields in sorted(_by_label(store).items()):
        if household is not None and label not in household:
            continue
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


def debts(store: Sidecar, *, include_business: bool = False) -> list[DebtRow]:
    """Every liability account instance, composed for **export**: each
    field served on `Surface.S4_EGRESS` with `Purpose.EXPORT` declared, so
    `balance_as_of`/`rate`/`limit`/`min_payment` (`L4`) render as themselves
    — the one cell where a declared purpose lifts S4's ceiling to `L4`
    (`rungs._CEILING[Surface.S4_EGRESS] == (Rung.L2, Rung.L4)`). `number`
    (`L5`) never renders, on any surface, purpose or not (I-13), and is
    never even asked for (`_OPTIONAL_FIELDS`).

    Rows sorted by label. A `checking` or `savings` instance never appears
    — only a kind `registry.account(kind).liability` reads `True` for does.
    `include_business` widens the scope to the business's own instances too
    (G8-business-books); the default excludes them.
    """
    return _compose(
        store, surface=Surface.S4_EGRESS, purpose=Purpose.EXPORT,
        include_business=include_business,
    )


def rows(store: Sidecar, *, include_business: bool = False) -> list[DebtRow]:
    """The same rows, composed for the household's own screen: each field
    served on `Surface.S1_LIST` with **no** purpose declared, so the `L4`
    fields **derive** — `"a balance is on file"`, never the number. What
    `schedules show` and `GET /api/schedules` draw from; only `export()`
    ever renders them."""
    return _compose(
        store, surface=Surface.S1_LIST, purpose=None, include_business=include_business,
    )


def _row_dict(row: DebtRow) -> dict[str, str]:
    """One row of the exported document. `label` and `kind` are always
    there; every other field appears **only when it is on file** — the key
    is absent rather than `null`, so nothing downstream can read a missing
    balance as a zero one or as a deliberately withheld one.

    Written out field by field rather than by reflection (I-16: this module
    reaches for nothing by computed name), with
    `test_the_document_row_keys_cannot_drift_from_the_composition` holding
    a populated row's keys equal to `("label", "kind", *_OPTIONAL_FIELDS)`
    — so `number`, absent from that tuple, is absent here too."""
    out: dict[str, str] = {"label": row.label, "kind": row.kind}
    for field, value in (
        ("institution", row.institution),
        ("opened", row.opened),
        ("balance_as_of", row.balance_as_of),
        ("rate", row.rate),
        ("limit", row.limit),
        ("min_payment", row.min_payment),
    ):
        if value is not None:
            out[field] = value
    return out


def _document(
    store: Sidecar, *, include_business: bool = False,
) -> tuple[dict[str, object], list[DebtRow], str]:
    """The composed export document, the rows it was built from (needed
    afterward to compose the whole document's own rung), and the full
    `NOTICE` text used — one call to `debts()`, never two, so the
    `composed_at` timestamp in the document and the rows behind it can
    never come from two different reads of the store.

    **G8-business-books: the byte-identical export, and a true notice.**
    The *rows* depend only on `include_business`: adding a business-owned
    account changes no household row, so the same household exported twice
    in the default mode — once with no business account on file and once
    with one — composes the identical row list, which is the byte-identical
    property the plan asks for (`tests/test_business_books.py`). The
    appended **sentence** is a statement of fact about this export, so it
    is not constant: with no business account on file there is nothing to
    have excluded (`BUSINESS_NONE_NOTICE`), with one on file and the
    default scope there is (`BUSINESS_NOTICE`), and with one on file and
    the scope widened it is in the rows (`BUSINESS_INCLUDED_NOTICE`).
    """
    if not accounts.business_labels(store):
        sentence = BUSINESS_NONE_NOTICE
    elif include_business:
        sentence = BUSINESS_INCLUDED_NOTICE
    else:
        sentence = BUSINESS_NOTICE
    full_notice = f"{NOTICE} {sentence}"
    debt_rows = debts(store, include_business=include_business)
    document = {
        "schema": SCHEMA,
        # Microseconds, not seconds: two exports of an unchanged schedule in
        # one session must still compose two distinct documents.
        "composed_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "rows": [_row_dict(row) for row in debt_rows],
        "count": len(debt_rows),
        "NOTICE": full_notice,
    }
    return document, debt_rows, full_notice


def export(
    store: Sidecar,
    *,
    confirm: Callable[[Wire], bool],
    purpose: Purpose = Purpose.EXPORT,
    out_dir: Path | None = None,
    include_business: bool = False,
) -> ExportReceipt:
    """Compose the household's liability schedule and take it out, through
    the engine's own export machinery — never reimplemented here.

    Builds the document once (`_document`), serializes it once into a
    `Wire` — "the preview is the payload," the same shape
    `homestead.keep.egress.send` uses — and calls `confirm(wire)`. **A
    declined confirmation raises `ExportRefused` before `export_record` is
    ever called**: nothing is written to `exports_dir()`, no
    `IntegrityLog` row, no `VisibleLog` line.

    **`out_dir` must be an absolute directory under `paths.home()`**, and
    both refusals name themselves. A *relative* path is refused here,
    before anything is composed or shown, rather than resolving against
    whatever the shell's working directory happened to be: the engine's
    `IntegrityLog` row records the reference and the purpose, **not the
    artifact's path**, so the only account of where a document went is the
    one the receipt showed the operator — and `exports/` names a different
    place from every directory. A path *outside the household root* is
    refused by `paths.ensure`, which resolves symlinks and `..` before it
    checks; that `ValueError` is translated into `ExportRefused` rather
    than reaching a surface as a traceback, and **is not re-checked here**
    — a second copy of a containment rule is a second answer to it, the
    drift the engine closed by giving `export_record` and `logs._ref` one
    shared validator. An export therefore lands inside the root and is
    copied out from there, which is the operator's act, not this package's.

    On confirmation, the whole document becomes one `Classified` — its rung
    is `compose()` over every row's own rung, never a constant, so a
    schedule of instances carrying only a kind and an institution composes
    `L3` and one carrying a balance composes `L4`. The one constant is the
    **empty** schedule's `L2`, and it is the honest score rather than a
    convenience: `compose()` of nothing is `L5`, which would deny at the
    gate and refuse an export of nothing, and an empty document does still
    say one true thing — "no liabilities are on file" — which is exactly
    the step-1/step-2 answer `packs/accounts.py` gives `kind` and `opened`:
    household metadata, no party, no protected category, no amount.

    The composed item carries `NOTICE` as its derived stand-in, and goes to
    `export_record()` **once**, under `matter="schedules"`,
    `item_type="debts"`, `item_id="export"`: one artifact, one
    `IntegrityLog` row, one `VisibleLog` line for the whole schedule, not
    one per account. `export_record` re-serves the document on `S4_EGRESS`
    with `purpose` itself (I-16 — this module is not the gate); the default
    `Purpose.EXPORT` is what makes that second gate agree with the one
    `debts()` already cleared while composing the rows.

    **A second export is not refused — it is a new file.** `export_record`
    creates with `O_EXCL` under a timestamp it stamps itself, so two
    exports of an unchanged schedule land as two documents rather than one
    clobbering the other: confirming the same export again, on a later day,
    is still a fact worth keeping.
    """
    if out_dir is not None and not Path(out_dir).is_absolute():
        raise ExportRefused(
            f"--out takes an absolute directory; {str(out_dir)!r} is "
            "relative and would mean a different place from every working "
            "directory. Nothing was composed and nothing was ledgered."
        )
    document, debt_rows, full_notice = _document(store, include_business=include_business)
    body = json.dumps(document, sort_keys=True, ensure_ascii=False)
    wire = Wire(method="FILE", url="schedules/debts", body=body)
    if not confirm(wire):
        raise ExportRefused(
            "declined at the preview: nothing was exported and nothing was "
            "ledgered — the same posture a refused network send takes."
        )
    rung = compose(*(row.rung for row in debt_rows)) if debt_rows else Rung.L2
    item = Classified(rung, document, full_notice)
    try:
        return export_record(
            item, "schedules", "debts", "export", purpose=purpose, exports=out_dir,
        )
    except ValueError as exc:
        # `paths.ensure` refusing a directory outside the household root —
        # the engine's own containment rule, reported by name here instead
        # of reaching a surface as a bare ValueError traceback (I-11).
        raise ExportRefused(
            f"--out must name a directory under {paths.home()}: {exc}. "
            "Nothing was written and nothing was ledgered — copy the "
            "exported document out of the household root yourself."
        ) from exc
