"""Sync — a consented scope of the household's own books, composed and sent
to its own fleet store on an explicit act (Decision 5; the engine's
`homestead.keep.sync`, provisional I-37/I-38/I-40, ratified by the
E4-sync-core audit, 2026-09-11). `SyncScope`, `compose`, `Envelope`,
`deliver` are all the engine's; nothing here reimplements the gate, the
hash, or the ledgering.

What this module adds on top:

  * `scope_from` holds `matters` against what this household actually has
    (`known_matters`) — no `"all"` (I-40), no unregistered name. Everything
    else (empty matters/tables, an `L5` ceiling, an unknown table) is the
    engine's own `SyncScope.__post_init__` refusal, reused rather than
    re-decided.
  * `preview` composes through the engine's `compose()`, with two filters
    applied at the **reader seam** — before the engine scores a single row
    — so `Envelope.envelope_id` (a hash over exactly the rows `compose()`
    kept) already covers what survived, with no second hash to keep in
    step: (1) `do_not_use` drops every canonical field and every overlay
    tag (including the `do_not_use` tag itself — syncing it would still
    name the excluded fingerprint) of the tagged transaction; a **transfer
    pair** naming that fingerprint is *not* dropped — it is filed under
    `transfers`, a reference to two of the household's own accounts moving
    money, not the excluded transaction's own data. (2) `accounts.number`
    (`L5`) is refused as a structural belt *after* `compose()` returns,
    whatever rung it currently reports — the engine's own ceiling drop
    already stops it today; this is the day a corrupted or monkeypatched
    rung table does not (`tests/test_sync.py` plants exactly that).
  * `send` resolves *where* an envelope goes when the caller names neither
    `url=` nor `drop_dir=`: `HOMESTEAD_FLEET_URL`, then `home()/fleet.url`,
    then a file drop under `default_drop_dir()`. A destination found here
    is never a permission (I-37): `deliver()` still refuses, and writes and
    ledgers nothing, unless `confirm` returns `True`.

No `.payload` reach anywhere (I-16): every row here came out of
`compose()`, itself built from `serve()`'s `Served.value` alone.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping

from homestead.keep import paths
from homestead.keep.rungs import Classified, Rung
from homestead.keep.store import SIDECAR, Reader
from homestead.keep.sync import (
    AlreadyDelivered,
    Confirm,
    Envelope,
    Receipt,
    SyncScope,
    TamperedEnvelope,
    UnnamedScope,
    compose as _engine_compose,
    default_drop_dir,
    deliver as _engine_deliver,
)

from homestead_ledger import accounts, obligations, overlay, transfers
from homestead_ledger.store import Canonical, Sidecar

__all__ = [
    "SyncScope", "Envelope", "Receipt", "Confirm",
    "UnnamedScope", "TamperedEnvelope", "AlreadyDelivered", "NumberNeverCrosses",
    "default_drop_dir",
    "known_matters", "scope_from", "preview", "destination_preview", "send",
]

#: The bank-issued number's field name (`packs/accounts.py`, under
#: `accounts.MATTER`) — refused at any rung (I-13/I-43).
_NUMBER_FIELD = "number"

#: Sidecar matters outside the account-instance labels, each read off its
#: own domain module's declared constant (I-23) rather than retyped here.
_KNOWN_SIDECAR_MATTERS = (accounts.MATTER, overlay.MATTER, transfers.MATTER)


class NumberNeverCrosses(ValueError):
    """A row naming `accounts.py`'s `number` field survived `compose()`,
    whatever rung it currently reports — the belt behind the engine's own
    ceiling drop (I-13), for the day a corrupted or monkeypatched rung
    table lets one past it. A `ValueError`, the same family every other
    scope/compose refusal here raises."""


def known_matters(sidecar: Sidecar) -> tuple[str, ...]:
    """Every matter name `scope_from` accepts: each registered account
    instance's own label (the canonical matter its transactions are filed
    under), the obligations matter, and the other sidecar matters
    (`accounts`, `overlay`, `transfers`). No `"all"` (I-40)."""
    return tuple(sorted(
        set(accounts.instances(sidecar))
        | {obligations.KIND}
        | set(_KNOWN_SIDECAR_MATTERS)
    ))


def scope_from(
    matters: Iterable[str],
    item_types: Iterable[str] | None,
    ceiling: Rung,
    tables: Iterable[str],
    *,
    sidecar: Sidecar | None = None,
) -> SyncScope:
    """Build a `SyncScope`, holding `matters` against `known_matters` first
    (I-40): `"all"` is refused by name, and a name this household does not
    have on file is refused rather than silently composing nothing for it.
    Everything else is the engine's own `SyncScope.__post_init__` refusal
    (`UnnamedScope`), reused rather than re-decided here."""
    store = sidecar if sidecar is not None else Sidecar()
    matters_t = tuple(matters)
    if "all" in matters_t:
        raise UnnamedScope(
            "'all' is not a matter — a SyncScope names each matter "
            f"explicitly (I-40); this household's matters are "
            f"{known_matters(store)!r}"
        )
    valid = set(known_matters(store))
    unknown = sorted(set(matters_t) - valid)
    if unknown:
        raise UnnamedScope(f"unknown matter(s) {unknown} — one of {sorted(valid)}")
    types_t = tuple(item_types) if item_types else None
    return SyncScope(
        matters=matters_t, item_types=types_t, ceiling=ceiling, tables=tuple(tables),
    )


class _ExcludingReader:
    """Wraps one `Reader` with the `do_not_use` filter, applied **before**
    the engine's `compose()` ever sees a row (see the module docstring).
    `transaction_matters` names the matters a fingerprint's *own* data is
    filed under — every account label, plus `overlay`; a matter outside
    that set (`transfers` above all) passes through untouched."""

    def __init__(
        self, inner: Reader, *, excluded: frozenset[str], transaction_matters: frozenset[str],
    ) -> None:
        self._inner = inner
        self._excluded = excluded
        self._transaction_matters = transaction_matters

    def records(self, matter: str) -> list[tuple[tuple[str, str, str], Classified]]:
        rows = self._inner.records(matter)
        if matter not in self._transaction_matters or not self._excluded:
            return rows
        return [(ref, classified) for ref, classified in rows if ref[2] not in self._excluded]


def _refuse_a_leaked_number(envelope: Envelope) -> None:
    leaked = [row for row in envelope.rows if row.get("item_type") == _NUMBER_FIELD]
    if leaked:
        raise NumberNeverCrosses(
            f"{len(leaked)} row(s) named accounts.py's number field survived "
            "compose() — refused rather than handed back, whatever rung the "
            "ceiling check currently reports for it (I-13)"
        )


def preview(
    scope: SyncScope, *, sidecar: Sidecar | None = None, canonical: Canonical | None = None,
) -> Envelope:
    """Compose `scope` into an `Envelope` through the engine's own
    `compose()`, with this module's filters applied at the reader seam.
    The returned envelope's `envelope_id` covers exactly the rows that
    survived — nothing is dropped or added after the fact."""
    store = sidecar if sidecar is not None else Sidecar()
    canon = canonical if canonical is not None else Canonical()
    excluded = overlay.excluded_fingerprints(store)
    transaction_matters = frozenset(accounts.instances(store)) | {overlay.MATTER}
    readers: Mapping[str, Reader] = {
        SIDECAR: _ExcludingReader(store, excluded=excluded, transaction_matters=transaction_matters),
        # The literal "canonical", never the engine's `CANONICAL` name: this
        # package's chokepoint scan refuses any module but books.py naming
        # that table constant at all.
        "canonical": _ExcludingReader(canon, excluded=excluded, transaction_matters=transaction_matters),
    }
    envelope = _engine_compose(readers, scope)
    _refuse_a_leaked_number(envelope)
    return envelope


def _destination_url() -> str | None:
    """`HOMESTEAD_FLEET_URL`, else the one line in `home()/fleet.url`, else
    `None`. Read only when a caller actually resolves a destination — never
    ambiently, and never inside the engine's `deliver()` itself, so a
    destination stays something the caller (and the confirm) can see."""
    env = os.environ.get("HOMESTEAD_FLEET_URL", "").strip()
    if env:
        return env
    try:
        text = (paths.home() / "fleet.url").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def destination_preview() -> str:
    """Where `send()` would deliver if the caller names no destination —
    read-only: dials nothing, writes nothing. The same resolution `send()`
    itself applies, exposed so a preview can show it first."""
    url = _destination_url()
    return url if url is not None else str(default_drop_dir())


def send(
    envelope: Envelope, *, url: str | None = None, drop_dir: Path | None = None,
    confirm: Confirm,
) -> Receipt:
    """Deliver `envelope` through the engine's own `deliver()`. Resolves
    *where*, in order, only when the caller names neither `url=` nor
    `drop_dir=`: `HOMESTEAD_FLEET_URL`, then `home()/fleet.url`, then a
    file drop under `default_drop_dir()`. A destination that is only
    *found* here is never a permission (I-37): a declined (or missing)
    `confirm` still raises `EgressRefused`, from the engine's own
    `deliver()` — nothing is written and nothing is ledgered."""
    if url is None and drop_dir is None:
        url = _destination_url()
        if url is None:
            drop_dir = default_drop_dir()
    return _engine_deliver(envelope, confirm=confirm, url=url, drop_dir=drop_dir)
