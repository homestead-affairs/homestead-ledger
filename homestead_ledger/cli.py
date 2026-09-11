"""CLI commands for homestead-ledger — real data, in the household root.

The household's own commands need only the engine:

  obligation   — add / list / show a recurring obligation (rent, insurance…)
  transaction  — add one transaction to the books, or list the account
  queue        — what's due (obligation due dates)
  ui           — the browser UI: entry forms, intake, queue, subscriptions

The Nestor-backed commands need the optional ``entity`` extra and say so in
one line when it is missing:

  resolve   — entity resolution for the merchant domain
  reconcile — numeric reconciliation for the amount domain
  verify    — check the Nestor ledger chain

``put`` is retired: one field under a random id in the wrong matter was a
record the queue never found. A bank-statement CSV still comes in through
``python -m homestead_ledger --import``. All commands operate on the household
root, not a throwaway.
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


def _needs_nestor() -> bool:
    """True when the Nestor-backed command can run; otherwise says why not."""
    if nestor_seam.available():
        return True
    print(f"  {nestor_seam.NOT_INSTALLED}", file=sys.stderr)
    return False


def _flag(args: list[str], name: str) -> tuple[list[str], str | None]:
    """Pull ``--name value`` out of ``args``; return the rest and the value."""
    rest: list[str] = []
    value: str | None = None
    i = 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            value = args[i + 1]
            i += 2
        else:
            rest.append(args[i])
            i += 1
    return rest, value


def _cmd_resolve(argv: list[str]) -> int:
    """resolve <surface> — resolve a merchant name."""
    if len(argv) < 2:
        print("usage: homestead-ledger resolve <surface>", file=sys.stderr)
        return 2
    if not _needs_nestor():
        return 1
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
    if not _needs_nestor():
        return 1
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


_OBLIGATION_USAGE = """\
usage: homestead-ledger obligation add <id> <payee> <amount> <due-date> <cadence> [--replace]
       homestead-ledger obligation list
       homestead-ledger obligation show <id>
  e.g.: homestead-ledger obligation add rent "Sunrise Properties LLC" 1450.00 2026-10-01 monthly
"""


def _cmd_obligation(argv: list[str]) -> int:
    """obligation <add|list|show> — the household's recurring obligations."""
    from homestead.keep.dates import UnparseableDate
    from homestead.keep.store import InvalidKey, RecordExists

    from homestead_ledger import obligations
    from homestead_ledger.store import Sidecar

    args = argv[1:]
    if not args:
        print(_OBLIGATION_USAGE, end="", file=sys.stderr)
        return 2
    sub, rest = args[0], args[1:]
    _boot()
    sidecar = Sidecar()

    if sub == "add":
        replace = "--replace" in rest
        rest = [a for a in rest if a != "--replace"]
        if len(rest) < 5:
            print(_OBLIGATION_USAGE, end="", file=sys.stderr)
            return 2
        item_id, name, amount, due_date, cadence = rest[:5]
        try:
            ref, replaced = obligations.add_obligation(
                sidecar, item_id=item_id, name=name, amount=amount, due_date=due_date,
                cadence=cadence, replace=replace,
            )
        except (ValueError, UnparseableDate, InvalidKey, RecordExists) as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        print(f"  stored: {obligations.KIND}/{ref[2]}")
        print("  payee L3 · amount L4 · due date L2 · cadence L2")
        if replaced is not None:
            print("  (replaced the previous obligation under this id)")
        if nestor_seam.available():
            try:
                resolver = nestor_seam.resolver_for("merchant", get_store())
                resolver.propose(name, name, reason="entered as payee")
                print(f"  proposed to merchant resolver: {name}")
            except Exception:
                pass
        return 0

    if sub == "list":
        found = obligations.rows(sidecar)
        if not found:
            print("  no obligations on file — `homestead-ledger obligation add <id> <payee> <amount> <due-date> <cadence>`")
            return 0
        print(f"  {len(found)} obligation(s):")
        for row in found:
            print(f"  [{row.rung.value}]  {row.item_id}: {row.name}  ·  due {row.due_date}  ·  {row.cadence}  ·  {row.amount}")
        return 0

    if sub == "show":
        if not rest:
            print(_OBLIGATION_USAGE, end="", file=sys.stderr)
            return 2
        fields = obligations.detail(sidecar, rest[0])
        if not fields:
            print(f"  {rest[0]}: no such obligation", file=sys.stderr)
            return 1
        print(f"  {obligations.KIND}/{rest[0]}")
        for field in ("name", "amount", "due_date", "cadence"):
            if field in fields:
                rung, value = fields[field]
                shown = value if value is not None else "(sealed)"
                print(f"  [{rung}]  {field.replace('_', ' ')}: {shown}")
        return 0

    print(f"unknown subcommand {sub!r} — one of: add, list, show", file=sys.stderr)
    return 2


