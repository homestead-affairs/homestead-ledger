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
  * `preview` composes through the engine's `compose()`, with the
    `do_not_use` filter applied at the **reader seam** — before the engine
    scores a single row — so `Envelope.envelope_id` (a hash over exactly
    the rows `compose()` kept) already covers what survived, with no second
    hash to keep in step. Then two refusals *after* `compose()` returns:
    an envelope carrying `accounts.number` (`L5`) at any rung, and an
    envelope carrying no rows at all.
  * `send` resolves *where* an envelope goes when the caller names neither
    `url=` nor `drop_dir=`: `HOMESTEAD_FLEET_URL`, then `home()/fleet.url`,
    then a file drop under `default_drop_dir()`. A destination found here
    is never a permission (I-37): `deliver()` still refuses, and writes and
    ledgers nothing, unless `confirm` returns `True`.
  * `wire_matches` is what a confirm is *for*. The engine hands the confirm
    a `Wire`; a confirm that returns `True` without looking at it has
    granted a permission, not confirmed an act, and would approve whatever
    envelope happened to reach the transport. Both surfaces here compare
    the `Wire` to the envelope the operator was actually shown.

**The `do_not_use` filter, and what it drops (G4-overlay: a tagged
transaction is excluded from "every S4 envelope/export").** For an excluded
fingerprint it drops, by `item_id`, every canonical row of that transaction,
every overlay tag on it — the `do_not_use` tag record included, since
syncing that would still name the fingerprint it excludes — **and the
`transfers` `pair` record either of whose legs is the excluded one.** The
builder kept transfer pairs, reasoning that a pair is a reference to two of
the household's own accounts rather than the excluded transaction's data.
That reading does not survive looking at the record: a pair is keyed
`(transfers, "pair", <fp_out>)` and its value names `counterpart`, so a pair
whose out-leg is excluded carries the excluded transaction's own content
hash as its `item_id`, and one whose in-leg is excluded carries it in
`counterpart`. Either way the excluded row's existence — and the fingerprint
that identifies it against the household's own books — crosses by reference.
"Excluded from every envelope" is read as excluding the reference too; a
pair with one excluded leg is dropped whole, because half a transfer is not
a fact about the other account, and fail-closed is the rule when the two
readings disagree (I-11). The counterpart's *own* rows are untouched: only
the pair record goes.

~~**A `pair`'s value is structured, and the fleet's `value` column is
text.** `homestead.keep.fleet_cli._validate_rows` refuses — by name, and the
*whole* envelope with it (I-11) — any row whose `value` is not a string, and
a `transfers` `pair` is served as a `dict` (it is `L2`, so `Served.value` is
the mapping). So an envelope whose scope names `transfers` composes and
drops to a file here and is then refused at `homestead-fleet ingest`. That
is the engine's own contract to settle (a `TEXT` column versus a structured
served value) and not a module's to paper over, so it is pinned by
`tests/test_sync.py::test_the_fleet_refuses_a_structured_pair_value_by_name`
rather than worked around: the refusal is loud, at the fleet end, before a
single row is written, and it is the honest state of the seam today.~~
(X7-drift correction, 2026-09-11: settled. The E7b audit kept the fleet's
`value` column `TEXT` rather than moving to `JSONB` — a mapping now crosses
as canonical JSON text, distinguished from a legacy plain-text row by a new
`value_format` column (`raw` before this change, `json` after), shipped in
engine 0.13.0. This package's own follow-up, `G7b-floor-0.13`, has landed
with it: `pyproject.toml`'s floor is `homestead-affairs>=0.13.0`, and the
pin above is now
`tests/test_sync.py::test_the_fleet_accepts_a_structured_pair_value`, with
`test_a_transfer_pair_crosses_end_to_end_as_a_structured_value` carrying a
pair the whole way. `tests/test_docs_drift.py` holds this paragraph's floor
to the one `pyproject.toml` declares, so a later raise cannot leave this
sentence behind.)

No `.payload` reach anywhere (I-16): every row here came out of
`compose()`, itself built from `serve()`'s `Served.value` alone, and the
filter reads `item_id`s off a record's `ref`, never its content.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
from pathlib import Path
from types import ModuleType
from typing import Iterable, Mapping

from homestead.keep import paths
from homestead.keep.egress import Wire
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

from homestead_ledger import accounts, overlay, packs, registry, transfers
from homestead_ledger.store import Canonical, Sidecar

