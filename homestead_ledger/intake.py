"""Text intake — extract structure from raw receipt/bill text, no agent in the loop.

Takes raw text (receipts, bills, bank statements, invoices) and pulls out
dollar amounts, dates, merchant/payee names, due dates, and account references
using anchored regex.  Pure extraction — never stores, never proposes, never
seals.  The caller decides what to keep.

This complements ``importer.py`` (structured CSV) with unstructured text
extraction — a receipt photographed, a bill pasted, a statement snippet.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Extracted", "extract"]


@dataclass(frozen=True)
class Extracted:
    """One item pulled from raw text."""

    kind: str
    text: str
    value: str
    start: int
    end: int
    field: str | None = None


# ── amount patterns ──────────────────────────────────────────────────────

_AMOUNT = re.compile(
    r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+\.\d{2})\b"
)
_AMOUNT_LABEL = re.compile(
    r"(?:Total|Subtotal|Amount|Balance|Due|Payment|Charge|Price|Cost)"
    r"[:\s]+\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})",
    re.IGNORECASE,
)


# ── date patterns ────────────────────────────────────────────────────────

_MONTHS: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dec": "12",
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DATE_WRITTEN = re.compile(
    rf"\b(?P<month>{_MONTH_RE})\.?\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
_DATE_ISO = re.compile(
    r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b",
)
_DATE_US = re.compile(
    r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b",
)


# ── due date patterns ───────────────────────────────────────────────────

_DUE_DATE = re.compile(
    r"(?:Due|Payment[ \t]+Due|Due[ \t]+Date|Pay[ \t]+by|Due[ \t]+by)"
    r"[:\s]+(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|(?:"
    + _MONTH_RE + r")\.?\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)


# ── merchant/payee patterns ─────────────────────────────────────────────

_MERCHANT_LABEL = re.compile(
    r"(?:Pay[ \t]+to|Payee|Merchant|From|Billed[ \t]+by|Vendor|Company)"
    r"[:\s]+([A-Z][A-Za-z0-9'.,&\- ]+?)(?:\n|$)",
)
_MERCHANT_RECEIPT = re.compile(
    r"^([A-Z][A-Z0-9 &'.#-]{2,30})\n",
    re.MULTILINE,
)


# ── account reference ───────────────────────────────────────────────────

_ACCOUNT_REF = re.compile(
    r"(?:Account|Acct)\.?[ \t]*(?:#|No\.?|Number)?[:\s]*"
    r"(?:\*{2,}|\.\.\.)?\s*(\d{4})\b",
    re.IGNORECASE,
)


# ── extraction ───────────────────────────────────────────────────────────

def _valid_date(year: int, month: int, day: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100


def _parse_date_str(s: str) -> str | None:
    """Try to parse a date string into YYYY-MM-DD."""
    m = _DATE_ISO.match(s)
    if m:
        y, mo, d = int(m["year"]), int(m["month"]), int(m["day"])
        if _valid_date(y, mo, d):
            return f"{y:04d}-{mo:02d}-{d:02d}"
    m = _DATE_US.match(s)
    if m:
        mo, d, y = int(m["month"]), int(m["day"]), int(m["year"])
        if _valid_date(y, mo, d):
            return f"{y:04d}-{mo:02d}-{d:02d}"
    for month_name, month_num in _MONTHS.items():
        if s.lower().startswith(month_name):
            m2 = _DATE_WRITTEN.match(s)
            if m2:
                mo_num = int(_MONTHS[m2["month"].lower()])
                d2, y2 = int(m2["day"]), int(m2["year"])
                if _valid_date(y2, mo_num, d2):
                    return f"{y2:04d}-{mo_num:02d}-{d2:02d}"
            break
    return None


def extract(text: str) -> list[Extracted]:
    """Extract structured items from raw receipt/bill text, sorted by position."""
    items: list[Extracted] = []
    seen: set[tuple[int, int, str]] = set()

    def _add(
        kind: str, matched: str, value: str,
        start: int, end: int, field: str | None = None,
    ) -> None:
        key = (start, end, kind)
        if key not in seen:
            seen.add(key)
            items.append(Extracted(kind, matched, value, start, end, field))

    # Dollar amounts with $
    for m in _AMOUNT.finditer(text):
        raw = m.group(1).replace(",", "")
        _add("amount", m.group(), raw, m.start(), m.end(), "amount")

    # Labeled amounts (Total: 45.99)
    for m in _AMOUNT_LABEL.finditer(text):
        raw = m.group(1).replace(",", "")
        _add("amount", m.group(), raw, m.start(), m.end(), "amount")

    # ISO dates
    for m in _DATE_ISO.finditer(text):
        y, mo, d = int(m["year"]), int(m["month"]), int(m["day"])
        if _valid_date(y, mo, d):
            _add("date", m.group(), f"{y:04d}-{mo:02d}-{d:02d}",
                 m.start(), m.end(), "date")

    # Written dates
    for m in _DATE_WRITTEN.finditer(text):
        mo_num = int(_MONTHS[m["month"].lower()])
        d, y = int(m["day"]), int(m["year"])
        if _valid_date(y, mo_num, d):
            _add("date", m.group(), f"{y:04d}-{mo_num:02d}-{d:02d}",
                 m.start(), m.end(), "date")

    # US dates
    for m in _DATE_US.finditer(text):
        mo, d, y = int(m["month"]), int(m["day"]), int(m["year"])
        if _valid_date(y, mo, d):
            _add("date", m.group(), f"{y:04d}-{mo:02d}-{d:02d}",
                 m.start(), m.end(), "date")

    # Due dates (labeled)
    for m in _DUE_DATE.finditer(text):
        date_str = m.group(1)
        parsed = _parse_date_str(date_str)
        if parsed:
            _add("due_date", m.group(), parsed,
                 m.start(), m.end(), "due_date")

    # Merchant — labeled
    for m in _MERCHANT_LABEL.finditer(text):
        _add("merchant", m.group(), m.group(1).strip(),
             m.start(), m.end(), "description")

    # Merchant — receipt header (all-caps or Title Case at start of line)
    for m in _MERCHANT_RECEIPT.finditer(text):
        name = m.group(1).strip()
        if len(name) > 3 and not name.isdigit():
            _add("merchant", m.group(), name,
                 m.start(), m.end(), "description")

    # Account references (last 4 digits)
    for m in _ACCOUNT_REF.finditer(text):
        _add("account", m.group(), m.group(1),
             m.start(), m.end(), "account_number")

    items.sort(key=lambda e: e.start)
    return items
