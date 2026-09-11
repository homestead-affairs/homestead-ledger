"""The overlay — the household's own layer over its read-only books.

`overlay.tag` writes `(overlay, category|note|confirmed_merchant|do_not_use,
<fingerprint>)`, never touching the canonical row a fingerprint names.
`packs/overlay.py` is not a discovered account or obligation pack (the same
posture `packs/accounts.py` holds); `overlay.excluded_fingerprints` is the
one seam `recurring`/a running total are filtered through, at the caller.
"""
from __future__ import annotations

import json

import pytest

from homestead.keep import paths
from homestead.keep.logs import Event, VisibleLog
from homestead.keep.rungs import Rung, Surface
from homestead.keep.store import CANONICAL, RecordExists, SQLiteAdapter
from homestead.keep.store import key as engine_key

from homestead_ledger import overlay, registry
from homestead_ledger.books import Transaction, import_transaction
from homestead_ledger.fingerprint import fingerprint as make_fingerprint
from homestead_ledger.packs import overlay as pack
from homestead_ledger.store import Canonical, Sidecar

LABEL = "chk-t"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    return Sidecar()


def _seed(monkeypatch, tmp_path, make_account, *, description="Whole Foods Market", amount="-84.23"):
    """One real transaction, on a registered instance, and its fingerprint."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    txn = Transaction(
        account=LABEL, kind="checking", date="2026-08-01", amount=amount,
        description=description,
    )
    fp = import_transaction(txn)
    return fp


# ── the pack is not a discovered account or obligation kind ────────────────

def test_the_overlay_sidecar_is_not_a_discovered_pack():
    """`packs/overlay.py` declares no `ACCOUNT`/`OBLIGATION` — the attributes
    `registry._discover_packs`/`_discover_obligation_packs` scan for — so
    neither registry ever finds it and it never joins `all_accounts()`/
    `all_obligations()`, the same guard `packs/accounts.py` carries."""
    assert not hasattr(pack, "ACCOUNT")
    assert not hasattr(pack, "OBLIGATION")
    assert "overlay" not in registry.all_accounts()
    assert "overlay" not in registry.all_obligations()
    assert pack not in registry._discover_packs().values()
    assert pack not in registry._discover_obligation_packs().values()


def test_the_pack_classifies_at_import_and_spans_the_declared_rungs():
    assert pack.FIELDS == {
        "category": Rung.L3,
        "confirmed_merchant": Rung.L3,
        "do_not_use": Rung.L2,
        "note": Rung.L4,
        "use": Rung.L3,
        "allowable_uses": Rung.L3,
    }


def test_every_field_records_the_matter_and_a_reason_that_names_a_step():
    for name, spec in pack.SCHEMA.items():
        assert spec.get("matter") == pack.MATTER, name
        why = spec.get("why", "")
        assert why, f"{name} declares a rung with no recorded reason"
        assert "step" in why, f"{name}'s why does not name a classification step"


def test_l3_and_l4_fields_carry_a_derived_form_with_no_digits():
    for name in ("category", "confirmed_merchant", "note"):
        derived = pack.SCHEMA[name]["derived"]
        assert derived and not any(ch.isdigit() for ch in derived)


# ── tagging: the fingerprint must already be on the books ──────────────────

def test_tag_refuses_an_unknown_fingerprint_by_name(store):
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, "0" * 64, category="groceries")
    assert "0" * 64 in str(exc.value)
    assert "no such transaction" in str(exc.value)
    # nothing was written
    assert list(store.records(overlay.MATTER)) == []


def test_tag_refuses_with_nothing_given_including_do_not_use_false(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    with pytest.raises(ValueError):
        overlay.tag(store, fp)
    with pytest.raises(ValueError):
        overlay.tag(store, fp, do_not_use=False)


def test_a_tag_on_a_pre_instance_row_still_works(tmp_path, monkeypatch, make_account, store):
    """A row written straight through the raw adapter, never through
    `books.import_transaction`, still tags — fingerprints are a content
    hash, stable regardless of the writer."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    fp = make_fingerprint(
        date="2020-01-01", amount="-10.00", description="Old Row", account="9821",
    )
    adapter = SQLiteAdapter(paths.home() / "homestead-ledger.db")
    blob = json.dumps({"rung": "L2", "payload": "2020-01-01", "derived": None})
    assert adapter.insert(CANONICAL, engine_key(LABEL, "date", fp), blob) is True

    written = overlay.tag(store, fp, category="groceries")
    assert "category" in written
    assert overlay.tags_of(store, fp) == {"category": "groceries"}


