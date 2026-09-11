"""homestead-ledger entry point.

**I-21: no auto-render on start.** The resting state is the cover; `view.run`
opens on it and draws a pane only when the operator asks — the list on
"Open checking account", the queue on "What's due".

**I-29: the surface holds no domain logic.** The entry point routes to
`view`, which composes through `Window` over the SQLite store and calculates
nothing.

Four ways in, mirroring homestead-law's `__main__.py`:
  * `--help` / `-h` — print this usage and exit 0. Never opens a window.
  * `--smoke` — start, prove every import survived packaging, exit without a
    display. What CI runs against the built artifact.
  * `--demo` — seed a synthetic checking account and obligations into a
    throwaway store and print the list, two details, the what's-due queue,
    and the recurring-charge pass, composed through the gate. The
    store → serve → surface pipeline, headless, on SQLite.
  * default — open the tkinter view on the cover. On a box with no tkinter
    or no display, this fails legibly: a one-line message pointing at
    `--demo` and `--smoke`, and a non-zero exit — never a raw
    `ModuleNotFoundError` or `TclError` traceback.
"""
from __future__ import annotations

import sys

USAGE = """\
usage: python -m homestead_ledger [--help] [--smoke | --demo]
       python -m homestead_ledger --import FILE --account-number N [--dry-run] [--account NAME]
       homestead-ledger <command> [args...]

  --help, -h   show this message and exit
  --smoke      prove every import survived packaging; exit without a display
  --demo       seed a synthetic checking account and obligations and print
               them, headless
  --import FILE --account-number N
               import a bank-statement CSV for one account (header
               auto-detected: single-amount or debit/credit split); prints
               the imported/skipped/errors tally. --account defaults to
               "checking"; --dry-run parses and tallies without writing
  (default)    open the tkinter view on the cover — requires tkinter and a
               display; falls back to a guidance message if neither is present

commands (real data, in the household root — $HOMESTEAD_HOME or ~/.homestead):
  obligation   obligation add <id> <payee> <amount> <due-date> <cadence> [--replace]
               obligation list · obligation show <id>
  transaction  transaction add <date> <amount> <description> --account-number N
               transaction list [--account NAME]
  queue        queue — what's due
  ui           ui [--port N] — entry forms, intake, queue and subscriptions in the browser

commands that need the `entity` extra (pip install 'homestead-ledger[entity]'):
  resolve      resolve <surface> — merchant entity resolution
  reconcile    reconcile <baseline> <observed> — compare amounts
  verify       verify — check ledger chain integrity
"""

