"""CLI commands for homestead-ledger — real data, in the household root.

The household's own commands need only the engine:

  obligation   — add / list / show / paid a recurring obligation (rent, insurance…)
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
from homestead_ledger.cadence import CADENCES
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


_OBLIGATION_USAGE = f"""\
usage: homestead-ledger obligation add <id> <payee> <amount> <due-date> <cadence> [--replace]
       homestead-ledger obligation list
       homestead-ledger obligation show <id>
       homestead-ledger obligation paid <id> --account <label> --fingerprint <fp> [--on YYYY-MM-DD] [--replace]
  e.g.: homestead-ledger obligation add rent "Sunrise Properties LLC" 1450.00 2026-10-01 monthly
        homestead-ledger obligation paid rent --account checking --fingerprint a1b2c3
  cadence: one of {", ".join(CADENCES)}
"""


def _cmd_obligation(argv: list[str]) -> int:
    """obligation <add|list|show|paid> — the household's recurring obligations."""
    import datetime as dt

    from homestead.keep.dates import UnparseableDate
    from homestead.keep.store import InvalidKey, RecordExists

    from homestead_ledger import obligations
    from homestead_ledger.cadence import UnknownCadence
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
        found = obligations.rows(sidecar, today=dt.date.today().isoformat())
        if not found:
            print("  no obligations on file — `homestead-ledger obligation add <id> <payee> <amount> <due-date> <cadence>`")
            return 0
        print(f"  {len(found)} obligation(s):")
        for row in found:
            mark = "  [incomplete — a field is not on file]" if row.gap else ""
            # `row.paid_on` is a reference — the date the paid-by record is
            # keyed under — never the account or fingerprint it also carries
            # (I-15). The ✓ is gated on `paid_current`, not on there being a
            # payment at all: a monthly bill paid in July and due again in
            # August has a payment on file and an *open* period, and a row
            # that ticks it says the household has paid when it has not.
            # Out of period, the date still reads — as "last paid", a fact —
            # but without the mark. `resolved` (a `once` obligation already
            # paid) is its own flag rather than folded into `paid`, since a
            # resolved obligation still lists here.
            if row.paid_current:
                paid = f"  paid ✓ {row.paid_on}"
            elif row.paid_on:
                paid = f"  last paid {row.paid_on}"
            else:
                paid = ""
            if row.resolved:
                paid += "  [resolved]"
            print(f"  [{row.rung.value}]  {row.item_id}: {row.name}  ·  due {row.due_date}  ·  {row.cadence}  ·  {row.amount}{mark}{paid}")
        return 0

    if sub == "paid":
        if not rest:
            print(_OBLIGATION_USAGE, end="", file=sys.stderr)
            return 2
        item_id, rest = rest[0], rest[1:]
        replace = "--replace" in rest
        rest = [a for a in rest if a != "--replace"]
        rest, account = _flag(rest, "--account")
        rest, fingerprint = _flag(rest, "--fingerprint")
        rest, on = _flag(rest, "--on")
        if not account or not fingerprint:
            print(_OBLIGATION_USAGE, end="", file=sys.stderr)
            return 2
        paid_on = on or dt.date.today().isoformat()
        try:
            paid_ref, rolled = obligations.mark_paid(
                sidecar, item_id, account=account, fingerprint=fingerprint,
                paid_on=paid_on, replace=replace,
            )
        except (ValueError, UnparseableDate, InvalidKey, RecordExists,
                UnknownCadence, KeyError) as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        print(f"  stored: {obligations.KIND}/{paid_ref[2]}")
        if not rolled.rolled:
            print(
                f"  recorded, schedule unchanged (still due {rolled.old_due}) — "
                "a later payment is already on file, so this one closes a "
                "period that is already closed"
            )
        elif rolled.new_due is not None:
            print(f"  due date rolled forward: {rolled.old_due} -> {rolled.new_due}")
        else:
            print(f"  resolved — {item_id} was a one-time obligation, now paid ({rolled.old_due})")
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

    print(f"unknown subcommand {sub!r} — one of: add, list, show, paid", file=sys.stderr)
    return 2


