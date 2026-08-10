"""The account-kind registry — the one enumeration of what the books hold.

I-23: **the registry is the only enumeration.** Anything that touches "all
accounts" iterates this, and nothing keeps an account list of its own — the
money-domain reading of the same rule homestead-law's `registry.py` states
against BUG-6 (three hand-kept matter lists that drifted; workers' comp fell
silently out of the urgent queue because the loop that raised urgency did not
know it existed). Nothing in this bite iterates "all accounts" yet — there is
no queue until bite 2 — but the registry is built now, before it has a
consumer, so that consumer never has a reason to keep its own list.

Keyed by account-kind name, valued by an `AccountType` that ties the name to
its **pack** — the closed, classified schema module (`homestead_ledger.packs.
checking`) that authored the fields. The registry holds a *reference* to the
pack, not a copy: `fields`/`schema` read `pack.FIELDS`/`pack.SCHEMA` live, so
there is exactly one field list in the process.

Only `checking` is built in bite 1 — savings and credit-card are the next
account kinds the model would need, and inventing a stub for either would be
the hand-kept phantom this file forbids (a name in the registry with no pack
behind it).
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Mapping

from homestead.keep.rungs import Rung

from homestead_ledger import packs
from homestead_ledger.packs import checking

__all__ = ["AccountType", "REGISTRY", "all_accounts", "account"]


@dataclass(frozen=True)
class AccountType:
    """One account kind, tied to the pack that defines its transaction
    schema. `pack` is the imported pack module — the host holding a reference
    to the thing it consumes, never the reverse. `fields`/`schema` read
    through to it live, so the registry can never carry a stale second copy."""

    name: str
    pack: ModuleType

    @property
    def fields(self) -> dict[str, Rung]:
        """The pack's classified fields, read live — not stored on the entry."""
        return self.pack.FIELDS

    @property
    def schema(self) -> dict[str, Any]:
        """The pack's closed schema, read live."""
        return self.pack.SCHEMA


def _entry(pack: ModuleType) -> AccountType:
    """An `AccountType` from a pack, reading its own declared `ACCOUNT` — the
    key this entry goes under and the pack's identity are the same value read
    once, so the validation below checks that reading rather than a
    transcription that could disagree with it."""
    return AccountType(name=pack.ACCOUNT, pack=pack)


#: The one enumeration (I-23). Only `checking` is built (bite 1); savings and
#: credit-card are the next account kinds, not built here.
REGISTRY: dict[str, AccountType] = {
    checking.ACCOUNT: _entry(checking),
}


def _discover_packs() -> dict[str, ModuleType]:
    """Every module under `homestead_ledger.packs` that declares an
    `ACCOUNT` — the set the registry is held against. A pack authored and
    left out of `REGISTRY` is BUG-6 exactly: an account kind that exists but
    that nothing iterating "all accounts" will ever reach."""
    found: dict[str, ModuleType] = {}
    for info in pkgutil.iter_modules(packs.__path__, prefix=f"{packs.__name__}."):
        module = importlib.import_module(info.name)
        name = getattr(module, "ACCOUNT", None)
        if isinstance(name, str) and name:
            found[name] = module
    return found


def _validate(registry: Mapping[str, Any], on_disk: Mapping[str, ModuleType]) -> None:
    """Hold the registry against the packs that actually exist, at import.
    Pure in its two arguments, so the guard can be fired against a
    deliberately broken registry in a test rather than only asserted about."""
    for key, entry in registry.items():
        if not isinstance(entry, AccountType):
            raise RuntimeError(
                f"REGISTRY[{key!r}] is a {type(entry).__name__}, not an AccountType"
            )
        if key != entry.name or key != entry.pack.ACCOUNT:
            raise RuntimeError(
                f"REGISTRY key {key!r} disagrees with its pack's ACCOUNT "
                f"({entry.pack.ACCOUNT!r}) — an account kind is keyed by the "
                "name its pack declares, read once, so the two cannot drift."
            )

    unregistered = sorted(set(on_disk) - set(registry))
    if unregistered:
        raise RuntimeError(
            f"packs with no registry entry: {unregistered}. Every pack that "
            "exists must be enumerated here (I-23) — an account kind the "
            "registry does not know is one nothing that iterates "
            "all_accounts() will reach, BUG-6's shape. Add it to REGISTRY."
        )
    phantom = sorted(set(registry) - set(on_disk))
    if phantom:
        raise RuntimeError(
            f"registry entries with no pack: {phantom}. A name in the "
            "enumeration with no pack behind it is the hand-kept phantom "
            "I-23 forbids — enumerate only what is built."
        )


_validate(REGISTRY, _discover_packs())


def all_accounts() -> tuple[str, ...]:
    """Every account kind the books hold — the one place to ask. Iterates
    `REGISTRY` and nothing else, so a caller cannot drift from it the way
    BUG-6's three lists did. A tuple, not a live view, so holding the return
    value cannot mutate the enumeration."""
    return tuple(REGISTRY)


def account(name: str) -> AccountType:
    """The `AccountType` for a name, or `KeyError`. Strict: a caller holding
    a name that is not registered has skipped a step upstream."""
    return REGISTRY[name]
