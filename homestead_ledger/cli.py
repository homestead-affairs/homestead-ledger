"""CLI commands for homestead-ledger — real data, in the household root.

The household's own commands need only the engine:

  account      — add / list / show a real account instance (bite 2b)
  obligation   — add / list / show / paid a recurring obligation (rent, insurance…)
  transaction  — add one transaction to the books, or list the account
  queue        — what's due (obligation due dates)
  schedules    — the household's liability schedule: show it, or export it
  sync         — send a consented scope of the books to the household's own fleet
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


#: The flags bite 2b retired from `transaction add` and `--import`: the
#: account number and the kind live on the account instance now. Kept as
#: data so the refusal and `__main__.py`'s own say the same thing.
_RETIRED_TRANSACTION_FLAGS = ("--account-number", "--kind")


def _stray_flags(rest: list[str]) -> list[str]:
    """Every ``--flag`` token still in ``rest`` after the known flags were
    pulled out by `_flag`.

    Worth refusing rather than ignoring, and on this sub-command worth more
    than that: `transaction add`'s description is *positional* — everything
    from the third argument on is joined into it — so an unconsumed flag is
    not dropped, it is **written into the books** as part of the payee.
    `transaction add … --account --account-number 4111…` stored the bank
    number in the row's L3 `description` and rendered it on `transaction
    list`, which is the one crossing I-43 and I-13 exist to stop. The same
    shape `--gaps` on `transaction add` is already refused for: a flag that
    looks honoured and is not.

    The cost is that a description token may not itself begin with ``--``;
    a payee name that does is not a thing a bank statement produces, and a
    refusal an operator can see beats a silent rewrite of what they typed.
    """
    return [token for token in rest if token.startswith("--")]


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


_ACCOUNT_USAGE = """\
usage: homestead-ledger account add <label> --kind KIND --number NUMBER
                                     [--institution NAME] [--opened DATE]
                                     [--balance-as-of AMOUNT] [--rate PCT]
                                     [--limit AMOUNT] [--payment-due-day DAY]
                                     [--min-payment AMOUNT] [--replace]
       homestead-ledger account list
       homestead-ledger account show <label>
  e.g.: homestead-ledger account add chk-main --kind checking --number 9821
  <label> is the household's own short name for one real account — never a
  registered kind name (checking, savings, credit_card, loan) and never the
  bank-issued number itself.
"""


def _cmd_account(argv: list[str]) -> int:
    """account <add|list|show> — the household's real accounts (bite 2b)."""
    from homestead.keep.dates import UnparseableDate
    from homestead.keep.store import InvalidKey, RecordExists

    from homestead_ledger import accounts
    from homestead_ledger.store import Sidecar

    args = argv[1:]
    if not args:
        print(_ACCOUNT_USAGE, end="", file=sys.stderr)
        return 2
    sub, rest = args[0], args[1:]
    _boot()
    sidecar = Sidecar()

    if sub == "add":
        replace = "--replace" in rest
        rest = [a for a in rest if a != "--replace"]
        rest, kind = _flag(rest, "--kind")
        rest, number = _flag(rest, "--number")
        rest, institution = _flag(rest, "--institution")
        rest, opened = _flag(rest, "--opened")
        rest, balance_as_of = _flag(rest, "--balance-as-of")
        rest, rate = _flag(rest, "--rate")
        rest, limit = _flag(rest, "--limit")
        rest, payment_due_day = _flag(rest, "--payment-due-day")
        rest, min_payment = _flag(rest, "--min-payment")
        if not rest or kind is None or number is None:
            print(_ACCOUNT_USAGE, end="", file=sys.stderr)
            return 2
        try:
            ref, replaced = accounts.add_account(
                sidecar, rest[0], kind=kind, number=number, institution=institution,
                opened=opened, balance_as_of=balance_as_of, rate=rate, limit=limit,
                payment_due_day=payment_due_day, min_payment=min_payment, replace=replace,
            )
        except (ValueError, UnparseableDate, InvalidKey, RecordExists) as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        print(f"  stored: {ref[0]}/{ref[2]}")
        print(
            "  kind L2 · institution L3 · number L5 (never shown) · opened L2 "
            "· balance/rate/limit/min-payment L4 · payment due day L2"
        )
        if replaced is not None:
            print("  (replaced the previous account under this label)")
        return 0

    if sub == "list":
        found = accounts.rows(sidecar)
        if not found:
            print("  no accounts on file — `homestead-ledger account add <label> --kind K --number N`")
            return 0
        print(f"  {len(found)} account(s):")
        for row in found:
            print(f"  [{row.rung.value}]  {row.label}: {row.kind}  ·  {row.institution}")
        return 0

    if sub == "show":
        if not rest:
            print(_ACCOUNT_USAGE, end="", file=sys.stderr)
            return 2
        label = rest[0]
        fields = accounts.detail(sidecar, label)
        if not fields:
            print(f"  {label}: no such account", file=sys.stderr)
            return 1
        print(f"  {accounts.MATTER}/{label}")
        for field in (
            "kind", "institution", "opened", "balance_as_of", "rate", "limit",
            "payment_due_day", "min_payment", "number",
        ):
            if field in fields:
                rung, value = fields[field]
                shown = value if value is not None else "(sealed)"
                print(f"  [{rung}]  {field.replace('_', ' ')}: {shown}")
        return 0

    print(f"unknown subcommand {sub!r} — one of: add, list, show", file=sys.stderr)
    return 2


_TRANSACTION_USAGE = """\
usage: homestead-ledger transaction add <date> <amount> <description> --account <label>
       homestead-ledger transaction list --account <label> [--gaps]
       homestead-ledger transaction tag <fingerprint> [--category C] [--note N]
                                        [--merchant M] [--do-not-use] [--replace]
       homestead-ledger transaction transfer <fp_out> <fp_in> [--replace]
       homestead-ledger transaction transfer --suggest
  e.g.: homestead-ledger transaction add 2026-08-01 -84.23 "Whole Foods Market" --account chk-main
        homestead-ledger transaction tag a1b2c3d4e5f6 --category groceries  (a prefix is enough)
  (a whole statement: python -m homestead_ledger --import FILE.csv --account <label>)
  <label> is a registered account instance — `account add` first, `account
  list` to see what's on file. The account number and kind live on the
  instance, not on the transaction.
  --gaps lists rows whose stored date is not ISO (YYYY-MM-DD) — pre-existing
  rows from before fix: G2c-importer-dates will not dedup against a re-import
  in the new ISO form; there is no migration (v1 is synthetic-only)
  `tag` names a fingerprint already on the books — the whole one, or the
  twelve characters `transaction list` prints (a prefix naming two rows is
  refused, never guessed). A category is a closed-shape word, raised
  automatically wherever it names a protected matter (medical, legal, …);
  --do-not-use excludes the transaction from recurring detection, budget
  envelopes and every export, and is set here, never cleared.
  transfer pairs an outgoing fingerprint with an incoming one — equal and
  opposite amounts, on two different accounts, within 5 days of each other —
  and excludes both from recurring detection and every household aggregate.
  <fp_out> is the outgoing leg (the account the money left); the other order
  is refused, not quietly swapped.
  --suggest proposes candidate pairs without writing anything; a candidate
  more than one row fits is listed once per candidate and marked ambiguous.
"""


def _cmd_transaction_tag(rest: list[str]) -> int:
    """transaction tag <fingerprint> [--category C] [--note N] [--merchant M]
    [--do-not-use] [--replace] — the household's own layer over one
    transaction, never a rewrite of the row itself."""
    from homestead.keep.store import RecordExists

    from homestead_ledger import overlay
    from homestead_ledger.store import Sidecar

    replace = "--replace" in rest
    do_not_use = "--do-not-use" in rest
    rest = [a for a in rest if a not in ("--replace", "--do-not-use")]
    rest, category = _flag(rest, "--category")
    rest, note = _flag(rest, "--note")
    rest, merchant = _flag(rest, "--merchant")
    stray = _stray_flags(rest)
    if stray or not rest:
        print(_TRANSACTION_USAGE, end="", file=sys.stderr)
        return 2
    fingerprint = rest[0]
    _boot()
    sidecar = Sidecar()
    try:
        written = overlay.tag(
            sidecar, fingerprint, category=category, note=note,
            confirmed_merchant=merchant, do_not_use=do_not_use or None,
            replace=replace,
        )
    except (ValueError, RecordExists) as exc:
        print(f"  refused: {exc}", file=sys.stderr)
        return 1
    if not written:
        print(
            "  nothing to tag — pass --category/--note/--merchant/--do-not-use",
            file=sys.stderr,
        )
        return 2
    # The *resolved* fingerprint, read back off a written ref — a prefix the
    # operator typed is not the key anything was written under.
    resolved = next(iter(written.values()))[0][2]
    print(f"  tagged: {overlay.MATTER}/{resolved[:12]}…  ({', '.join(sorted(written))})")
    return 0


_TRANSFER_USAGE = """\
usage: homestead-ledger transaction transfer <fp_out> <fp_in> [--replace]
       homestead-ledger transaction transfer --suggest
  <fp_out>/<fp_in> are full transaction fingerprints (`transaction list`
  shows the first 12 characters of each). <fp_out> is the outgoing leg — the
  account the money left — so the record says what actually happened; the
  other order is refused by name, never swapped for you.
  --replace retires every pairing either leg is already part of, then writes
  this one. --suggest takes no other argument.
"""


def _cmd_transaction_transfer(rest: list[str]) -> int:
    """transaction transfer <fp_out> <fp_in> [--replace] | --suggest."""
    from homestead.keep.store import RecordExists

    from homestead_ledger import transfers
    from homestead_ledger.store import Sidecar

    _boot()
    sidecar = Sidecar()
    if "--suggest" in rest:
        # `--suggest` proposes over the whole books; a fingerprint or a
        # `--replace` alongside it describes a write this branch does not do,
        # and accepting one would read as though it had been honoured.
        if len(rest) != 1:
            print(_TRANSFER_USAGE, end="", file=sys.stderr)
            return 2
        found = transfers.suggest(sidecar)
        if not found:
            print("  no candidate transfers found")
            return 0
        print(f"  {len(found)} candidate pair(s) — nothing written:")
        for fp_out, fp_in, ambiguous in found:
            mark = "  (ambiguous — more than one row fits; pick one)" if ambiguous else ""
            print(f"  {fp_out[:12]}…  ->  {fp_in[:12]}…{mark}")
        return 0

    replace = "--replace" in rest
    rest = [a for a in rest if a != "--replace"]
    if len(rest) != 2:
        print(_TRANSFER_USAGE, end="", file=sys.stderr)
        return 2
    fp_out, fp_in = rest
    try:
        ref, replaced = transfers.pair(sidecar, fp_out, fp_in, replace=replace)
    except (ValueError, RecordExists) as exc:
        print(f"  refused: {exc}", file=sys.stderr)
        return 1
    print(f"  paired: {ref[2][:12]}…  ->  {fp_in[:12]}…")
    if replaced is not None:
        print("  (replaced a previous pairing — either leg's old pair is retired)")
    return 0


def _cmd_transaction(argv: list[str]) -> int:
    """transaction <add|list|tag|transfer> — one transaction into the books,
    the account listed, the household's own layer over one transaction, or
    two transactions paired as a transfer."""
    from homestead.keep.dates import UnparseableDate, parse_deadline
    from homestead.keep.store import RecordExists

    from homestead_ledger import accounts, balance, books, money, overlay, transfers
    from homestead_ledger.app.window import Window
    from homestead_ledger.store import Canonical, Sidecar

    args = argv[1:]
    if not args:
        print(_TRANSACTION_USAGE, end="", file=sys.stderr)
        return 2
    sub, rest = args[0], args[1:]
    if sub == "tag":
        return _cmd_transaction_tag(rest)
    if sub == "transfer":
        # `transfer` names two fingerprints, not `--account <label>` — it
        # takes the branch before the account handling below ever looks for
        # one.
        return _cmd_transaction_transfer(rest)
    rest, account = _flag(rest, "--account")
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
    stray = _stray_flags(rest)
    if stray:
        retired = [flag for flag in stray if flag in _RETIRED_TRANSACTION_FLAGS]
        if retired:
            print(
                f"  {retired[0]} is retired — the account number and kind "
                "live on the account instance now (`account add <label> "
                "--kind K --number N`); pass --account <label> naming the "
                "instance instead",
                file=sys.stderr,
            )
        else:
            print(
                f"  unrecognized flag {stray[0]} for `transaction {sub}` — "
                "see the usage below (a description is positional, and an "
                "unrecognized flag would otherwise be written into it)",
                file=sys.stderr,
            )
            print(_TRANSACTION_USAGE, end="", file=sys.stderr)
        return 2
    if not account:
        print(_TRANSACTION_USAGE, end="", file=sys.stderr)
        return 2
    _boot()
    sidecar = Sidecar()
    # Bite 2b: a transaction is filed under a registered account *instance*
    # (a label), never a bare kind name. An unregistered label would grow a
    # whole phantom matter in the canonical books — rows nothing that
    # iterates `accounts.instances()` (the subscription pass, the window)
    # would ever reach. Refused by name, never created.
    if not accounts.label_exists(sidecar, account):
        print(f"  {accounts.unknown_label(account)}", file=sys.stderr)
        return 2

    if sub == "add":
        if len(rest) < 3:
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
        kind = accounts.kind_of(sidecar, account)
        txn = books.Transaction(
            account=account, kind=kind, date=date, amount=amount,
            description=description.strip(),
        )
        try:
            item_id = books.import_transaction(txn)
        except RecordExists as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        print(f"  on the books: {account}/{item_id[:12]}…")
        print("  date L2 · description L3 · amount L4")
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
        seen: list[str] = []
        for row in rows:
            _, field, item_id = row.ref
            if item_id not in seen:
                seen.append(item_id)
            other = transfers.other_label(sidecar, item_id)
            marker = f"  (transfer → {other})" if other else ""
            print(f"  [{row.rung.value}]  {item_id[:12]}  {field}: {row.text}{marker}")
        # Bite 4: the overlay, shown by reference — a category renders or
        # derives, a note (always L4) derives, `do_not_use` is a mark, never
        # a value read off the field. Only a tagged transaction gets a line;
        # an untagged one prints nothing new here.
        excluded = overlay.excluded_fingerprints(sidecar)
        for item_id in seen:
            tags = overlay.tags_of(sidecar, item_id)
            marks = [f"{field}: {text}" for field, text in tags.items()]
            if item_id in excluded:
                marks.append("do-not-use")
            if marks:
                print(f"  [{item_id[:12]}]  {' · '.join(marks)}")
        return 0

    print(f"unknown subcommand {sub!r} — one of: add, list, tag, transfer", file=sys.stderr)
    return 2


