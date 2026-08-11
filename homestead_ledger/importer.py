"""The CSV importer — bite 4's first slice: a bank-statement CSV, one account
at a time, into the books.

**This module writes nothing itself.** Every row that parses becomes a
`books.Transaction` and is handed to `books.import_transaction` — the one
place allowed to name `homestead.keep.store.CANONICAL`
(`tests/test_invariants_chokepoint.py` enforces that structurally over this
whole package, this module included). This file never reaches `.payload`
either: a parsed amount is a plain string this module builds itself, never a
`Classified` read back off the store.

**Dedup is not a new mechanism — it is the fingerprint seam already proven in
`books.py`/`fingerprint.py`.** Re-importing an overlapping statement range
computes the same content fingerprint for each already-seen row, so
`import_transaction` refuses it with `RecordExists` (I-7/I-9); this module
catches that refusal and counts the row `skipped`, not `imported` and not an
error. `RecordExists` covers two different things, distinguished only by
message text (`books.py` documents why: `date`'s refusal, index 0, is the
ordinary re-import gate; a refusal on any other field is a much rarer
torn-write signal from an earlier interrupted import). This module treats
only the former as an idempotent skip; the latter is surfaced as an error an
operator should see, never folded into an ordinary re-import's silence.

**`--dry-run` touches no adapter at all.** A dry run parses every row and
tallies what would import — it never calls `books.import_transaction`, so it
never calls `store.insert`, so there is nothing to roll back and nothing to
race.

**Unparseable rows are counted and surfaced, never dropped and never guessed
into a fact (I-8/I-25).** A row with no date, an unparseable amount, or a
header shape this module does not recognize raises inside the row parser;
this module catches only that, counts it as an error, and prints one line to
stderr naming the row — it never invents a date or an amount to keep a
partial row moving.
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from homestead.keep.store import RecordExists

from homestead_ledger import books
from homestead_ledger.packs import checking

__all__ = [
    "ImportResult",
    "detect_format",
    "import_csv",
]

#: header sets (lower-cased) that identify each supported shape. Checked in
#: this order — debit/credit first — so a file that (unusually) carries all
#: four columns is read as the split shape, not the single-amount one.
_DEBIT_CREDIT_HEADERS = {"date", "description", "debit", "credit"}
_SINGLE_AMOUNT_HEADERS = {"date", "description", "amount"}


@dataclass(frozen=True)
class ImportResult:
    """The tally a run produces — real or `--dry-run` alike. `error_messages`
    is one entry per row counted in `errors`, in file order, the same text
    this module also writes to stderr as the row is hit."""

    imported: int = 0
    skipped: int = 0
    errors: int = 0
    error_messages: tuple[str, ...] = field(default_factory=tuple)


def detect_format(headers: list[str]) -> str:
    """Which supported shape a header row names — `"single_amount"` or
    `"debit_credit"` — matched case-insensitively so `Date`/`date`/`DATE` all
    count. An unrecognized shape raises `ValueError` naming what was seen and
    what was expected, rather than guessing at a parser (I-25: mirror, not
    judge, applies to a header row too — this module does not infer a shape
    it was not told)."""
    normalized = {h.strip().lower() for h in headers if h}
    if _DEBIT_CREDIT_HEADERS <= normalized:
        return "debit_credit"
    if _SINGLE_AMOUNT_HEADERS <= normalized:
        return "single_amount"
    raise ValueError(
        f"unrecognized CSV header shape {headers!r} — expected either "
        f"{sorted(_SINGLE_AMOUNT_HEADERS)} (single-amount, debits negative / "
        f"credits positive) or {sorted(_DEBIT_CREDIT_HEADERS)} (debit/credit "
        "split)"
    )


def _clean_decimal(raw: str) -> Decimal:
    """A bank CSV's numeric text, stripped of the formatting a spreadsheet
    export commonly adds ($ prefix, thousands commas) — never its sign or
    magnitude. Raises `ValueError` (not `InvalidOperation` — the parser's own
    exception type) on anything that is not, in the end, a number."""
    text = raw.strip().replace(",", "").replace("$", "").strip()
    if not text:
        raise ValueError("missing amount")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"amount is not a number: {raw!r}") from exc


def _single_amount(raw: str) -> str:
    """The single-amount shape's value is already signed by convention
    (debits negative, credits positive) — parsed only to validate it is a
    real number and to normalize stray formatting, never to re-sign it."""
    return str(_clean_decimal(raw))


def _debit_credit_amount(debit_raw: str, credit_raw: str) -> str:
    """Combine a debit/credit split into one signed amount string, matching
    `books._derived_for`'s convention exactly: a debit becomes negative, a
    credit stays positive — regardless of whether the source column itself
    carried a sign, since bank exports vary on that."""
    debit_raw = (debit_raw or "").strip()
    credit_raw = (credit_raw or "").strip()
    if debit_raw and credit_raw:
        raise ValueError(
            f"both Debit ({debit_raw!r}) and Credit ({credit_raw!r}) are "
            "populated for one row — a torn or ambiguous export, not a "
            "transaction this module will guess a sign for"
        )
    if not debit_raw and not credit_raw:
        raise ValueError("neither Debit nor Credit is populated — missing amount")
    if debit_raw:
        return str(-abs(_clean_decimal(debit_raw)))
    return str(abs(_clean_decimal(credit_raw)))


def _header_map(headers: list[str]) -> dict[str, str]:
    """lower-cased field name → the header string actually in the file, so a
    row parser can look up `"date"` regardless of how the source capitalized
    it."""
    return {h.strip().lower(): h for h in headers}


def _cell(row: dict[str, str], hmap: dict[str, str], name: str) -> str:
    key = hmap.get(name)
    if key is None:
        return ""
    return row.get(key) or ""


def _parse_single_amount_row(
    row: dict[str, str], hmap: dict[str, str], *, account: str, account_number: str
) -> books.Transaction:
    date = _cell(row, hmap, "date").strip()
    if not date:
        raise ValueError("missing date")
    description = _cell(row, hmap, "description").strip()
    amount = _single_amount(_cell(row, hmap, "amount"))
    return books.Transaction(
        account=account, date=date, amount=amount, description=description,
        account_number=account_number,
    )


def _parse_debit_credit_row(
    row: dict[str, str], hmap: dict[str, str], *, account: str, account_number: str
) -> books.Transaction:
    date = _cell(row, hmap, "date").strip()
    if not date:
        raise ValueError("missing date")
    description = _cell(row, hmap, "description").strip()
    amount = _debit_credit_amount(_cell(row, hmap, "debit"), _cell(row, hmap, "credit"))
    return books.Transaction(
        account=account, date=date, amount=amount, description=description,
        account_number=account_number,
    )


_ROW_PARSERS: dict[str, Callable[..., books.Transaction]] = {
    "single_amount": _parse_single_amount_row,
    "debit_credit": _parse_debit_credit_row,
}

#: Substring that marks a `RecordExists` as the ordinary de-dup gate (`date`,
#: index 0 in `books._FIELD_ORDER`) rather than the rarer torn-write signal
#: on a later field — `books.py`'s own two messages are the only place this
#: distinction is made, so this module matches its text rather than
#: inventing a second mechanism.
_ORDINARY_REIMPORT_MARKER = "already on the books"


def import_csv(
    path: str | Path,
    *,
    account: str = checking.ACCOUNT,
    account_number: str,
    dry_run: bool = False,
    adapter=None,
) -> ImportResult:
    """Import one bank-statement CSV for one account.

    `account` is the pack label (`checking.ACCOUNT` by default); `account_number`
    is the L5 bank identifier — both are parameters for the whole statement,
    never a per-row column, because a statement is for one account. `adapter`
    is passed straight through to `books.import_transaction` (`None` uses this
    package's own database) — the same seam the tests use to point at a tmp
    store via `HOMESTEAD_HOME`.

    Returns an `ImportResult` tally. Raises `ValueError` immediately, before
    reading any row, if the header names neither supported shape — an
    unrecognized file is refused outright, not silently misread.
    """
    path = Path(path)
    imported = skipped = errors = 0
    error_messages: list[str] = []

    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        fmt = detect_format(headers)
        parser = _ROW_PARSERS[fmt]
        hmap = _header_map(headers)

        for line_no, row in enumerate(reader, start=2):  # header is line 1
            try:
                txn = parser(row, hmap, account=account, account_number=account_number)
            except ValueError as exc:
                errors += 1
                message = f"{path.name}:{line_no}: {exc}"
                error_messages.append(message)
                print(f"homestead_ledger.importer: unparseable row — {message}", file=sys.stderr)
                continue

            if dry_run:
                # Tally what would import — no adapter touched, nothing to
                # roll back. A real dedup check would itself be a store read,
                # which "touches no adapter at all" forbids.
                imported += 1
                continue

            try:
                books.import_transaction(txn, adapter=adapter)
                imported += 1
            except RecordExists as exc:
                message = str(exc)
                if _ORDINARY_REIMPORT_MARKER in message:
                    # the ordinary de-dup gate (date, the first field written)
                    # refused an already-seen fingerprint — idempotent
                    # re-import, not a problem (I-7/I-9).
                    skipped += 1
                else:
                    # a later field refused after `date` already succeeded —
                    # books.py's own torn-write signal, not an ordinary
                    # re-import. An operator should see this, never a silent
                    # skip.
                    errors += 1
                    error_messages.append(message)
                    print(
                        f"homestead_ledger.importer: torn-write signal on "
                        f"{path.name}:{line_no} — {message}",
                        file=sys.stderr,
                    )

    return ImportResult(
        imported=imported, skipped=skipped, errors=errors,
        error_messages=tuple(error_messages),
    )
