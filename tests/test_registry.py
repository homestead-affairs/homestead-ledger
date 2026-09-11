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


def test_the_bite_2a_account_kinds_are_registered():
    """`checking` (bite 1) plus `savings`, `credit_card` and `loan` (bite
    2a) — every account kind built so far, and nothing invented beyond it: a
    name with no pack behind it is the hand-kept phantom I-23 forbids."""
    assert set(all_accounts()) == {"checking", "savings", "credit_card", "loan"}
    assert "heloc" not in REGISTRY, "not built — no phantom entry"


def test_all_accounts_iterates_the_registry_and_nothing_else():
    assert set(all_accounts()) == set(REGISTRY)
    assert isinstance(all_accounts(), tuple)
    assert all(isinstance(name, str) for name in all_accounts())


def test_all_accounts_order_is_pinned_because_surfaces_read_it_in_order():
    """`all_accounts()` is an *ordered* contract, not just a set: the cover
    draws one button per kind in this order (`app/view.account_buttons`) and
    the browser form's `<select>` is built in it — so its **first** entry is
    the account a transaction posts to before the operator touches anything.
    A reordering of `REGISTRY` would silently move that default to another
    account; it is pinned here so such a change has to be deliberate.
    `checking` stays first because it is `books.Transaction.kind`'s default."""
    assert all_accounts() == ("checking", "savings", "credit_card", "loan")
    assert all_accounts()[0] == checking.ACCOUNT
    assert all_accounts() == tuple(REGISTRY)  # insertion order, nothing re-sorted
    assert all_accounts() == all_accounts()  # stable across calls


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
        account("heloc")
    with pytest.raises(KeyError):
        account("not_an_account")


# ── bite 2b — the accounts sidecar matter is not a discovered account kind ──

def test_the_accounts_sidecar_is_not_a_discovered_pack():
    """`packs/accounts.py` declares a schema for the sidecar matter
    `accounts` (real account instances, decision 9) — it is not a pack in
    `all_accounts()`, and must never become one: a label could then be
    mistaken for a kind, exactly what I-43's own refusal exists to prevent.
    It declares no `ACCOUNT`/`OBLIGATION` (the attributes `_discover_packs`/
    `_discover_obligation_packs` scan for), so neither registry ever finds
    it — checked directly against both discovery functions, not only against
    today's `REGISTRY` contents."""
    from homestead_ledger.packs import accounts as accounts_pack

    assert not hasattr(accounts_pack, "ACCOUNT")
    assert not hasattr(accounts_pack, "OBLIGATION")
    assert "accounts" not in all_accounts()
    assert accounts_pack not in registry_mod._discover_packs().values()
    assert accounts_pack not in registry_mod._discover_obligation_packs().values()


# ── the import-time guard fires — BUG-6's shape, from each side ─────────────

def _fake_pack(name: str, *, liability: bool = False) -> types.ModuleType:
    mod = types.ModuleType(f"homestead_ledger.packs._fake_{name}")
    mod.ACCOUNT = name
    mod.LIABILITY = liability
    mod.FIELDS = {"description": Rung.L3}
    mod.SCHEMA = {"description": {"rung": Rung.L3, "account": name}}
    return mod


#: A never-registered account name, used across this file's planted-violation
#: fixtures — `savings` used to play this role before bite 2a built it for
#: real; a genuinely fake name keeps these fixtures honest now that "savings"
#: is one of the real, registered kinds.
_UNBUILT = "heloc"


def test_a_pack_on_disk_with_no_entry_fails_the_build():
    heloc = _fake_pack(_UNBUILT)
    on_disk = {**registry_mod._discover_packs(), _UNBUILT: heloc}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate(dict(REGISTRY), on_disk)
    assert _UNBUILT in str(exc.value)
    assert "no registry entry" in str(exc.value)


def test_a_registry_entry_with_no_pack_is_a_phantom_and_fails_the_build():
    phantom = registry_mod._entry(_fake_pack(_UNBUILT))
    broken = {**REGISTRY, _UNBUILT: phantom}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate(broken, registry_mod._discover_packs())
    assert _UNBUILT in str(exc.value)
    assert "no pack" in str(exc.value)


