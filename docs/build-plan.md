# `homestead-ledger` — build plan

*Module two of the Homestead · Affairs face: the homesteader keeping their own
books. A fresh build in this repo on the shared engine — not a port. The engine
(`homestead.keep`, published as `homestead-affairs`, Apache-2.0) is already built
and shipped, so this is a much lighter build than `homestead-law` was: it pins the
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

## Status

| Bite | State | What landed |
|---|---|---|
| **0 — bind the seat** | ✅ done | store binding (SQLite over `homestead.keep.store`), the no-egress AST guard (I-17), CI (cold, engine from PyPI, 3 OSes), this plan |
| **1 — the books** | ✅ done | accounts+transactions pack (classified at import), the registry (I-23), content-fingerprint identity (idempotent import), derived running balance, the display-free `app/window` + headless `--demo`; **+ the I-16 chokepoint added in audit** (mirror-not-judge made structural) |
| **2 — what's due** | ✅ done | the obligations pack (sidecar-declared, classified at import), `all_obligations()` (a second I-23 enumeration), the **queue** (urgency over `homestead.keep.dates`; reads due-dates *through* `serve()`, not `.payload`; gaps first, I-8), the `app/cover` re-identification port (I-31), and the **pure recurring-charge detector** (`recurring.py`, imports nothing from the package). `--demo` shows books → queue → cover → a detected monthly charge. |
| **3 — the app** | ✅ done | tkinter S1 view (cover→list→detail), the stdlib `ttk` surface theme, PyInstaller packaging + a CI artifact job. **Theme follow-on complete:** the theme was hoisted into the engine (`homestead.app.theme`, released as 0.1.0) and both this module and `homestead-law` repointed to it — one shared copy, no drift. |
| **4 — import + wire + guard** | ✅ done | **CSV import** (`importer.py` — header-auto-detect for single-amount and debit/credit-split, fingerprint-seam dedup, `--dry-run`; routes every write through `books.import_transaction`, names no `CANONICAL`). **App wired to the real books** — `view.compose_store()` opens the window on the operator's own `~/.homestead` store so an imported statement appears in the list/detail/cover/queue, with a clearly-labelled throwaway-demo fallback on an empty first run (the real root is never seeded). **No-egress confirmed end-to-end** — a runtime guard (`test_no_egress_runtime.py`) poisons `socket` and proves the real import + app-compose paths never dial out, atop the static AST sweep. Outward bridge **deferred to v2** (see below). |

**X7-drift addendum (2026-09-11): bites 5 and up.** This table stops at bite
4 because that is where the Homestead · Affairs face's own bite numbering
(0–4) ends; everything since is a `G<n>` bite from that plan
(`so-lets-plan-it-sparkling-shell.md`), each released and each holding its
own tests: account instances and the one-record account number (G2b,
0.5.0), cadence-driven due-date roll-forward (G3, 0.4.0), the Chapter 13
debt schedule export (G4-schedules-export, 0.6.0), transfers between the
household's own accounts (G4-transfers, 0.7.0), the per-transaction overlay
— category, note, confirmed merchant, do-not-use (G4-overlay, 0.8.0),
per-category budgets (G4-budget, 0.9.0), fleet sync (G5-sync, 0.10.0), and
business-owned/restricted accounts with a grant report (G8-business-books,
unreleased as of this sweep — see `docs/PLAN-affairs-face.md`). README's own
"## Module status" table is the accurate, kept-current row-per-capability
record now; this file's narrative is not re-derived here to avoid two copies
saying the same thing on two different days.

~~**Suite: 195 passed.**~~ *(X7-drift correction: a literal count in prose is
a number the next added test makes false again — it already has, more than
once, and the exact figure differs with and without the optional `entity`
extra installed. Described qualitatively instead: green on `pytest -q`, cold
and on both legs.)* Licensed **Apache-2.0** (matching the engine and the
fleet). ~~Pins `homestead-affairs>=0.1.0,<1.0` from PyPI (0.1.0 is where the
shared `homestead.app.theme` landed — the floor this view needs...)~~
*(X7-drift correction: the floor has moved twice since — 0.3.0 for the
account packs (G2a), then `>=0.11.0,<1.0` for G5-sync's `homestead.keep.sync`
— see `pyproject.toml`'s own dependency comment for the current floor and
why. The `<1.0` cap reasoning is unchanged: a real compatibility range — the
engine bumps the minor for a feat, so every pre-1.0 release resolves, and
1.0.0 is reserved for the first breaking change.)*

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
| 5 | **Rungs (settled in bite 1):** `amount`→**L4** (money category), `account_number`/SSN→**L5** (key material), `date`→**L2** (household activity, not a public record the way a court date is — so L2 not L1), `description`/payee→**L3** (resolves to a party). Declared at schema-definition time; unclassified fails the build. |
| 6 | **Mirror-not-judge is structural, not disciplinary.** The I-16 chokepoint (`tests/test_invariants_chokepoint.py`) enforces by AST scan that only `books.py` names the `CANONICAL` table, no surface reaches a `.payload` or reflects, and every audit bypass is caught. The read-only handle alone was not enough (the import writes canonical by bypassing it through the raw adapter). |
| 7 | **Apache-2.0**, matching the engine and the fleet. |