__all__ = [
    "SyncScope", "Envelope", "Receipt", "Confirm", "Wire",
    "UnnamedScope", "TamperedEnvelope", "AlreadyDelivered",
    "NumberNeverCrosses", "NothingToSync",
    "default_drop_dir",
    "known_matters", "scope_from", "preview", "resolve_destination",
    "destination_preview", "send",
    "wire_matches",
]

#: The bank-issued number's field name (`packs/accounts.py`, under
#: `accounts.MATTER`) — refused at any rung (I-13/I-43).
_NUMBER_FIELD = "number"

#: The canonical table's name, as the literal rather than the engine's
#: `CANONICAL` constant: this package's chokepoint scan refuses any module
#: but `books.py` naming that constant at all ("mirror, not judge" made
#: structural), so the one place the two spellings could drift is pinned by
#: `tests/test_sync.py::test_the_canonical_table_literal_is_the_engines_own`.
_CANONICAL = "canonical"


class NumberNeverCrosses(ValueError):
    """A row naming `accounts.py`'s `number` field survived `compose()`,
    whatever rung it currently reports — the belt behind the engine's own
    ceiling drop (I-13), for the day a corrupted or monkeypatched rung
    table lets one past it. A `ValueError`, the same family every other
    scope/compose refusal here raises."""


class NothingToSync(UnnamedScope):
    """A scope that composed **no rows**. Every name in it was registered,
    so `scope_from` had nothing to refuse, and yet nothing survived: an
    `--types` that matches no item type on file, a matter with no records
    yet, a ceiling below everything the scope holds.

    Refused rather than delivered, because a zero-row envelope is still a
    *delivery*: it writes a file (or dials), spends the envelope id, writes
    an `IntegrityLog` row and a visible line, and tells the operator their
    sync went through. "Nothing to sync" and "synced nothing" must not read
    the same in a log whose whole job is to say what left (I-11, I-38). An
    `UnnamedScope`, so a caller already handling the scope refusals catches
    this one too."""


def _sidecar_matters(package: ModuleType = packs) -> frozenset[str]:
    """Every matter name a pack under `package` declares — discovered, not
    listed (I-23).

    A sidecar pack declares `MATTER` where an account pack declares
    `ACCOUNT` and an obligation pack declares `OBLIGATION`, so this is
    `registry._discover_packs`'s own scan pointed at the third attribute.
    Kept discovering rather than hand-written (the first version of this
    module named `accounts`/`overlay`/`transfers`/`budget` in a tuple) for
    BUG-6's reason: a pack authored and left out of the list is a matter
    the household holds that `sync` will refuse to name, and nobody finds
    out until they try to sync it. Pure in `package`, so the discovery can
    be fired against a planted pack in a test rather than only asserted
    about."""
    found: set[str] = set()
    for info in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}."):
        module = importlib.import_module(info.name)
        name = getattr(module, "MATTER", None)
        if isinstance(name, str) and name:
            found.add(name)
    return frozenset(found)


