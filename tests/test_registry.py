"""I-23 — the registry is the only enumeration, money-domain reading.

The ledger's `all_accounts()` is the money analog of homestead-law's
`all_matters()`, built against the same failure it defends: BUG-6 was three
hand-kept matter lists that drifted, one silently dropping a whole matter type
from the urgent queue. Nothing here builds a queue yet (bite 2) — but the
registry is built now, the way homestead-law built it before any consumer
needed it, so nothing downstream ever has a reason to keep its own account
list.
"""
from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

from homestead.keep.rungs import Rung
from homestead_ledger import registry as registry_mod
from homestead_ledger.packs import checking
from homestead_ledger.registry import REGISTRY, AccountType, account, all_accounts

PKG = Path(__file__).resolve().parent.parent / "homestead_ledger"


def test_i23_the_registry_is_the_only_enumeration():
    assert set(all_accounts()) == set(REGISTRY)


def test_checking_is_registered_and_is_the_only_built_pack():
    """One pack in bite 1 — savings and credit-card are the next account
    kinds, deliberately not here: a name with no pack behind it is the
    hand-kept phantom I-23 forbids."""
    assert set(all_accounts()) == {"checking"}
    assert "savings" not in REGISTRY, "not built — no phantom entry"
    assert "credit_card" not in REGISTRY, "not built — no phantom entry"


def test_all_accounts_iterates_the_registry_and_nothing_else():
    assert set(all_accounts()) == set(REGISTRY)
    assert isinstance(all_accounts(), tuple)
    assert all(isinstance(name, str) for name in all_accounts())


def test_an_entry_ties_an_account_to_its_pack():
    entry = account("checking")
    assert isinstance(entry, AccountType)
    assert entry.name == checking.ACCOUNT == "checking"
    assert entry.pack is checking


def test_the_registry_does_not_hardcode_the_field_list_it_reads_it():
    """`fields`/`schema` are properties over `pack.FIELDS`/`pack.SCHEMA` —
    identity, not a copy, so there is nowhere for a second list to drift from
    the first."""
    entry = account("checking")
    assert entry.fields is checking.FIELDS
    assert entry.schema is checking.SCHEMA
    assert entry.fields["account_number"] is Rung.L5
    assert set(entry.fields) == set(checking.SCHEMA)


def test_account_is_strict_about_an_unknown_name():
    with pytest.raises(KeyError):
        account("savings")
    with pytest.raises(KeyError):
        account("not_an_account")


# ── the import-time guard fires — BUG-6's shape, from each side ─────────────

def _fake_pack(name: str) -> types.ModuleType:
    mod = types.ModuleType(f"homestead_ledger.packs._fake_{name}")
    mod.ACCOUNT = name
    mod.FIELDS = {"description": Rung.L3}
    mod.SCHEMA = {"description": {"rung": Rung.L3, "account": name}}
    return mod


def test_a_pack_on_disk_with_no_entry_fails_the_build():
    savings = _fake_pack("savings")
    on_disk = {"checking": checking, "savings": savings}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate(dict(REGISTRY), on_disk)
    assert "savings" in str(exc.value)
    assert "no registry entry" in str(exc.value)


def test_a_registry_entry_with_no_pack_is_a_phantom_and_fails_the_build():
    phantom = registry_mod._entry(_fake_pack("savings"))
    broken = {**REGISTRY, "savings": phantom}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate(broken, {"checking": checking})
    assert "savings" in str(exc.value)
    assert "no pack" in str(exc.value)


def test_a_key_that_disagrees_with_its_packs_account_fails_the_build():
    misfiled = registry_mod.AccountType(name="chekcing", pack=checking)  # typo'd key
    broken = {"chekcing": misfiled}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate(broken, {"checking": checking})
    assert "disagrees" in str(exc.value)


def test_an_entry_that_is_not_an_account_type_fails_the_build():
    with pytest.raises(RuntimeError):
        registry_mod._validate({"checking": "checking"}, {"checking": checking})


def test_the_real_registry_passes_its_own_guard():
    registry_mod._validate(REGISTRY, registry_mod._discover_packs())
    assert set(registry_mod._discover_packs()) == set(REGISTRY)


def test_adding_a_pack_to_the_registry_needs_no_other_code_change(monkeypatch):
    """A second account kind appears in `all_accounts()` the instant it is in
    `REGISTRY`, with no other code touched — the whole point of one
    enumeration."""
    savings = registry_mod._entry(_fake_pack("savings"))
    monkeypatch.setitem(registry_mod.REGISTRY, "savings", savings)

    assert set(all_accounts()) == {"checking", "savings"}
    assert account("savings").fields == {"description": Rung.L3}


# ── the structural guard: the registry is the ONLY enumeration ──────────────

ACCOUNT_ENUM_ALLOWED = {PKG / "registry.py"}


def _account_name_enumerations(tree: ast.AST, names: set[str]) -> list[int]:
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


def test_no_module_outside_the_registry_hardcodes_the_set_of_accounts():
    names = set(all_accounts())
    offenders: list[str] = []
    for mod in sorted(PKG.rglob("*.py")):
        if "__pycache__" in mod.parts:
            continue
        if mod in ACCOUNT_ENUM_ALLOWED or _is_pack(mod):
            continue
        for lineno in _account_name_enumerations(ast.parse(mod.read_text("utf-8")), names):
            offenders.append(f"{mod.relative_to(PKG.parent)}:{lineno}")
    assert not offenders, (
        f"an account name is enumerated by hand outside the registry at {offenders}. "
        "I-23 — iterate all_accounts() rather than keeping a list."
    )


def test_the_structural_guard_fires_on_a_planted_enumeration(tmp_path):
    names = {"checking", "savings", "credit_card"}
    literal = tmp_path / "queue.py"
    literal.write_text("ALL_ACCOUNTS = ['checking', 'savings', 'credit_card']\n", "utf-8")
    membership = tmp_path / "nav.py"
    membership.write_text("def is_account(a):\n    return a in ('checking', 'savings')\n", "utf-8")
    assert _account_name_enumerations(ast.parse(literal.read_text()), names)
    assert _account_name_enumerations(ast.parse(membership.read_text()), names)
