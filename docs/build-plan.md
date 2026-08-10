# `homestead-ledger` — build plan

*Module two of the Homestead · Affairs face: the homesteader keeping their own
books. A fresh build in this repo on the shared engine — not a port. The engine
(`homestead.keep`, published as `homestead-affairs`) is already built and
shipped, so this is a much lighter build than `homestead-law` was: it pins the
engine and adds only the money-domain layer on top.*

**Predecessor:** `safe-app-store/apps/private-ledger` — read as a specification
source and a reusable-pattern quarry, never copy-pasted (copied code carries
copied defects; the knowledge travels, not the tree). The face doc names this
module as the thing `private-ledger` **succeeds**.

**Product spec:** `safe-app-store/docs/the-self-portrait.md` — the "mirror, not
judge" loops (a confirmed merchant guess is a *seal*, reused not re-guessed; the
mirror watches you respond to it; the ledger grades its own predictions) and the
deliberate blind spot: *family is the spec, protected by being the one thing the
system cannot see* — surfaced only as structure, never as content.

---

## What it is

The household's own money record. **Mirror, not judge:** it reflects the
household's money and never authors a financial judgment or edits a transaction —
the engine's I-6 (canonical read-only) and I-25 (never authors a fact), applied
to money. Local-first embedded **SQLite**, self-contained, no listening socket,
sharing the `~/.homestead` root with `homestead-law`. Optional fleet sync is an
**S4 egress** through the gate; `L5` never crosses.

### Settled decisions

