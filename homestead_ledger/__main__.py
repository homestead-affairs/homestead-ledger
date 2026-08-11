"""homestead-ledger entry point.

**I-21: no auto-render on start.** The resting state is the cover; a future
tkinter view (bite 3) opens on it and draws the list only when the operator
opens an account.

Three ways in, mirroring homestead-law's `__main__.py`:
  * `--smoke` — start, prove every import survived packaging, exit without a
    display. What CI runs against the built artifact.
  * `--demo` — seed a synthetic checking account into a throwaway store and
    print the list and two details, composed through the gate. The
    store → serve → surface pipeline, headless, on SQLite.
  * default — the tkinter window lands in bite 3; for now this says so.
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--smoke" in argv:
        # Prove the interpreter and every import survived packaging — this
        # module's store, its pack and registry, the books, the derived
        # balance, and the window/demo surfaces — and exit without a display.
        from homestead.keep import paths

        from homestead_ledger import balance, books, registry, store  # noqa: F401
        from homestead_ledger.app import demo, window  # noqa: F401
        from homestead_ledger.packs import checking  # noqa: F401

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

    print("homestead-ledger: the app surface lands in a later bite; try --smoke or --demo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