_BUDGET_USAGE = """\
usage: homestead-ledger budget set <category> <YYYY-MM> <amount> [--replace]
       homestead-ledger budget show [--month YYYY-MM]
  e.g.: homestead-ledger budget set groceries 2026-09 400.00
        homestead-ledger budget show --month 2026-09
  <category> is the same closed-shape word `transaction tag --category`
  takes. A limit never renders on `show` — only whether spending in a
  category this month is within it, over it, unset, or absent altogether;
  --month defaults to the current calendar month.
"""


def _cmd_budget(argv: list[str]) -> int:
    """budget <set|show> — a household's own per-category, per-month
    spending limit, and the derived state it reads through."""
    import datetime as dt

    from homestead.keep.store import RecordExists

    from homestead_ledger import budget
    from homestead_ledger.store import Canonical, Sidecar

    args = argv[1:]
    if not args:
        print(_BUDGET_USAGE, end="", file=sys.stderr)
        return 2
    sub, rest = args[0], args[1:]
    _boot()
    sidecar = Sidecar()

    if sub == "set":
        replace = "--replace" in rest
        rest = [a for a in rest if a != "--replace"]
        if len(rest) < 3:
            print(_BUDGET_USAGE, end="", file=sys.stderr)
            return 2
        category, month, amount = rest[0], rest[1], rest[2]
        try:
            ref, replaced = budget.set_limit(
                sidecar, category, month, amount, replace=replace,
            )
        except (ValueError, RecordExists) as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        print(f"  stored: {budget.MATTER}/{ref[2]}")
        print("  limit L4 — never shown again on `budget show`, only its state")
        if replaced is not None:
            print("  (replaced the previous limit for this category and month)")
        return 0

    if sub == "show":
        rest, month = _flag(rest, "--month")
        month = month or dt.date.today().strftime("%Y-%m")
        try:
            rows, gaps = budget.envelopes(Canonical(), sidecar, month)
        except ValueError as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        if not rows and not gaps.uncategorised and not gaps.undated:
            print(f"  {month}: nothing to show — no limits and no spending on file")
            return 0
        print(f"  {month}:")
        for row in rows:
            print(f"  {row.category}: {budget.state_text(row)}")
        print(f"  needs a category: {gaps.uncategorised}")
        # A row whose date no calendar can read sits in no month at all —
        # `transaction list --gaps` is where the operator goes to fix one.
        print(f"  needs a date: {gaps.undated}")
        return 0

    print(f"unknown subcommand {sub!r} — one of: set, show", file=sys.stderr)
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


