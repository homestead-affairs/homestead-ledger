"""CLI commands for homestead-ledger — real data, wired through Nestor.

Each command maps to a Nestor capability or a ledger operation:

  resolve   — entity resolution for merchant domain
  reconcile — numeric reconciliation for amount domain
  put       — store a field value (checking or obligation)
  queue     — what's due (obligation deadlines)
  verify    — check the Nestor ledger chain
  ui        — launch the browser intake UI
  import    — import a bank-statement CSV (delegates to importer)

All commands operate on the household root, not a throwaway.
"""
from __future__ import annotations

import sys

from homestead.keep import paths

from homestead_ledger import nestor_seam
from homestead_ledger.nestor_store import get_store

__all__ = ["run_cli", "COMMANDS"]


def _boot() -> None:
    """Bind Nestor's seam and ensure dirs exist."""
    root = paths.home()
    root.mkdir(parents=True, exist_ok=True)
    (root / "keep").mkdir(parents=True, exist_ok=True)
    nestor_seam.bind(root)


def _cmd_resolve(argv: list[str]) -> int:
    """resolve <surface> — resolve a merchant name."""
    if len(argv) < 2:
        print("usage: homestead-ledger resolve <surface>", file=sys.stderr)
        return 2
    _boot()
    surface = " ".join(argv[1:])
    store = get_store()
    resolver = nestor_seam.resolver_for("merchant", store)
    result = resolver.resolve(surface)
    print(f"surface:    {surface}")
    if result.get("sealed"):
        print(f"canonical:  {result['canonical']}  (sealed)")
    elif result.get("provenance", {}).get("suggestion"):
        print(f"suggestion: {result['provenance']['suggestion']}  (draft)")
    else:
        print("no match")
    print(f"confidence: {result.get('confidence', 0):.2f}")
    return 0


def _cmd_reconcile(argv: list[str]) -> int:
    """reconcile <baseline> <observed> — compare two amounts."""
    if len(argv) < 3:
        print("usage: homestead-ledger reconcile <baseline> <observed>", file=sys.stderr)
        return 2
    _boot()
    try:
        baseline = float(argv[1])
        observed = float(argv[2])
    except ValueError:
        print("amounts must be numeric", file=sys.stderr)
        return 1
    store = get_store()
    reconciler = nestor_seam.reconciler_for("amount", store)
    result = reconciler.check(baseline, observed)
    print(f"baseline: {baseline}")
    print(f"observed: {observed}")
    print(f"within tolerance: {result.get('ok', result.get('within_tolerance', False))}")
    if "difference" in result:
        print(f"difference: {result['difference']}")
    return 0


def _cmd_put(argv: list[str]) -> int:
    """put <field> <value> — store a ledger field value."""
    if len(argv) < 3:
        print("usage: homestead-ledger put <field> <value>", file=sys.stderr)
        return 2
    from homestead.keep.rungs import Classified, Rung
    from homestead_ledger.packs.checking import FIELDS as CHECK_FIELDS
    from homestead_ledger.packs.obligations import FIELDS as OBL_FIELDS
    from homestead_ledger.store import Sidecar

    _boot()
    field = argv[1]
    value = " ".join(argv[2:])
    all_fields = {**CHECK_FIELDS, **OBL_FIELDS}
    if field not in all_fields:
        print(f"unknown field: {field}", file=sys.stderr)
        print(f"known fields: {', '.join(sorted(all_fields))}", file=sys.stderr)
        return 1
    rung = all_fields[field]
    item = Classified(rung, value, None)
    item_id = f"cli-{field}-{hash(value) & 0xFFFFFFFF:08x}"
    sidecar = Sidecar()
    account = "checking"
    sidecar.put(account, field, item_id, item, overwrite=True)
    print(f"stored {field}={value} at {rung.value}")
    return 0


def _cmd_queue(argv: list[str]) -> int:
    """queue — show what's due."""
    import datetime as dt

    from homestead_ledger import queue as queue_mod
    from homestead_ledger.store import Sidecar

    _boot()
    today = dt.date.today().isoformat()
    sidecar = Sidecar()
    items = queue_mod.queue(sidecar, today=today)
    if not items:
        print("nothing due")
        return 0
    for item in items:
        flag = ""
        if item.gap:
            flag = "  [date unreadable]"
        elif item.overdue:
            flag = f"  [{abs(item.days_until)}d overdue]"
        elif item.days_until is not None and item.days_until <= 14:
            flag = f"  [in {item.days_until}d]"
        print(f"  {item.rung.value}  {item.shown}{flag}")
    return 0


def _cmd_verify(argv: list[str]) -> int:
    """verify — check the Nestor ledger chain."""
    _boot()
    ok = nestor_seam.verify_ledger()
    if ok:
        print("ledger chain: ok")
    else:
        print("ledger chain: BROKEN", file=sys.stderr)
    return 0 if ok else 1


def _cmd_ui(argv: list[str]) -> int:
    """ui [--port N] — launch the browser intake UI."""
    from homestead_ledger.server import serve
    port = 8385
    if "--port" in argv:
        try:
            idx = argv.index("--port")
            port = int(argv[idx + 1])
        except (IndexError, ValueError):
            print("--port requires a number", file=sys.stderr)
            return 2
    serve(port=port)
    return 0


COMMANDS: dict[str, tuple] = {
    "resolve":   (_cmd_resolve,   "resolve <surface> — merchant entity resolution"),
    "reconcile": (_cmd_reconcile, "reconcile <baseline> <observed> — compare amounts"),
    "put":       (_cmd_put,       "put <field> <value> — store a ledger field"),
    "queue":     (_cmd_queue,     "queue — show what's due"),
    "verify":    (_cmd_verify,    "verify — check ledger chain integrity"),
    "ui":        (_cmd_ui,        "ui [--port N] — intake UI in the browser"),
}


def run_cli(argv: list[str]) -> int:
    """Dispatch a CLI command."""
    if not argv:
        return 2
    name = argv[0]
    if name not in COMMANDS:
        print(f"unknown command: {name}", file=sys.stderr)
        for cmd, (_, desc) in sorted(COMMANDS.items()):
            print(f"  {desc}")
        return 2
    handler, _ = COMMANDS[name]
    return handler(argv)
