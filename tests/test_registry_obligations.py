"""I-23 for obligations — the money analog of `tests/test_registry.py`'s
account-registry suite, and of homestead-law's `all_matters()`. Nothing
iterates "all obligations" yet outside `queue.py` (bite 2) — the registry is
still built as the one enumeration first, so `queue.py` never keeps a list of
its own.
"""
from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

from homestead.keep.rungs import Rung
from homestead_ledger import registry as registry_mod
from homestead_ledger.packs import obligations
from homestead_ledger.registry import (
    OBLIGATION_REGISTRY,
    ObligationType,
    all_obligations,
    obligation,
)

PKG = Path(__file__).resolve().parent.parent / "homestead_ledger"


def test_i23_the_obligation_registry_is_the_only_enumeration():
    assert set(all_obligations()) == set(OBLIGATION_REGISTRY)


def test_obligations_is_registered_and_is_the_only_built_pack():
    """One pack in bite 2 — a second obligation kind is deliberately not
    here: a name with no pack behind it is the hand-kept phantom I-23
    forbids."""
    assert set(all_obligations()) == {"obligations"}


def test_all_obligations_iterates_the_registry_and_nothing_else():
    assert set(all_obligations()) == set(OBLIGATION_REGISTRY)
    assert isinstance(all_obligations(), tuple)
    assert all(isinstance(name, str) for name in all_obligations())


def test_an_entry_ties_an_obligation_kind_to_its_pack():
    entry = obligation("obligations")
    assert isinstance(entry, ObligationType)
    assert entry.name == obligations.OBLIGATION == "obligations"
    assert entry.pack is obligations


def test_the_registry_does_not_hardcode_the_field_list_it_reads_it():
    entry = obligation("obligations")
    assert entry.fields is obligations.FIELDS
    assert entry.schema is obligations.SCHEMA
    assert entry.fields["due_date"] is Rung.L2
    assert set(entry.fields) == set(obligations.SCHEMA)


def test_obligation_is_strict_about_an_unknown_name():
    with pytest.raises(KeyError):
        obligation("rent")
    with pytest.raises(KeyError):
        obligation("not_an_obligation")


# ── the import-time guard fires — BUG-6's shape, from each side ─────────────

def _fake_pack(name: str) -> types.ModuleType:
    mod = types.ModuleType(f"homestead_ledger.packs._fake_obl_{name}")
    mod.OBLIGATION = name
    mod.FIELDS = {"name": Rung.L3}
    mod.SCHEMA = {"name": {"rung": Rung.L3, "obligation": name}}
    return mod


def test_a_pack_on_disk_with_no_entry_fails_the_build():
    subscriptions = _fake_pack("subscriptions")
    on_disk = {"obligations": obligations, "subscriptions": subscriptions}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate_obligations(dict(OBLIGATION_REGISTRY), on_disk)
    assert "subscriptions" in str(exc.value)
    assert "no registry entry" in str(exc.value)


def test_a_registry_entry_with_no_pack_is_a_phantom_and_fails_the_build():
    phantom = registry_mod._obligation_entry(_fake_pack("subscriptions"))
    broken = {**OBLIGATION_REGISTRY, "subscriptions": phantom}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate_obligations(broken, {"obligations": obligations})
    assert "subscriptions" in str(exc.value)
    assert "no pack" in str(exc.value)


def test_a_key_that_disagrees_with_its_packs_obligation_fails_the_build():
    misfiled = registry_mod.ObligationType(name="obligatoins", pack=obligations)  # typo'd key
    broken = {"obligatoins": misfiled}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate_obligations(broken, {"obligations": obligations})
    assert "disagrees" in str(exc.value)


def test_an_entry_that_is_not_an_obligation_type_fails_the_build():
    with pytest.raises(RuntimeError):
        registry_mod._validate_obligations({"obligations": "obligations"}, {"obligations": obligations})


def test_the_real_obligation_registry_passes_its_own_guard():
    registry_mod._validate_obligations(OBLIGATION_REGISTRY, registry_mod._discover_obligation_packs())
    assert set(registry_mod._discover_obligation_packs()) == set(OBLIGATION_REGISTRY)


def test_adding_a_pack_to_the_registry_needs_no_other_code_change(monkeypatch):
    """A second obligation kind appears in `all_obligations()` the instant it
    is in `OBLIGATION_REGISTRY`, with no other code touched."""
    subscriptions = registry_mod._obligation_entry(_fake_pack("subscriptions"))
    monkeypatch.setitem(registry_mod.OBLIGATION_REGISTRY, "subscriptions", subscriptions)

    assert set(all_obligations()) == {"obligations", "subscriptions"}
    assert obligation("subscriptions").fields == {"name": Rung.L3}


# ── the structural guard: the registry is the ONLY enumeration ──────────────

OBLIGATION_ENUM_ALLOWED = {PKG / "registry.py"}


def _obligation_name_enumerations(tree: ast.AST, names: set[str]) -> list[int]:
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and elt.value in names:
                    hits.append(node.lineno)
        elif isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                if isinstance(operand, ast.Constant) and operand.value in names:
                    hits.append(node.lineno)
    return hits


def _is_pack(mod: Path) -> bool:
    return "packs" in mod.relative_to(PKG).parts


def test_no_module_outside_the_registry_hardcodes_the_set_of_obligations():
    names = set(all_obligations())
    offenders: list[str] = []
    for mod in sorted(PKG.rglob("*.py")):
        if "__pycache__" in mod.parts:
            continue
        if mod in OBLIGATION_ENUM_ALLOWED or _is_pack(mod):
            continue
        for lineno in _obligation_name_enumerations(ast.parse(mod.read_text("utf-8")), names):
            offenders.append(f"{mod.relative_to(PKG.parent)}:{lineno}")
    assert not offenders, (
        f"an obligation kind is enumerated by hand outside the registry at {offenders}. "
        "I-23 — iterate all_obligations() rather than keeping a list."
    )
