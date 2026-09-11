"""The budget — per-category, per-month spending limits, and the derived
envelope state a household reads them through.

`(budget, "limit", "<category>.<YYYY-MM>")` is the one record `set_limit`
writes (decision 9) — never a figure the books themselves produced
("mirror, not judge", restated for a number the household typed).
`category` is held to the identical closed shape and protected-word list
`overlay.py` classifies a transaction's own category against — mirrored
here rather than imported (`overlay._CATEGORY` is private), with
`PROTECTED_CATEGORY_WORDS` read straight off `packs.overlay` so there is
only ever one word list. **A protected category's *limit* is `L4` either
way** (money has no lower floor); what still argues up is the category's
own *name* wherever an envelope names one on a list
(`_displayed_category`, the same stand-in `overlay.tags_of` gives).

**`envelopes()` never stores anything.** It is arithmetic over the books
(`balance.dated_transactions` — mirrored exactly; no `.payload` of its own)
and the limits on file, recomputed on every call — `balance.
running_balance`'s own posture for a running total. Every figure it
touches to decide "over or within" comes through the gate first
(`Served.value` at `S1_DETAIL`); a caller reads only `category`,
`spent_state`, `limit_state` and the boolean `over` (I-8/I-15: never a
figure on `S1_LIST`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from homestead.keep.logs import Event, VisibleLog
from homestead.keep.rungs import Classified, Disposition, Surface, serve

from homestead_ledger import accounts, overlay
from homestead_ledger.balance import dated_transactions
from homestead_ledger.packs import budget as pack
from homestead_ledger.packs import overlay as overlay_pack
from homestead_ledger.store import Canonical, RecordExists, Ref, Replaced, Sidecar, key

__all__ = [
    "MATTER", "FIELDS", "Envelope",
    "set_limit", "limits", "limit_detail", "envelopes", "state_text",
]

MATTER = pack.MATTER
FIELDS = pack.FIELDS

#: Mirrors `overlay._CATEGORY` — held equal to it by `tests/test_budget.py`.
_CATEGORY = re.compile(r"^[a-z][a-z0-9-]{0,39}$")

#: `YYYY-MM`, zero-padded, 01-12 only.
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

#: A positive amount, at most two decimal places, no sign and no exponent —
#: stricter than `money.decimal_amount`, which accepts `1e3` and rounds
#: three decimals rather than refusing them. A limit is typed by hand, not
#: read off a bank statement, so it needs none of that tolerance.
_AMOUNT = re.compile(r"^\d+(\.\d{1,2})?$")

#: The category's own derived stand-in, read off `overlay`'s schema rather
#: than retyped — the identical string `overlay.tags_of` gives a protected
#: category on `S1_LIST`.
_CATEGORY_DERIVED = overlay_pack.SCHEMA["category"]["derived"]

#: The four labels a surface may show for one envelope — never a figure.
NO_LIMIT = "no limit set"
NO_SPEND = "no spend"
LIMIT_SET = "a limit is set"
HAS_SPEND = "spending on file"


def _category(value: object) -> str:
    text = str(value).strip()
    if not _CATEGORY.match(text):
        raise ValueError(
            "a category is a short, closed-shape word: lowercase letters, "
            "digits and hyphens, 1-40 characters, starting with a letter "
            "(groceries, medical-copay) — the same shape `transaction tag "
            "--category` takes"
        )
    return text


def _month(value: object) -> str:
    text = str(value).strip()
    if not _MONTH.match(text):
        raise ValueError(
            "a month is YYYY-MM (2026-09) — the calendar month a budget "
            "limit or an envelope applies to"
        )
    return text


def _limit_amount(value: object) -> Decimal:
    text = str(value).strip()
    if not _AMOUNT.match(text):
        raise ValueError(
            "a budget limit is a positive amount with at most two decimal "
            "places (400, 400.00) — no sign, no scientific notation"
        )
    amount = Decimal(text)
    if amount <= 0:
        raise ValueError("a budget limit is greater than zero")
    return amount


def _is_protected(category: str) -> bool:
    """Substring containment — the false-negative-avoiding rule
    `overlay._is_protected` applies, reused via `PROTECTED_CATEGORY_WORDS`
    rather than a second list."""
    return any(word in category for word in overlay_pack.PROTECTED_CATEGORY_WORDS)


def _displayed_category(category: str) -> str:
    """`category` as an envelope names it on `S1_LIST`: the real word, or —
    the instant it contains a protected word — the same derived stand-in
    `overlay.tags_of` gives its own `category` field. Argues up only, the
    same as `overlay.tag`."""
    return _CATEGORY_DERIVED if _is_protected(category) else category


def set_limit(
    store: Sidecar, category: str, month: str, amount: object, *, replace: bool = False,
) -> tuple[Ref, Replaced | None]:
    """Set the household's own spending limit for one category and month.
    Returns the limit's ref and, on an explicit replace, what it displaced.

    Refuses, before writing anything: a bad category shape, a month that is
    not `YYYY-MM`, or an amount that is not a positive number with at most
    two decimal places. **The occupied-key refusal is the store's, not a
    check's (I-9)** — the write is `overwrite=False` unless `replace`, so
    the adapter's own atomic insert is the gate. Logs `Event.RECORD_ADDED`
    with the reference `(budget, "<category>.<month>")` only — never the
    amount (I-15).
    """
    cat = _category(category)
    mon = _month(month)
    value = _limit_amount(amount)
    item_id = f"{cat}.{mon}"
    record = Classified(FIELDS["limit"], f"{value:.2f}", pack.SCHEMA["limit"]["derived"])
    ref = key(MATTER, "limit", item_id)
    if replace:
        replaced = store.put(MATTER, "limit", item_id, record, overwrite=True)
    else:
        try:
            replaced = store.put(MATTER, "limit", item_id, record, overwrite=False)
        except RecordExists:
            raise RecordExists(
                f"{MATTER}/{item_id} already has a limit. A write never "
                "silently overwrites (I-9): pass --replace (the CLI) or "
                '"replace": true (the UI) to replace it.'
            ) from None
    VisibleLog().record(Event.RECORD_ADDED, ref=(MATTER, item_id))
    return ref, replaced


def limits(store: Sidecar, month: str, *, surface: Surface = Surface.S1_LIST) -> dict[str, str]:
    """Every category's limit on file for `month`, served at `surface` —
    never `.payload`. `L4`'s ceiling on `S1_LIST` is derive with no
    exception, so this always reads as `pack.SCHEMA["limit"]["derived"]`
    there; `limit_detail` (`S1_DETAIL`) is where the actual figure renders."""
    mon = _month(month)
    suffix = f".{mon}"
    out: dict[str, str] = {}
    for (_, field, item_id), record in store.records(MATTER):
        if field != "limit" or not item_id.endswith(suffix):
            continue
        category = item_id[: -len(suffix)]
        served = serve(record, surface)
        if served.disposition is not Disposition.DENY:
            out[category] = str(served.value)
    return out


def limit_detail(store: Sidecar, category: str, month: str) -> str | None:
    """The actual limit amount for one category and month, opened
    explicitly (`S1_DETAIL` renders `L4` with no purpose needed) — `None`
    if there is no limit on file for it, or the gate denies it."""
    cat = _category(category)
    mon = _month(month)
    try:
        record = store.get(MATTER, "limit", f"{cat}.{mon}")
    except KeyError:
        return None
    served = serve(record, Surface.S1_DETAIL)
    return None if served.disposition is Disposition.DENY else str(served.value)


@dataclass(frozen=True)
class Envelope:
    """One category's state for one month, as a surface may show it —
    never a figure (I-8/I-15): `spent_state`/`limit_state` are derived
    labels, `over` is the one boolean a comparison inside this module may
    hand outward. `category` is already the `S1_LIST` form
    (`_displayed_category`) — the real word only if it is not protected."""

    category: str
    spent_state: str
    limit_state: str
    over: bool


def state_text(envelope: Envelope) -> str:
    """The one label a surface shows for `envelope`. "no limit set" beats
    "no spend": a category with neither a limit nor any spending reads as
    having no limit rather than as unexpectedly empty."""
    if envelope.limit_state == NO_LIMIT:
        return NO_LIMIT
    if envelope.spent_state == NO_SPEND:
        return NO_SPEND
    return "over limit" if envelope.over else "within limit"


def envelopes(
    canonical: Canonical, store: Sidecar, month: str,
) -> tuple[list[Envelope], int]:
    """Every category's spend-versus-limit state for `month`, and the count
    of transactions with no category at all — "uncategorised", by count
    only, never folded into a figure.

    Spend is read through `balance.dated_transactions` (no `.payload` of
    this module's own) over every registered account instance, filtered to
    `month`, to outflows only (`amount < 0`, `recurring.py`'s own
    convention), with `overlay.excluded_fingerprints` (`do_not_use`)
    dropped before anything is summed. A transaction's category comes from
    `overlay.tags_of` at `S1_DETAIL` — the real word, needed to group spend
    under the same key a limit is filed under; only the *result*
    (`Envelope.category`) derives on the way out.

    A limit's real figure is read once, through the gate at `S1_DETAIL`
    (`Served.value`, never `.payload`), purely to decide `over` — the
    number itself never leaves this function. Nothing here writes to
    `store`.
    """
    mon = _month(month)
    excluded = overlay.excluded_fingerprints(store)

    spent_by_category: dict[str, Decimal] = {}
    uncategorised = 0
    for label in accounts.instances(store):
        for item_id, txn_date, amount, _description in dated_transactions(canonical, label):
            if item_id in excluded or amount >= 0 or not str(txn_date).startswith(mon):
                continue
            category = overlay.tags_of(store, item_id, surface=Surface.S1_DETAIL).get("category")
            if category is None:
                uncategorised += 1
                continue
            spent_by_category[category] = spent_by_category.get(category, Decimal("0")) + Decimal(str(abs(amount)))

    limit_by_category: dict[str, Decimal] = {}
    for category, text in limits(store, mon, surface=Surface.S1_DETAIL).items():
        try:
            limit_by_category[category] = Decimal(text)
        except InvalidOperation:
            continue   # a corrupt limit on file joins no comparison (I-11)

    out: list[Envelope] = []
    for category in sorted(set(spent_by_category) | set(limit_by_category)):
        spent = spent_by_category.get(category)
        limit = limit_by_category.get(category)
        out.append(Envelope(
            category=_displayed_category(category),
            spent_state=HAS_SPEND if spent is not None else NO_SPEND,
            limit_state=LIMIT_SET if limit is not None else NO_LIMIT,
            over=spent is not None and limit is not None and spent > limit,
        ))
    return out, uncategorised
