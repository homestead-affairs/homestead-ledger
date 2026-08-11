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
| **3 — the app** | ▶ next | tkinter S1 view (cover→list→detail, reveal-expire) + a stdlib surface theme + packaging |
| **4 — import + wire + guard** | queued | CSV import + queue-in-app + no-egress guard + optional outward bridge |

**Suite: 159 passed.** Licensed **Apache-2.0** (matching the engine and the fleet).
Pins `homestead-affairs>=0.0.2,<1.0` from PyPI (0.0.3 is the current Apache
release; the `<1.0` cap is a real compatibility range — the engine cuts 1.0.0 on
a breaking change).

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

- **Bite 3 — the app.** *(next)* A tkinter S1 **view** (`app/view.py`) drawing the
  `Window`/`cover` state built in bites 1–2, mirroring law's `app/`: the resting
  cover (obligations queue counts that survive re-identification, I-31), the
  accounts→transactions list (amounts as derived L4, account# never a row),
  transaction detail with reveal-expire (I-32), and the what's-due queue. The
  chokepoint guards it — the view draws served values and reaches no `.payload`.
  **A stdlib `theme.py`** lands here (`ttk.Style`: a real font, spacing, flat
  widgets, rungs coloured as meaning — the "don't-look-like-Win98" pass, PySide6
  the reserved v2 escape hatch). Packaging (PyInstaller spec + a CI artifact job,
  as the engine/law have) with a window to package.
  - **Follow-on (theme sharing):** the theme is built in the ledger first, then
    hoisted into the engine (`homestead` → a new release) and both law and ledger
    repointed to it, so there is one shared copy and law stops looking dated too.
    That is a small coordinated PR set after the ledger's app proves the theme —
    not folded into this bite, to keep it one repo.
- **Bite 4 — import + wire + guard.** CSV import (header-auto-detect, hash-dedup,
  `--dry-run`); the queue wired into the app; the no-egress guard confirmed; an
  optional aggregate-only outward bridge that degrades to absent.
- **Then:** the ledger's own PyPI release machinery (the shape the engine uses).
  Decide the distribution name at release time — `homestead-ledger` may be free on
  PyPI (unlike the bare `homestead`, which forced `homestead-affairs`).

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

### Deferred v2+ (all specced by the survey)

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

---

## Related

- `safe-app-store/docs/homestead-affairs-face.md` — the face and this module's charter
- `safe-app-store/docs/the-self-portrait.md` — the "mirror not judge" product spec
- `safe-app-store/docs/homestead-rungs.md` — money → L4, keys → L5
- `safe-app-store/docs/homestead-law-build-plan.md` — the sibling module's plan (the template)
- `safe-app-store/apps/private-ledger/` — the predecessor (spec source, not a source tree)