def test_a_pack_without_liability_fails_the_build():
    """Every account pack must declare `LIABILITY` as a bool — a pack that
    leaves it undeclared (or spells it as a string, an int, anything but a
    real bool) fails the build with the field named, the same posture
    `classify_schema` takes for a missing rung (I-11's shape, restated for
    this declaration)."""
    mod = types.ModuleType("homestead_ledger.packs._fake_no_liability")
    mod.ACCOUNT = _UNBUILT
    mod.FIELDS = {"description": Rung.L3}
    mod.SCHEMA = {"description": {"rung": Rung.L3, "account": _UNBUILT}}
    # LIABILITY deliberately never set on `mod`.
    broken = {**REGISTRY, _UNBUILT: registry_mod._entry(mod)}
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate(broken, {**registry_mod._discover_packs(), _UNBUILT: mod})
    assert _UNBUILT in str(exc.value)
    assert "LIABILITY" in str(exc.value)

    # and a non-bool LIABILITY is caught exactly the same way — a string or
    # an int is not the bool `AccountType.liability` and `balance.
    # running_balance` need, even though it might read as "truthy."
    mod.LIABILITY = "yes"
    with pytest.raises(RuntimeError) as exc:
        registry_mod._validate(broken, {**registry_mod._discover_packs(), _UNBUILT: mod})
    assert "LIABILITY" in str(exc.value)


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
    """A new account kind appears in `all_accounts()` the instant it is in
    `REGISTRY`, with no other code touched — the whole point of one
    enumeration."""
    before = set(all_accounts())
    heloc = registry_mod._entry(_fake_pack(_UNBUILT))
    monkeypatch.setitem(registry_mod.REGISTRY, _UNBUILT, heloc)

    assert set(all_accounts()) == before | {_UNBUILT}
    assert account(_UNBUILT).fields == {"description": Rung.L3}


def test_the_readme_names_every_registered_account_kind():
    """The README told the operator `--account` takes "an account kind the
    registry knows (`checking` today)" for a whole bite after three more were
    built — a doc claim that went stale precisely because nothing read it.
    Every registered kind is named there, so adding one without saying so
    fails here rather than in the operator's hands."""
    readme = (PKG.parent / "README.md").read_text("utf-8")
    missing = [name for name in all_accounts() if name not in readme]
    assert not missing, (
        f"the README does not name {missing} — it tells the operator which "
        "account kinds `--account`/`--kind` accept."
    )


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


def test_the_pack_exclusion_is_a_path_boundary_not_a_name_guess():
    """Planted: `_is_pack` is what lets a real pack legitimately enumerate its
    own account kind without tripping the scan below — every `packs/*.py`
    module names its own `OBLIGATION`/`FIELDS` literal, so without this
    exclusion the guard would fire on every pack in the repo. Two names that
    have never existed on disk, one under `packs/` and one merely beside it,
    prove the boundary is the path segment and not a hand-kept pair."""
    assert _is_pack(PKG / "packs" / "planted_pack.py")
    assert not _is_pack(PKG / "planted_pack.py")
    assert not _is_pack(PKG / "app" / "planted_pack.py")
    # "packages.py" contains "pack" as a substring but is not a path segment
    # equal to "packs" — the guard must not be fooled by a name that merely
    # looks like one.
    assert not _is_pack(PKG / "packages.py")


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
    names = set(all_accounts())
    literal = tmp_path / "queue.py"
    literal.write_text(f"ALL_ACCOUNTS = {sorted(names)!r}\n", "utf-8")
    membership = tmp_path / "nav.py"
    membership.write_text(
        f"def is_account(a):\n    return a in {tuple(sorted(names))!r}\n", "utf-8"
    )
    assert _account_name_enumerations(ast.parse(literal.read_text()), names)
    assert _account_name_enumerations(ast.parse(membership.read_text()), names)


@pytest.mark.parametrize("name", sorted(all_accounts()))
def test_the_structural_guard_fires_on_each_registered_name_alone(tmp_path, name):
    """One planted name at a time, in each shape the scan reads — a list, a
    set, a tuple and a bare `==` compare. A guard proved only on a plant
    naming three of four kinds has not been shown to catch the fourth, which
    is exactly the kind a later bite adds and forgets."""
    names = set(all_accounts())
    plants = {
        "list": f"ACCOUNTS = [{name!r}]\n",
        "set": f"ACCOUNTS = {{{name!r}}}\n",
        "tuple": f"ACCOUNTS = ({name!r},)\n",
        "compare": f"def is_it(a):\n    return a == {name!r}\n",
    }
    for shape, source in plants.items():
        mod = tmp_path / f"planted_{shape}.py"
        mod.write_text(source, "utf-8")
        assert _account_name_enumerations(ast.parse(mod.read_text()), names), (
            f"the guard missed {name!r} planted as a {shape}"
        )
