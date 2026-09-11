"""`schedules.py` — the household's liability schedule, composed and exported
without ever drafting or filing (provisional I-44).

Mirrors `test_accounts.py`'s own shape for the planted-number section: a
distinctive number, read on every surface this bite touches, asserted absent
everywhere but the one write that put it there.
"""
from __future__ import annotations

import json

import pytest
from homestead.keep import paths
from homestead.keep.export import ExportRefused
from homestead.keep.rungs import Rung, Surface
from homestead.keep import rungs as rungs_mod

from homestead_ledger import accounts, schedules
from homestead_ledger.store import Sidecar

pytestmark = pytest.mark.usefixtures("_home")


@pytest.fixture
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))


@pytest.fixture
def store():
    return Sidecar()


# ── the cell this whole bite rests on ───────────────────────────────────────


def test_s4_egress_ceiling_with_a_purpose_is_l4():
    """Pinned: the cell in the engine's crossing table `debts()` relies on
    to render `balance_as_of`/`rate`/`limit`/`min_payment` as themselves
    rather than as their derived stand-in, once a purpose is declared."""
    assert rungs_mod._CEILING[Surface.S4_EGRESS] == (Rung.L2, Rung.L4)


# ── only liability instances appear ─────────────────────────────────────────


def test_checking_and_savings_are_absent_from_debts_and_rows(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    accounts.add_account(store, "sav-main", kind="savings", number="2")
    assert schedules.debts(store) == []
    assert schedules.rows(store) == []


def test_a_card_and_a_loan_are_present(store):
    accounts.add_account(store, "chk-main", kind="checking", number="1")
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        institution="Chase", balance_as_of="1200.00",
    )
    accounts.add_account(
        store, "auto-loan", kind="loan", number="778", institution="Ally",
        balance_as_of="18450.00",
    )
    debts = schedules.debts(store)
    assert [row.label for row in debts] == ["auto-loan", "visa-chase"]  # sorted
    assert {row.kind for row in debts} == {"credit_card", "loan"}


# ── an absent optional field is None, never "0.00" (I-31's spirit) ─────────


def test_a_liability_with_no_balance_as_of_shows_it_absent_not_zero(store):
    accounts.add_account(store, "visa-chase", kind="credit_card", number="4242")
    (row,) = schedules.debts(store)
    assert row.balance_as_of is None
    assert row.rate is None
    assert row.limit is None
    assert row.min_payment is None
    (shown,) = schedules.rows(store)
    assert shown.balance_as_of is None


# ── two surfaces, two dispositions ──────────────────────────────────────────


def test_debts_renders_l4_fields_under_the_declared_export_purpose(store):
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        institution="Chase", balance_as_of="1200.00", rate="19.99",
        limit="5000.00", min_payment="35.00",
    )
    (row,) = schedules.debts(store)
    assert row.institution == "Chase"
    assert row.balance_as_of == "1200.00"
    assert row.rate == "19.99"
    assert row.limit == "5000.00"
    assert row.min_payment == "35.00"


