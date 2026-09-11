"""G8-business-books — business-owned and restricted accounts.

Account instances gain `owner` (`household`/`business`, default household)
and `restricted` (a grant account whose spend must map to a closed list of
allowable uses). Every household aggregate excludes business-owned accounts
unless `include_business`/`--include-business` widens the scope; a
restricted account's outflow with no allowable-use tag is a gap, never a
refusal; `grant report` composes spend by allowable use; a transfer between
a household and a business account is tagged `commingling`, by reference;
`payroll`/`tax`/`409a`/`cap-table` are refused by name, always.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest
from homestead.keep import paths
from homestead.keep.export import ExportRefused
from homestead.keep.rungs import Rung
from homestead.keep.store import RecordExists

from homestead_ledger import accounts, budget, grant_report, overlay, registry, schedules, transfers
from homestead_ledger.app import demo as demo_mod
from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.cli import run_cli
from homestead_ledger.packs import accounts as accounts_pack
from homestead_ledger.store import Canonical, Sidecar

pytestmark = pytest.mark.usefixtures("_home")


@pytest.fixture
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))


@pytest.fixture
def store():
    return Sidecar()


def _txn(label: str, kind: str, *, date: str, amount: str, description: str = "x") -> str:
    return import_transaction(
        Transaction(account=label, kind=kind, date=date, amount=amount, description=description)
    )


# ── packs/accounts.py: owner/restricted are declared, L2, argue no protection ─


def test_owner_and_restricted_are_declared_l2():
    assert accounts_pack.FIELDS["owner"] is Rung.L2
    assert accounts_pack.FIELDS["restricted"] is Rung.L2


def test_owner_and_restricted_carry_the_matter_and_a_why():
    for field in ("owner", "restricted"):
        spec = accounts_pack.SCHEMA[field]
        assert spec["matter"] == accounts_pack.MATTER
        assert spec["why"]


# ── accounts.py: owner default, set_owner/set_restricted, the two rosters ──


def test_an_instance_with_no_owner_record_reads_household(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    assert accounts.owner_of(store, "chk-a") == "household"
    assert accounts.is_restricted(store, "chk-a") is False


def test_add_account_takes_owner_and_restricted(store):
    accounts.add_account(store, "biz-chk", kind="checking", number="2", owner="business")
    accounts.add_account(store, "grant-chk", kind="checking", number="3", restricted=True)
    assert accounts.owner_of(store, "biz-chk") == "business"
    assert accounts.owner_of(store, "grant-chk") == "household"
    assert accounts.is_restricted(store, "grant-chk") is True
    assert accounts.is_restricted(store, "biz-chk") is False


@pytest.mark.parametrize("owner", ["Business", " business ", "BUSINESS"])
def test_owner_is_case_and_whitespace_insensitive(store, owner):
    accounts.add_account(store, "biz-chk", kind="checking", number="2", owner=owner)
    assert accounts.owner_of(store, "biz-chk") == "business"


@pytest.mark.parametrize("owner", ["employer", "nonprofit", ""])
def test_an_owner_outside_the_closed_set_is_refused(store, owner):
    with pytest.raises(ValueError):
        accounts.add_account(store, "chk-a", kind="checking", number="1", owner=owner)
    assert accounts.instances(store) == []


def test_a_trailing_space_around_a_valid_owner_still_trims_clean(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1", owner="household ")
    assert accounts.owner_of(store, "chk-a") == "household"


def test_set_owner_after_the_fact_and_its_refusals(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    ref, replaced = accounts.set_owner(store, "chk-a", "business")
    assert replaced is None
    assert accounts.owner_of(store, "chk-a") == "business"
    with pytest.raises(RecordExists):
        accounts.set_owner(store, "chk-a", "household")
    with pytest.raises(ValueError):
        accounts.set_owner(store, "no-such-label", "business")


def test_set_restricted_is_set_only_never_cleared(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="3")
    accounts.set_restricted(store, "grant-chk")
    assert accounts.is_restricted(store, "grant-chk") is True
    with pytest.raises(ValueError):
        accounts.set_restricted(store, "grant-chk", False)
    with pytest.raises(ValueError):
        accounts.set_restricted(store, "no-such-label")


def test_household_and_business_labels_partition_every_instance(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    accounts.add_account(store, "biz-chk", kind="checking", number="2", owner="business")
    accounts.add_account(store, "grant-chk", kind="checking", number="3", restricted=True)
    assert set(accounts.household_labels(store)) == {"chk-a", "grant-chk"}
    assert set(accounts.business_labels(store)) == {"biz-chk"}
    assert set(accounts.household_labels(store)) | set(accounts.business_labels(store)) == set(
        accounts.instances(store)
    )


def test_the_resting_cover_counts_household_instances_only(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    accounts.add_account(store, "chk-b", kind="checking", number="2")
    accounts.add_account(store, "biz-chk", kind="checking", number="3", owner="business")
    # Two household instances survive I-31's k>=2 gate; the business one
    # never enters the count that gate is applied to at all.
    assert accounts.cover(store) == {"instances": 2}


# ── I-43, extended: a business account's number is still one L5 record ─────


_PLANTED_NUMBER = "BIZ-9999-PLANTED"


def test_a_business_accounts_number_is_still_one_l5_record_never_rendered(store):
    accounts.add_account(
        store, "biz-chk", kind="checking", number=_PLANTED_NUMBER, owner="business",
    )
    assert accounts.detail(store, "biz-chk")["number"] == ("L5", None)
    assert _PLANTED_NUMBER not in repr(accounts.rows(store))
    for row in schedules.debts(store, include_business=True):
        assert not hasattr(row, "number")
    assert _PLANTED_NUMBER not in repr(schedules.debts(store, include_business=True))
    assert _PLANTED_NUMBER not in repr(schedules.rows(store, include_business=True))


# ── overlay.py: NOT_COMPUTED_HERE — a closed refusal, category and use ─────


@pytest.mark.parametrize("word", overlay.NOT_COMPUTED_HERE)
def test_every_not_computed_here_word_refuses_as_a_category(store, word):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    fp = _txn("chk-a", "checking", date="2026-09-01", amount="-10.00")
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp, category=word)
    assert "accountant" in str(exc.value)
    assert overlay.tags_of(store, fp) == {}


@pytest.mark.parametrize("word", overlay.NOT_COMPUTED_HERE)
def test_every_not_computed_here_word_refuses_as_a_use(store, word):
    accounts.add_account(store, "grant-chk", kind="checking", number="1", restricted=True)
    overlay.set_allowable_uses(store, "grant-chk", ["software"])
    fp = _txn("grant-chk", "checking", date="2026-09-01", amount="-10.00")
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp, use=word)
    assert "accountant" in str(exc.value)


def test_not_computed_here_words_never_pass_shape_validation_either(store):
    """`409a`/`cap-table` would fail the ordinary category shape too (a
    digit-leading or already-hyphenated word) — pinned so the accountant
    message is shown *before* that generic refusal, not after."""
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    fp = _txn("chk-a", "checking", date="2026-09-01", amount="-10.00")
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp, category="409a")
    assert "accountant" in str(exc.value)


@pytest.mark.parametrize("word", overlay.NOT_COMPUTED_HERE)
def test_every_not_computed_here_word_refuses_as_a_cli_subcommand(word, capsys):
    assert run_cli([word]) == 1
    assert "accountant" in capsys.readouterr().err


def test_not_computed_here_is_closed_and_none_slip_through_the_registry():
    """None of `NOT_COMPUTED_HERE` is a registered account/obligation kind
    or an ordinary category — pinned so the closed list stays a refusal,
    never accidentally a valid enumeration member somewhere else."""
    assert not set(overlay.NOT_COMPUTED_HERE) & set(registry.all_accounts())
    assert not set(overlay.NOT_COMPUTED_HERE) & set(registry.all_obligations())


# ── overlay.py: allowable uses, per account label ───────────────────────────


def test_set_allowable_uses_refuses_a_not_computed_here_word_in_the_list(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="1")
    with pytest.raises(ValueError) as exc:
        overlay.set_allowable_uses(store, "grant-chk", ["payroll", "software"])
    assert "accountant" in str(exc.value)
    assert overlay.allowable_uses_of(store, "grant-chk") == frozenset()


def test_set_allowable_uses_refuses_unknown_label_and_empty_list(store):
    with pytest.raises(ValueError):
        overlay.set_allowable_uses(store, "no-such-label", ["software"])
    accounts.add_account(store, "grant-chk", kind="checking", number="1")
    with pytest.raises(ValueError):
        overlay.set_allowable_uses(store, "grant-chk", [])


def test_set_allowable_uses_dedupes_and_sorts(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="1")
    overlay.set_allowable_uses(store, "grant-chk", ["travel", "software", "travel"])
    assert overlay.allowable_uses_of(store, "grant-chk") == frozenset({"software", "travel"})


def test_allowable_uses_of_an_unset_account_is_empty(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="1")
    assert overlay.allowable_uses_of(store, "grant-chk") == frozenset()


# ── overlay.tag(use=...): validated against the account's own closed set ──


def test_use_with_no_allowable_uses_on_file_is_refused(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="1", restricted=True)
    fp = _txn("grant-chk", "checking", date="2026-09-01", amount="-10.00")
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp, use="software")
    assert "grant-chk" in str(exc.value)


def test_use_outside_the_declared_set_is_refused_by_name(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="1", restricted=True)
    overlay.set_allowable_uses(store, "grant-chk", ["software", "travel"])
    fp = _txn("grant-chk", "checking", date="2026-09-01", amount="-10.00")
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp, use="rent")
    assert "rent" in str(exc.value)
    assert overlay.tags_of(store, fp).get("use") is None


def test_a_valid_use_is_written_and_read_back(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="1", restricted=True)
    overlay.set_allowable_uses(store, "grant-chk", ["software", "travel"])
    fp = _txn("grant-chk", "checking", date="2026-09-01", amount="-10.00")
    written = overlay.tag(store, fp, use="software")
    assert "use" in written
    assert overlay.tags_of(store, fp)["use"] == "software"


# ── budget.envelopes: include_business, needs_use, commingling ─────────────


def test_envelopes_exclude_business_accounts_by_default(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    accounts.add_account(store, "biz-chk", kind="checking", number="2", owner="business")
    _txn("chk-a", "checking", date="2026-09-05", amount="-50.00", description="Groceries")
    _txn("biz-chk", "checking", date="2026-09-06", amount="-500.00", description="AWS")
    overlay.tag(store, _fp_of(store, "chk-a"), category="groceries")
    canonical = Canonical()
    rows, gaps = budget.envelopes(canonical, store, "2026-09")
    assert gaps.uncategorised == 0  # the business row never enters the count
    rows_all, gaps_all = budget.envelopes(canonical, store, "2026-09", include_business=True)
    assert gaps_all.uncategorised == 1  # AWS, on the business account, uncategorised


def _fp_of(store: Sidecar, label: str) -> str:
    """The one transaction fingerprint on `label` — a small helper for the
    tests above that post exactly one row per account."""
    canonical = Canonical()
    for (_, field, item_id), _record in canonical.records(label):
        if field == "date":
            return item_id
    raise AssertionError(f"no transaction on {label!r}")


def test_needs_use_counts_a_restricted_accounts_untagged_outflow(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="1", restricted=True)
    fp = _txn("grant-chk", "checking", date="2026-09-05", amount="-75.00", description="AWS")
    overlay.tag(store, fp, category="cloud-hosting")  # category and use are independent facts
    canonical = Canonical()
    rows, gaps = budget.envelopes(canonical, store, "2026-09")
    assert gaps.needs_use == 1
    assert gaps.uncategorised == 0  # categorised, so no category gap — needs_use is separate


def test_needs_use_is_zero_once_tagged(store):
    accounts.add_account(store, "grant-chk", kind="checking", number="1", restricted=True)
    overlay.set_allowable_uses(store, "grant-chk", ["software"])
    fp = _txn("grant-chk", "checking", date="2026-09-05", amount="-75.00", description="AWS")
    overlay.tag(store, fp, use="software")
    canonical = Canonical()
    _rows, gaps = budget.envelopes(canonical, store, "2026-09")
    assert gaps.needs_use == 0


def test_commingling_count_reflects_live_cross_owner_pairs(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    accounts.add_account(store, "biz-chk", kind="checking", number="2", owner="business")
    fp_out = _txn("chk-a", "checking", date="2026-09-01", amount="-40.00", description="reimb")
    fp_in = _txn("biz-chk", "checking", date="2026-09-02", amount="40.00", description="reimb")
    transfers.pair(store, fp_out, fp_in)
    canonical = Canonical()
    _rows, gaps = budget.envelopes(canonical, store, "2026-09", include_business=True)
    assert gaps.commingling == 1


# ── transfers.py: commingling — tagged by reference, never an amount ───────


def test_pair_is_commingled_only_when_the_two_owners_differ(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    accounts.add_account(store, "chk-b", kind="checking", number="2")
    fp_out = _txn("chk-a", "checking", date="2026-09-01", amount="-40.00")
    fp_in = _txn("chk-b", "checking", date="2026-09-01", amount="40.00")
    transfers.pair(store, fp_out, fp_in)
    assert transfers.is_commingled(store, fp_out) is False
    assert transfers.commingling_count(store) == 0


def test_pair_across_the_household_business_line_is_commingled_both_ways(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    accounts.add_account(store, "biz-chk", kind="checking", number="2", owner="business")
    fp_out = _txn("chk-a", "checking", date="2026-09-01", amount="-40.00")
    fp_in = _txn("biz-chk", "checking", date="2026-09-01", amount="40.00")
    transfers.pair(store, fp_out, fp_in)
    assert transfers.is_commingled(store, fp_out) is True
    assert transfers.is_commingled(store, fp_in) is True  # from the incoming side too
    assert transfers.commingling_count(store) == 1


_PLANTED_AMOUNT = "40404.04"


def test_the_commingling_tag_never_carries_an_amount_on_s1_list(store):
    accounts.add_account(store, "chk-a", kind="checking", number="1")
    accounts.add_account(store, "biz-chk", kind="checking", number="2", owner="business")
    fp_out = _txn("chk-a", "checking", date="2026-09-01", amount=f"-{_PLANTED_AMOUNT}")
    fp_in = _txn("biz-chk", "checking", date="2026-09-01", amount=_PLANTED_AMOUNT)
    transfers.pair(store, fp_out, fp_in)
    # `is_commingled`/`commingling_count` are the two doors a surface reads
    # this fact through — neither can be handed an amount to leak, because
    # neither ever reads one; pinned by inspecting the whole live-pairs view
    # a surface never gets, to be sure it isn't in there to begin with.
    assert _PLANTED_AMOUNT not in repr(transfers.is_commingled(store, fp_out))
    assert _PLANTED_AMOUNT not in repr(transfers.commingling_count(store))


# ── schedules.py: include_business, BUSINESS_NOTICE, byte-identical export ─


def test_debts_and_rows_exclude_business_accounts_by_default(store):
    accounts.add_account(store, "biz-card", kind="credit_card", number="1", owner="business")
    assert schedules.debts(store) == []
    assert schedules.rows(store) == []
    assert len(schedules.debts(store, include_business=True)) == 1
    assert len(schedules.rows(store, include_business=True)) == 1


def test_export_notice_names_the_exclusion_or_the_inclusion(store):
    accounts.add_account(store, "visa-chase", kind="credit_card", number="1")
    receipt = schedules.export(store, confirm=lambda w: True)
    doc = json.loads(receipt.artifact.read_text("utf-8"))["content"]
    assert doc["NOTICE"] == f"{schedules.NOTICE} {schedules.BUSINESS_NOTICE}"

    receipt2 = schedules.export(store, confirm=lambda w: True, include_business=True)
    doc2 = json.loads(receipt2.artifact.read_text("utf-8"))["content"]
    assert "included" in doc2["NOTICE"]
    assert doc2["NOTICE"] != doc["NOTICE"]


def _freeze_clock(monkeypatch, *modules) -> None:
    """`datetime.now` pinned to one instant, everywhere a `composed_at` or
    an artifact stamp is drawn from it. Two places need it, separately:
    `homestead.keep.export._write_artifact` re-imports `datetime` from the
    stdlib module on every call (`from datetime import datetime` *inside*
    the function), so patching the stdlib module's own class — the same
    freeze `test_schedules.py::test_a_colliding_artifact_name_refuses_
    rather_than_overwrites` uses — reaches it; `schedules.py`/
    `grant_report.py` each bind `datetime` once, at import time, into their
    own namespace, so that reference has to be repointed directly too, or
    it keeps the original class regardless of what the stdlib module now
    says."""
    import datetime as _datetime

    real = _datetime.datetime
    frozen = real(2026, 9, 11, 12, 0, 0, 0, tzinfo=_datetime.timezone.utc)

    class _Frozen(real):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(_datetime, "datetime", _Frozen)
    for module in modules:
        monkeypatch.setattr(module, "datetime", _Frozen)


def test_household_export_is_byte_identical_with_or_without_a_business_account(
    store, monkeypatch, tmp_path,
):
    """The default (`include_business=False`) export of the same household
    liabilities does not change when a business account is added — it is
    excluded from the rows either way, and `NOTICE` states the standing
    policy rather than a fact about this particular export."""
    import homestead_ledger.schedules as schedules_mod

    _freeze_clock(monkeypatch, schedules_mod)
    accounts.add_account(store, "visa-chase", kind="credit_card", number="1", balance_as_of="500.00")
    without = schedules.export(store, confirm=lambda w: True, out_dir=tmp_path / "a")
    body_without = without.artifact.read_text("utf-8")

    accounts.add_account(store, "biz-card", kind="credit_card", number="2", owner="business")
    with_biz = schedules.export(store, confirm=lambda w: True, out_dir=tmp_path / "b")
    body_with_biz = with_biz.artifact.read_text("utf-8")
    assert body_without == body_with_biz

    included = schedules.export(
        store, confirm=lambda w: True, out_dir=tmp_path / "c", include_business=True,
    )
    assert included.artifact.read_text("utf-8") != body_without


# ── grant_report.py: spend by allowable use ─────────────────────────────────


@pytest.fixture
def grant_account(store):
    accounts.add_account(store, "grant-main", kind="checking", number="1", restricted=True)
    overlay.set_allowable_uses(store, "grant-main", ["software", "travel"])
    return "grant-main"


def _tag(store, label, *, date, amount, description, use=None):
    fp = _txn(label, "checking", date=date, amount=amount, description=description)
    if use is not None:
        overlay.tag(store, fp, use=use)
    return fp


def test_export_rows_aggregates_count_and_total_per_use(store, grant_account):
    _tag(store, grant_account, date="2026-01-05", amount="-100.00", description="a", use="software")
    _tag(store, grant_account, date="2026-02-05", amount="-50.00", description="b", use="software")
    _tag(store, grant_account, date="2026-03-05", amount="-30.00", description="c", use="travel")
    rows, needs_use = grant_report.export_rows(
        Canonical(), store, grant_account, "2026-01", "2026-03",
    )
    by_use = {r.use: (r.count, r.total) for r in rows}
    assert by_use == {"software": (2, "150.00"), "travel": (1, "30.00")}
    assert needs_use == 0


def test_export_rows_excludes_inflows_and_out_of_period_rows(store, grant_account):
    _tag(store, grant_account, date="2026-01-05", amount="500.00", description="award", use=None)
    _tag(store, grant_account, date="2025-12-05", amount="-10.00", description="before", use="software")
    _tag(store, grant_account, date="2026-01-05", amount="-20.00", description="in-period", use="software")
    rows, needs_use = grant_report.export_rows(
        Canonical(), store, grant_account, "2026-01", "2026-01",
    )
    assert [(r.use, r.count, r.total) for r in rows] == [("software", 1, "20.00")]
    assert needs_use == 0  # the untagged inflow is not spend, and not a gap


def test_needs_use_counts_untagged_outflows_in_period(store, grant_account):
    _tag(store, grant_account, date="2026-01-05", amount="-20.00", description="a", use="software")
    _tag(store, grant_account, date="2026-01-06", amount="-30.00", description="b", use=None)
    rows, needs_use = grant_report.export_rows(
        Canonical(), store, grant_account, "2026-01", "2026-01",
    )
    assert needs_use == 1


def test_export_rows_refuses_an_unknown_label_and_a_backwards_period(store, grant_account):
    with pytest.raises(ValueError):
        grant_report.export_rows(Canonical(), store, "no-such-label", "2026-01", "2026-01")
    with pytest.raises(ValueError):
        grant_report.export_rows(Canonical(), store, grant_account, "2026-03", "2026-01")


def test_list_rows_masks_the_total_and_keeps_the_count(store, grant_account):
    _tag(store, grant_account, date="2026-01-05", amount="-20.00", description="a", use="software")
    rows, needs_use = grant_report.list_rows(
        Canonical(), store, grant_account, "2026-01", "2026-01",
    )
    assert rows == [{"use": "software", "count": 1, "total": "a total is on file"}]
    assert "20.00" not in json.dumps(rows)


_PLANTED_TOTAL = "918273.64"


def test_the_planted_total_never_appears_in_list_rows_or_either_log(store, grant_account):
    _tag(
        store, grant_account, date="2026-01-05", amount=f"-{_PLANTED_TOTAL}",
        description="big one", use="software",
    )
    rows, _needs_use = grant_report.list_rows(
        Canonical(), store, grant_account, "2026-01", "2026-01",
    )
    assert _PLANTED_TOTAL not in json.dumps(rows)

    receipt = grant_report.export(
        Canonical(), store, grant_account, "2026-01", "2026-01", confirm=lambda w: True,
    )
    assert _PLANTED_TOTAL in receipt.artifact.read_text("utf-8")  # the export itself does carry it

    integrity = (paths.logs_dir() / "integrity.jsonl").read_text("utf-8")
    visible = (paths.logs_dir() / "visible.jsonl").read_text("utf-8")
    for log in (integrity, visible):
        assert _PLANTED_TOTAL not in log
        assert "big one" not in log


def test_export_document_carries_grant_report_notice(store, grant_account):
    _tag(store, grant_account, date="2026-01-05", amount="-20.00", description="a", use="software")
    receipt = grant_report.export(
        Canonical(), store, grant_account, "2026-01", "2026-01", confirm=lambda w: True,
    )
    doc = json.loads(receipt.artifact.read_text("utf-8"))["content"]
    assert doc["NOTICE"] == grant_report.GRANT_REPORT_NOTICE
    assert doc["schema"] == grant_report.SCHEMA
    assert doc["needs_use"] == 0


def test_export_confirm_declined_writes_and_ledgers_nothing(store, grant_account):
    # `_tag`'s own `overlay.tag` call already wrote a visible-log line (the
    # "use" tag itself) — before the declined export, so it is counted
    # rather than mistaken for something the export wrote.
    _tag(store, grant_account, date="2026-01-05", amount="-20.00", description="a", use="software")
    before_visible = (paths.logs_dir() / "visible.jsonl").read_text("utf-8").splitlines()
    before_integrity = 0
    integrity_path = paths.logs_dir() / "integrity.jsonl"
    if integrity_path.exists():
        before_integrity = len(integrity_path.read_text("utf-8").splitlines())
    with pytest.raises(ExportRefused):
        grant_report.export(
            Canonical(), store, grant_account, "2026-01", "2026-01", confirm=lambda w: False,
        )
    after_integrity = (
        len(integrity_path.read_text("utf-8").splitlines()) if integrity_path.exists() else 0
    )
    assert after_integrity == before_integrity
    assert (paths.logs_dir() / "visible.jsonl").read_text("utf-8").splitlines() == before_visible


def test_export_refuses_a_relative_out_dir_before_composing_anything(store, grant_account):
    asked: list[object] = []
    with pytest.raises(ExportRefused):
        grant_report.export(
            Canonical(), store, grant_account, "2026-01", "2026-01",
            confirm=lambda wire: asked.append(wire) or True,
            out_dir=pathlib.Path("somewhere/else"),
        )
    assert asked == []


def test_export_refuses_an_out_dir_outside_the_household_root(store, grant_account, tmp_path):
    outside = tmp_path.parent / "somebody-elses-folder"
    outside.mkdir(exist_ok=True)
    with pytest.raises(ExportRefused) as raised:
        grant_report.export(
            Canonical(), store, grant_account, "2026-01", "2026-01",
            confirm=lambda w: True, out_dir=outside,
        )
    assert "--out" in str(raised.value)
    assert not list(outside.rglob("*.json"))


def test_export_honours_an_absolute_out_dir_and_never_clobbers(store, grant_account, tmp_path):
    folder = tmp_path / "for-the-funder"
    first = grant_report.export(
        Canonical(), store, grant_account, "2026-01", "2026-01",
        confirm=lambda w: True, out_dir=folder,
    )
    second = grant_report.export(
        Canonical(), store, grant_account, "2026-01", "2026-01",
        confirm=lambda w: True, out_dir=folder,
    )
    assert first.artifact != second.artifact
    assert len(sorted(folder.rglob("*.json"))) == 2


# ── chokepoint: grant_report.py reaches no payload, and is off the allow-list ─


def test_grant_report_is_off_the_chokepoint_allow_list():
    from tests.test_invariants_chokepoint import ALLOWED_PAYLOAD, PKG

    assert (PKG / "grant_report.py") not in ALLOWED_PAYLOAD


def test_grant_report_module_reaches_no_payload():
    source = pathlib.Path(grant_report.__file__).read_text("utf-8")
    tree = ast.parse(source)
    hits = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "payload"
    ]
    assert hits == []


# ── sync: business rows are not dropped; owner/restricted cross at L2/L3 ──


def test_sync_does_not_drop_a_business_owned_account_from_its_own_matter(store, monkeypatch):
    """The operator's scope decides what to sync — a business account is a
    matter like any other, and `_ExcludingReader` filters only `do_not_use`
    fingerprints, never by an account's `owner`."""
    from homestead.keep.rungs import Rung as _Rung
    from homestead_ledger import sync as sync_mod

    accounts.add_account(store, "biz-chk", kind="checking", number="1", owner="business")
    _txn("biz-chk", "checking", date="2026-09-01", amount="-10.00", description="AWS")
    scope = sync_mod.scope_from(["biz-chk"], None, _Rung.L2, ("canonical",), sidecar=store)
    envelope = sync_mod.preview(scope, sidecar=store, canonical=Canonical())
    assert envelope.count > 0


