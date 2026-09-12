"""`schedules.py` — the household's liability schedule, composed and exported
without ever drafting or filing (provisional I-44).

Mirrors `test_accounts.py`'s own shape for the planted-number section: a
distinctive number, read on every surface this bite touches, asserted absent
everywhere but the one write that put it there.
"""
from __future__ import annotations

import json
import pathlib

import pytest
from homestead.keep import paths
from homestead.keep.export import ExportRefused
from homestead.keep.rungs import Rung, Surface
from homestead.keep import rungs as rungs_mod

from homestead_ledger import accounts, schedules
from homestead_ledger.store import Sidecar

from tests._scans import terms_found

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
    assert row.opened is None
    (shown,) = schedules.rows(store)
    assert shown.balance_as_of is None


def test_an_absent_field_is_a_missing_key_in_the_document_not_a_null(store):
    """A `null` in the artifact is a reading a stranger has to make — a zero
    balance, a withheld one, an unknown one. An absent key is not."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        institution="Chase",
    )
    receipt = schedules.export(store, confirm=lambda wire: True)
    body = receipt.artifact.read_text("utf-8")
    (row,) = json.loads(body)["content"]["rows"]
    # the exact key set below already proves "balance_as_of" is absent, not
    # merely null
    assert row == {"label": "visa-chase", "kind": "credit_card",
                   "institution": "Chase"}
    assert terms_found(body, ("null",)) == []


def test_the_document_row_keys_cannot_drift_from_the_composition(store):
    """A fully populated row carries exactly the fields this module
    composes — so a field added to `_OPTIONAL_FIELDS` and forgotten in
    `_row_dict` (or the reverse) fails here rather than silently dropping
    out of the artifact that leaves the household."""
    full = schedules.DebtRow(
        label="visa-chase", kind="credit_card", institution="Chase",
        opened="2019-03-01", balance_as_of="1200.00", rate="19.99",
        limit="5000.00", min_payment="35.00", rung=Rung.L4,
    )
    assert set(schedules._row_dict(full)) == {
        "label", "kind", *schedules._OPTIONAL_FIELDS
    }


def test_no_composed_field_is_above_l4_so_none_can_deny_on_egress(store):
    """Structural, not incidental: every field this module ever hands to
    `serve()` is declared `L4` or below in `packs/accounts.py`, so nothing
    it composes can `DENY` on S4 under the declared purpose. `number`
    (`L5`) is the field this keeps out, and it fails the moment anyone
    adds it — or any other L5 field — to `_OPTIONAL_FIELDS`."""
    from homestead.keep.rungs import compose as _compose_rungs

    from homestead_ledger.packs import accounts as pack

    composed = ("kind", *schedules._OPTIONAL_FIELDS)
    assert "number" not in composed
    assert _compose_rungs(*(pack.FIELDS[f] for f in composed)) is Rung.L4
    assert pack.FIELDS["number"] is Rung.L5


def test_the_composed_rung_check_fires_on_a_planted_l5_field(store):
    """The rung check above had never been shown to catch anything: it reads
    the real `_OPTIONAL_FIELDS`, which is L4 today and would be L4 under a
    check that did nothing. Planted — `number` added to the tuple — the
    composition must read `L5`, which is what makes the assertion above a
    guard rather than a restatement of today's table.

    Planted in a local tuple rather than by patching the module: what is
    being proven is that the *arithmetic* rises, and a monkeypatched module
    constant would prove the same thing while leaving a torn `schedules`
    behind if the test failed midway."""
    from homestead.keep.rungs import compose as _compose_rungs

    from homestead_ledger.packs import accounts as pack

    planted = ("kind", *schedules._OPTIONAL_FIELDS, "number")
    assert _compose_rungs(*(pack.FIELDS[f] for f in planted)) is Rung.L5, (
        "an L5 field in the composition must raise the composed rung to L5 — "
        "otherwise the check above cannot notice one being added"
    )


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


def test_opened_is_l2_and_renders_on_both_surfaces(store):
    """A debt schedule carries the date each account was opened: `opened` is
    `L2` household metadata in `packs/accounts.py`, below both surfaces'
    plain ceiling, so it renders as itself on the screen and in the export
    — no purpose needed, and it lifts no row's rung."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        opened="2019-03-01",
    )
    assert schedules.debts(store)[0].opened == "2019-03-01"
    (shown,) = schedules.rows(store)
    assert shown.opened == "2019-03-01"
    assert shown.rung is Rung.L2


# ── the number is never asked for, on any surface ───────────────────────────


def test_debtrow_has_no_number_field_at_all():
    assert not hasattr(schedules.DebtRow, "number")
    fields = {f for f in schedules.DebtRow.__dataclass_fields__}
    assert "number" not in fields