## The record model — the heart of "mirror not judge"

Money enters as **canonical** and is immutable; the household's judgments live in
the **sidecar** overlay.

- **Canonical** — imported transactions, one record **per field** keyed by
  `(account, field, fingerprint)` (not one composed record — a composed record
  would collapse to the `max` rung, L5, and hide the whole transaction). Read-only
  by type (I-6): the app has no write path; only `books.py` (the import) writes,
  and the chokepoint enforces that. Transaction identity is a **content
  fingerprint** (sha256 of date + amount + description + account), so re-importing
  the same statement is idempotent and never silently overwrites (I-7, I-9). The
  import distinguishes an ordinary re-import from a torn partial-import and
  surfaces the latter for an operator.
- **Sidecar** — categorization, notes, budget envelopes, a confirmed merchant
  name, a marked-`do_not_use` flag. The only thing the app writes.
- **Rungs** (engine-enforced) — decision 5 above; a corrupt or unclassified row
  reads **L5** on the way out.

## The reuse map

| Layer | Reuse | Source |
|---|---|---|
| Record core (canonical/sidecar/rungs/deadlines/gate/sealed log/paths) | pin `homestead-affairs` | the shipped engine |
| Store binding (SQLite over `homestead.keep.store`) | done, bite 0 | `homestead-law/store.py` |
| Transaction dedup / idempotent import | done, bite 1 | `njord/idempotency.py`, `story-timeline/import_csv.py` |
| No-egress AST test / the I-16 chokepoint | done, bites 0–1 | `marching-arts/tests/test_no_egress.py`; `homestead/tests/test_invariants_chokepoint.py` |
| Recurring-charge detector (pure, stdlib, `today`-injected) | **bite 2** — lift near-verbatim | `private-ledger/subscriptions.py` |
| "What's due" queue | **bite 2** — the engine's deadline machinery | homestead-law's queue |
| The app (tkinter S1 list/detail/cover) + shared theme | **bite 3** — mirror law's `app/` | `homestead`/`homestead-law` |
| Optional aggregate-only outward seam | **bite 4** — injected `ingest`, degrade-to-no-op | `private-ledger/willow_bridge.py` |
| CSV import (header-detect, hash-dedup, `--dry-run`) | **bite 4** | `story-timeline/import_csv.py` |
| OFX/PDF/OCR ingestion *(v2)* | classify→route→scrub→promote | `willow_nest_spec.md`, `nest-seed` |
| Merchant/entity resolution *(v2, optional)* | contract-first seam, degrade-to-absent, **never deposits affairs into Nestor** | `docs/drafts/nestor_seam.py` |
| Grade-your-own-predictions *(v2)* | append-only predictions + `calibration.py` | `the-almanac.md`, `oakenscrolls-office` |
| Promotion `semantic_seam` *(if ever registered)* | pure stdlib SQLite/FTS5 search, one declared symbol; `conflict_scan` ranking | Jeles corpus pattern; `stores/promote_check.py` |