def known_matters(sidecar: Sidecar) -> tuple[str, ...]:
    """Every matter name `scope_from` accepts: each registered account
    instance's own label (the canonical matter its transactions are filed
    under), every obligation kind the obligation registry enumerates, and
    every sidecar matter a pack declares (`accounts`, `overlay`,
    `transfers`, `budget`, and whatever a later pack adds). Read off the
    registry and the packs, never a list kept here (I-23). No `"all"`
    (I-40)."""
    return tuple(sorted(
        set(accounts.instances(sidecar))
        | set(registry.all_obligations())
        | set(_sidecar_matters())
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
    (`UnnamedScope`), reused rather than re-decided here.

    `item_types` is *not* held against a list — there is no registry of
    item types, and inventing one here would be the hand-kept enumeration
    I-23 forbids. A type nobody has a record under is caught where it shows
    itself: `preview` refuses the empty envelope it composes
    (`NothingToSync`)."""
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

    `excluded` maps a matter to the `item_id`s that never leave under it —
    a per-matter map rather than one set plus a rule, because the ids differ
    by matter: under an account label or `overlay` they are the excluded
    transactions' own fingerprints, and under `transfers` they are the keys
    of the pair records either of whose legs is excluded. A matter with no
    entry passes through untouched.

    Every other `Reader` method is delegated unchanged, so `compose()` (and
    anything else handed this) sees a complete reader rather than an object
    that answers one question and raises `AttributeError` on the next. The
    delegations are written out rather than done with `getattr`/`__getattr__`
    — explicit, and nothing here reads a record by computed name."""

    def __init__(self, inner: Reader, *, excluded: Mapping[str, frozenset[str]]) -> None:
        self._inner = inner
        self._excluded = excluded

    def records(self, matter: str) -> list[tuple[tuple[str, str, str], Classified]]:
        rows = self._inner.records(matter)
        drop = self._excluded.get(matter)
        if not drop:
            return rows
        return [(ref, classified) for ref, classified in rows if ref[2] not in drop]

    def get(self, matter: str, item_type: str, item_id: str) -> Classified:
        return self._inner.get(matter, item_type, item_id)

    def has(self, matter: str, item_type: str, item_id: str) -> bool:
        return self._inner.has(matter, item_type, item_id)

    def advise(self, matter: str, item_type: str, item_id: str) -> tuple:
        return self._inner.advise(matter, item_type, item_id)

    def deadlines(self, matter: str) -> list:
        return self._inner.deadlines(matter)


def _excluded_pair_keys(store: Sidecar, excluded: frozenset[str]) -> frozenset[str]:
    """The `transfers` `pair` records that name an excluded fingerprint —
    by their own `item_id`, which is the outgoing leg's.

    An excluded fingerprint is itself a key when it is the outgoing leg (or
    when a *retired* pairing was once keyed by it — a retired record names
    no counterpart, but it still names the fingerprint it is keyed by), and
    `transfers.counterpart_of` gives the key when the excluded leg is the
    incoming one. Both are added; a fingerprint that turns out not to key a
    pair record simply matches nothing."""
    keys = set(excluded)
    for fingerprint in excluded & transfers.paired_fingerprints(store):
        counterpart = transfers.counterpart_of(store, fingerprint)
        if counterpart is not None:
            keys.add(counterpart)
    return frozenset(keys)


def _exclusions(store: Sidecar) -> dict[str, frozenset[str]]:
    """Which `item_id`s never leave, per matter — see `_ExcludingReader`."""
    excluded = overlay.excluded_fingerprints(store)
    if not excluded:
        return {}
    by_matter: dict[str, frozenset[str]] = {
        matter: excluded for matter in (*accounts.instances(store), overlay.MATTER)
    }
    by_matter[transfers.MATTER] = _excluded_pair_keys(store, excluded)
    return by_matter


def _refuse_a_leaked_number(envelope: Envelope) -> None:
    leaked = [row for row in envelope.rows if row.get("item_type") == _NUMBER_FIELD]
    if leaked:
        raise NumberNeverCrosses(
            f"{len(leaked)} row(s) named accounts.py's number field survived "
            "compose() — refused rather than handed back, whatever rung the "
            "ceiling check currently reports for it (I-13)"
        )


def _refuse_unknown_item_types(readers: Mapping[str, Reader], scope: SyncScope) -> None:
    """An `item_types` entry that names nothing the scope's own matters hold
    — refused by name, before `compose()` freezes an envelope of nothing.

    Read off the record, not off a list: there is no registry of item types
    to hold a name against (a pack's `FIELDS` is the item types it
    *declares*, and modules legitimately write item types a schema does not
    enumerate), so inventing one here would be the hand-kept enumeration
    I-23 forbids and would refuse honest names. What the household actually
    has on file under the matters named cannot be wrong about itself.

    Only runs when the operator narrowed by type: `item_types is None` is
    "every item type", which can name nothing wrong. Skipping it then also
    keeps the ordinary sync to one pass over the records."""
    if scope.item_types is None:
        return
    on_file: set[str] = set()
    for table in scope.tables:
        for matter in scope.matters:
            on_file |= {ref[1] for ref, _ in readers[table].records(matter)}
    unknown = sorted(set(scope.item_types) - on_file)
    if unknown:
        raise UnnamedScope(
            f"unknown item type(s) {unknown} — the matters named "
            f"({list(scope.matters)}) hold {sorted(on_file)}. Refused by "
            "name rather than composed into an envelope of nothing: a typo "
            "in --types matches no row, and a sync of no rows is still a "
            "delivery (I-40)"
        )


def _refuse_an_empty_envelope(envelope: Envelope, scope: SyncScope) -> None:
    if envelope.count == 0:
        raise NothingToSync(
            "nothing to sync: matters "
            f"{list(scope.matters)}, item types "
            f"{list(scope.item_types) if scope.item_types is not None else 'any'}, "
            f"tables {list(scope.tables)} at ceiling {scope.ceiling.value} "
            "matched no record on file — refused rather than delivered as an "
            "envelope of nothing (I-38: a delivery is ledgered, and an empty "
            "one would read as a sync that happened)"
        )


def preview(
    scope: SyncScope, *, sidecar: Sidecar | None = None, canonical: Canonical | None = None,
) -> Envelope:
    """Compose `scope` into an `Envelope` through the engine's own
    `compose()`, with this module's filter applied at the reader seam.
    The returned envelope's `envelope_id` covers exactly the rows that
    survived — nothing is dropped or added after the fact.

    Refuses (nothing is written or ledgered either way — this composes and
    returns, it never delivers): `NumberNeverCrosses` if a row naming
    `accounts.number` survived, `NothingToSync` if no row did."""
    store = sidecar if sidecar is not None else Sidecar()
    canon = canonical if canonical is not None else Canonical()
    excluded = _exclusions(store)
    readers: Mapping[str, Reader] = {
        SIDECAR: _ExcludingReader(store, excluded=excluded),
        _CANONICAL: _ExcludingReader(canon, excluded=excluded),
    }
    _refuse_unknown_item_types(readers, scope)
    envelope = _engine_compose(readers, scope)
    _refuse_a_leaked_number(envelope)
    _refuse_an_empty_envelope(envelope, scope)
    return envelope


def wire_matches(envelope: Envelope, wire: Wire) -> bool:
    """Whether `wire` is the delivery of exactly `envelope`.

    What a confirm exists to ask. The engine hands a confirm the `Wire` it
    is about to hand the transport — the shown thing and the sent thing are
    one object — but only if the confirm actually *reads* it: a callback
    that returns `True` unconditionally is an ambient permission wearing a
    confirm's signature, and it would approve any envelope that reached the
    transport, including one composed after the operator looked.

    The file leg's `Wire` carries the target path and the byte count (the
    engine keeps rows off it: the content was composed and shown before
    `deliver` was called), so both are checked — the file is named by
    `envelope_id` and the size is this envelope's own frozen bytes. The URL
    leg's `Wire` carries the whole serialized envelope, so it is re-read
    through `Envelope.from_bytes` (which re-verifies the id against the
    contents, I-11) and compared as **bytes**, not as an id."""
    if wire.method == "FILE":
        return (
            Path(wire.url).name == f"{envelope.envelope_id}.json"
            and wire.body == f"{len(envelope.to_bytes())} bytes"
        )
    try:
        offered = Envelope.from_bytes(wire.body.encode("utf-8"))
    except (TamperedEnvelope, UnicodeEncodeError):
        return False
    return offered.to_bytes() == envelope.to_bytes()


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


def resolve_destination(*, url: str | None = None) -> tuple[str | None, Path | None]:
    """Where a sync would go, as the `(url, drop_dir)` pair `send()` takes:
    an explicit `url` wins, then `HOMESTEAD_FLEET_URL`, then the one line in
    `home()/fleet.url`, then a file drop under `default_drop_dir()`.

    **Resolved once, by the caller, and carried.** A surface that shows a
    destination at preview and lets `send()` resolve again at send time is
    showing one thing and doing another: a `fleet.url` file written (or the
    environment variable exported) between the two turns a previewed file
    drop into a network POST that nobody was asked about — the L5-sync audit
    found exactly that on the law side, 2026-09-11. Both surfaces here
    resolve here, once, and hand the answer to `send()` unchanged; the
    confirm then holds the `Wire` against the envelope (`wire_matches`), so
    a destination that changed underneath is visible in the `Wire` as well.
    Read-only: dials nothing, writes nothing, creates no directory."""
    if url is not None:
        return url, None
    found = _destination_url()
    if found is not None:
        return found, None
    return None, default_drop_dir()


def destination_preview(*, url: str | None = None) -> str:
    """`resolve_destination` as the one string a preview shows."""
    resolved_url, drop_dir = resolve_destination(url=url)
    return resolved_url if resolved_url is not None else str(drop_dir)


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
    `deliver()` — nothing is written and nothing is ledgered.

    `confirm` is shown the `Wire` and should hold it against `envelope`
    (`wire_matches`) before it says yes; both surfaces in this package do."""
    if url is None and drop_dir is None:
        url, drop_dir = resolve_destination()
    return _engine_deliver(envelope, confirm=confirm, url=url, drop_dir=drop_dir)