_PLANTED_NUMBER = "9999-4242-PLANTED"
_PLANTED_BALANCE = "13579.24"


def _plant(store) -> None:
    accounts.add_account(
        store, "visa-plant", kind="credit_card", number=_PLANTED_NUMBER,
        institution="Chase", balance_as_of=_PLANTED_BALANCE,
    )


def test_the_planted_number_never_appears_in_debts_or_rows(store):
    _plant(store)
    assert _PLANTED_NUMBER not in repr(schedules.debts(store))
    assert _PLANTED_NUMBER not in repr(schedules.rows(store))


def test_the_planted_number_never_appears_in_the_export_document_or_file(store):
    _plant(store)
    receipt = schedules.export(store, confirm=lambda wire: True)
    body = receipt.artifact.read_text("utf-8")
    assert terms_found(body, (_PLANTED_NUMBER,)) == []
    doc = json.loads(body)["content"]
    assert terms_found(json.dumps(doc), (_PLANTED_NUMBER,)) == []


def test_neither_log_carries_a_number_a_balance_or_a_party(store):
    """I-15: the logs carry references. The number is the obvious plant; the
    *balance* is the harder one — it is the value the whole export exists to
    move, and the one a log line would be most tempted to summarize — and so
    is the institution the account resolves to."""
    _plant(store)
    receipt = schedules.export(store, confirm=lambda wire: True)
    assert terms_found(receipt.artifact.read_text("utf-8"), (_PLANTED_BALANCE,)) == [_PLANTED_BALANCE]

    integrity = (paths.logs_dir() / "integrity.jsonl").read_text("utf-8")
    visible = (paths.logs_dir() / "visible.jsonl").read_text("utf-8")
    forbidden = (_PLANTED_NUMBER, _PLANTED_BALANCE, "Chase", "visa-plant")
    for log in (integrity, visible):
        assert terms_found(log, forbidden) == []
    row = json.loads(integrity.strip().splitlines()[-1])
    assert (row["matter"], row["item_type"], row["item_id"], row["purpose"]) == (
        "schedules", "debts", "export", "export",
    )


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
    # G8-business-books: the appended sentence is a statement of fact about
    # this export — this household holds no business-owned account, so the
    # true sentence is that none is on file, not that some were excluded.
    assert doc["NOTICE"] == f"{schedules.NOTICE} {schedules.BUSINESS_NONE_NOTICE}"

    after_integrity = len(integrity_path.read_text("utf-8").splitlines())
    assert after_integrity == before_integrity + 1

    visible = (paths.logs_dir() / "visible.jsonl").read_text("utf-8")
    assert terms_found(visible, ('"exported"',)) == ['"exported"']


def test_the_documents_rung_is_composed_over_the_rows_not_hard_coded(store):
    """`L4` on a schedule carrying a balance is the composition, not a
    constant: a household whose only liability instance has a kind and an
    institution and no money on file exports at `L3`. A hard-coded `L4`
    would overstate what left the house, and fails here."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242", institution="Chase",
    )
    assert schedules.export(store, confirm=lambda wire: True).rung is Rung.L3

    accounts.add_account(
        store, "auto-loan", kind="loan", number="778", balance_as_of="18450.00",
    )
    assert schedules.export(store, confirm=lambda wire: True).rung is Rung.L4


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


def test_a_refusal_after_a_real_export_leaves_both_logs_byte_identical(store):
    """The engine's `export_record` does not confirm anything: it writes the
    artifact and appends both logs the moment the gate lets the item
    through. This module's own `confirm` is therefore the **only** gate, and
    "nothing was ledgered" has to hold against logs that already exist — an
    empty-file check would pass even if a refusal appended a row."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00",
    )
    schedules.export(store, confirm=lambda wire: True)
    integrity_path = paths.logs_dir() / "integrity.jsonl"
    visible_path = paths.logs_dir() / "visible.jsonl"
    before = (integrity_path.read_bytes(), visible_path.read_bytes())
    artifacts = sorted(paths.exports_dir().rglob("*.json"))

    with pytest.raises(ExportRefused):
        schedules.export(store, confirm=lambda wire: False)

    assert (integrity_path.read_bytes(), visible_path.read_bytes()) == before
    assert sorted(paths.exports_dir().rglob("*.json")) == artifacts


# ── --out: absolute or refused, and never a clobber ────────────────────────


