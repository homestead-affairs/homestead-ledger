"""nestor_seam.py -- the ONLY place this module touches Nestor.

Nestor is an OPTIONAL EXTRA (`pyproject.toml`'s `[project.optional-
dependencies] entity`), pinned to `nestor-meaning>=0.11.0,<1.0`. Nothing here
raises on import, nothing here crashes a surface when Nestor is absent. The
household's own books (`homestead_ledger.books`, `homestead_ledger.store`)
exist regardless; Nestor's ledger is bound only when the extra is present and
`bind()` has run.

===========================================================================
TAKEN FROM NESTOR   (pin: nestor-meaning >=0.11.0)
===========================================================================

  EntityResolver(store, domain=...)                       nestor.entity
      .resolve(surface) -> dict      read-only; fuzzy-match a surface form
                                     against sealed aliases
      .seal(surface, canonical, verifier=...)             human-initiated write
      .add_alias(surface, canonical, verifier=...)        human-initiated write

  Reconciler(store, domain=..., abs_tol=..., pct_tol=...)  nestor.reconcile
      Numeric baseline-vs-observation checking. Compares a claimed figure
      against a known baseline and flags discrepancies beyond tolerance --
      obligation amounts, recurring charges, balance assertions.

  Storage                                                 nestor.storage
      A Protocol. Nestor owns no persistence -- "a concrete implementation is
      *injected* by the host." `resolver_for()` and `reconciler_for()` take
      the store as a parameter rather than constructing one; a SQLite (or
      other) adapter conforming to the Protocol is this module's own build
      item, not this seam's.

  set_ledger_path(path)                                   nestor.cascade
      REQUIRED. See PRECONDITIONS. `bind()` calls this -- it is the only
      function in this module that changes where Nestor's audit trail lives.

  ledger.verify(path, expected_head=...)                  nestor.ledger
      Verify the chain on read/boot. A broken chain is a refusal upstream of
      this call -- `verify_ledger()` reports `False` for the caller to act on,
      the same convention `homestead.keep.logs.IntegrityLog.verify()` uses.

===========================================================================
NOT TAKEN   (deliberate -- the omissions carry as much weight as the takings)
===========================================================================

  nestor.cascade translation pipeline   translate_text, translate_segment,
      graduate_segment. Translation is not this module's domain.

  nestor.matcher / nestor.semantic_matcher   reached only through
      EntityResolver. Never imported directly; that is how the surface widens.

  nestor.serve / nestor.ui / nestor.ui_page   an HTTP server. ``ui.py`` imports
      ``http.server`` and ``urllib.parse`` at module level, which would put a
      network import in the import-pure core and fail this repo's own
      `test_no_egress` the moment the extra was installed and this seam
      imported it eagerly. It is not imported here, anywhere, ever.

  DecisionMemory / nestor.memory    not this module's domain.

  nestor.answer * curator * frank * glossary * langid * segment * calibrate
      * portable * keyring * signing * embedding_store * sqlite_store
      * engine * cli
      Not our business. Some are excellent. Not ours.

===========================================================================
PRECONDITIONS   -- all three MUST hold before any Nestor call in this process
===========================================================================

1.  THE LEDGER IS PINNED INSIDE `<household root>/keep/ledger.jsonl`.

    Nestor's hash-chained ledger is **not part of the Storage protocol** --
    injecting the store does not cover it. Unbound, it resolves independently:

        _LEDGER_OVERRIDE  ->  $NESTOR_LEDGER  ->  "data/ledger.jsonl"

    So a default install writes to ``data/ledger.jsonl`` relative to the
    working directory: outside the household root, outside anything this
    module's own rules reach. `bind()` exists to close that window before any
    other Nestor call in this process -- see `SeamNotBoundError`.

    The path is not invented here. This seam calls **only**
    `homestead.keep.paths` for WHERE and never Nestor's own household
    resolver, so there is one resolver on this side of the boundary, not two
    that could drift. `<root>/keep/ledger.jsonl` is then handed to
    `set_ledger_path()` as an explicit path.

2.  THE STORE IS PASSED EXPLICITLY, NEVER SET GLOBALLY.

    ``nestor.storage`` offers ``set_store()`` as a process-wide global. This
    seam does not call it. `resolver_for()` and `reconciler_for()` require the
    caller's `store` explicitly, so two modules can never share a resolver's
    store by accident, and so the household's store cannot be picked up by code
    that was not handed it.

3.  NESTOR IS PINNED TO A TAG.

    `nestor-meaning>=0.11.0,<1.0`, never a branch on anything that ships.
    Never vendored: vendored source gets read and edited, a wheel in
    site-packages does not. See `pyproject.toml`'s `entity` extra.

===========================================================================
DOMAINS
===========================================================================

  "merchant"    payee entity resolution -- the surface form written in the
                record (a bank description, a payee line) resolved to a
                canonical merchant or payee identity.

  "amount"      numeric reconciliation for obligation checking -- a claimed
                figure compared against a known baseline (scheduled payment,
                recurring charge, balance assertion).

===========================================================================
SPECIAL CONSTRAINT
===========================================================================

  **Never deposits household affairs into Nestor.** The Nestor store must live
  inside `~/.homestead`; raw descriptions and amounts must not flow outward.
  This seam pins the ledger inside the household root and passes a store the
  caller controls. Nothing here opens a channel to any location Nestor might
  resolve on its own.

===========================================================================
COVENANT
===========================================================================

  This seam never seals anything on its own initiative.
  `EntityResolver.seal` / `.add_alias` are human-initiated writes upstream of
  this module (a caller passes a `verifier=`); nothing here calls them, and
  nothing here manufactures a `verifier`. A machine proposes; only a named
  human seals.

===========================================================================
FOR AGENTS AND FUTURE READERS
===========================================================================

Nestor is a PINNED DEPENDENCY consumed only through this file. Do not modify
it, do not propose changes to it, and do not move logic from this module into
it. If Nestor needs a change, that is an issue on Nestor's own repo.

The subject of work here is *how this module uses Nestor*, never Nestor itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from homestead.keep import paths

__all__ = [
    "bind",
    "resolver_for",
    "reconciler_for",
    "verify_ledger",
    "SeamNotBoundError",
]


class SeamNotBoundError(RuntimeError):
    """A Nestor call was attempted before `bind()` pinned the ledger.

    Raised rather than defaulted, because the default is the leak: an unbound
    ledger writes household entity resolutions to `data/ledger.jsonl` in the
    working directory. Fail closed.
    """


_bound: bool = False
_ledger_path: Optional[Path] = None


def bind(household_root: Path | None = None) -> Path:
    """Pin Nestor's ledger inside the household root. Call once, before use.

    `household_root` defaults to `homestead.keep.paths.home()` -- the one
    resolver this module is permitted to call -- and should only be passed
    explicitly by a test or an operator who deliberately moved the root.

    Sets Nestor's ledger location to `<household_root>/keep/ledger.jsonl` --
    computed here from this repo's own resolver and passed to
    `nestor.cascade.set_ledger_path()` as an explicit path, so it holds
    whatever Nestor's own household root happens to be (PRECONDITION 1).
    Idempotent: calling it again with the same root re-asserts the same path;
    calling it with a different root re-binds to the new one. Returns the
    ledger path that is now pinned.

    Nestor is imported here, not at module load, so a checkout without the
    `entity` extra still imports this module cleanly.
    """
    global _bound, _ledger_path

    from nestor.cascade import set_ledger_path

    root = Path(household_root) if household_root is not None else paths.home()
    ledger = root / "keep" / "ledger.jsonl"
    set_ledger_path(ledger)
    _ledger_path = ledger
    _bound = True
    return ledger


def resolver_for(domain: str, store: Any) -> Any:
    """An `EntityResolver` over an explicitly-injected household store.

    `domain` separates disjoint entity graphs within one store -- "merchant",
    "party", etc. -- so a payee resolution and a party resolution never
    cross-talk.

    `store` is required and passed straight through to Nestor -- this seam
    never calls `nestor.storage.set_store()` and never falls back to a global
    (PRECONDITION 2). Raises `SeamNotBoundError` if `bind()` has not run:
    constructing a resolver with an unpinned ledger is the leak this seam
    exists to prevent, so it is refused before Nestor is even imported.
    """
    if not _bound:
        raise SeamNotBoundError(
            "resolver_for() called before bind(). Call nestor_seam.bind() "
            "once at startup -- an EntityResolver built on an unpinned ledger "
            "would write household entity resolutions to data/ledger.jsonl "
            "in the working directory, outside anything this module's own "
            "rules reach."
        )

    from nestor.entity import EntityResolver

    return EntityResolver(store, domain=domain)


def reconciler_for(
    domain: str,
    store: Any,
    abs_tol: float = 0.0,
    pct_tol: float = 0.05,
) -> Any:
    """A `Reconciler` over an explicitly-injected household store.

    `domain` separates disjoint reconciliation scopes -- "amount" for
    obligation checking, so a scheduled-payment baseline and a balance
    assertion never cross-talk.

    `store` is required and passed straight through to Nestor -- this seam
    never calls `nestor.storage.set_store()` and never falls back to a global
    (PRECONDITION 2). `abs_tol` and `pct_tol` set the tolerance window for
    numeric comparison (default: exact match within 5% relative).

    Raises `SeamNotBoundError` if `bind()` has not run.
    """
    if not _bound:
        raise SeamNotBoundError(
            "reconciler_for() called before bind(). Call nestor_seam.bind() "
            "once at startup -- a Reconciler built on an unpinned ledger "
            "would write to data/ledger.jsonl in the working directory, "
            "outside anything this module's own rules reach."
        )

    from nestor.reconcile import Reconciler

    return Reconciler(store, domain=domain, abs_tol=abs_tol, pct_tol=pct_tol)


def verify_ledger(expected_head: Optional[str] = None) -> bool:
    """Walk the hash chain and confirm every link. Run on read/boot.

    Returns `True` for an intact chain (or no ledger yet -- Nestor's own
    `verify()` treats absence as trivially valid) and `False` for a broken one.
    The bool return, not an exception, is deliberate: a broken chain is a
    refusal for the *caller* to act on -- nothing in this module decides what
    "refusal" means for a given surface.

    Raises `SeamNotBoundError` if `bind()` has not run: there is no ledger
    path to verify until this seam has pinned one.
    """
    if not _bound:
        raise SeamNotBoundError(
            "verify_ledger() called before bind(). Call nestor_seam.bind() "
            "once at startup so there is a pinned ledger path to verify."
        )

    from nestor.ledger import verify

    ok, _detail = verify(str(_ledger_path), expected_head=expected_head)
    return ok
