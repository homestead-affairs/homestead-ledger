"""The overlay — the household's own layer over its read-only books.

`books.py` is the one writer of the canonical books ("mirror, not judge"): a
transaction is imported once and never edited. A household still wants to
say things *about* a transaction — "this was groceries", "call the bank
about this one", "this never counts as spending" — without touching the row.
This module is that layer: one record per field, keyed `(overlay,
<category|note|confirmed_merchant|do_not_use>, <fingerprint>)`, the same
one-record-per-field shape `accounts.py`/`obligations.py` already establish.
The **fingerprint** (`books.fingerprint`) is the key on both sides — never a
per-account item id — because a category is a fact about *this* transaction
wherever it is filed, and the fingerprint is already its one stable name.

**`tag` is the pack's advisory made concrete.** `packs/overlay.py` declares
`category` at `L3` — the floor every ordinary category sits at — with a
closed word list, `PROTECTED_CATEGORY_WORDS`. A category whose text
*contains* one of those words is written at `L4` instead, reusing the
schema's own `derived` string for the L4 case. **There is no path here that
composes an already-`L4` category back down** — `homestead.keep.advise`'s
"argue up, never down" rule, for one closed word list.

**`excluded_fingerprints` is the seam a household's own aggregates read
through — and the seam `G4-transfers`/`G4-budget`/`G5-sync` will read too.**
It reads *only* `do_not_use`. `recurring.detect_recurring` and a running
balance take plain tuples with no notion of "excluded"; the filtering
happens at the *callers* that build those tuples (`server.py`'s
`/api/subscriptions`, `cli.py`'s `transaction list`), never inside
`balance.py`/`recurring.py` — neither imports this module. `G4-transfers` is
expected to union its own excluded pair-fingerprints into this same set.
"""
from __future__ import annotations

import re

from homestead.keep.logs import Event, VisibleLog
from homestead.keep.rungs import Classified, Disposition, Rung, Surface, serve

from homestead_ledger import accounts
from homestead_ledger.packs import overlay as pack
from homestead_ledger.store import Canonical, RecordExists, Ref, Replaced, Sidecar, key

__all__ = [
    "MATTER", "FIELDS", "PROTECTED_CATEGORY_WORDS",
    "unknown_fingerprint", "ambiguous_fingerprint",
    "tag", "tags_of", "excluded_fingerprints",
]

MATTER = pack.MATTER
FIELDS = pack.FIELDS
PROTECTED_CATEGORY_WORDS = pack.PROTECTED_CATEGORY_WORDS

#: The three fields `tags_of` reads back. `do_not_use` is deliberately not
#: among them — a caller checks it by reference (`excluded_fingerprints`).
_TAG_FIELDS = ("category", "confirmed_merchant", "note")

#: Lowercase letters, digits and hyphens, 1-40 characters, starting with a
#: letter — the same posture every closed id in this package takes
#: (`obligations._ID`, `accounts._ID`).
_CATEGORY = re.compile(r"^[a-z][a-z0-9-]{0,39}$")

#: What a free-text field will hold. A field with no ceiling is a place to
#: paste a bank statement into, and an `L4` note that holds a statement is a
#: statement classified as a note. `confirmed_merchant` is a *name* and gets
#: a name's length; `note` is a sentence or two about one row.
_TEXT_LIMITS = {"confirmed_merchant": 120, "note": 2000}

#: The shortest prefix `tag` will resolve to a whole fingerprint. `cli.py`'s
#: `transaction list` shows twelve characters and the browser row carries the
#: whole thing in `data-fp`, so eight is already shorter than anything a
#: surface offers to copy; below that a string is a typo, not a reference.
_MIN_PREFIX = 8


def unknown_fingerprint(fingerprint: str) -> str:
    """The "no such transaction" refusal. Names the fingerprint the operator
    typed — a reference, not the row (I-15) — never a date, amount or
    description a lookup might have found."""
    return (
        f"{fingerprint!r}: no such transaction on the books. A fingerprint "
        "must already be on the books — `transaction list --account "
        "<label>` shows what is on file — before it can be tagged."
    )


def ambiguous_fingerprint(prefix: str, count: int) -> str:
    """The "that prefix names more than one transaction" refusal. Names the
    prefix the operator typed and *how many* rows begin with it — a count is
    not a row (I-15) — never which rows, never a date, amount or description
    of either."""
    return (
        f"{prefix!r}: {count} transactions on the books begin with that. A "
        "prefix has to name exactly one row: type more of the fingerprint "
        "(the whole one always works) and tag again."
    )


