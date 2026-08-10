"""homestead-ledger entry point.

The app surface (an S1 window, mirroring homestead-law's) lands in a later bite.
For now this exposes `--smoke`: prove, headless, that the pinned engine is
installed and the store binding resolves — the same check homestead-law's CI
runs. No network, no window, no writes.
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--smoke" in argv:
        import homestead_ledger.store as store  # noqa: F401  (binding imports)
        from homestead.keep import paths

        print(f"homestead-ledger ok · books at {paths.home() / 'homestead-ledger.db'}")
        return 0
    print("homestead-ledger: the app surface lands in a later bite; try --smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