_SCHEDULES_USAGE = """\
usage: homestead-ledger schedules show
       homestead-ledger schedules export [--out DIR]
  e.g.: homestead-ledger schedules export
  `show` lists every liability account instance (credit cards, loans) on
  file — the amount fields as "a balance is on file", never the number.
  `export` composes the same schedule into a JSON file — the amounts
  themselves, never the number — after showing exactly what will be
  written and asking for confirmation. --out DIR writes there instead of
  the default exports directory; DIR must be an absolute path under
  the household root (copy the file out from there yourself).
"""


def _cmd_schedules(argv: list[str]) -> int:
    """schedules <show|export> — the household's liability schedule."""
    from homestead.keep.export import ExportRefused

    from homestead_ledger import schedules
    from homestead_ledger.store import Sidecar

    args = argv[1:]
    if not args:
        print(_SCHEDULES_USAGE, end="", file=sys.stderr)
        return 2
    sub, rest = args[0], args[1:]
    _boot()
    sidecar = Sidecar()

    if sub == "show":
        found = schedules.rows(sidecar)
        if not found:
            print(
                "  no liability accounts on file — `homestead-ledger account "
                "add <label> --kind credit_card --number <number>` (or "
                "--kind loan)"
            )
            return 0
        print(f"  {len(found)} liability account(s):")
        for row in found:
            institution = row.institution or "(not on file)"
            balance = row.balance_as_of or "(not on file)"
            print(
                f"  [{row.rung.value}]  {row.label} ({row.kind}): "
                f"{institution}  ·  {balance}"
            )
        return 0

    if sub == "export":
        from pathlib import Path

        rest, out = _flag(rest, "--out")
        if rest:
            # `export` takes no positional argument, so anything left after
            # `--out` was consumed is a typo — including `--out` itself with
            # no value after it, which `_flag` leaves in `rest`. The same
            # reasoning `_stray_flags` states for `transaction add`: a flag
            # that looks honoured and is not. Here it would quietly export
            # to the default directory instead of the one that was asked
            # for, which is a file in the wrong place and a ledger row
            # saying an export happened.
            print(f"  refused: unexpected argument(s) {rest}", file=sys.stderr)
            print(_SCHEDULES_USAGE, end="", file=sys.stderr)
            return 2
        out_dir = Path(out) if out else None

        def confirm(wire) -> bool:
            print("  about to export the household's liability schedule:")
            print(f"  {wire.method} {wire.url}")
            print("  " + "-" * 60)
            print(wire.body)
            print("  " + "-" * 60)
            answer = input("  write this file? [y/N] ").strip().lower()
            return answer in ("y", "yes")

        try:
            receipt = schedules.export(sidecar, confirm=confirm, out_dir=out_dir)
        except ExportRefused as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        print(f"  exported: {receipt.artifact}")
        print(f"  {receipt.ref}  [{receipt.rung.value}]  {receipt.disposition.value}")
        print(f"  ledger head: {receipt.head}")
        return 0

    print(f"unknown subcommand {sub!r} — one of: show, export", file=sys.stderr)
    return 2