def test_a_relative_out_dir_is_refused_before_anything_is_composed(store, tmp_path):
    """`"exports"` names a different directory from every working directory,
    and the engine's IntegrityLog row records the reference and the purpose,
    not the path — so a relative `--out` is refused rather than resolved
    against whatever `cwd` happened to be."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00",
    )
    asked: list[object] = []
    with pytest.raises(ExportRefused):
        schedules.export(
            store, confirm=lambda wire: asked.append(wire) or True,
            out_dir=pathlib.Path("somewhere/else"),
        )
    assert asked == []                                     # never even shown
    assert not (paths.logs_dir() / "integrity.jsonl").exists()
    assert not (paths.logs_dir() / "visible.jsonl").exists()


def test_an_absolute_out_dir_under_the_home_is_honoured_and_never_clobbers(
    store, tmp_path
):
    """`--out` picks a directory; two exports into it are two files.
    `export_record` creates with `O_EXCL` under a stamp of its own, so the
    first document's bytes are still the first document's bytes
    afterwards."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00",
    )
    folder = tmp_path / "for-the-attorney"
    first = schedules.export(store, confirm=lambda w: True, out_dir=folder)
    assert folder in first.artifact.parents
    kept = first.artifact.read_bytes()

    second = schedules.export(store, confirm=lambda w: True, out_dir=folder)
    assert second.artifact != first.artifact
    assert first.artifact.read_bytes() == kept
    assert len(sorted(folder.rglob("*.json"))) == 2
    assert not list(paths.exports_dir().rglob("*.json"))   # not both places


def test_an_out_dir_outside_the_household_root_is_refused_by_name(store, tmp_path):
    """The engine's `paths.ensure` will not create a directory outside
    `home()` — so an export is written inside the household root and copied
    out from there, not written straight into someone else's folder. That
    refusal reaches this module as a bare `ValueError`; it must not reach a
    surface as one (I-11: refuse by name). Nothing is written, nothing is
    ledgered."""
    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00",
    )
    outside = tmp_path.parent / "somebody-elses-folder"
    outside.mkdir(exist_ok=True)
    # …and a symlink *inside* the root pointing out of it: `paths.ensure`
    # resolves before it checks, and this module re-checks nothing of its
    # own, so it cannot disagree with that answer (the shared-validator
    # lesson from the engine's issue #23).
    disguised = tmp_path / "looks-inside"
    disguised.symlink_to(outside, target_is_directory=True)
    for where in (outside, disguised):
        with pytest.raises(ExportRefused) as raised:
            schedules.export(store, confirm=lambda w: True, out_dir=where)
        assert "--out" in str(raised.value)
    assert not list(outside.rglob("*.json"))
    assert not (paths.logs_dir() / "integrity.jsonl").exists()
    assert not (paths.logs_dir() / "visible.jsonl").exists()


def test_a_colliding_artifact_name_refuses_rather_than_overwrites(store, monkeypatch):
    """The `O_EXCL` claim itself, planted: with the export stamp frozen, a
    second export lands on the first one's exact filename and the exclusive
    create refuses. Nothing is appended to either log when it does — the
    artifact is written before the ledger rows, so a failed write cannot
    leave a ledgered export with no document behind it."""
    import datetime as _datetime

    real = _datetime.datetime
    frozen = real(2026, 9, 11, 12, 0, 0, 500000, tzinfo=_datetime.timezone.utc)

    class _Frozen(real):
        @classmethod
        def now(cls, tz=None):
            return frozen

    accounts.add_account(
        store, "visa-chase", kind="credit_card", number="4242",
        balance_as_of="1200.00",
    )
    monkeypatch.setattr(_datetime, "datetime", _Frozen)
    schedules.export(store, confirm=lambda w: True)
    integrity = (paths.logs_dir() / "integrity.jsonl").read_bytes()
    with pytest.raises(FileExistsError):
        schedules.export(store, confirm=lambda w: True)
    assert (paths.logs_dir() / "integrity.jsonl").read_bytes() == integrity
    assert len(sorted(paths.exports_dir().rglob("*.json"))) == 1


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
    assert terms_found(readme, (schedules.NOTICE,)) == [schedules.NOTICE]


# ── I-23: no hand-kept liability-kind list in this module ──────────────────


def test_no_hardcoded_kind_literal_in_schedules_py():
    """2026-09-11: delegates to `test_registry`'s own
    `_account_name_enumerations` -- the same I-23 structural scan, already
    owned and planted there (G9d-inline-scans, "Inline scans the meta-scan
    cannot see")."""
    import ast
    from pathlib import Path

    from homestead_ledger import registry
    from tests.test_registry import _account_name_enumerations

    names = set(registry.all_accounts())
    tree = ast.parse(
        (Path(__file__).resolve().parent.parent / "homestead_ledger" / "schedules.py")
        .read_text("utf-8")
    )
    hits = _account_name_enumerations(tree, names)
    assert hits == [], (
        f"schedules.py hardcodes an account-kind literal at {hits} — I-23 "
        "says iterate registry.all_accounts()/registry.account(kind) instead."
    )
