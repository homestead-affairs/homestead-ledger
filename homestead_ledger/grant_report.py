"""Spend by allowable use, for one account, over a period — composed and
exported, never drafted (G8-business-books, provisional I-44).

A restricted (grant) account's transactions are tagged with an
`overlay.py` `use` — the allowable-use bucket its own award terms permit
(`overlay.allowable_uses_of`). This module aggregates those tags into one
report: how much was spent under each use — net of any refund carrying the
same use, the ruling `budget.py` already states for a category's spend, so
a funder is never read a gross figure the account never spent — and how
many outflows are still
waiting on one (`needs_use` — a gap, never a refusal; grant money arrives
before the operator has typed the award terms in). It carries no
transaction description, no fingerprint, and no account number — a use
word and two numbers per row, nothing else.

**Two compositions, the same split `schedules.py` already draws.**
`export_rows()` is for the terminal export: real counts and real totals,
served on `Surface.S4_EGRESS` with `Purpose.EXPORT` declared, through the
same `Wire`-preview-then-`export_record` pattern `schedules.export()`
already uses — copied exactly, including its `--out` refusals (relative
refused, outside the household root refused, `O_EXCL` new-file-per-export).
`list_rows()` is for `GET /api/grant/report`: counts only, and a total that
never leaves as a figure — "a total is on file" — `Surface.S1_LIST`, no
export door on the server (the same "an export is a terminal act, not a
browser click" posture `schedules.py` states for its own export).

There is no `Classified` record behind a computed total — a sum is
arithmetic over the books, not a stored field — so this module never reads
a payload of its own (`homestead_ledger/balance.py`'s `dated_transactions`
is the one payload-boundary read behind it, already declared there); this
module is not on `tests/test_invariants_chokepoint.py`'s allow-list and has
no business being on it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from homestead.keep import paths
from homestead.keep.egress import Wire
from homestead.keep.export import ExportReceipt, ExportRefused, export_record
from homestead.keep.rungs import Classified, Purpose, Rung

from homestead_ledger import accounts, budget, overlay, transfers
from homestead_ledger.balance import dated_transactions
from homestead_ledger.store import Canonical, Sidecar

__all__ = [
    "SCHEMA", "GRANT_REPORT_NOTICE", "UseRow",
    "export_rows", "list_rows", "export",
]

#: The export document's schema identifier — versioned the same way
#: `schedules.SCHEMA` is.
SCHEMA = "homestead-ledger.grant-report/1"

#: This document's own notice — **not** `schedules.NOTICE` with a sentence
#: appended, which is what an earlier draft carried: that sentence opens "a
#: list of the household's liabilities" and closes on the Chapter 13 plan
#: payment, and this document is neither. A notice states what the reader
#: is holding, so it has to be true of *this* document. It keeps the same
#: two disclaimers `schedules.NOTICE` carries, said about a report instead
#: — and carved out of the I-44 phrase guard by value, the same way
#: `schedules.NOTICE` and `schedules.BUSINESS_SENTENCES` are
#: (`tests/test_i44_no_drafting.py`).
GRANT_REPORT_NOTICE = (
    "Spend by allowable use for one account over a period, as the ledger "
    "holds it, for the household's own use. It is not a report on any "
    "official form, it carries no form number, and the award terms — not "
    "this ledger — decide what qualifies."
)

#: `_MONTH`'s own shape, called rather than copied — one validator for
#: every `YYYY-MM` this package reads, the same "called rather than
#: mirrored" posture `budget._category` already takes on `overlay._category`.
_month = budget._month


@dataclass(frozen=True)
class UseRow:
    """One allowable-use bucket's state for a period, as the **export**
    composes it — `count` and `total` are both real (`total` formatted to
    two places); `list_rows()` below builds its own, S1-safe dict instead
    of this dataclass."""

    use: str
    count: int
    total: str


def _period(period_start: str, period_end: str) -> tuple[str, str]:
    start = _month(period_start)
    end = _month(period_end)
    if end < start:
        raise ValueError(
            f"--period end month ({end}) is before its start month "
            f"({start}) — the range runs forward, oldest month first"
        )
    return start, end


def _aggregate(
    canonical: Canonical, sidecar: Sidecar, label: str, start: str, end: str,
) -> tuple[dict[str, tuple[int, Decimal]], int]:
    """`{use: (count, total)}` over `label`'s rows whose ISO month falls in
    `[start, end]`, plus how many **outflows** in that window carry no `use`
    tag yet (`needs_use`). Excludes `do_not_use` and either leg of a paired
    transfer, the same exclusions every household aggregate applies —
    neither is spend against an allowable use.

    **A use's total is net of what came back**, the ruling
    `budget.envelopes` already states for a category: a refund on a
    restricted account — an inflow carrying a `use` tag — subtracts from
    that use's total, because what was spent under a use is what went out
    less what came back, and a funder reading a gross figure would be read
    a number the account never spent. `count` counts **outflows** only (a
    refund is not a second piece of spending), and a use whose only row in
    the period is a refund gets no row at all, exactly as a category whose
    only row is a refund gets no envelope.

    An **untagged inflow is not a gap**: the grant money arriving is not an
    outflow waiting on an allowable use, so it never reaches `needs_use`.
    """
    if not accounts.label_exists(sidecar, label):
        raise ValueError(accounts.unknown_label(label))
    excluded = overlay.excluded_fingerprints(sidecar) | transfers.paired_fingerprints(sidecar)
    by_use: dict[str, tuple[int, Decimal]] = {}
    spending_uses: set[str] = set()
    needs_use = 0
    for item_id, txn_date, amount, _description in dated_transactions(canonical, label):
        if item_id in excluded:
            continue
        text = str(txn_date)
        if len(text) < 7 or not (start <= text[:7] <= end):
            continue
        use = overlay.tags_of(sidecar, item_id).get("use")
        if use is None:
            if amount < 0:
                needs_use += 1
            continue
        count, total = by_use.get(use, (0, Decimal("0")))
        if amount < 0:
            spending_uses.add(use)
            count += 1
        # `-amount` is positive for an outflow and negative for a refund,
        # and each row becomes a `Decimal` of its own rather than summing
        # floats — `budget.envelopes`'s own arithmetic, one level down.
        by_use[use] = (count, total + Decimal(str(-amount)))
    return {use: totals for use, totals in by_use.items() if use in spending_uses}, needs_use


def export_rows(
    canonical: Canonical, sidecar: Sidecar, label: str, period_start: str, period_end: str,
) -> tuple[list[UseRow], int]:
    """The real rows and the `needs_use` gap for `label` over the period —
    what the CLI's `grant report` export composes. Sorted by use word; each
    `total` is net of refunds tagged with the same use (`_aggregate`)."""
    start, end = _period(period_start, period_end)
    by_use, needs_use = _aggregate(canonical, sidecar, label, start, end)
    rows = [
        UseRow(use=use, count=count, total=f"{total:.2f}")
        for use, (count, total) in sorted(by_use.items())
    ]
    return rows, needs_use


#: The stand-in a total reads as on `S1_LIST` — a total is never a figure
#: there, the same posture `accounts.DERIVED`/`schedules`'s derived fields
#: already take for money content.
_TOTAL_ON_FILE = "a total is on file"


def list_rows(
    canonical: Canonical, sidecar: Sidecar, label: str, period_start: str, period_end: str,
) -> tuple[list[dict[str, object]], int]:
    """`export_rows()`'s counts, with every total masked to
    `_TOTAL_ON_FILE` — what `GET /api/grant/report` serves. There is no
    export door on the server; only the CLI export renders a real total."""
    rows, needs_use = export_rows(canonical, sidecar, label, period_start, period_end)
    return [{"use": r.use, "count": r.count, "total": _TOTAL_ON_FILE} for r in rows], needs_use


def _document(
    canonical: Canonical, sidecar: Sidecar, label: str, period_start: str, period_end: str,
) -> dict[str, object]:
    rows, needs_use = export_rows(canonical, sidecar, label, period_start, period_end)
    return {
        "schema": SCHEMA,
        "composed_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "label": label,
        "period": f"{period_start}..{period_end}",
        "rows": [{"use": r.use, "count": r.count, "total": r.total} for r in rows],
        "needs_use": needs_use,
        "NOTICE": GRANT_REPORT_NOTICE,
    }


def export(
    canonical: Canonical,
    sidecar: Sidecar,
    label: str,
    period_start: str,
    period_end: str,
    *,
    confirm: Callable[[Wire], bool],
    purpose: Purpose = Purpose.EXPORT,
    out_dir: Path | None = None,
) -> ExportReceipt:
    """Compose the allowable-use report and take it out — `schedules.
    export()`'s pattern, copied exactly: an absolute `--out` under the
    household root or none at all, a `Wire` preview shown before anything
    is written, and `export_record` called once on confirmation.

    Refuses, before anything is composed or shown: an unknown `label`, a
    malformed period, or an end month before the start month. The document
    is always `Rung.L4` — every row it carries is a money total once
    declared, the same "this is inherently money content" posture
    `budget.set_limit` takes for a hand-typed limit, rather than a
    `compose()` over stored fields the way `schedules.py`'s composed rows
    are (a computed sum is not a `Classified` record of its own)."""
    if out_dir is not None and not Path(out_dir).is_absolute():
        raise ExportRefused(
            f"--out takes an absolute directory; {str(out_dir)!r} is "
            "relative and would mean a different place from every working "
            "directory. Nothing was composed and nothing was ledgered."
        )
    try:
        start, end = _period(period_start, period_end)
        document = _document(canonical, sidecar, label, start, end)
    except ValueError as exc:
        raise ExportRefused(str(exc)) from exc

    body = json.dumps(document, sort_keys=True, ensure_ascii=False)
    wire = Wire(method="FILE", url="grant/report", body=body)
    if not confirm(wire):
        raise ExportRefused(
            "declined at the preview: nothing was exported and nothing was "
            "ledgered — the same posture a refused network send takes."
        )
    item = Classified(Rung.L4, document, GRANT_REPORT_NOTICE)
    try:
        return export_record(
            item, "grant", "report", label, purpose=purpose, exports=out_dir,
        )
    except ValueError as exc:
        raise ExportRefused(
            f"--out must name a directory under {paths.home()}: {exc}. "
            "Nothing was written and nothing was ledgered — copy the "
            "exported document out of the household root yourself."
        ) from exc
