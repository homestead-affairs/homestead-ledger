"""The books — the one place transactions enter the canonical record.

`homestead.keep.store.Canonical` ships with no write method at all, by
design: "the operator's own tools grow the canonical record; the app reads it
and never edits or deletes it" (the engine's own `record.py` docstring, the
file-backed sibling of the SQLite `store.py` this repo binds to). This module
is that operator tool for homestead-ledger — a bank statement import, in bite
4's shape; here, a single `import_transaction` that bite 1's tests and
`--demo` both call. **Nothing else in this package writes to CANONICAL**, and
this module is deliberately the only one that reaches
`homestead.keep.store.CANONICAL` directly.

**Mirror, not judge.** The app — the demo, the future tkinter window, any
surface — only ever gets `Canonical`'s read-only handle. This module is not
"the app" in that sense: it is the tool that grows the books, the same way a
bank's own statement is the thing that grows a paper ledger. Once a
transaction is imported it is immutable; there is no `update_transaction`
here or anywhere in this package.

**Identity is a content fingerprint (I-7/I-9).** A transaction's key is
`sha256(date, amount, description, account_number)` — `fingerprint.py` — so
importing the same statement line twice computes the same item id both
times. Each of a transaction's four fields is written as its own record,
keyed `(account, field, fingerprint)`, mirroring homestead-law's one-record-
per-field custody pack: that is what lets the gate cross each field
independently (an amount denied at L5 would hide the whole transaction if it
were one record; account_number and amount are stored separately so one
being sealed does not seal the rest).

**Bite 2a — classification is registry-driven, not `checking`-shaped.**
`Transaction` gains `kind`: the registered account kind (`registry.
all_accounts()`) whose pack actually authored the four fields' rungs and
derived forms. `account` stays the *matter* name for now — the label a
transaction is filed under, which bite 2b turns into an instance distinct
from its kind; until then the two are the same value in practice, but this
module never assumes that (it reads `kind`, never `account`, to find the
pack). `import_transaction` looks the kind up through `registry.account`,
which is strict by design (`KeyError` on an unregistered name) — refused
here by name, as a `ValueError`, rather than let a phantom kind's fields get
classified against the wrong pack or crash uninformatively.

The first field written (`date`) is the de-duplication gate: its atomic
`insert` either succeeds (a genuinely new transaction) or fails because the
key is occupied, and a failure there refuses the whole import before any new
row is written (I-9 — no silent clobber, no partial duplicate). A failure on
any of the *other* three fields, after `date` succeeded, is a different and
much rarer thing — a torn write from an earlier crash mid-import — and is
reported as a corruption signal rather than treated as an ordinary
re-import. True cross-field atomicity (all four fields landing together or
not at all, even across a process crash) is not built in this bite; it would
need either a single-blob record or a transactional multi-key write the
underlying adapter does not expose, and is noted here as a known limitation
rather than silently assumed away.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from homestead.keep.rungs import Classified
from homestead.keep.store import CANONICAL, RecordExists, SQLiteAdapter, key

from homestead_ledger import registry
from homestead_ledger.fingerprint import fingerprint
from homestead_ledger.packs import checking  # default `kind` below, nothing else
from homestead_ledger.store import _adapter as _ledger_adapter

__all__ = ["Transaction", "import_transaction", "owed"]

#: The fields written per transaction, in write order. `date` first and on
#: purpose — see the module docstring on why it is the de-duplication gate.
_FIELD_ORDER = ("date", "amount", "description", "account_number")


@dataclass(frozen=True)
class Transaction:
    """One transaction as imported, before classification — plain strings.
    `import_transaction` is where each field becomes `Classified` at its
    `kind`'s registered pack's declared rung; nothing here re-declares or
    infers one. `kind` defaults to `checking.ACCOUNT` only so that existing
    callers who never dealt with a second account kind keep working
    unchanged — a caller that means a different kind always says so."""

    account: str
    date: str
    amount: str
    description: str
    account_number: str
    kind: str = checking.ACCOUNT


def _blob(item: Classified) -> str:
    """The wire shape `homestead.keep.store._hydrate` reads back: `{"rung",
    "payload", "derived"}`. That function is private to the engine — an
    adapter deliberately never derives its own serialization — so this
    repeats its documented shape rather than importing a private name.
    `tests/test_books.py::test_import_transaction_bypasses_canonical_and_
    sidecar_deliberately` round-trips a written record back through the real
    `Canonical.get`, which is what would catch this drifting from the
    engine's own format.
    """
    return json.dumps({"rung": item.rung.value, "payload": item.payload, "derived": item.derived})


def _derived_for(schema: dict, field: str, payload: str) -> str | None:
    """The stand-in text for a field whose rung can be derived (L3/L4) —
    never the payload restated, never its magnitude — read off the account
    kind's *own* pack declaration rather than a convention hardcoded here.

    A field whose declaration carries `derived_by_sign` (bite 2a: `amount`,
    on every account pack) picks the form for the payload's sign — `"-"` or
    `"+"` — so a liability pack's charge/payment wording and an asset pack's
    debit/credit wording each come from the pack that means them, never from
    a guess this module makes about what "negative" implies for a kind it
    was not told about. A field with a plain `derived` string (`description`)
    returns that unconditionally; a field with neither (`date`,
    `account_number`) returns `None` — L2 and L5 need no derived form.
    """
    spec = schema[field]
    sign_forms = spec.get("derived_by_sign")
    if sign_forms is not None:
        sign = "-" if payload.strip().startswith("-") else "+"
        return sign_forms[sign]
    return spec.get("derived")


def import_transaction(txn: Transaction, *, adapter: SQLiteAdapter | None = None) -> str:
    """Write one transaction into the canonical books, keyed by its content
    fingerprint. Refuses a re-import of the same transaction (I-9) rather
    than duplicating or overwriting it; see the module docstring for exactly
    what "refuses" covers and does not.

    Classifies each field through `registry.account(txn.kind)` — the
    registered pack's own `FIELDS`/`SCHEMA`, read live, never one pack's
    fields hardcoded for every kind (I-23: the registry is the only
    enumeration, and that includes which pack answers for a kind). `txn.kind`
    naming a kind that is not registered is refused by name, as a
    `ValueError`, before any row is written — the same "fail closed, name the
    field" posture the rest of this module already takes.

    Returns the transaction's item id (its fingerprint), so a caller can
    immediately look the transaction back up through `Canonical`.

    `adapter` defaults to this module's own `homestead-ledger.db` (the same
    file `homestead_ledger.store`'s `Canonical`/`Sidecar` bind to, not the
    engine's bare `homestead.db` default) — a caller only ever passes one
    explicitly to point at a different database, as the tests do via
    `HOMESTEAD_HOME`.
    """
    try:
        account_type = registry.account(txn.kind)
    except KeyError:
        raise ValueError(
            f"{txn.kind!r} is not a registered account kind — one of "
            f"{registry.all_accounts()} (see registry.all_accounts())"
        ) from None

    item_id = fingerprint(
        date=txn.date, amount=txn.amount, description=txn.description,
        account=txn.account_number,
    )
    store = adapter if adapter is not None else _ledger_adapter()
    payloads = {
        "date": txn.date,
        "amount": txn.amount,
        "description": txn.description,
        "account_number": txn.account_number,
    }

    for index, field in enumerate(_FIELD_ORDER):
        payload = payloads[field]
        rung = account_type.fields[field]
        classified = Classified(rung, payload, _derived_for(account_type.schema, field, payload))
        ref = key(txn.account, field, item_id)
        wrote = store.insert(CANONICAL, ref, _blob(classified))
        if wrote:
            continue
        if index == 0:
            raise RecordExists(
                f"{txn.account}/{field}/{item_id}: this transaction is already "
                "on the books. A content-fingerprint id refuses a re-import "
                "rather than repeating it (I-7/I-9) — re-importing an "
                "overlapping statement range must not duplicate a transaction."
            )
        raise RecordExists(
            f"{txn.account}/{field}/{item_id}: this field already exists but "
            f"{_FIELD_ORDER[0]!r} for the same transaction did not (it was just "
            "written by this call) — a partial record from an earlier "
            "interrupted import, not an ordinary re-import. The books may be "
            "inconsistent for this transaction and want an operator's look."
        )

    return item_id


def owed(total: float) -> float:
    """A liability's *owed* figure, from its raw signed running total.

    Every account pack signs `amount` from the household's own side (see
    each pack's module docstring): money leaving is negative on every kind,
    which for a liability means a charge is negative and a payment/credit is
    positive — exactly the same signs an asset account gives a debit and a
    credit. Summing those the way an asset account's running total works
    would leave a card with three charges and no payments reading
    *negative*, which is correct arithmetic and the wrong word for a debt:
    a household says it owes three hundred dollars, not that its card reads
    minus three hundred. Negating the total once, here, is that conversion —
    the one place it happens, so `balance.running_balance(..., liability=
    True)` does not have to know the sign convention itself, only that a
    liability's total needs this applied and an asset's does not.
    """
    return -total