# ── the protected-shape composition: argues up, never down ─────────────────

def test_an_ordinary_category_stays_l3_and_renders_on_s1_list(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="groceries")
    assert store.get(overlay.MATTER, "category", fp).rung is Rung.L3
    assert overlay.tags_of(store, fp) == {"category": "groceries"}


def test_a_protected_shape_category_is_composed_up_to_l4_and_derives(tmp_path, monkeypatch, make_account, store):
    """`medical-copay` contains `medical` — composed to L4, derives on
    S1_LIST (ceiling L3): the real word never reaches the list."""
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="medical-copay")
    assert store.get(overlay.MATTER, "category", fp).rung is Rung.L4
    served = overlay.tags_of(store, fp, surface=Surface.S1_LIST)
    assert served == {"category": "a category is on file"}
    assert "medical-copay" not in served.values()
    # and the real word is still there on the detail pane, once opened
    detail = overlay.tags_of(store, fp, surface=Surface.S1_DETAIL)
    assert detail["category"] == "medical-copay"


@pytest.mark.parametrize("word", sorted(pack.PROTECTED_CATEGORY_WORDS))
def test_every_protected_word_raises_a_category_containing_it(tmp_path, monkeypatch, make_account, store, word):
    fp = _seed(monkeypatch, tmp_path, make_account, description=f"row for {word}")
    overlay.tag(store, fp, category=f"{word}-thing"[:40])
    assert store.get(overlay.MATTER, "category", fp).rung is Rung.L4


def test_the_advisory_never_composes_down(tmp_path, monkeypatch, make_account, store):
    """No path writes an already-protected category at L3 — the advisory
    argues up only (`homestead.keep.advise`'s own rule, applied here)."""
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="medical-copay", replace=True)
    assert store.get(overlay.MATTER, "category", fp).rung is Rung.L4
    # re-tagging the very same protected word again (replace) still lands L4
    overlay.tag(store, fp, category="medical-copay", replace=True)
    assert store.get(overlay.MATTER, "category", fp).rung is Rung.L4