**Not reused:** `vault-paths` (superseded by `homestead.keep.paths`), the
`willow-*`/`pg-*`/`fleet-presence` libs (fleet-internal), `private-ledger/_archived/*`,
and `docs/the-fourth-store.md` (it's about Nestor, not money).

## Build order — remaining

Each bite ends with its tests green; the tests come first and start red.

- **Bite 3 — the app.** ✅ *done.* A tkinter S1 **view** (`app/view.py`) draws the
  `Window`/`cover` state built in bites 1–2, mirroring law's `app/`: the resting
  cover (obligations queue counts that survive re-identification, I-31), the
  accounts→transactions list (amounts as derived L4, account# never a row),
  transaction detail, and the what's-due queue. The chokepoint guards it — the
  view draws served values and reaches no `.payload`. A stdlib `ttk.Style` theme
  (real font, spacing, flat widgets, rungs coloured as meaning — the
  "don't-look-like-Win98" pass; PySide6 the reserved v2 escape hatch) landed, and
  packaging (PyInstaller spec + CI artifact job, as the engine/law have).
  - **Follow-on (theme sharing):** ✅ *done.* The theme was hoisted into the engine
    (`homestead.app.theme`, released as **0.1.0**) and both law and ledger
    repointed to it, so there is one shared copy and law stops looking dated too.
    A small coordinated PR set (ledger #4, law #5) after the ledger's app proved
    the theme.
- **Bite 4 — import + wire + guard.** ✅ *done.* CSV import (`importer.py` —
  header-auto-detect, fingerprint-seam dedup, `--dry-run`); the app wired to the
  real books (`view.compose_store()` — real store when it holds anything, a
  labelled throwaway-demo fallback when empty, the real root never seeded); and
  the no-egress guard confirmed end-to-end (a runtime `socket`-poison test over
  the real import and app-compose paths, atop the static AST sweep). The
  **optional aggregate-only outward bridge is deferred to v2** — a money ledger's
  purest v1 posture is strictly egress-free, and the bridge is already specced;
  it slots into v2 as an injected, default-absent, aggregates-only seam.
- **Then:** the ledger's own PyPI release machinery (the shape the engine uses).
  ✅ *done.* release-please + Trusted Publishing (OIDC) ported from the engine:
  `release-please-config.json` (`bump-minor-pre-major` false, so 1.0 means a
  break), the `release-please.yml` / `release.yml` workflows (PAT-cut tag →
  top-level publish, the fleet's hard-won provenance shape), hatch-vcs deriving
  the version from the tag, `tools/changelog_dedup.py`, a seeded `CHANGELOG.md`,
  and `tests/test_invariants_release.py` guarding that the four files agree.
  The distribution name is **`homestead-ledger`** (confirmed free on PyPI — no
  `-affairs` workaround the bare `homestead` forced). One-time account setup (the
  PyPI pending publisher + `pypi` environment + `RELEASE_PLEASE_TOKEN`) is the
  only thing between here and the first `0.0.2` release.

### Audit follow-ups (non-blocking)

- **Payee-category sensitivity** — `description`→L3 uniformly does not yet catch a
  payee that *leaks a category* (a clinic, a named person → L4/L5). The
  "mirror not judge" tension in miniature; a future per-payee sensitivity pass.
- **`balance.py` is a second payload boundary** — it reaches `.payload` for
  arithmetic (allow-listed with the chokepoint). Could later fold into the store
  seam so there is a single boundary (the engine's shape).
- **Obligation-kind anonymity axis** — the obligations cover applies I-31 over the
  single obligation *kind* bite 2 registers, so it shows "Nothing is open" even
  with items due. Faithful to the re-identification rule; whether *kind* is the
  right granularity (vs. per-obligation-type matters) is worth a later look.
- **Cosmetic** — the demo's second checking cover line prints a doubled `cover —`.
- **Torn-write atomicity** — a partial import (fields 2–4 failing after field 1)
  is detected and surfaced, not silently assumed; a batched/transactional import
  would close it fully.
- **`RecordExists` disambiguation is by message text** *(bite 4)* — the importer
  tells an ordinary idempotent re-import (skip) from a torn-write signal (error)
  by matching `books.py`'s prose (`"already on the books"`). It is the only
  signal `books.py` exposes today, and it is tested, but it couples the importer
  to a sentence. A later cleanup would have `books.import_transaction` raise two
  distinct `RecordExists` subclasses so the caller branches on type, not text.

### Deferred v2+ (all specced by the survey)

The **optional aggregate-only outward bridge** (`private-ledger/willow_bridge.py`'s
pattern) — an injected, **default-absent** `ingest` seam that emits only
aggregates that survive re-identification (counts, totals, normalized-merchant
due facts), never a transaction/description/amount/account number, routed through
the gate (S4); the package imports no network library, so I-17's AST sweep stays
green and nothing egresses unless a transport is explicitly injected. Deferred
from bite 4 to keep v1 strictly egress-free. Then also:
OFX/PDF/OCR ingestion (`nest-pipeline`); envelope-budget and net-worth views; the
calibration / grade-your-predictions loop (`the-almanac`'s `calibration.py`, ~70
stdlib lines); the Nestor merchant-canonicalization seam (`nestor_seam.py`,
optional extra, pinned inside `/.homestead`, read/attest only — **never** deposits
household affairs into Nestor, per the face-4 carve-out); DB-trigger immutability
(`intake-desk`) and hash-chain tamper-evidence (`aristarchus`) as defense-in-depth
beyond the engine's sealed log; the promotion semantic-seam.

## Invariants

**Carried from the engine (free):** I-1…I-15 (dates, the record, rungs),
I-19/I-20 (`/.homestead` paths), I-21/I-31/I-32/I-35 (cover, reveal-expire,
re-identification), I-26 (import-pure core), I-27/I-28 (cold install, bare pytest).

**Enforced in-repo:**
- **I-17 — no egress.** An AST sweep over the package: no network import, no
  `eval`/`exec`/`__import__`. A money ledger is the canonical "must not egress"
  case. *(bite 0)*
- **I-16 — one chokepoint / mirror-not-judge.** Only `books.py` names `CANONICAL`;
  no surface reaches a `.payload` or reflects; every audit bypass is caught. *(bite 1)*

**New / ledger-specific:**
- **Mirror, not judge** — the app never writes a transaction; money is overlaid,
  never edited (I-6/I-25 for money), enforced by the chokepoint.
- **Money classification** — decision 5, at schema-definition time.
- **Idempotent import** — identity is a content fingerprint; re-import never
  duplicates and never silently overwrites.
- **Family is never content** — the household graph is surfaced only as structure,
  never rendered as a person's record (the self-portrait's blind spot).

**Promoted from provisional (ratified by the engine's E4-sync-core audit,
2026-09-11; this module is a *tested consumer*, not the thing that ratified
them):**
- **I-37** — a sync is ledgered only on a confirmed act; a refused confirm
  writes and ledgers nothing (`tests/test_sync.py`'s declined-confirm tests).
- **I-38** — an envelope is delivered once; a repeat is refused rather than
  re-sent (`tests/test_sync.py`'s `AlreadyDelivered` tests, both legs).
- **I-40** — a `SyncScope` names each matter explicitly; there is no `"all"`,
  and `homestead_ledger.sync.scope_from` holds a name against what this
  household actually has on file before a scope is even built.
- **I-43** — an account's bank-issued number lives in exactly one record and
  never crosses a sync at any ceiling. This one is the ledger's own (G2b
  wrote it; the engine's sync audit did not rule on it): what is promoted
  here is the sync half, held by this module's structural belt, independent
  of the engine's ceiling drop (`tests/test_sync.py`'s planted number and
  the monkeypatched-rung-table regression).

`homestead_ledger.sync` is no longer unbuilt — G5-sync (`homestead_ledger/
sync.py`, `tests/test_sync.py`, the CLI's `sync` command, the server's Sync
tab).

**Known seam, recorded rather than papered over (G5-sync audit,
2026-09-11).** A `transfers` `pair` record is `L2` and is served as a
*mapping* (`counterpart`, `from`, `to`), while the fleet's `canonical`/
`sidecar` tables give `value` a `TEXT` column — so
`homestead.keep.fleet_cli._validate_rows` refuses such a row by name, and
with it the whole envelope (I-11). An envelope whose scope names
`transfers` therefore composes here, drops to a file, and is refused at
`homestead-fleet ingest` before a row is written. That is the engine's own
contract to settle (a text column versus a structured served value), not a
consumer's to work around; it is pinned by
`tests/test_sync.py::test_the_fleet_refuses_a_structured_pair_value_by_name`
so the day it changes, this notices.

**Left out of this bite (G5-sync audit):** the Sync tab has no `--types`
control — the API takes `types` and refuses an unknown one by name, and the
browser simply never sends the field.

---

## Related

- `safe-app-store/docs/homestead-affairs-face.md` — the face and this module's charter
- `safe-app-store/docs/the-self-portrait.md` — the "mirror not judge" product spec
- `safe-app-store/docs/homestead-rungs.md` — money → L4, keys → L5
- `safe-app-store/docs/homestead-law-build-plan.md` — the sibling module's plan (the template)
- `safe-app-store/apps/private-ledger/` — the predecessor (spec source, not a source tree)
