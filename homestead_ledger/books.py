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
`sha256(date, amount, description, account_number)` — `fingerprint.py` —
so importing the same statement line twice computes the same item id both
times. The account number is no longer one of the fields a transaction
itself carries (bite 2b, I-43 below); it is read once, from the account
instance, purely to compute this same fingerprint. Each of a transaction's
fields is written as its own record, keyed `(account, field, fingerprint)`,
mirroring homestead-law's one-record-per-field custody pack: that is what
lets the gate cross each field independently — an amount denied at L5 would
hide the whole transaction if it were one record; the fields are stored
separately so one being sealed does not seal the rest.

**Bite 2a — classification is registry-driven, not `checking`-shaped.**
`Transaction` gains `kind`: the registered account kind (`registry.
all_accounts()`) whose pack actually authored the four fields' rungs and
derived forms. `import_transaction` looks the kind up through
`registry.account`, which is strict by design (`KeyError` on an unregistered
name) — refused here by name, as a `ValueError`, rather than let a phantom
kind's fields get classified against the wrong pack or crash uninformatively.

**Bite 2b — `account` is an instance label, and the account number lives in
exactly one record (I-43).** `Transaction.account` is no longer a kind name
in disguise: it is the operator-chosen label of a registered account
*instance* (`accounts.py`), and the *canonical matter* a transaction's four
— now three — fields are filed under. `kind` stays a field on `Transaction`
so every call site still names it explicitly (the same AST scan bite 2a
added, `test_every_transaction_in_the_package_says_which_kind_it_is`), but
its value is no longer typed twice by a human: a caller looks it up with
`accounts.kind_of(sidecar, label)` and passes that along, and
`import_transaction` re-derives it from the instance itself and refuses a
disagreement — a defence against a stale or hand-typed value, not a second
place a kind is *decided*. A transaction filed under a label with no
account instance is refused by name, before anything is written.