def test_a_bad_category_shape_is_refused_before_anything_is_written(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    with pytest.raises(ValueError):
        overlay.tag(store, fp, category="Has Spaces")
    assert overlay.tags_of(store, fp) == {}


# ── note: derives on S1_LIST, renders on S1_DETAIL, never the reverse ──────

def test_note_never_renders_on_s1_list_but_renders_on_s1_detail(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, note="call the bank about this one")
    assert store.get(overlay.MATTER, "note", fp).rung is Rung.L4
    on_list = overlay.tags_of(store, fp, surface=Surface.S1_LIST)
    assert on_list["note"] == "a note is on file"
    assert "call the bank" not in on_list["note"]
    on_detail = overlay.tags_of(store, fp, surface=Surface.S1_DETAIL)
    assert on_detail["note"] == "call the bank about this one"


def test_an_empty_note_is_refused(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    with pytest.raises(ValueError):
        overlay.tag(store, fp, note="   ")


# ── confirmed_merchant: L3, the same posture as description ────────────────

def test_confirmed_merchant_is_l3_and_renders_on_s1_list(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, confirmed_merchant="Wells Fargo Wire Desk")
    assert store.get(overlay.MATTER, "confirmed_merchant", fp).rung is Rung.L3
    assert overlay.tags_of(store, fp)["confirmed_merchant"] == "Wells Fargo Wire Desk"


# ── do_not_use: excluded_fingerprints, and only that field ─────────────────

def test_do_not_use_is_l2_and_read_only_through_excluded_fingerprints(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, do_not_use=True)
    assert store.get(overlay.MATTER, "do_not_use", fp).rung is Rung.L2
    assert fp in overlay.excluded_fingerprints(store)
    # do_not_use is never among tags_of's own keys — a caller checks it by
    # reference, never reads a value off the field.
    assert "do_not_use" not in overlay.tags_of(store, fp)


def test_excluded_fingerprints_reads_only_do_not_use(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="groceries", note="x", confirmed_merchant="y")
    assert overlay.excluded_fingerprints(store) == frozenset()
    overlay.tag(store, fp, do_not_use=True)
    assert overlay.excluded_fingerprints(store) == frozenset({fp})


# ── do_not_use excludes from the recurring pass, filtered at the caller ────

def test_do_not_use_excludes_a_fingerprint_from_the_recurring_pass(tmp_path, monkeypatch, make_account):
    """The pattern `/api/subscriptions` applies: drop `do_not_use` rows
    (by fingerprint) before handing the rest to `detect_recurring`."""
    from datetime import date

    from homestead_ledger import balance
    from homestead_ledger.recurring import detect_recurring

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    fps = [
        import_transaction(Transaction(
            account=LABEL, kind="checking", date=d, amount="-15.99",
            description="Netflix",
        ))
        for d in ("2026-06-01", "2026-07-01", "2026-08-01")
    ]
    sidecar = Sidecar()
    overlay.tag(sidecar, fps[-1], do_not_use=True)

    excluded = overlay.excluded_fingerprints(sidecar)
    dated = balance.dated_transactions(Canonical(), LABEL)
    all_txns = [(d, a, desc) for _fp, d, a, desc in dated]
    filtered_txns = [(d, a, desc) for fp, d, a, desc in dated if fp not in excluded]
    assert len(all_txns) == 3 and len(filtered_txns) == 2

    # three monthly occurrences meet detect_recurring's own minimum; drop the
    # excluded one and two remain, below it — the exclusion changed the answer.
    today = date(2026, 8, 15)
    assert detect_recurring(all_txns, today=today)
    assert detect_recurring(filtered_txns, today=today) == []


# ── occupied-field refusal (I-9), independently per field ───────────────────

def test_tagging_the_same_field_twice_is_refused_without_replace(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="groceries")
    with pytest.raises(RecordExists):
        overlay.tag(store, fp, category="dining")
    # unchanged
    assert overlay.tags_of(store, fp) == {"category": "groceries"}


def test_replace_overwrites_the_occupied_field(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="groceries")
    written = overlay.tag(store, fp, category="dining", replace=True)
    assert written["category"][1] is not None   # Replaced, reporting the prior value
    assert overlay.tags_of(store, fp) == {"category": "dining"}


def test_a_second_independent_field_needs_no_replace(tmp_path, monkeypatch, make_account, store):
    """Unlike `add_account`/`add_obligation`, an overlay's fields are
    independent facts about the same fingerprint — setting `category` does
    not occupy `note`."""
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="groceries")
    overlay.tag(store, fp, note="a note added later")
    assert overlay.tags_of(store, fp)["category"] == "groceries"
    assert overlay.tags_of(store, fp, surface=Surface.S1_DETAIL)["note"] == "a note added later"


# ── refusals never echo a row's date, amount or description (I-15) ─────────

def test_refusals_never_echo_the_transaction(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account, description="Very Secret Payee", amount="-999.99")
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp, category="Not Valid Shape")
    assert "Very Secret Payee" not in str(exc.value)
    assert "999.99" not in str(exc.value)

    overlay.tag(store, fp, category="groceries")
    with pytest.raises(RecordExists) as exc2:
        overlay.tag(store, fp, category="dining")
    assert "Very Secret Payee" not in str(exc2.value)
    assert "999.99" not in str(exc2.value)


# ── the visible log carries a reference only ────────────────────────────────