_SYNC_USAGE = """\
usage: homestead-ledger sync --matters M[,M...] --ceiling L1|L2|L3|L4
                              [--types T[,T...]] [--tables sidecar,canonical]
                              [--url URL] [--init-household]
  e.g.: homestead-ledger sync --matters chk-main,obligations --ceiling L3
  Composes a consented scope of the household's own record and sends it to
  its own fleet store — shown in full and confirmed interactively, never
  in the background. --matters names each matter explicitly; there is no
  "all". --tables defaults to both. --ceiling never exceeds L4. --url
  overrides HOMESTEAD_FLEET_URL / a fleet.url file in the household root;
  with neither set, the envelope is dropped as a file under the exports
  directory instead — a destination is never a permission (I-37).
  --init-household mints this household's own id — required before the
  first sync ever run here.
"""


def _cmd_sync(argv: list[str]) -> int:
    """sync --matters a,b --ceiling L3 [...] — send a consented scope to the fleet."""
    from homestead.keep.egress import EgressRefused
    from homestead.keep.household import household_id
    from homestead.keep.logs import IntegritySealError
    from homestead.keep.rungs import Rung

    from homestead_ledger import sync as sync_mod
    from homestead_ledger.schedules import NOTICE
    from homestead_ledger.store import Sidecar

    args = argv[1:]
    rest, matters_raw = _flag(args, "--matters")
    rest, types_raw = _flag(rest, "--types")
    rest, tables_raw = _flag(rest, "--tables")
    rest, ceiling_raw = _flag(rest, "--ceiling")
    rest, url = _flag(rest, "--url")
    init_household = "--init-household" in rest
    rest = [t for t in rest if t != "--init-household"]
    if rest or not matters_raw or not ceiling_raw:
        print(_SYNC_USAGE, end="", file=sys.stderr)
        return 2

    _boot()
    household_file = paths.home() / "household.id"
    if not household_file.exists() and not init_household:
        print(
            "  refused: no household id on file yet — pass --init-household "
            "to mint one (a one-time, exclusive act) before the first sync",
            file=sys.stderr,
        )
        return 1

    try:
        ceiling = Rung(ceiling_raw)
    except ValueError:
        print(
            f"  refused: --ceiling {ceiling_raw!r} is not one of L1, L2, L3, L4",
            file=sys.stderr,
        )
        return 2

    matters = tuple(m.strip() for m in matters_raw.split(",") if m.strip())
    types = tuple(t.strip() for t in types_raw.split(",") if t.strip()) if types_raw else None
    tables = (
        tuple(t.strip() for t in tables_raw.split(",") if t.strip())
        if tables_raw else ("sidecar", "canonical")
    )

    sidecar = Sidecar()
    try:
        scope = sync_mod.scope_from(matters, types, ceiling, tables, sidecar=sidecar)
        envelope = sync_mod.preview(scope, sidecar=sidecar)
    except ValueError as exc:
        print(f"  refused: {exc}", file=sys.stderr)
        return 1

    household = household_id()  # mints once, only reached with --init-household or an id already on file
    # Resolved once, here, and handed to send() unchanged — never resolved a
    # second time after the operator has been shown where this goes.
    dest_url, dest_dir = sync_mod.resolve_destination(url=url)
    counts: dict[str, int] = {}
    for row in envelope.rows:
        counts[row["table"]] = counts.get(row["table"], 0) + 1
    print(f"  household: {household}")
    print(f"  pre-sync head: {envelope.head}")
    for table in sorted(tables):
        print(f"  {table}: {counts.get(table, 0)} row(s)")
    print(f"  ceiling: {ceiling.value}")
    print(f"  destination: {dest_url if dest_url is not None else dest_dir}")
    print(f"  {NOTICE}")

    if not sys.stdin.isatty():
        print(
            "  refused: sync needs an interactive terminal to confirm "
            "(I-37) — there is no --yes on this side",
            file=sys.stderr,
        )
        return 1

    def confirm(wire) -> bool:
        # The yes is read *after* the whole Wire is printed, and the Wire is
        # held against the envelope composed above first: a confirm that
        # says yes to whatever it is handed is a permission, not a confirm.
        if not sync_mod.wire_matches(envelope, wire):
            print(
                "  refused: the delivery offered is not the envelope "
                f"previewed above ({envelope.envelope_id}) — nothing sent",
                file=sys.stderr,
            )
            return False
        print("  about to sync the household's own record to its fleet:")
        print(wire.preview())
        answer = input("  send? [y/N] ").strip().lower()
        return answer in ("y", "yes")

    try:
        receipt = sync_mod.send(envelope, url=dest_url, drop_dir=dest_dir, confirm=confirm)
    except (EgressRefused, sync_mod.AlreadyDelivered) as exc:
        print(f"  refused: {exc}", file=sys.stderr)
        return 1
    except IntegritySealError as exc:
        # A sealed ledger with no key (or without the `sealed` extra) cannot
        # be read to say whether this envelope already went — refused by
        # name (I-11), never a traceback, and nothing was delivered.
        print(f"  refused: {exc}", file=sys.stderr)
        return 1

    print(f"  sent: envelope {receipt.envelope_id}")
    print(f"  destination: {receipt.destination}")
    print(f"  ledger head: {receipt.head}")
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
    "account":     (_cmd_account,     "account <add|list|show> — real accounts"),
    "obligation":  (_cmd_obligation,  "obligation <add|list|show|paid> — recurring obligations"),
    "transaction": (_cmd_transaction, "transaction <add|list|transfer> — the books"),
    "resolve":     (_cmd_resolve,     "resolve <surface> — merchant entity resolution"),
    "reconcile":   (_cmd_reconcile,   "reconcile <baseline> <observed> — compare amounts"),
    "put":         (_cmd_put,         "put — retired; use obligation add / transaction add"),
    "queue":       (_cmd_queue,       "queue — show what's due"),
    "budget":      (_cmd_budget,      "budget <set|show> — per-category, per-month spending limits"),
    "schedules": (_cmd_schedules, "schedules <show|export> — the liability schedule"),
    "sync":      (_cmd_sync,      "sync --matters a,b --ceiling L3 — send a scope to the fleet"),
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
