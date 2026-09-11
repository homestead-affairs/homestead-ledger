"""Account **instances** — the real accounts a household actually holds.

Before this bite, `books.Transaction.account` named an account *kind*
directly (`"checking"`) — fine while a household holds one of each kind, but
a real household holds several checking accounts, several cards. Decision 9
("account instances — label ≠ L5 number") fixes that: an operator registers
each real account once, under a **label** of their own choosing (`chk-main`,
`visa-chase`) — never a kind name, and never the bank-issued number itself —
and every transaction is filed under that label from then on. `kind` is
looked up from the instance, not retyped at every transaction.

This module is the writer and reader for that sidecar matter (`accounts`,
`packs/accounts.py`'s schema), in exactly the one-record-per-field shape
`obligations.py` already established for its own sidecar matter: `add_account`
writes each declared field present, keyed `(accounts, <field>, <label>)`;
`instances`/`kind_of`/`label_exists`/`rows`/`detail` read it back, every one
of them through the gate (`serve()`, `Served.value` — never `.payload`).

**A label can never be mistaken for a kind (I-43).** `all_accounts()`
(`checking`, `savings`, `credit_card`, `loan`, …) is the registry's own closed
set of *kinds*; a label equal to one of those names is refused outright, so
nothing downstream — a transaction's matter, a CLI argument, a UI dropdown —
can ever read one string and be unsure whether it names a kind or one
household's particular account.

**`number` is L5 and this module never reads its own payload.** Every
function here serves through the gate; `number` therefore never renders on
any surface this module exposes (S1_LIST or S1_DETAIL — I-13, no override
anywhere). `books.py` is the one place that reads the raw number, directly
off the sidecar's payload, because the transaction fingerprint still needs
the real bank-issued identifier (I-43's "one record", not "nowhere") — and
`books.py` is already this package's one allowed payload boundary
(`tests/test_invariants_chokepoint.py`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from homestead.keep.dates import parse_deadline
from homestead.keep.rungs import Classified, Disposition, Rung, Surface, compose, serve

from homestead_ledger import money, registry
from homestead_ledger.app.cover import cover_counts
from homestead_ledger.packs import accounts as pack
from homestead_ledger.store import InvalidKey, RecordExists, Ref, Replaced, Sidecar, key

__all__ = [
    "MATTER", "FIELDS", "MISSING", "SEALED", "AccountRow",
    "add_account", "instances", "kind_of", "label_exists", "rows", "detail", "cover",
]

MATTER = pack.MATTER
FIELDS = pack.FIELDS

#: The stand-in text for the L3/L4 fields — the same convention
#: `obligations.py`'s `DERIVED` uses. Every string here names that a fact is
#: on file, never its magnitude.
DERIVED: dict[str, str] = {
    "institution": "an institution is on file",
    "balance_as_of": "a balance is on file",
    "rate": "a rate is on file",
    "limit": "a limit is on file",
    "min_payment": "a minimum payment is on file",
}

#: What a field that is not on file reads as on the list — never a plausible
#: blank (I-8): an instance that never recorded a rate is a gap, not a zero.
MISSING = "(missing)"

#: What a field the gate refused reads as — present, classified, and not for
#: this surface. `number` (L5) always reads this way, everywhere (I-13).
SEALED = "(sealed)"

#: Write order. `kind` first: it is always present (`add_account` requires
#: it), so it is the de-duplication gate — the field `instances()`,
#: `kind_of()` and `label_exists()` all key off. The same posture
#: `obligations.py` gives `due_date` and `books.py` gives `date`.
_ORDER = (
    "kind", "number", "institution", "opened", "balance_as_of", "rate",
    "limit", "payment_due_day", "min_payment",
)

#: The closed id shape every matter instance in this build uses (the plan's
#: decision 2): lowercase letters, digits and hyphens, 1-40 characters,
#: starting with a letter or digit, no dot — so a future `<label>.<sub>` id
#: stays unambiguous. Identical to `obligations.py`'s `_ID`.
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def _label(value: object) -> str:
    """`value` as a valid, non-kind-colliding label, or `InvalidKey`.

    Refuses without echoing anything but the value itself back (it is a
    reference the operator typed and will see again, not a secret) — the
    same posture `obligations._identifier` takes for its own id.
    """
    ident = str(value).strip()
    if not _ID.match(ident):
        raise InvalidKey(
            "an account label is the household's own short name for one "
            "real account: lowercase letters, digits and hyphens, 1-40 "
            "characters, starting with a letter or digit (chk-main, "
            "visa-chase) — never the bank-issued number"
        )
    if ident in registry.all_accounts():
        raise InvalidKey(
            f"{ident!r} is a registered account *kind*, not a label — a "
            "label equal to a kind name could be mistaken for one (I-43). "
            "Pick a different label for this account (chk-main, "
            "visa-chase, …) and name the kind with --kind."
        )
    return ident


def _payment_due_day(value: object) -> str:
    text = str(value).strip()
    if not text.isdigit() or not 1 <= int(text) <= 31:
        raise ValueError("payment_due_day is a day of the month, 1-31")
    return str(int(text))


def add_account(
    store: Sidecar,
    label: str,
    *,
    kind: str,
    number: str,
    institution: str | None = None,
    opened: str | None = None,
    balance_as_of: object | None = None,
    rate: object | None = None,
    limit: object | None = None,
    payment_due_day: object | None = None,
    min_payment: object | None = None,
    replace: bool = False,
) -> tuple[Ref, Replaced | None]:
    """Register one real account under `label`. Returns its `kind` field's
    ref and, on an explicit replace, what that field displaced.

    `kind` must be a registered account kind (`registry.all_accounts()`) and
    `number` is required and non-empty — every other field is optional and
    is written only when given, never as a placeholder. Refuses — before
    writing anything — a bad or kind-colliding label, an unregistered kind,
    a missing number, an unparseable `opened` date, a non-finite money field,
    or a `payment_due_day` outside 1-31.

    **The occupied-label refusal is the store's, not a check's (I-9)**,
    exactly as `obligations.add_obligation` documents for its own id: `kind`
    (always present) is written first with `overwrite=False`, so the
    adapter's own atomic insert is the gate rather than a `has()` check that
    could go stale between two writers. `replace=True` is the one path that
    overwrites, and reports what it displaced.

    **The torn-write gap.** As many as nine separate writes with no
    multi-key transaction underneath — the same limitation `books.py` and
    `obligations.py` document for their own multi-field records, for the
    same reason. `rows()`/`detail()` show an absent field as `MISSING`
    rather than guessing one in.
    """
    ident = _label(label)
    try:
        registry.account(kind)
    except KeyError:
        raise ValueError(
            f"{kind!r} is not a registered account kind — one of "
            f"{registry.all_accounts()} (see registry.all_accounts())"
        ) from None
    account_number = str(number).strip()
    if not account_number:
        raise ValueError(
            "an account number is required — `account add <label> --kind "
            "<kind> --number <number>`"
        )

    values: dict[str, str] = {"kind": kind, "number": account_number}
    if institution is not None and str(institution).strip():
        values["institution"] = str(institution).strip()
    if opened is not None:
        values["opened"] = parse_deadline(opened).iso
    if balance_as_of is not None:
        values["balance_as_of"] = money.amount_text(balance_as_of, field="balance_as_of")
    if rate is not None:
        values["rate"] = money.amount_text(rate, field="rate")
    if limit is not None:
        values["limit"] = money.amount_text(limit, field="limit")
    if payment_due_day is not None:
        values["payment_due_day"] = _payment_due_day(payment_due_day)
    if min_payment is not None:
        values["min_payment"] = money.amount_text(min_payment, field="min_payment")

    ref = key(MATTER, "kind", ident)
    order = [field for field in _ORDER if field in values]
    replaced: Replaced | None = None
    for index, field in enumerate(order):
        record = Classified(FIELDS[field], values[field], DERIVED.get(field))
        first = index == 0
        if first and not replace:
            try:
                store.put(MATTER, field, ident, record, overwrite=False)
            except RecordExists:
                raise RecordExists(
                    f"{MATTER}/{ident} already exists. A write never "
                    "silently overwrites (I-9): pass --replace (the CLI) or "
                    '"replace": true (the UI) to replace it.'
                ) from None
            continue
        result = store.put(MATTER, field, ident, record, overwrite=True)
        if first:
            replaced = result
    return ref, replaced


def instances(store: Sidecar) -> list[str]:
    """Every account label on file, sorted — read off `kind`, the field
    every instance always has (the same posture `obligations.rows` takes
    reading `due_date`)."""
    return sorted(
        item_id for (_, field, item_id), _ in store.records(MATTER) if field == "kind"
    )


def kind_of(store: Sidecar, label: str) -> str:
    """The registered kind `label`'s instance was declared under.

    Served on `S1_LIST` — `kind` is `L2`, so this always renders when the
    instance exists — and refused **by name** (I-11) when there is no such
    instance: a transaction filed under an unregistered label is exactly the
    phantom-matter shape I-23 forbids for a kind, one level down.
    """
    try:
        record = store.get(MATTER, "kind", label)
    except KeyError:
        raise ValueError(
            f"{label!r}: no such account instance — `account add {label} "
            "--kind <kind> --number <number>` first, or `account list` to "
            "see what is on file"
        ) from None
    served = serve(record, Surface.S1_LIST)
    if served.disposition is Disposition.DENY:
        # kind is declared L2, below every surface's plain ceiling, so this
        # can never actually happen while the pack stays as declared — fail
        # closed by name anyway rather than assume the crossing never moves.
        raise ValueError(f"{label!r}: its account kind is sealed and unreadable")
    return str(served.value)


def label_exists(store: Sidecar, label: str) -> bool:
    """Whether `label` has an account instance on file at all."""
    return store.has(MATTER, "kind", label)


@dataclass(frozen=True)
class AccountRow:
    """One account instance as the list pane shows it: its label, the kind
    (renders — L2) and the institution (renders, or its derived form, or a
    gap) — never the number (L5, I-13, never a row or a detail anywhere)."""

    label: str
    kind: str
    institution: str
    rung: Rung


def _served(record: Classified, surface: Surface) -> str | None:
    served = serve(record, surface)
    return None if served.disposition is Disposition.DENY else str(served.value)


#: The fields `rows()` actually shows — `number` is never among them (I-13),
#: so it never enters this row's composed rung either: a rung badge on a row
#: that cannot ever display the number would otherwise always read `L5` and
#: say nothing about what the row actually shows.
_ROW_FIELDS = ("kind", "institution")


def rows(store: Sidecar) -> list[AccountRow]:
    """Every account instance on file, by label."""
    by_label: dict[str, dict[str, Classified]] = {}
    for (_, field, item_id), record in store.records(MATTER):
        by_label.setdefault(item_id, {})[field] = record
    out: list[AccountRow] = []
    for label in sorted(by_label):
        fields = by_label[label]

        def text(field: str) -> str:
            if field not in fields:
                return MISSING
            value = _served(fields[field], Surface.S1_LIST)
            return SEALED if value is None else value

        out.append(AccountRow(
            label=label, kind=text("kind"), institution=text("institution"),
            rung=compose(*(fields[f].rung for f in _ROW_FIELDS if f in fields)),
        ))
    return out


def detail(store: Sidecar, label: str) -> dict[str, tuple[str, str | None]]:
    """One account instance opened in the detail pane: field → (rung,
    rendered value or `None` where the gate refused). `number` always lands
    here as `(L5, None)` (I-13) — its rung is visible, its value never is.
    Empty if there is no such label."""
    out: dict[str, tuple[str, str | None]] = {}
    for (_, field, found), record in store.records(MATTER):
        if found == label:
            out[field] = (record.rung.value, _served(record, Surface.S1_DETAIL))
    return out


def cover(store: Sidecar) -> dict[str, int]:
    """The counts the resting cover may show about the household's account
    instances (I-31): with fewer than two instances on file, absence, not
    zero — a count over a single account resolves to that one account the
    instant it is read."""
    labels = instances(store)
    return cover_counts(labels, instances=len(labels))
