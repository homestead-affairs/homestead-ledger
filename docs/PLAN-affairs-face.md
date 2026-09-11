# The Homestead · Affairs plan — this module's face

This is not a new plan. It is the ledger-naming excerpts of
`so-lets-plan-it-sparkling-shell.md` (the Homestead · Affairs build-out plan,
held by the orchestrating session — this repo does not carry the full
document) copied verbatim, one bite struck through as its PR lands. Unlanded
items stay unstruck. `tests/test_plan_affairs_face.py` asserts every struck
line names a PR number, so a strikethrough here can never be wishful.

Struck lines carry `(#PR, released X.Y.Z)` — **both**, because a PR number
says a change merged and a release number says it shipped, and the two are
not the same event here (every bite below merged one PR ahead of the
release-please PR that actually cut its version). PR numbers and release
versions are read from this repo's own `git log`/`CHANGELOG.md`, not
asserted from memory. A bite named in the plan but not yet landed keeps its
plain text, and every ledger bite the plan names has an entry here whether
it landed or not — this file does not get ahead of what merged, and it does
not quietly drop what has not started.

## Wave 0 — land the base (parallel)

~~**W0-LEDGER** `homestead-ledger`, existing branch. Fix first: Records nav
button; `--smoke` imports `server`, `cli`, `obligations`, `importer`. Tests:
every `<section id="t-X">` has a `show('X'` button (structural); a `--smoke`
import-coverage scan with a planted omission. Audit: `obligations.
add_obligation` TOCTOU → first field `overwrite=False` unless `replace`
(I-9); `rows()` rung max via `compose()` not string order (I-14);
`/api/transaction` errors never echo the account number.~~ (#23, released
0.2.0 — "obligation and transaction entry a household can use itself",
followed by "close the orphaned Records tab, the add-obligation race, and
the doors' refusals".)

## Wave 2 — modules adopt 0.3.0 (parallel)

~~**G2a-account-packs** ledger `feat:` — floor 0.3.0; `packs/savings.py`,
`credit_card.py`, `loan.py` (`LIABILITY`); `books.import_transaction`
classifies via `registry.account(kind)`; `derived_by_sign`; liability CSVs
need `--liability-columns` on a debit/credit header; one cover button per
kind. Test: `grep checking.FIELDS books.py` empty; planted-literal guard
covers four names.~~ (#29, released 0.3.0 — "three account packs,
registry-driven classification, liability sign".)

~~**G2c-importer-dates** ledger `fix:` — rows parsed to ISO;
`BANK_DATE_FORMATS` + `--bank`; a slashed date without `--bank` is a
per-row error; fingerprint over ISO (dedup across formats); `transaction
list --gaps`. No migration (v1 synthetic-only), documented.~~ (#26,
released 0.2.1 — "parse importer dates to ISO with a per-bank format
table", followed by "let the declared bank date format win, and stop
echoing the cell".)

## Wave 3 — instances, jurisdiction, the three law packs, ledger instances

~~**G2b-account-instances** ledger `feat:`, depends G2a+G2c — `accounts.py`
sidecar matter `accounts` (label id; `kind` L2, `institution` L3, `number`
L5, `opened` L2, `balance_as_of` L4, `rate` L4, `limit` L4,
`payment_due_day` L2, `min_payment` L4); `Transaction.account` = label;
canonical matter = label; fingerprint uses the instance number inside
`books.py` (allowed boundary) and the per-transaction `account_number`
record is no longer written (I-43); `importer --account <label>` required;
labels equal to a kind name refused; cover over `accounts.instances()`.~~
(#33, released 0.5.0 — "account instances — a label, never a kind, and one
number record".)

~~**G3-cadence-paidby** ledger `feat:` (parallel) — `cadence.py` closed
`CADENCES` incl. `biweekly`, `roll_forward` (month-end clamp; from the
previous due date, repeated until past `paid_on`); `mark_paid` writes
`(obligations, "paid_by", "<id>.<date>")` L2 `{account, fingerprint}`,
overwrites `due_date` (reports `Replaced`), logs `ITEM_RESOLVED`; recurring
gains a biweekly bucket; `obligation paid`, `/api/obligation/paid`,
`paid ✓` marks by reference.~~ (#31, released 0.4.0 — "cadence-driven
due-date roll-forward and obligation paid-by tracking", followed by
"anchor a month-end obligation's due day, and stop a stale paid mark".)

## Wave 4 — sync in the engine; ledger overlay; law surfaces

~~**G4-overlay** ledger `feat:`, depends G2b — `overlay.py` +
`packs/overlay.py` (validated at import; neither registry discovers it —
add a guard): `(label, category|note|confirmed_merchant|do_not_use,
<fingerprint>)`; category L3, raised to L4 by a closed protected-shape word
list (advisory argues up only); note L4; `do_not_use` L2 excludes from
recurring, budget and every S4 envelope/export; `transaction tag`, server
form/columns.~~ (#39, released 0.8.0 — "overlay a transaction — category,
note, confirmed merchant, do-not-use", followed by "close the overlay's
protected-word gaps, resolve a typed fingerprint prefix, and cap free
text".)

~~**G4-transfers** ledger `feat:` — `(transfers, "pair", <fp_out>)` L2
`{counterpart, from, to}`; equal-and-opposite within 5 days; excluded from
aggregates; "transfer → visa-chase" on the list.~~ (#36, released 0.7.0 —
"pair transfers between the household's own accounts (decision 9)",
followed by "narrow the transfers chokepoint entry, and make a pairing say
what happened".)

~~**G4-budget** ledger `feat:`, depends G4-overlay — `(budget, "limit",
"<category>.<YYYY-MM>")` L4; `envelopes(canonical, sidecar, month)` derived
never stored; served derived on the list.~~ (#41, released 0.9.0 — "budget
limits per category and month, envelopes derived on the list", followed by
"net a month's refunds, refuse a non-ISO date into a month, drop the
unwritten budget note".)

~~**G4-schedules-export** ledger `feat:`, depends G2b — `schedules.debts()`
composed L4 rows from liability instances (never the number); `schedules
export --purpose export` through the engine's `export_record`; Chapter 13
plan payment is an ordinary obligation; I-44 guard + "no official form
number" grep guard (plant).~~ (#35, released 0.6.0 — "compose and export
the household's Chapter 13 debt schedule", followed by "refuse an --out
this export cannot honour, and anchor the I-44 carve-out".)

## Wave 5 — sync in the modules; keyed integrity

~~**G5-sync** ledger `feat:` — same shape with `{"sidecar": Sidecar(),
"canonical": Canonical()}`; `accounts.number` can never cross; `do_not_use`
rows dropped; canonical rows labelled so the fleet inserts, never upserts;
`--smoke` imports `sync`.~~ (#43, released 0.10.0 — "sync a consented scope
of the books to the fleet — CLI and Sync tab", followed by "the Send click
confirms this envelope, and nothing crosses by reference".)

## Wave 7 — drift and closure sweep (one bite per repo, `test:`/`docs:`)

~~**G7b-floor-0.13** ledger `build(deps):` — raise the floor to the release
carrying E7b, flip the pinned refusal test to a pass, and sync a transfer
pair end to end.~~ (#47, released 0.11.0 — "build(deps): floor
homestead-affairs at 0.13.0", with "test: a transfer pair crosses to the
fleet as a structured value" and "test: strike the old refusal sentence, and
pin the pair row's rung and disposition" on the same PR. The engine side is
E7b: `value` stays `TEXT`, a mapping crosses as canonical JSON text under a
new `value_format` column, shipped as engine 0.13.0. `pyproject.toml` now
declares `homestead-affairs>=0.13.0,<1.0`, and the pin is
`tests/test_sync.py::test_the_fleet_accepts_a_structured_pair_value` — the
refusal test, flipped, keeping its history. This sweep merged that branch
rather than racing it, because its own corrected `sync.py` paragraph quotes
the floor this bite raises.)

~~**G8-business-books** ledger `feat:`, depends G2b + G4-overlay + G4-budget
— account instances gain `owner` L2 ∈ {`household`, `business`} and
`restricted` L2 (a grant account whose spend must map to `allowable_uses`);
every household aggregate — budget envelopes, recurring, the Chapter 13
`schedules.debts()` export, the cover — **excludes business-owned accounts
unless `--include-business` is passed**, and the export names the
exclusion in its `NOTICE`; transactions on a restricted account require an
`allowable_use` overlay category (closed set entered by the operator from
the award terms; a transaction without one is listed under a "needs a use"
gap, never refused — grant money arrives before the operator has typed the
terms); `grant report <label> --period YYYY-MM..YYYY-MM` = spend by
allowable use, served on S4 with `Purpose.EXPORT`, references and totals
only; a transfer between a household and a business account is tagged
`commingling` and listed by reference (not refused: sometimes a founder
does pay a business expense personally; the point is that it is visible).
No payroll, no tax computation, no 409A, no cap-table math: UNCERTAIN →
refuse by name, pointing at the accountant. Audit: a business account's
number is still one L5 record (I-43); the household schedules export
byte-identical with and without a business account present unless the flag
is passed; the commingling tag never carries an amount on S1_LIST.~~ (#45, released
0.11.0 — `feat: business-owned and restricted accounts — aggregates exclude
them, grant report by allowable use, commingling by reference`, followed by
two audit commits on the same PR: `824c221` "fix: a notice states this
export's own state, and a use total is net of refunds" and `e8c226b` "test:
the browser door's own G8 pins". The release is 0.11.0, cut by #46, which
also carries G7b's `build(deps):` floor raise — one release, two bites,
because #47 merged between #45 and the release-please PR.)

*Two open UI gaps the merged code itself carries, recorded here rather than
struck as done or flagged as drift (neither claim is false, both are simply
unfinished): the browser's Add Account form (`server.py::_post_account`)
already accepts `owner`/`restricted` in its JSON body and `add_account`
already takes both keywords, but the rendered HTML form has no field for
either — only the CLI (`account add --owner/--restricted`) or a raw API
call can set them today. And `include_business` is read from every
relevant endpoint's query string (`server.py`'s `_get_subscriptions`,
`_get_budget`, `_get_schedules`), but no page ships an "include business
accounts" checkbox to set it — the flag exists and is tested
(`tests/test_business_books.py`), it just has no browser control yet.*

**X7-drift-<repo>** — `tests/test_docs_drift.py` grep-guards for known
stale sentences; the meta-scan `tests/test_scans_fire.py` (every AST-guard
helper must have a planted-violation test; itself planted); README status
tables; `docs/PLAN-affairs-face.md` = this plan with items struck through
as they land. *(This bite, X7-drift-ledger. Unstruck on its own branch,
`claude/ledger-drift` — a bite does not strike itself before the
orchestrator has opened and merged its PR; the strikethrough and PR number
land in the same commit the orchestrator makes, or a follow-up on this
branch once merged — the same posture `claude/health-drift` recorded for
its own identical case.)*

## Open items this face records

Not drift (no sentence anywhere claims otherwise) and not a struck bite —
things the tree carries unfinished, written down so the next sweep does not
have to rediscover them.

- **The two G8 UI gaps** above: `owner`/`restricted` have no field on the
  browser's Add Account form, and `include_business` has no checkbox on any
  page. Both are wired and tested server-side; only the HTML is missing.
- **Inline scans the meta-scan cannot see.** `tests/test_scans_fire.py`
  reads module-level helpers. A guard written inline in a test body is
  invisible to it and can never be planted — the X7 audit factored out the
  three page scans in `tests/test_server.py` and the second-copy guard in
  `tests/test_budget.py`, but the suite still carries inline scans of this
  shape (for example `tests/test_view.py`'s module-scope tkinter check and
  `tests/test_nestor_seam.py`'s lazy-import check). Each is asserted against
  the real tree and none has been shown to fire on a violation.
- **Duplicated chokepoint scans.** `tests/test_queue.py`,
  `tests/test_recurring.py`, `tests/test_transfers.py`,
  `tests/test_budget.py` and `tests/test_business_books.py` each re-implement
  the `.payload`-reach walk that `tests/test_invariants_chokepoint.py`
  already owns and plants. The mechanism is proven once; the copies are not,
  and a copy that drifts is the shape this whole sweep is about.
- **Closed here, recorded so it is not re-opened as an open item:** the
  cover's distribution gate. The sweep's first pass called
  `accounts.cover`'s missing `by_matter` wiring an open item; the audit found
  the package calls its own port of `cover_counts`, not the engine's, and
  that the port had missed both of the engine's hardenings. `app/cover.py` is
  now an adapter over the engine's one copy and `queue.cover` passes its
  distribution — `fix:` on this branch, with the `(2, 0)`-fails /
  `(1, 1)`-passes law at both levels. `accounts.cover` passes none, and the
  proof that it need not is a test rather than a comment.