def _resolve(canonical: Canonical, sidecar: Sidecar, fingerprint: str) -> str:
    """The **whole** fingerprint `fingerprint` names, or a refusal.

    Two rules, and they are the bite's ruling on truncated ids:

    1. **A key is always the whole fingerprint.** The item id this module
       writes under is the same 64-hex sha256 `books.import_transaction`
       keys the canonical row under — never a truncation of one. The engine's
       `keep.store.key` puts no length or alphabet on an item id (it refuses a
       separator, a `..`, a NUL and surrounding whitespace, and nothing else),
       so the whole digest is a valid id and there is nothing to shorten.
       Truncation would *create* the collision that hashing rules out.
    2. **Only what the operator types may be short.** `transaction list`
       prints twelve characters, so a prefix is what a household actually has
       to hand; it is resolved here, against the books, to the one whole
       fingerprint it names. A prefix matching two rows is **refused by name**
       (`ambiguous_fingerprint`) rather than resolved to the first — the only
       place a shortened id could ever pick the wrong row, closed.

    Checks every registered instance (`accounts.instances`): a fingerprint
    carries no account of its own — `tag` takes only the fingerprint, as
    `obligations.mark_paid` already does for its own. A household holds a
    handful of accounts; this is not CSV import's hot path.
    """
    labels = accounts.instances(sidecar)
    if any(canonical.has(label, "date", fingerprint) for label in labels):
        return fingerprint
    if len(fingerprint) < _MIN_PREFIX:
        raise ValueError(unknown_fingerprint(fingerprint))
    matches = sorted({
        item_id
        for label in labels
        for (_, field, item_id), _record in canonical.records(label)
        if field == "date" and item_id.startswith(fingerprint)
    })
    if not matches:
        raise ValueError(unknown_fingerprint(fingerprint))
    if len(matches) > 1:
        raise ValueError(ambiguous_fingerprint(fingerprint, len(matches)))
    return matches[0]


def _category(value: object) -> str:
    text = str(value).strip()
    if not _CATEGORY.match(text):
        raise ValueError(
            "a category is a short, closed-shape word: lowercase letters, "
            "digits and hyphens, 1-40 characters, starting with a letter "
            "(groceries, medical-copay)"
        )
    return text


def _is_protected(category: str) -> bool:
    """Whether the category *string* contains a `PROTECTED_CATEGORY_WORDS`
    word as a **substring** — not whether one of its `-`-separated tokens
    equals one.

    The rule and the reason are pinned in `packs/overlay.py`: substring
    containment over-classifies (`medically-unrelated-shop` contains
    `medical` and is raised) and never under-classifies, and over-classifying
    is the direction "argue up, never down" permits. A token rule would leave
    `medically-unrelated-shop` on the list at `L3`; this one does not."""
    return any(word in category for word in PROTECTED_CATEGORY_WORDS)


def _text(value: object, *, field: str) -> str:
    """One free-text field's value: non-empty, under `_TEXT_LIMITS[field]`,
    and — for a merchant *name* — one line of ordinary text. The refusals
    name the field and the limit, never the value (I-15)."""
    name = field.replace("_", " ")
    text = str(value).strip()
    if not text:
        raise ValueError(f"a {name}, if given, is not empty")
    if len(text) > _TEXT_LIMITS[field]:
        raise ValueError(
            f"a {name} is at most {_TEXT_LIMITS[field]} characters — the "
            "overlay says something about a transaction; it is not a place "
            "to keep a document"
        )
    if any(ord(ch) < 32 and ch != "\n" for ch in text) or (
        field == "confirmed_merchant" and "\n" in text
    ):
        raise ValueError(
            f"a {name} is plain text — a control character is not part of "
            "a name a household would recognise"
        )
    return text


