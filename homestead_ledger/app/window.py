"""S1 — the window's surface state, ported from homestead-law's `app/window.py`
for the money domain. Same shape, same invariants; only the domain words
change (a matter's field becomes a transaction's field).

`Window` is the two S1 panes as a state machine, with no display attached. It
rests on the **cover** (I-21: the record is not drawn before a human asks),
and on request composes either the **list** (`S1_LIST`) or the **detail**
(`S1_DETAIL`). A view — tkinter, bite 3 — draws whatever the window currently
holds; nothing in this module knows how to draw anything.

**I-29 — the surface holds no domain logic.** Everything here composes
through `serve()` and calculates nothing: no rung is compared, no ceiling is
read, no `.payload` is reached. What the window keeps are `Row`s (a
reference, a rung, and already-served text) and a `Served` — both already
through the gate. That is why the list cannot show an `L4` amount and the
cover cannot show anything: the *shape* of what the window holds, not a check
in this file.

**A `Row` carries a reference, never a record.** `Ref` is `(account, field,
item_id)` — a reference exactly as a log entry is (I-15), never the datum. A
click can carry a ref back to `open_detail`, which re-serves that one record
for the pane the operator opened, so an interactive list never has to hold a
payload it was not asked to show.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from homestead.keep.rungs import (
    Classified,
    Disposition,
    Rung,
    Served,
    Surface,
    serve,
)

__all__ = ["Ref", "Row", "Window"]

#: A reference to one record — its key, not its content (I-15).
Ref = tuple[str, str, str]

_COVER = "cover"
_LIST = "list"
_DETAIL = "detail"


@dataclass(frozen=True)
class Row:
    """One line in the list pane: a reference, a rung, and the served text.
    `text` is what `serve(S1_LIST)` handed back — the payload for L1-L3, the
    derived form for L4. An L5 field never becomes a `Row` at all."""

    ref: Ref
    rung: Rung
    text: str


class Window:
    """The S1 surface, resting on the cover until a human asks.

    `state` is one of `"cover"`, `"list"`, `"detail"`. `rows` are the
    composed list; `detail` is the served datum of the open pane. Both are
    empty at rest — the cover draws nothing (I-21).
    """

    def __init__(self) -> None:
        self._state = _COVER
        self._rows: list[Row] = []
        self._detail: Served | None = None
        self._records: dict[Ref, Classified] = {}

    @property
    def state(self) -> str:
        return self._state

    @property
    def rows(self) -> list[Row]:
        """A copy, so a view holding it cannot mutate the surface's state."""
        return list(self._rows)

    @property
    def detail(self) -> Served | None:
        return self._detail

    def open_list(self, items: Iterable[tuple[Ref, Classified]]) -> list[Row]:
        """Compose the list pane (`S1_LIST`) from an account's records, each
        paired with its reference. The gate drops `L5` (an account number),
        derives `L4` (an amount), and renders the rest (`L1`-`L3`); a dropped
        record leaves no row and no trace. Records are kept keyed by ref so a
        click can open one — the ref is the only handle the list keeps."""
        self._records = {}
        rows: list[Row] = []
        for ref, record in items:
            self._records[ref] = record
            served = serve(record, Surface.S1_LIST)
            if served.disposition is Disposition.DENY:
                continue
            rows.append(Row(ref=ref, rung=served.rung, text=str(served.value)))
        self._rows = rows
        self._detail = None
        self._state = _LIST
        return self.rows

    def open_detail(self, ref: Ref) -> Served:
        """Open one record in the detail pane (`S1_DETAIL`), named by its
        ref. Opening it *is* the purpose declaration, so no purpose is
        passed — and `serve` still denies an `L5`, which no act overrides.
        Re-served rather than read from the row, so nothing a `Row` carries
        is a payload."""
        record = self._records[ref]
        self._detail = serve(record, Surface.S1_DETAIL)
        self._state = _DETAIL
        return self._detail

    def close(self) -> None:
        """Back to the cover, letting go of the working set and whatever was
        shown. A reveal does not persist past the act that asked for it
        (I-32's reveal-timeout ground)."""
        self._state = _COVER
        self._rows = []
        self._detail = None
        self._records = {}