def test_owner_and_restricted_cross_sync_at_l2_the_pack_declares(store, monkeypatch):
    from homestead.keep.rungs import Rung as _Rung
    from homestead_ledger import sync as sync_mod

    accounts.add_account(store, "grant-chk", kind="checking", number="1", restricted=True, owner="business")
    scope = sync_mod.scope_from(["accounts"], ["restricted"], _Rung.L2, ("sidecar",), sidecar=store)
    envelope = sync_mod.preview(scope, sidecar=store, canonical=Canonical())
    assert envelope.count == 1
    assert envelope.rows[0]["rung"] == "L2"


def test_allowable_uses_crosses_sync_at_l3_the_pack_declares(store):
    from homestead.keep.rungs import Rung as _Rung
    from homestead_ledger import sync as sync_mod

    accounts.add_account(store, "grant-chk", kind="checking", number="1")
    overlay.set_allowable_uses(store, "grant-chk", ["software"])
    scope = sync_mod.scope_from(["overlay"], ["allowable_uses"], _Rung.L3, ("sidecar",), sidecar=store)
    envelope = sync_mod.preview(scope, sidecar=store, canonical=Canonical())
    assert envelope.count == 1
    assert envelope.rows[0]["rung"] == "L3"


# ── --smoke imports grant_report; --demo seeds a business + restricted one ─