| # | Decision |
|---|---|
| 1 | **Single-entry** signed transactions + running balance (private-ledger's model), not double-entry. Matches "mirror not judge," lowest scope. |
| 2 | **CSV import is in v1** — a ledger with no import path is manual-entry-only. Header-auto-detect + hash-dedup + `--dry-run` (the `story-timeline/import_csv.py` shape). OFX/PDF/OCR are v2. |
| 3 | **Books first, then the "what's due" queue** (mirrors homestead-law's build order). |
| 4 | Born in this repo, like homestead-law — **not** in `safe-app-store/apps/`. The store's playground/promotion gates apply only if it is ever registered there; the invariants live in-repo, as the engine's do. |

## The record model — the heart of "mirror not judge"

Money enters as **canonical** and is immutable; the household's judgments live in
the **sidecar** overlay.

- **Canonical** — imported transactions and statements. Read-only by type (I-6):
  the app has no write path. Transaction identity is a **content fingerprint**
  (sha256 of date + amount + description + account), so re-importing the same
  statement is idempotent and never silently overwrites (I-7 one key, I-9 no
  silent clobber). Confirmed by `njord/idempotency.py`, `story-timeline` hash-dedup.
- **Sidecar** — categorization, notes, budget envelopes, a confirmed merchant
  name, a marked-`do_not_use` flag. The only thing the app writes. The
  correction-not-mutation shape is `kitchen-pudding`'s: the original claim and the
  current belief are both always answerable.
- **Rungs** (engine-enforced): amount-tied-to-account → **L4**; account number /
  SSN → **L5**; due-date / schedule → **L1/L2**; payee/creditor name → **L3/L4**.
  A corrupt or unclassified row reads **L5** on the way out.

## The reuse map

| Layer | Reuse | Source |
|---|---|---|
| Record core (canonical/sidecar/rungs/deadlines/gate/sealed log/paths) | pin `homestead-affairs` | the shipped engine |
| Store binding (SQLite over `homestead.keep.store`) | copy `homestead-law/store.py` | this repo, bite 0 |
| Transaction dedup / idempotent import | content fingerprint | `njord/idempotency.py`, `story-timeline/import_csv.py` |
| Recurring-charge detector (pure, stdlib, `today`-injected) | lift near-verbatim | `private-ledger/subscriptions.py` |
| "What's due" queue | the engine's deadline machinery | homestead-law's queue |
| No-egress AST test | vendored scanner | `marching-arts/tests/test_no_egress.py` (done, bite 0) |
| The app (tkinter S1 list/detail/cover) | mirror the engine/law `app/` | `homestead`/`homestead-law` |
| Optional aggregate-only outward seam | injected `ingest`, degrade-to-no-op | `private-ledger/willow_bridge.py` |
| CSV/OFX/PDF ingestion *(v2)* | classify→route→scrub→promote | `willow_nest_spec.md`, `nest-seed`, `story-timeline` |
| Merchant/entity resolution *(v2, optional)* | contract-first seam, degrade-to-absent, **never deposits affairs into Nestor** | `docs/drafts/nestor_seam.py` |
| Grade-your-own-predictions *(v2)* | append-only predictions + `calibration.py` | `the-almanac.md`, `oakenscrolls-office` |
| Promotion `semantic_seam` *(if ever registered)* | pure stdlib SQLite/FTS5 search, one declared symbol; `conflict_scan` "refutes not resembles" ranking | Jeles corpus pattern; `stores/promote_check.py` |

**Not reused:** `vault-paths` (superseded by `homestead.keep.paths`), the
`willow-*`/`pg-*`/`fleet-presence` libs (fleet-internal), `private-ledger/_archived/*`,
and `docs/the-fourth-store.md` (it's about Nestor, not money).

## Build order

Each bite ends with its tests green; the tests come first and start red.

- **Bite 0 — the seat is bound.** *(this push)* Repo scaffold, pin
  `homestead-affairs`, the store binding (SQLite `homestead-ledger.db` in
  `~/.homestead`), the no-egress AST guard (I-17), CI (cold checkout, engine from
  PyPI, three OSes), this plan. *Exit: cold `pip install -e .` + bare `pytest`
  green; no-egress green; `--smoke` runs.*
- **Bite 1 — the books.** Accounts + transactions schema pack, classified at
  import (amount→L4, account#→L5), the registry as the only enumeration (I-23),
  transaction identity = content fingerprint (idempotent), running balance
  derived. Canonical immutable; sidecar for categorization/notes/budget. The
  **mirror-not-judge** invariant (no write path to a transaction) lands as a test.
- **Bite 2 — what's due.** Recurring obligations/renewals with due dates over
  `homestead.keep.dates`; the queue = *what the season owes*; the recurring-charge
  detector lifted from private-ledger.
- **Bite 3 — the app.** tkinter S1 list/detail (accounts→transactions;
  obligations) mirroring law's `app/`, the cover with the re-identification check
  (a "$X due / 1 overdue" aggregate is L2 only after it passes), account-number
  patterns→L5 (I-18), the single chokepoint; `--demo` headless. Packaging
  (PyInstaller) lands here, with the window to package.
- **Bite 4 — import + wire + guard.** CSV import (header-detect, hash-dedup,
  `--dry-run`); the queue wired into the app; the no-egress guard confirmed; an
  optional aggregate-only outward bridge that degrades to absent.
- **Then:** PyPI release machinery (the same shape the engine now uses).

### Deferred v2+ (all specced by the survey)

OFX/PDF/OCR ingestion (`nest-pipeline`); envelope-budget and net-worth views; the
calibration / grade-your-predictions loop (`the-almanac`'s `calibration.py`, ~70
stdlib lines); the Nestor merchant-canonicalization seam (`nestor_seam.py`,
optional extra, pinned inside `/.homestead`, read/attest only — **never** deposits
household affairs into Nestor, per the face-4 carve-out); DB-trigger immutability
(`intake-desk`) and hash-chain tamper-evidence (`aristarchus`) as defense-in-depth
beyond the engine's sealed log; the promotion semantic-seam.

## Invariants

**Carried from the engine (free):** I-1…I-15 (dates, the record, rungs), I-16 (one
chokepoint), I-17 (no egress — re-asserted in-repo by the no-egress AST test),
I-19/I-20 (`/.homestead` paths), I-21/I-31/I-32/I-35 (cover, reveal-expire,
re-identification), I-26 (import-pure core), I-27/I-28 (cold install, bare pytest).

**New / ledger-specific:**
- **Mirror, not judge** — the app has no write path to a transaction; money is
  overlaid, never edited (the money reading of I-6/I-25).
- **Money classification** — amount→L4, account#/SSN→L5, due-date→L1/L2, at
  schema-definition time; unclassified fails the build.
- **Idempotent import** — a transaction's identity is a content fingerprint;
  re-import never duplicates and never silently overwrites.
- **Family is never content** — the household graph is surfaced only as structure,
  never rendered as a person's record (the self-portrait's blind spot).

---

## Related

- `safe-app-store/docs/homestead-affairs-face.md` — the face and this module's charter
- `safe-app-store/docs/the-self-portrait.md` — the "mirror not judge" product spec
- `safe-app-store/docs/homestead-rungs.md` — money → L4, keys → L5
- `safe-app-store/docs/homestead-law-build-plan.md` — the sibling module's plan (the template)
- `safe-app-store/apps/private-ledger/` — the predecessor (spec source, not a source tree)
