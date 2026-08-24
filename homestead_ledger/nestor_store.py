"""The Nestor store adapter — a SqliteStore inside the household root.

This module creates and exposes the Nestor SqliteStore that lives at
``<household_root>/nestor-ledger.db``.  It is the host's adapter — distinct
from ``nestor_seam.py``, which is the boundary.  The seam says *how* this
module calls Nestor; this module says *where* the memory lives.

The store is created lazily (``get_store()``) and cached per process, so two
callers in the same process share one connection.  It is always inside the
household root, never a global or a temp: Nestor's entity and reconciliation
memory for a matter is a household artefact, not a session artefact.

Uses ``nestor.sqlite_store.SqliteStore`` directly — a dependency-inversion
boundary that Nestor's own contract says a host should inject.  The import is
local (inside ``get_store``), so the ``entity`` optional extra not being
installed does not break this import.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from homestead.keep import paths

__all__ = ["get_store", "store_path"]

_store: Optional[Any] = None
_store_path: Optional[Path] = None


def store_path(household_root: Path | None = None) -> Path:
    """The path where Nestor's ledger store lives — inside the household root."""
    root = Path(household_root) if household_root is not None else paths.home()
    return root / "nestor-ledger.db"


def get_store(household_root: Path | None = None) -> Any:
    """A SqliteStore at ``<household_root>/nestor-ledger.db``, cached per process.

    Creates the parent directory if needed (``paths.home()`` may not exist on
    first run).  The store is the Nestor Storage protocol's reference SQLite
    implementation, injected here by the host rather than set globally
    (nestor_seam.py PRECONDITION 2).
    """
    global _store, _store_path

    from nestor.sqlite_store import SqliteStore

    p = store_path(household_root)
    if _store is not None and _store_path == p:
        return _store

    p.parent.mkdir(parents=True, exist_ok=True)
    _store = SqliteStore(str(p))
    _store_path = p
    return _store
