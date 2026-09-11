"""One reading of a money amount, for every door a household enters one through.

The CSV importer had a `Decimal`-based reading of a bank column; the CLI and
the browser UI each grew their own `float()`. `float()` is the wrong reading
twice over:

* **It accepts what is not a number.** `float("nan")`, `float("inf")` and
  `float("-inf")` all succeed, and `f"{float('nan'):.2f}"` is the string
  `"nan"` — which then lands in the books as an amount, makes every running
  balance downstream `nan`, and compares false to itself. `Decimal` parses
  those spellings too, so the finite check below is the part that matters and
  is the reason this is a function rather than a one-liner at each door.
* **It is binary floating point.** `f"{float('0.1') + float('0.2'):.2f}"` is
  the household's money, and base-2 rounding is not the arithmetic a ledger
  is read in. `Decimal` keeps the decimal digits the operator typed.

**No error here echoes the amount** (I-15). An amount is `L4` in both packs
(`packs/checking.py`, `packs/obligations.py`), and I-15 allows an error to
name a *field*, never to repeat an `L3+` value — including a value that was
refused, which reaches the same log, the same stderr and the same browser as
one that was accepted. The messages name the field and give an example of the
shape wanted instead.

This module holds no store, no clock and no I/O: it is a parser and nothing
else, so every door can share it without sharing anything else.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

__all__ = ["decimal_amount", "amount_text"]

#: Formatting a spreadsheet or a bank export adds around the number — stripped,
#: never the sign and never the magnitude.
_STRIP = (",", "$")


def decimal_amount(raw: object, *, field: str = "amount") -> Decimal:
    """`raw` as an exact `Decimal`, or `ValueError` naming `field`.

    Refuses the empty string, anything `Decimal` cannot read, and — the case
    `float()` and a bare `Decimal()` both wave through — `nan`, `inf` and
    `-inf`. A non-finite amount is not a smaller number: it is a value that
    poisons every sum it joins, and I-11 says absence and corruption refuse by
    name rather than default.
    """
    text = str(raw).strip()
    for junk in _STRIP:
        text = text.replace(junk, "")
    text = text.strip()
    if not text:
        raise ValueError(f"{field} is missing")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"{field} is not a number (e.g. 1450.00, or -84.23 for a debit)"
        ) from exc
    if not value.is_finite():
        raise ValueError(
            f"{field} is not a finite number — an infinity or a NaN is not an "
            "amount a ledger can add up"
        )
    return value


def amount_text(raw: object, *, field: str = "amount") -> str:
    """`raw` as the two-decimal string the packs store — `"1450.00"`,
    `"-84.23"`. The sign is the caller's convention (debits negative), never
    re-derived here."""
    return f"{decimal_amount(raw, field=field):.2f}"