def test_the_visible_log_carries_a_reference_never_the_tagged_content(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="groceries", note="do not tell anyone about this bribe")
    log_path = paths.logs_dir() / "visible.jsonl"
    assert log_path.exists()
    lines = [json.loads(line) for line in log_path.read_text("utf-8").splitlines() if line.strip()]
    assert lines, "tag() logged nothing"
    events = {line["event"] for line in lines}
    assert events <= {Event.NOTE_ADDED.value, Event.RECORD_ADDED.value}
    for line in lines:
        assert line["ref"] == f"{overlay.MATTER}/{fp}"
        blob = json.dumps(line)
        assert "groceries" not in blob
        assert "bribe" not in blob
    # and record() itself refuses a free-string event (F-4's own guard,
    # exercised directly rather than assumed)
    with pytest.raises(TypeError):
        VisibleLog().record("tagged", ref=(overlay.MATTER, fp))


# ── the protected list is held to the categories a step 1 would name ───────

#: One ordinary way a household writes each protected category a rung
#: procedure's step 1 names. Every one of these must land at `L4`: a word
#: dropped from `PROTECTED_CATEGORY_WORDS` shows up here as a category
#: sitting at `L3`, which is a category *rendered on the list* — the exact
#: failure the list exists to prevent, and one no other test in this file
#: would notice (the parametrized test above only checks the words that are
#: already on the list, so it can never catch one that is missing).
PROTECTED_CATEGORIES = (
    "medical-copay", "health-insurance", "therapy-session", "pharmacy",
    "clinic-visit", "hospital-bill", "dental-work", "doctor-visit",
    "psych-eval", "rehab-program",
    "attorney-retainer", "legal-fees", "counseling", "counsel-retainer",
    "court-filing", "bankruptcy-trustee", "trustee-payment",
    "child-support", "custody-evaluator",
    "church-offering", "religious-school", "mosque-donation",
    "synagogue-dues", "temple-fees", "tithe",
    "union-dues", "political-donation", "immigration-attorney",
)


@pytest.mark.parametrize("category", PROTECTED_CATEGORIES)
def test_every_protected_category_a_household_would_write_lands_at_l4(
    tmp_path, monkeypatch, make_account, store, category,
):
    fp = _seed(monkeypatch, tmp_path, make_account, description=f"row for {category}")
    overlay.tag(store, fp, category=category)
    assert store.get(overlay.MATTER, "category", fp).rung is Rung.L4
    # and therefore never the word itself on the list
    assert overlay.tags_of(store, fp)["category"] == pack.SCHEMA["category"]["derived"]


def test_the_matching_rule_is_substring_not_whole_word(tmp_path, monkeypatch, make_account, store):
    """Pinned, because the two rules disagree and only one of them is safe:
    `medically-unrelated-shop` contains `medical` but has no `-`-separated
    token equal to it. Substring containment raises it (over-classifies);
    a whole-word rule would leave it at `L3`, rendered on the list. The
    advisory argues up, never down, so over-classification is the side this
    is allowed to be wrong on."""
    assert overlay._is_protected("medically-unrelated-shop") is True
    assert overlay._is_protected("legalize-parking") is True
    # …and a category naming nothing on the list is untouched, so the rule
    # is not simply "everything is L4".
    assert overlay._is_protected("groceries") is False
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, category="medically-unrelated-shop")
    assert store.get(overlay.MATTER, "category", fp).rung is Rung.L4


# ── the item id is the whole fingerprint; a typed prefix is resolved ───────

def test_the_record_is_keyed_by_the_whole_fingerprint_never_a_truncation(
    tmp_path, monkeypatch, make_account, store,
):
    """The bite's ruling on truncated ids: the engine's `keep.store.key` puts
    no length or alphabet on an item id, so the 64-hex digest is a valid id
    and there is nothing to shorten — truncation would *create* the collision
    hashing rules out."""
    fp = _seed(monkeypatch, tmp_path, make_account)
    assert len(fp) == 64
    engine_key(overlay.MATTER, "category", fp)          # a valid key as it stands
    overlay.tag(store, fp[:12], category="groceries")   # typed short…
    assert store.has(overlay.MATTER, "category", fp)    # …written long
    assert not store.has(overlay.MATTER, "category", fp[:12])
    assert overlay.excluded_fingerprints(store) == frozenset()