def tag(
    store: Sidecar,
    fingerprint: str,
    *,
    category: str | None = None,
    note: str | None = None,
    confirmed_merchant: str | None = None,
    do_not_use: bool | None = None,
    replace: bool = False,
    canonical: Canonical | None = None,
) -> dict[str, tuple[Ref, Replaced | None]]:
    """Tag one transaction by its content fingerprint. Returns each field
    actually written, mapped to its ref and — on `replace` — what it
    displaced.

    `fingerprint` must already be on the books — refused **by name**, before
    anything is written, when it is not (`unknown_fingerprint`), never
    echoing a row this happened to find while looking. It may be the whole
    64-hex fingerprint or a prefix of at least `_MIN_PREFIX` characters (what
    `transaction list` prints); a prefix that names two rows is refused
    (`ambiguous_fingerprint`), never resolved to the first — see `_resolve`,
    which is also this bite's ruling on truncated ids. **The record is always
    keyed by the whole fingerprint**, whatever was typed. `canonical`
    defaults to `Canonical()`; a caller passes one only to point at another
    database.

    At least one of `category`/`note`/`confirmed_merchant`/`do_not_use` must
    be given.

    **Each field is its own gate, independently (I-9) — unlike
    `add_account`/`add_obligation`, whose several fields belong to *one row*
    created together and share one dedup gate.** An overlay's four item
    types are independent facts about the same fingerprint — `category`
    today, a `note` next month — so each is its own atomic insert, refused
    on its own (`RecordExists`) unless `replace`. A call tagging several
    fields that hits an occupied one partway through leaves the rest written
    and is refused for that one — the same torn-write posture
    `add_account`/`add_obligation` document, restated for fields that were
    never one record.

    **The protected-shape composition** lives here, not in the pack: a
    `category` containing a `PROTECTED_CATEGORY_WORDS` word is written at
    `L4`, never the declared `L3` floor — see the module docstring.
    """
    typed = str(fingerprint).strip()
    if not typed:
        raise ValueError("a fingerprint is required")
    if do_not_use is False:
        # Not the same as leaving it out. There is no un-tag path in this
        # bite, so a `False` that quietly wrote nothing would read to the
        # caller as "cleared" — fail closed and say so (I-11).
        raise ValueError(
            "do_not_use is set here, never cleared: there is no un-tag path "
            "yet, so passing it as false would silently do nothing. Leave it "
            "out instead."
        )
    canon = canonical if canonical is not None else Canonical()
    fp = _resolve(canon, store, typed)

    values: dict[str, Classified] = {}
    if category is not None:
        text = _category(category)
        rung = Rung.L4 if _is_protected(text) else Rung.L3
        values["category"] = Classified(rung, text, pack.SCHEMA["category"]["derived"])
    if confirmed_merchant is not None:
        text = _text(confirmed_merchant, field="confirmed_merchant")
        values["confirmed_merchant"] = Classified(
            FIELDS["confirmed_merchant"], text, pack.SCHEMA["confirmed_merchant"]["derived"]
        )
    if note is not None:
        text = _text(note, field="note")
        values["note"] = Classified(FIELDS["note"], text, pack.SCHEMA["note"]["derived"])
    if do_not_use:
        values["do_not_use"] = Classified(FIELDS["do_not_use"], "true")

    if not values:
        raise ValueError(
            "tag at least one of category, note, confirmed_merchant, "
            "do_not_use — there is nothing to write otherwise"
        )

    out: dict[str, tuple[Ref, Replaced | None]] = {}
    for field, record in values.items():
        ref = key(MATTER, field, fp)
        if replace:
            replaced = store.put(MATTER, field, fp, record, overwrite=True)
        else:
            try:
                replaced = store.put(MATTER, field, fp, record, overwrite=False)
            except RecordExists:
                raise RecordExists(
                    f"{MATTER}/{field}/{fp[:12]}… is already tagged. A "
                    "write never silently overwrites (I-9): pass --replace "
                    '(the CLI) or "replace": true (the UI) to replace it.'
                ) from None
        out[field] = (ref, replaced)

    # A reference only (I-15): the matter and the fingerprint, never the
    # category word, the note text or the merchant name just stored.
    if "note" in out:
        VisibleLog().record(Event.NOTE_ADDED, ref=(MATTER, fp))
    if set(out) - {"note"}:
        VisibleLog().record(Event.RECORD_ADDED, ref=(MATTER, fp))
    return out


def tags_of(
    store: Sidecar, fingerprint: str, *, surface: Surface = Surface.S1_LIST,
) -> dict[str, str]:
    """`category`/`confirmed_merchant`/`note` on file for `fingerprint`,
    served at `surface` — never `.payload`. An ordinary `category` renders
    on `S1_LIST`; one raised to `L4` derives there; `note` (always `L4`)
    derives on `S1_LIST` and renders on `S1_DETAIL` — a caller opening a
    transaction's detail passes `Surface.S1_DETAIL` explicitly.

    `do_not_use` is never among these — `excluded_fingerprints` is how a
    caller reads that one."""
    out: dict[str, str] = {}
    for field in _TAG_FIELDS:
        try:
            record = store.get(MATTER, field, fingerprint)
        except KeyError:
            continue
        served = serve(record, surface)
        if served.disposition is not Disposition.DENY:
            out[field] = str(served.value)
    return out


def excluded_fingerprints(store: Sidecar) -> frozenset[str]:
    """Every fingerprint the household has marked `do_not_use` — read from
    that one field only. `recurring.detect_recurring` and a running balance
    both drop a transaction in this set, filtered at the caller that already
    builds their input tuples — never a `.payload` reach here (a field's own
    presence is the fact), and neither `balance.py` nor `recurring.py`
    imports this module. `G4-transfers` is expected to union its own
    excluded pair-fingerprints into this same set at its own call sites."""
    return frozenset(
        item_id for (_, field, item_id), _record in store.records(MATTER)
        if field == "do_not_use"
    )