def test_rows_derives_l4_fields_with_no_purpose_declared(store):
    """S1_LIST semantics: the amount fields never render the number-shaped
    value here — only the export does, under the declared purpose."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00", rate="19.99", limit="5000.00",
        min_payment="35.00",
    )
    (row,) = schedules.rows(store)
    assert row.balance_as_of == "a balance is on file"
    assert row.rate == "a rate is on file"
    assert row.limit == "a limit is on file"
    assert row.min_payment == "a minimum payment is on file"
    assert "1200.00" not in repr(row)


def test_institution_renders_on_both_surfaces(store):
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242", institution="Chase",
    )
    assert schedules.debts(store)[0].institution == "Chase"
    assert schedules.rows(store)[0].institution == "Chase"


# ── the number is never asked for, on any surface ───────────────────────────


def test_debtrow_has_no_number_field_at_all():
    assert not hasattr(schedules.DebtRow, "number")
    fields = {f for f in schedules.DebtRow.__dataclass_fields__}
    assert "number" not in fields


_PLANTED_NUMBER = "9999-4242-PLANTED"


def _plant(store) -> None:
    accounts.add_account(
        store, "visa-plant", kind="credit_card", number=_PLANTED_NUMBER,
        institution="Chase", balance_as_of="500.00",
    )


def test_the_planted_number_never_appears_in_debts_or_rows(store):
    _plant(store)
    assert _PLANTED_NUMBER not in repr(schedules.debts(store))
    assert _PLANTED_NUMBER not in repr(schedules.rows(store))


def test_the_planted_number_never_appears_in_the_export_document_or_file(store):
    _plant(store)
    receipt = schedules.export(store, confirm=lambda wire: True)
    body = receipt.artifact.read_text("utf-8")
    assert _PLANTED_NUMBER not in body
    doc = json.loads(body)["content"]
    assert _PLANTED_NUMBER not in json.dumps(doc)


def test_the_planted_number_never_appears_in_either_log(store):
    _plant(store)
    schedules.export(store, confirm=lambda wire: True)
    visible = (paths.logs_dir() / "visible.jsonl").read_text("utf-8")
    integrity = (paths.logs_dir() / "integrity.jsonl").read_text("utf-8")
    assert _PLANTED_NUMBER not in visible
    assert _PLANTED_NUMBER not in integrity


def test_the_planted_number_never_appears_in_the_confirm_preview(store):
    """The `Wire` shown to the operator before they approve is the same
    object that gets written — "the preview is the payload" — so if the
    number is absent from the artifact it was also absent from what the
    operator was shown."""
    _plant(store)
    previews: list[str] = []

    def confirm(wire) -> bool:
        previews.append(wire.body)
        return True

    schedules.export(store, confirm=confirm)
    assert len(previews) == 1
    assert _PLANTED_NUMBER not in previews[0]


# ── export composes one document, through the engine's own machinery ───────


def test_export_writes_one_artifact_one_integrity_row_one_visible_line(store):
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00",
    )
    before_integrity = 0
    integrity_path = paths.logs_dir() / "integrity.jsonl"
    if integrity_path.exists():
        before_integrity = len(integrity_path.read_text("utf-8").splitlines())

    receipt = schedules.export(store, confirm=lambda wire: True)

    assert receipt.artifact.exists()
    assert receipt.ref == "schedules/debts/export"
    doc = json.loads(receipt.artifact.read_text("utf-8"))["content"]
    assert doc["schema"] == schedules.SCHEMA
    assert doc["count"] == 1
    assert doc["rows"][0]["balance_as_of"] == "1200.00"
    assert doc["NOTICE"] == schedules.NOTICE

    after_integrity = len(integrity_path.read_text("utf-8").splitlines())
    assert after_integrity == before_integrity + 1

    visible = (paths.logs_dir() / "visible.jsonl").read_text("utf-8").splitlines()
    assert any('"exported"' in line for line in visible)


def test_a_refused_confirm_writes_nothing_and_ledgers_nothing(store):
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00",
    )
    with pytest.raises(ExportRefused):
        schedules.export(store, confirm=lambda wire: False)

    assert not paths.exports_dir().exists() or not list(paths.exports_dir().rglob("*.json"))
    integrity_path = paths.logs_dir() / "integrity.jsonl"
    assert not integrity_path.exists()
    visible_path = paths.logs_dir() / "visible.jsonl"
    assert not visible_path.exists()


def test_a_second_export_is_a_new_file_with_a_new_composed_at(store):
    """Decided: identical content composes a new document with a new
    timestamp rather than being refused — a household confirming the same
    export again, on a later date, is still a fact worth keeping."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00",
    )
    first = schedules.export(store, confirm=lambda wire: True)
    second = schedules.export(store, confirm=lambda wire: True)

    assert first.artifact != second.artifact
    assert first.artifact.exists() and second.artifact.exists()
    doc1 = json.loads(first.artifact.read_text("utf-8"))["content"]
    doc2 = json.loads(second.artifact.read_text("utf-8"))["content"]
    assert doc1["composed_at"] != doc2["composed_at"]


def test_an_empty_schedule_still_exports_with_a_plain_rung(store):
    """No liability instance on file — `count: 0`, and the whole item's
    rung is `L2`, not the engine's own `compose()`-of-nothing `L5`: this
    module does not let an empty household's export come out sealed."""
    receipt = schedules.export(store, confirm=lambda wire: True)
    doc = json.loads(receipt.artifact.read_text("utf-8"))["content"]
    assert doc["count"] == 0
    assert doc["rows"] == []
    assert receipt.rung is Rung.L2
    assert receipt.disposition.value == "render"


# ── the README quotes the NOTICE verbatim ───────────────────────────────────


def test_the_readme_quotes_the_notice_verbatim():
    from pathlib import Path

    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text("utf-8")
    assert schedules.NOTICE in readme


# ── I-23: no hand-kept liability-kind list in this module ──────────────────


def test_no_hardcoded_kind_literal_in_schedules_py():
    import ast
    from pathlib import Path

    from homestead_ledger import registry

    names = set(registry.all_accounts())
    tree = ast.parse(
        (Path(__file__).resolve().parent.parent / "homestead_ledger" / "schedules.py")
        .read_text("utf-8")
    )
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and elt.value in names:
                    hits.append(node.lineno)
        elif isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                if isinstance(operand, ast.Constant) and operand.value in names:
                    hits.append(node.lineno)
    assert hits == [], (
        f"schedules.py hardcodes an account-kind literal at {hits} — I-23 "
        "says iterate registry.all_accounts()/registry.account(kind) instead."
    )
