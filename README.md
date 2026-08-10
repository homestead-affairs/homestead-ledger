# homestead-ledger

**Homestead · Affairs — module two.** The homesteader keeping their own books.

A **self-contained** desktop module: it ships to a household who double-clicks
it, so its store is embedded **SQLite** — a linked library, not a server (the
face's 2026-08-04 "no listening socket" decision holds; SQLite binds no port).
The record layer is the engine's: `store.py` is a thin binding —
`homestead.keep.store`'s adapter contract on a SQLite backing, in the ledger
database. It **pins the engine from PyPI** — `homestead-affairs>=0.0.2,<1.0` (the
distribution name; `import homestead` is unchanged) — and shares the
`~/.homestead` root with homestead-law, because a household's affairs are one
thing.

## Mirror, not judge

The ledger **reflects** the household's money; it never authors a financial
judgment and never edits a transaction. Concretely, that is the engine's record
model applied to money:

- **Canonical = the household's own books** — imported transactions, statements —
  **read-only by type** (I-6). The app has no write path to them.
- **Sidecar = the household's overlay** — categorization, notes, budget envelopes,
  a confirmed merchant name. This is where the app writes.
- Money amounts tied to an account are **L4**; account numbers / SSNs are **L5**;
  due-dates and schedules are **L1/L2** (see the engine's rung model). The engine
  enforces this at the storage boundary; a corrupt or unclassified row reads
  **L5** on the way out.

The shared **Postgres** engine on the fleet side is a *sync target* reached
through the egress gate — never a runtime dependency of the shipped app. Sync is
an **S4 egress**: an `L5` record never crosses, and what lands in the shared store
is only what the household chose to expose.

> **Status: bite 0 — the seat is bound.** The store binding
> (`homestead.keep.store` on a SQLite ledger db), a no-egress AST guard over this
> package (I-17 — a money ledger must never dial out), CI (cold checkout, engine
> from PyPI, three OSes), and the build plan (`docs/build-plan.md`). The books,
> the "what's due" queue, CSV import, and the app land in the bites that follow.

## The method

Test-first, as in `homestead`: every claim is a check somebody can run. From a
cold checkout — the engine (`homestead.keep`) resolves from PyPI as
`homestead-affairs`, no sibling checkout needed:

```bash
pip install -e .    # pulls homestead-affairs (homestead.keep) from PyPI
pytest -q
```

The full build plan — the reuse map, the bite order, the invariants that carry
from the engine and the ones new to money — is in
[`docs/build-plan.md`](docs/build-plan.md).

MIT.