def test_a_prefix_shorter_than_the_minimum_is_refused_by_name(tmp_path, monkeypatch, make_account, store):
    fp = _seed(monkeypatch, tmp_path, make_account)
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp[:4], category="groceries")
    assert "no such transaction" in str(exc.value)


def test_an_ambiguous_prefix_is_refused_never_resolved_to_the_first(
    tmp_path, monkeypatch, make_account, store,
):
    """Planted, because two sha256 digests sharing eight hex characters
    cannot be found by searching for them: two canonical rows are written
    straight through the adapter under ids that *do* collide on a prefix, and
    the refusal has to fire rather than pick one."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    make_account("checking", label=LABEL, number="9821")
    adapter = SQLiteAdapter(paths.home() / "homestead-ledger.db")
    blob = json.dumps({"rung": "L2", "payload": "2020-01-01", "derived": None})
    ids = ["abc12345" + "0" * 56, "abc12345" + "1" * 56]
    for item_id in ids:
        assert adapter.insert(CANONICAL, engine_key(LABEL, "date", item_id), blob) is True

    with pytest.raises(ValueError) as exc:
        overlay.tag(store, "abc12345", category="groceries")
    message = str(exc.value)
    assert "abc12345" in message and "2 transactions" in message
    # a count, never which rows (I-15)
    assert ids[0] not in message and ids[1] not in message
    assert list(store.records(overlay.MATTER)) == []

    # the whole id still resolves to exactly its own row
    overlay.tag(store, ids[0], category="groceries")
    assert store.has(overlay.MATTER, "category", ids[0])
    assert not store.has(overlay.MATTER, "category", ids[1])


# ── free text has a ceiling, and do_not_use is set, never cleared ──────────

@pytest.mark.parametrize("field,value", [
    ("note", "x" * 2001),
    ("confirmed_merchant", "x" * 121),
    ("confirmed_merchant", "Wells Fargo\nWire Desk"),
    ("note", "a note with a \x00 in it"),
])
def test_free_text_that_is_not_a_note_or_a_name_is_refused(
    tmp_path, monkeypatch, make_account, store, field, value,
):
    """An `L4` field with no ceiling is a place to paste a bank statement
    into, and a statement pasted into a note is a statement classified as a
    note. The refusal names the field and the limit, never the value."""
    fp = _seed(monkeypatch, tmp_path, make_account)
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp, **{field: value})
    assert value not in str(exc.value)
    assert overlay.tags_of(store, fp, surface=Surface.S1_DETAIL) == {}


def test_do_not_use_false_is_refused_rather_than_silently_ignored(
    tmp_path, monkeypatch, make_account, store,
):
    """There is no un-tag path in this bite, so a `False` that quietly wrote
    nothing would read to the caller as "cleared" (I-11)."""
    fp = _seed(monkeypatch, tmp_path, make_account)
    overlay.tag(store, fp, do_not_use=True)
    with pytest.raises(ValueError) as exc:
        overlay.tag(store, fp, do_not_use=False, replace=True)
    assert "never cleared" in str(exc.value)
    assert fp in overlay.excluded_fingerprints(store)


# ── I-23: the discovery attribute is what keeps this pack out (planted) ────

def test_the_registry_would_find_this_pack_if_it_declared_one(monkeypatch):
    """The absence asserted above is only load-bearing if `ACCOUNT` /
    `OBLIGATION` is what the scan actually reads. Plant each on the overlay
    pack and the matching registry finds it — so leaving them off is the
    thing keeping the sidecar out, not luck."""
    monkeypatch.setattr(pack, "ACCOUNT", "overlay", raising=False)
    assert registry._discover_packs().get("overlay") is pack
    monkeypatch.delattr(pack, "ACCOUNT")

    monkeypatch.setattr(pack, "OBLIGATION", "overlay", raising=False)
    assert registry._discover_obligation_packs().get("overlay") is pack
    monkeypatch.delattr(pack, "OBLIGATION")

    # and with the plants removed the sidecar is invisible again
    assert "overlay" not in registry._discover_packs()
    assert "overlay" not in registry._discover_obligation_packs()
