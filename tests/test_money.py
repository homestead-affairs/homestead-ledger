"""One reading of an amount, for every door — and the two readings it replaces.

The CLI and the browser UI each parsed an amount with `float()`. `float()`
accepts three spellings that are not amounts (`nan`, `inf`, `-inf`), and
`f"{float('nan'):.2f}"` is the string `"nan"` — which lands in the books as an
amount and makes every running balance after it `nan`. The CSV importer used
`Decimal`, which is exact but accepts the same three spellings.

These tests are the floor under `money.py`: the spellings it must refuse, the
formatting it must strip, the exactness it must keep, and the rule that no
refusal repeats the value it refused (I-15 — an amount is L4 in both packs).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from homestead_ledger import money


@pytest.mark.parametrize("raw", ["nan", "NaN", "-nan", "inf", "-inf", "Infinity", "sNaN"])
def test_a_non_finite_spelling_is_refused_by_name(raw):
    """`float()` and a bare `Decimal()` both accept every one of these. An
    amount that is not finite is not a large amount — it poisons every sum it
    joins and compares false to itself (I-11: corruption refuses by name)."""
    with pytest.raises(ValueError, match="finite"):
        money.decimal_amount(raw)


@pytest.mark.parametrize("raw", ["", "   ", "lots", "12 dollars", "1,2.3.4", "--5", "$"])
def test_what_is_not_a_number_is_refused(raw):
    with pytest.raises(ValueError):
        money.decimal_amount(raw)


def test_no_refusal_echoes_the_value():
    """I-15: an error may name a field, never repeat an L3+ value — and a
    rejected amount reaches the same stderr, the same log and the same browser
    as an accepted one."""
    for raw in ("4242.42lots", "nan", "8675309"):
        for call in (money.decimal_amount, money.amount_text):
            try:
                call(raw)
            except ValueError as exc:
                assert raw not in str(exc), (raw, str(exc))
                assert "amount" in str(exc)


def test_the_field_name_travels_with_the_refusal():
    with pytest.raises(ValueError, match="opening balance"):
        money.decimal_amount("lots", field="opening balance")


def test_formatting_is_stripped_and_sign_and_magnitude_are_not():
    assert money.amount_text("$1,450") == "1450.00"
    assert money.amount_text("-84.23") == "-84.23"
    assert money.amount_text(" 1500 ") == "1500.00"
    assert money.amount_text(-96.4) == "-96.40"
    assert money.amount_text("1e3") == "1000.00"       # a real, finite number


def test_the_arithmetic_is_decimal_not_binary():
    """`float("0.1") + float("0.2")` is not `0.3`, and a household's money is
    read in decimal digits, not in base 2."""
    assert money.decimal_amount("0.1") + money.decimal_amount("0.2") == Decimal("0.3")
    assert money.decimal_amount("1450.00") == Decimal("1450.00")
