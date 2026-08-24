"""Tests for homestead_ledger.intake — text extraction from receipts and bills."""
from __future__ import annotations

import pytest
from homestead_ledger.intake import Extracted, extract


# ── dollar amount extraction ──────────────────────────────────────────────

class TestAmounts:
    def test_simple_dollar(self):
        items = extract("Total: $12.34")
        amounts = [i for i in items if i.kind == "amount"]
        assert any(a.value == "12.34" for a in amounts)

    def test_large_amount(self):
        items = extract("Balance: $1,234.56")
        amounts = [i for i in items if i.kind == "amount"]
        assert any(a.value == "1234.56" for a in amounts)

    def test_labeled_amount(self):
        items = extract("Subtotal: 45.99")
        amounts = [i for i in items if i.kind == "amount"]
        assert any(a.value == "45.99" for a in amounts)

    def test_multiple_amounts(self):
        items = extract("Item: $10.00  Tax: $0.80  Total: $10.80")
        amounts = [i for i in items if i.kind == "amount"]
        assert len(amounts) >= 3

    def test_amount_field(self):
        items = extract("$25.00")
        amounts = [i for i in items if i.kind == "amount"]
        assert all(a.field == "amount" for a in amounts)


# ── date extraction ───────────────────────────────────────────────────────

class TestDates:
    def test_iso_date(self):
        items = extract("Date: 2026-08-15")
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-08-15" for d in dates)

    def test_written_date(self):
        items = extract("Invoice date: August 15, 2026")
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-08-15" for d in dates)

    def test_us_date(self):
        items = extract("Date: 8/15/2026")
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-08-15" for d in dates)

    def test_abbreviated_month(self):
        items = extract("Paid on Jan. 5, 2026")
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-01-05" for d in dates)

    def test_date_field(self):
        items = extract("2026-01-15")
        dates = [i for i in items if i.kind == "date"]
        assert all(d.field == "date" for d in dates)


# ── due date extraction ───────────────────────────────────────────────────

class TestDueDates:
    def test_due_by(self):
        items = extract("Due by 9/1/2026")
        due = [i for i in items if i.kind == "due_date"]
        assert any(d.value == "2026-09-01" for d in due)

    def test_payment_due(self):
        items = extract("Payment Due: 2026-09-15")
        due = [i for i in items if i.kind == "due_date"]
        assert any(d.value == "2026-09-15" for d in due)

    def test_pay_by(self):
        items = extract("Pay by September 1, 2026")
        due = [i for i in items if i.kind == "due_date"]
        assert any(d.value == "2026-09-01" for d in due)

    def test_due_date_field(self):
        items = extract("Due by 9/1/2026")
        due = [i for i in items if i.kind == "due_date"]
        assert all(d.field == "due_date" for d in due)


# ── merchant extraction ──────────────────────────────────────────────────

class TestMerchants:
    def test_pay_to(self):
        items = extract("Pay to: Pacific Gas & Electric")
        merchants = [i for i in items if i.kind == "merchant"]
        assert any("Pacific Gas" in m.value for m in merchants)

    def test_receipt_header(self):
        items = extract("TARGET STORE #1234\n123 Main St")
        merchants = [i for i in items if i.kind == "merchant"]
        assert any("TARGET" in m.value for m in merchants)

    def test_merchant_label(self):
        items = extract("Merchant: Amazon Web Services")
        merchants = [i for i in items if i.kind == "merchant"]
        assert any("Amazon" in m.value for m in merchants)

    def test_billed_by(self):
        items = extract("Billed by: State Farm Insurance")
        merchants = [i for i in items if i.kind == "merchant"]
        assert any("State Farm" in m.value for m in merchants)

    def test_merchant_field(self):
        items = extract("Pay to: Acme Corp")
        merchants = [i for i in items if i.kind == "merchant"]
        assert all(m.field == "description" for m in merchants)


# ── account reference extraction ──────────────────────────────────────────

class TestAccountRefs:
    def test_account_last4(self):
        items = extract("Account: ***1234")
        accounts = [i for i in items if i.kind == "account"]
        assert any(a.value == "1234" for a in accounts)

    def test_acct_no(self):
        items = extract("Acct No. 5678")
        accounts = [i for i in items if i.kind == "account"]
        assert any(a.value == "5678" for a in accounts)

    def test_account_dots(self):
        items = extract("Account: ...9012")
        accounts = [i for i in items if i.kind == "account"]
        assert any(a.value == "9012" for a in accounts)

    def test_account_field(self):
        items = extract("Account #1234")
        accounts = [i for i in items if i.kind == "account"]
        assert all(a.field == "account_number" for a in accounts)


# ── full receipt ──────────────────────────────────────────────────────────

class TestFullReceipt:
    SAMPLE = """\
SAFEWAY STORE #2847
1234 Oak Ave, Sacramento CA

Date: 8/15/2026

Groceries          $45.67
Tax                 $3.65
Total              $49.32

Account: ***4321
"""

    def test_finds_amounts(self):
        items = extract(self.SAMPLE)
        amounts = [i for i in items if i.kind == "amount"]
        values = {a.value for a in amounts}
        assert "45.67" in values
        assert "49.32" in values

    def test_finds_date(self):
        items = extract(self.SAMPLE)
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-08-15" for d in dates)

    def test_finds_merchant(self):
        items = extract(self.SAMPLE)
        merchants = [i for i in items if i.kind == "merchant"]
        assert any("SAFEWAY" in m.value for m in merchants)

    def test_finds_account(self):
        items = extract(self.SAMPLE)
        accounts = [i for i in items if i.kind == "account"]
        assert any(a.value == "4321" for a in accounts)

    def test_sorted_by_position(self):
        items = extract(self.SAMPLE)
        positions = [i.start for i in items]
        assert positions == sorted(positions)

    def test_no_duplicates(self):
        items = extract(self.SAMPLE)
        keys = [(i.start, i.end, i.kind) for i in items]
        assert len(keys) == len(set(keys))


# ── full bill ─────────────────────────────────────────────────────────────

class TestFullBill:
    SAMPLE = """\
Pacific Gas & Electric Company
Account Number: ***7890

Billing Period: July 1 - July 31, 2026
Due Date: 8/20/2026

Current Charges:
  Electric Service     $89.45
  Gas Service          $23.10
  Total Due           $112.55

Pay by August 20, 2026
"""

    def test_finds_due_date(self):
        items = extract(self.SAMPLE)
        due = [i for i in items if i.kind == "due_date"]
        assert any(d.value == "2026-08-20" for d in due)

    def test_finds_total(self):
        items = extract(self.SAMPLE)
        amounts = [i for i in items if i.kind == "amount"]
        values = {a.value for a in amounts}
        assert "112.55" in values

    def test_finds_account(self):
        items = extract(self.SAMPLE)
        accounts = [i for i in items if i.kind == "account"]
        assert any(a.value == "7890" for a in accounts)


# ── edge cases ────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_text(self):
        assert extract("") == []

    def test_no_financial_content(self):
        items = extract("The weather is sunny today in Los Angeles.")
        amounts = [i for i in items if i.kind == "amount"]
        assert len(amounts) == 0

    def test_extracted_is_frozen(self):
        items = extract("$10.00")
        with pytest.raises(AttributeError):
            items[0].kind = "other"