The bank-issued `account_number` is no longer one of `Transaction`'s own
fields, and is no longer written per transaction at all: it lives in exactly
one record now, the instance's own L5 `number` (`accounts.py`,
`packs/accounts.py`) — provisional **I-43**. The transaction fingerprint
still needs it, so `_account_number` reads it directly off the sidecar's raw
payload — this module is the one allowed payload boundary for that read,
exactly as it already is for writing the canonical books
(`tests/test_invariants_chokepoint.py`). Rows written before this bite still
carry their own `account_number` record; there is no migration (documented
in the README, matching fix: G2c-importer-dates' own "no migration" note).

The first field written (`date`) is the de-duplication gate: its atomic
`insert` either succeeds (a genuinely new transaction) or fails because the
key is occupied, and a failure there refuses the whole import before any new
row is written (I-9 — no silent clobber, no partial duplicate). A failure on
either of the *other* two fields, after `date` succeeded, is a different and
much rarer thing — a torn write from an earlier crash mid-import — and is
reported as a corruption signal rather than treated as an ordinary
re-import. True cross-field atomicity (all fields landing together or not at
all, even across a process crash) is not built in this bite; it would need
either a single-blob record or a transactional multi-key write the
underlying adapter does not expose, and is noted here as a known limitation
rather than silently assumed away.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from homestead.keep.rungs import Classified
from homestead.keep.store import CANONICAL, RecordExists, SQLiteAdapter, key

from homestead_ledger import accounts, registry
from homestead_ledger.fingerprint import fingerprint
from homestead_ledger.store import Sidecar
from homestead_ledger.store import _adapter as _ledger_adapter

__all__ = ["Transaction", "import_transaction", "owed"]

#: The fields written per transaction, in write order. `date` first and on
#: purpose — see the module docstring on why it is the de-duplication gate.
#: `account_number` is no longer among these (I-43) — it lives once, on the
#: account instance.
_FIELD_ORDER = ("date", "amount", "description")


@dataclass(frozen=True)
class Transaction:
    """One transaction as imported, before classification — plain strings.
    `import_transaction` is where each field becomes `Classified` at its
    `kind`'s registered pack's declared rung; nothing here re-declares or
    infers one.

    `account` is the label of a registered account *instance*
    (`accounts.py`) — the matter a transaction is filed under — and `kind`
    is that instance's own registered kind, named explicitly at every call
    site (see the module docstring) rather than defaulted, so a caller
    always states the kind it means."""

    account: str
    date: str
    amount: str
    description: str
    kind: str


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
    returns that unconditionally; a field with neither (`date`) returns
    `None` — L2 needs no derived form.
    """
    spec = schema[field]
    sign_forms = spec.get("derived_by_sign")
    if sign_forms is not None:
        sign = "-" if payload.strip().startswith("-") else "+"
        return sign_forms[sign]
    return spec.get("derived")


def _account_number(sidecar: Sidecar, label: str) -> str:
    """The instance's L5 `number`, read directly off the sidecar's raw
    payload (I-43) — this module is the one allowed payload boundary for the
    reach (`tests/test_invariants_chokepoint.py`), because the transaction
    fingerprint needs the real bank-issued identifier and no surface may
    ever see it (I-13). Refused by name if the instance never recorded one —
    `accounts.add_account` requires it, so this is only reachable by writing
    a sidecar record directly, off the classified path."""
    try:
        record = sidecar.get(accounts.MATTER, "number", label)
    except KeyError:
        raise ValueError(
            f"{label!r}: its account instance has no number on file"
        ) from None
    return record.payload


def import_transaction(txn: Transaction, *, adapter: SQLiteAdapter | None = None) -> str:
    """Write one transaction into the canonical books, keyed by its content
    fingerprint. Refuses a re-import of the same transaction (I-9) rather
    than duplicating or overwriting it; see the module docstring for exactly
    what "refuses" covers and does not.

    `txn.account` must name a registered account **instance**
    (`accounts.py`) — refused by name, before anything is written, when it
    does not. The instance's own kind (`accounts.kind_of`) is read and held
    against `txn.kind`: a disagreement is refused rather than silently
    trusted, since a stale or hand-typed `kind` would otherwise classify a
    card's fields against the checking pack (or vice versa) with nothing
    visible at the call site. Classification itself goes through
    `registry.account(kind)` — the registered pack's own `FIELDS`/`SCHEMA`,
    read live, never one pack's fields hardcoded for every kind (I-23).

    Returns the transaction's item id (its fingerprint), so a caller can
    immediately look the transaction back up through `Canonical`.

    `adapter` defaults to this module's own `homestead-ledger.db` (the same
    file `homestead_ledger.store`'s `Canonical`/`Sidecar` bind to, not the
    engine's bare `homestead.db` default) — a caller only ever passes one
    explicitly to point at a different database, as the tests do via
    `HOMESTEAD_HOME`. The account-instance lookup always uses this module's
    own default `Sidecar()`, matching every other domain module in this
    package (`obligations.py`, `queue.py`).
    """
    sidecar = Sidecar()
    instance_kind = accounts.kind_of(sidecar, txn.account)
    if txn.kind != instance_kind:
        raise ValueError(
            f"{txn.account!r} is registered as {instance_kind!r}, not "
            f"{txn.kind!r} — a transaction's kind is derived from its "
            "account instance and must not disagree with it"
        )
    try:
        account_type = registry.account(instance_kind)
    except KeyError:
        raise ValueError(
            f"{instance_kind!r} is not a registered account kind — one of "
            f"{registry.all_accounts()} (see registry.all_accounts())"
        ) from None

    account_number = _account_number(sidecar, txn.account)
    item_id = fingerprint(
        date=txn.date, amount=txn.amount, description=txn.description,
        account=account_number,
    )
    store = adapter if adapter is not None else _ledger_adapter()
    payloads = {
        "date": txn.date,
        "amount": txn.amount,
        "description": txn.description,
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