_CLI_COMMANDS = {
    "obligation", "transaction", "resolve", "reconcile", "put", "queue", "verify", "ui",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--help" in argv or "-h" in argv:
        # Handled before any other branch, and before `view` is imported, so
        # `--help` never touches tkinter or a display.
        print(USAGE, end="")
        return 0

    if "--smoke" in argv:
        # Prove the interpreter and **every runtime module** survived
        # packaging, and exit without a display. This is the only leg CI runs
        # against the built PyInstaller artifact, so a module it does not name
        # is a module whose packaging is untested — the browser UI and the CLI
        # were exactly that until now, and either one is a whole layer of the
        # app that could be missing from the binary with a green smoke test.
        # `tests/test_main.py::test_smoke_imports_every_runtime_module` holds
        # this block against the package on disk so a new module cannot be
        # left out of it.
        from homestead.app import theme  # noqa: F401
        from homestead.keep import paths

        from homestead_ledger import (  # noqa: F401
            balance,
            books,
            cli,
            fingerprint,
            importer,
            intake,
            money,
            nestor_seam,
            nestor_store,
            obligations,
            queue,
            recurring,
            registry,
            server,
            store,
        )
        from homestead_ledger.app import cover, demo, view, window  # noqa: F401
        from homestead_ledger.packs import (  # noqa: F401
            checking,
            obligations as _obligations_pack,
        )

        print(f"homestead-ledger ok · books at {paths.home() / 'homestead-ledger.db'}")
        return 0

    if "--demo" in argv:
        # A throwaway household root, so the demo imports synthetic
        # transactions nowhere real. Compose the surfaces through the gate
        # and print what a view would draw — headless, on SQLite. Books
        # first (bite 1), then what's due — the queue, its resting cover,
        # and the recurring-charge pass (bite 2).
        import os
        import tempfile

        from homestead_ledger.app import demo
        from homestead_ledger.store import Sidecar

        with tempfile.TemporaryDirectory(prefix="homestead-ledger-demo-") as tmp:
            os.environ["HOMESTEAD_HOME"] = tmp
            print(demo.compose_demo())
            print()
            print(demo.compose_queue(Sidecar()))
            print()
            print(demo.compose_recurring())
        return 0

    if argv and argv[0] in _CLI_COMMANDS:
        from homestead_ledger.cli import run_cli
        return run_cli(argv)

    if "--import" in argv:
        # Bite 4 — a bank-statement CSV import, headless, no tkinter touched.
        # Imported inside this branch so `--smoke` and every other path stay
        # clean of the importer's own imports.
        from homestead_ledger import importer, registry
        from homestead_ledger.packs import checking

        try:
            csv_index = argv.index("--import")
            csv_path = argv[csv_index + 1]
        except IndexError:
            print("homestead-ledger: --import requires a file path", file=sys.stderr)
            return 2

        if "--account-number" not in argv:
            print("homestead-ledger: --import requires --account-number N", file=sys.stderr)
            return 2
        try:
            number_index = argv.index("--account-number")
            account_number = argv[number_index + 1]
        except IndexError:
            print("homestead-ledger: --account-number requires a value", file=sys.stderr)
            return 2

        account = checking.ACCOUNT
        if "--account" in argv:
            try:
                account_index = argv.index("--account")
                account = argv[account_index + 1]
            except IndexError:
                print("homestead-ledger: --account requires a value", file=sys.stderr)
                return 2

        # I-23: the registry is the only enumeration. An unregistered account
        # name here would import a whole statement into a phantom account —
        # rows in the canonical books that nothing iterating `all_accounts()`
        # will ever reach, which is BUG-6's shape with a bank statement in it.
        if account not in registry.all_accounts():
            print(
                f"homestead-ledger: unknown account {account!r} — one of: "
                f"{', '.join(registry.all_accounts())}",
                file=sys.stderr,
            )
            return 2

        dry_run = "--dry-run" in argv

        try:
            result = importer.import_csv(
                csv_path, account=account, account_number=account_number, dry_run=dry_run,
            )
        except (ValueError, FileNotFoundError) as exc:
            print(f"homestead-ledger: import failed — {exc}", file=sys.stderr)
            return 1

        label = "would-import" if dry_run else "imported"
        print(f"{label}={result.imported} skipped={result.skipped} errors={result.errors}")
        for message in result.error_messages:
            print(f"  error: {message}", file=sys.stderr)
        return 1 if result.errors else 0

    # Imported inside main so the module stays importable on a headless box.
    from homestead_ledger.app import view

    try:
        import tkinter
    except ModuleNotFoundError as exc:
        # Covers both "no tkinter package at all" (name == "tkinter") and "the
        # package is present but its C extension isn't built" (name ==
        # "_tkinter", the common cause on minimal/CI Python builds).
        if exc.name not in ("tkinter", "_tkinter"):
            raise
        print(
            "homestead-ledger: tkinter is not available on this interpreter — "
            "try `--demo` (headless pipeline) or `--smoke` (import check) instead.",
            file=sys.stderr,
        )
        return 1

    try:
        return view.run()
    except tkinter.TclError:
        # "couldn't connect to display" and friends — tkinter imports fine but
        # there is nowhere to open a window (e.g. a headless server/container).
        print(
            "homestead-ledger: no display available to open the window — "
            "try `--demo` (headless pipeline) or `--smoke` (import check) instead.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