def test_smoke_imports_grant_report():
    source = pathlib.Path(demo_mod.__file__).parent.parent.joinpath("__main__.py").read_text("utf-8")
    assert "grant_report" in source


def test_demo_seeds_one_business_and_one_restricted_account(store):
    demo_mod.seed_business_accounts(store)
    assert accounts.owner_of(store, demo_mod.BUSINESS_LABEL) == "business"
    assert accounts.is_restricted(store, demo_mod.GRANT_LABEL) is True
    assert accounts.owner_of(store, demo_mod.GRANT_LABEL) == "household"


def test_compose_business_books_reports_the_household_only_scope(store):
    out = demo_mod.compose_business_books(store)
    assert demo_mod.BUSINESS_LABEL in out
    assert demo_mod.GRANT_LABEL in out
    assert "household-only scope: 1 of 2" in out


# ── CLI: account add/set-owner/allowable-uses, transaction tag --use ──────


def test_cli_account_add_owner_and_restricted(capsys):
    assert run_cli([
        "account", "add", "grant-cli", "--kind", "checking", "--number", "1", "--restricted",
    ]) == 0
    sidecar = Sidecar()
    assert accounts.is_restricted(sidecar, "grant-cli") is True
    assert run_cli([
        "account", "add", "biz-cli", "--kind", "checking", "--number", "2",
        "--owner", "business",
    ]) == 0
    assert accounts.owner_of(sidecar, "biz-cli") == "business"


