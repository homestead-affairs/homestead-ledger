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

  --help, -h   show this message and exit
  --smoke      prove every import survived packaging; exit without a display
  --demo       seed a synthetic checking account and obligations and print
               them, headless
  (default)    open the tkinter view on the cover — requires tkinter and a
               display; falls back to a guidance message if neither is present
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--help" in argv or "-h" in argv:
        # Handled before any other branch, and before `view` is imported, so
        # `--help` never touches tkinter or a display.
        print(USAGE, end="")
        return 0

    if "--smoke" in argv:
        # Prove the interpreter and every import survived packaging — this
        # module's store, its pack and registry, the books, the derived
        # balance, and the app surfaces (window, cover, demo, view) plus the
        # shared engine theme the view now draws from — and exit without a
        # display.
        from homestead.app import theme  # noqa: F401
        from homestead.keep import paths

        from homestead_ledger import balance, books, registry, store  # noqa: F401
        from homestead_ledger.app import demo, view, window  # noqa: F401
        from homestead_ledger.packs import checking, obligations  # noqa: F401

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