_TRANSACTION_USAGE = """\
usage: homestead-ledger transaction add <date> <amount> <description> --account-number N [--account NAME]
       homestead-ledger transaction list [--account NAME] [--gaps]
  e.g.: homestead-ledger transaction add 2026-08-01 -84.23 "Whole Foods Market" --account-number 9821
  (a whole statement: python -m homestead_ledger --import FILE.csv --account-number N [--bank NAME])
  --gaps lists rows whose stored date is not ISO (YYYY-MM-DD) — pre-existing
  rows from before fix: G2c-importer-dates will not dedup against a re-import
  in the new ISO form; there is no migration (v1 is synthetic-only)
"""


def _cmd_transaction(argv: list[str]) -> int:
    """transaction <add|list> — one transaction into the books, or the account listed."""
    from homestead.keep.dates import UnparseableDate, parse_deadline
    from homestead.keep.store import RecordExists

    from homestead_ledger import balance, books, money, registry
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
    gaps_only = "--gaps" in rest
    rest = [a for a in rest if a != "--gaps"]
    # `--gaps` narrows `list` and belongs to no other sub-command. Swallowing
    # it silently on `add` would let `transaction add … --gaps` write the row
    # anyway and report success, which is a flag that looks honoured and is
    # not — the shape a household reads as "it did what I asked".
    if gaps_only and sub != "list":
        print(
            f"  --gaps is only for `transaction list`, not `transaction {sub}`",
            file=sys.stderr,
        )
        return 2
    # I-23: the registry is the only enumeration. An unregistered `--account`
    # would otherwise grow a whole phantom account in the canonical books —
    # rows nothing that iterates `all_accounts()` (the queue, the subscription
    # pass, the window) would ever reach. Refused by name, never created.
    if account not in registry.all_accounts():
        print(
            f"  unknown account {account!r} — one of: "
            f"{', '.join(registry.all_accounts())}",
            file=sys.stderr,
        )
        return 2
    _boot()

    if sub == "add":
        rest, account_number = _flag(rest, "--account-number")
        if len(rest) < 3 or not account_number:
            print(_TRANSACTION_USAGE, end="", file=sys.stderr)
            return 2
        date, amount, description = rest[0], rest[1], " ".join(rest[2:])
        try:
            date = parse_deadline(date).iso
            # `money.amount_text`, not `float()`: `float("nan")` and
            # `float("inf")` both succeed and land an amount in the books that
            # poisons every sum it joins. The refusal names the field and
            # never repeats the value (I-15 — an amount is L4).
            amount = money.amount_text(amount)
        except (UnparseableDate, ValueError) as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        if not description.strip():
            print("  refused: a transaction names its payee or description", file=sys.stderr)
            return 1
        txn = books.Transaction(
            account=account, kind=account, date=date, amount=amount,
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
        if gaps_only:
            # I-16: never `.payload` here — `row.text` is already what
            # `serve(S1_LIST)` handed back for this L2 field, so checking it
            # against `balance.is_iso_date` never reaches the record itself.
            rows = [
                row for row in rows
                if row.ref[1] == "date" and not balance.is_iso_date(row.text)
            ]
            if not rows:
                print(f"  {account}: no gaps — every stored date is ISO (YYYY-MM-DD)")
                return 0
            print(
                f"  {account}: {len(rows)} row(s) with a pre-ISO date — imported "
                "before fix: G2c-importer-dates; will not dedup against a "
                "re-import in the new ISO form (no migration, v1 is synthetic-only)"
            )
            for row in rows:
                _, field, item_id = row.ref
                print(f"  [{row.rung.value}]  {item_id[:12]}  {field}: {row.text}")
            return 0
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
    "obligation":  (_cmd_obligation,  "obligation <add|list|show|paid> — recurring obligations"),
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