def test_cli_account_set_owner(capsys):
    run_cli(["account", "add", "chk-cli", "--kind", "checking", "--number", "1"])
    assert run_cli(["account", "set-owner", "chk-cli", "business"]) == 0
    assert accounts.owner_of(Sidecar(), "chk-cli") == "business"


def test_cli_account_allowable_uses_and_tag_use(capsys):
    run_cli([
        "account", "add", "grant-cli", "--kind", "checking", "--number", "1", "--restricted",
    ])
    assert run_cli([
        "account", "allowable-uses", "grant-cli", "--set", "software,travel",
    ]) == 0
    assert overlay.allowable_uses_of(Sidecar(), "grant-cli") == frozenset({"software", "travel"})
    fp = _txn("grant-cli", "checking", date="2026-09-01", amount="-20.00")
    assert run_cli(["transaction", "tag", fp, "--use", "software"]) == 0
    assert overlay.tags_of(Sidecar(), fp)["use"] == "software"


def test_cli_transaction_list_annotates_commingling(capsys):
    run_cli(["account", "add", "chk-cli", "--kind", "checking", "--number", "1"])
    run_cli([
        "account", "add", "biz-cli", "--kind", "checking", "--number", "2",
        "--owner", "business",
    ])
    fp_out = _txn("chk-cli", "checking", date="2026-09-01", amount="-40.00")
    fp_in = _txn("biz-cli", "checking", date="2026-09-01", amount="40.00")
    run_cli(["transaction", "transfer", fp_out, fp_in])
    capsys.readouterr()
    run_cli(["transaction", "list", "--account", "chk-cli"])
    out = capsys.readouterr().out
    assert "commingling" in out