_TRANSACTION_USAGE = """\
usage: homestead-ledger transaction add <date> <amount> <description> --account-number N [--account NAME]
       homestead-ledger transaction list [--account NAME]
  e.g.: homestead-ledger transaction add 2026-08-01 -84.23 "Whole Foods Market" --account-number 9821
  (a whole statement: python -m homestead_ledger --import FILE.csv --account-number N)
"""


def _cmd_transaction(argv: list[str]) -> int:
    """transaction <add|list> — one transaction into the books, or the account listed."""
    from homestead.keep.dates import UnparseableDate, parse_deadline
    from homestead.keep.store import RecordExists

    from homestead_ledger import books
    from homestead_ledger.app.window import Window
    from homestead_ledger.packs import checking
    from homestead_ledger.store import Canonical

    args = argv[1:]
    if not args:
        print(_TRANSACTION_USAGE, end="", file=sys.stderr)
        return 2
    sub, rest = args[0], args[1:]
    rest, account = _flag(rest, "--account")
    account = account or checking.ACCOUNT
    _boot()

    if sub == "add":
        rest, account_number = _flag(rest, "--account-number")
        if len(rest) < 3 or not account_number:
            print(_TRANSACTION_USAGE, end="", file=sys.stderr)
            return 2
        date, amount, description = rest[0], rest[1], " ".join(rest[2:])
        try:
            date = parse_deadline(date).iso
            amount = f"{float(amount.replace(',', '').replace('$', '')):.2f}"
        except UnparseableDate as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        except ValueError:
            print(f"  refused: amount {amount!r} is not a number (e.g. -84.23)", file=sys.stderr)
            return 1
        if not description.strip():
            print("  refused: a transaction names its payee or description", file=sys.stderr)
            return 1
        txn = books.Transaction(
            account=account, date=date, amount=amount,
            description=description.strip(), account_number=account_number.strip(),
        )
        try:
            item_id = books.import_transaction(txn)
        except RecordExists as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        print(f"  on the books: {account}/{item_id[:12]}…")
        print("  date L2 · description L3 · amount L4 · account number L5")
        return 0

    if sub == "list":
        window = Window()
        rows = window.open_list(Canonical().records(account))
        if not rows:
            print(f"  {account}: nothing on the books — `homestead-ledger transaction add …` or `--import`")
            return 0
        print(f"  {account}: {len(rows)} row(s) (each transaction is a date, a description and an amount)")
        for row in rows:
            _, field, item_id = row.ref
            print(f"  [{row.rung.value}]  {item_id[:12]}  {field}: {row.text}")
        return 0

    print(f"unknown subcommand {sub!r} — one of: add, list", file=sys.stderr)
    return 2


def _cmd_put(argv: list[str]) -> int:
    """put — retired; one field under a random id was a record nothing could find."""
    print("  `put` is retired — enter an obligation or a transaction whole:", file=sys.stderr)
    print(_OBLIGATION_USAGE, end="", file=sys.stderr)
    print(_TRANSACTION_USAGE, end="", file=sys.stderr)
    return 1


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
        print(f"  {item.rung.value}  {item.ref[2]}: {item.shown}{flag}")
    return 0


def _cmd_verify(argv: list[str]) -> int:
    """verify — check the Nestor ledger chain."""
    if not _needs_nestor():
        return 1
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
    "obligation":  (_cmd_obligation,  "obligation <add|list|show> — recurring obligations"),
    "transaction": (_cmd_transaction, "transaction <add|list> — the books"),
    "resolve":     (_cmd_resolve,     "resolve <surface> — merchant entity resolution"),
    "reconcile":   (_cmd_reconcile,   "reconcile <baseline> <observed> — compare amounts"),
    "put":         (_cmd_put,         "put — retired; use obligation add / transaction add"),
    "queue":       (_cmd_queue,       "queue — show what's due"),
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
