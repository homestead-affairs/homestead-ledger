"""homestead-ledger's store — `homestead.keep`'s adapter seam on a SQLite backing.

The record layer is the engine's (`homestead.keep.store`), tested there against
every backing. This module is the thin binding: the `Sidecar` and `Canonical` it
ships write to and read from a **SQLite** database in the shared `/.homestead`
root — the self-contained app's backing, no server. The invariants
(I-6/I-7/I-9/I-11) are the engine's contract; here we only choose the backing and
the database.

**Mirror, not judge.** In this module the *canonical* store holds the household's
own money record — imported transactions, statements — and is **read-only by
type** (I-6): the app has no write path to it. The household's overlay —
categorization, notes, budget envelopes, a confirmed merchant name — goes to the
*sidecar*. The app reflects the books; it never edits them.

Law and the ledger share the root — a household's affairs are one thing — and
each keeps its own database in it (`homestead-law.db`, `homestead-ledger.db`).
"""
from __future__ import annotations

from homestead.keep import paths
from homestead.keep.store import (
    Canonical as _Canonical,
    Due,
    InvalidKey,
    RecordExists,
    Ref,
    Replaced,
    Sidecar as _Sidecar,
    SQLiteAdapter,
    key,
)

__all__ = [
    "key", "InvalidKey", "RecordExists", "Replaced", "Due", "Ref",
    "Sidecar", "Canonical",
]


def _adapter() -> SQLiteAdapter:
    """This module's database — its own file in the shared `/.homestead` root."""
    return SQLiteAdapter(paths.home() / "homestead-ledger.db")


class Sidecar(_Sidecar):
    """The household's writable overlay, on SQLite in the ledger database."""

    def __init__(self) -> None:
        super().__init__(_adapter())


class Canonical(_Canonical):
    """The read-only handle over the household's own books (I-6)."""

    def __init__(self) -> None:
        super().__init__(_adapter())
