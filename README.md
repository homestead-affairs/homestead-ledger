# homestead-ledger

**Homestead · Affairs — module two.** The homesteader keeping their own books.

A **self-contained** desktop module: it ships to a household who double-clicks
it, so its store is embedded **SQLite** — a linked library, not a server (the
face's 2026-08-04 "no listening socket" decision holds; SQLite binds no port).
The record layer is the engine's: `store.py` is a thin binding —
`homestead.keep.store`'s adapter contract on a SQLite backing, in the ledger
database. It **pins the engine from PyPI** — `homestead-affairs>=0.1.0,<1.0` (the
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

## Entering your own information

The demo (`--demo`) is synthetic. The household's own books go into the
household root — `$HOMESTEAD_HOME`, else `~/.homestead` — and nothing below
needs the optional `entity` extra:

```bash
pip install -e .

homestead-ledger ui                                              # entry forms, intake, queue and subscriptions, on localhost
homestead-ledger account add chk-main --kind checking --number 9821   # register the real account first
homestead-ledger obligation add rent "Sunrise Properties LLC" 1450.00 2026-10-01 monthly
homestead-ledger obligation list                                 # the list pane: payee, due date, cadence; the amount derives
homestead-ledger obligation show rent                            # the detail pane: the amount renders
homestead-ledger queue                                           # what's due
homestead-ledger transaction add 2026-08-01 -84.23 "Whole Foods Market" --account chk-main
homestead-ledger transaction list --account chk-main             # the books, through the gate — the account number is never a row
python -m homestead_ledger --import statement.csv --account chk-main   # a whole statement
homestead-ledger account add visa-chase --kind credit_card --number 4242
python -m homestead_ledger --import card.csv --account visa-chase \
  --liability-columns debit,credit                                     # a card statement
python -m homestead_ledger --import statement.csv --account chk-main --bank chase   # a slashed date column
homestead-ledger transaction list --account chk-main --gaps      # rows whose stored date predates this fix
python -m homestead_ledger                                       # the window, on these books (the demo only if empty)
```

Every imported row's date is parsed to ISO before it is ever written.
`--bank <name>` declares which day/month order *that statement's* date column
is written in (`wells-fargo`, `chase`, `bank-of-america`, `capital-one`,
`usaa`, `discover`, `amex`) and is tried **first**, so the operator's own
declaration is never overruled by a guess from somewhere else; a cell that
does not fit it still parses if it is unambiguous on its own (`2026-08-01`,
`August 1, 2026`, …). A slashed, ambiguous date (`08/01/2026`) with no bank
named is a per-row import error, never a guess, and a refusal names the field
rather than echoing the cell. This is what
lets the same transaction imported once as `08/01/2026 --bank chase` and once
as `2026-08-01` dedup as the same row. **There is no migration** for a
transaction already on the books from before this fix with an unparsed,
slashed date (v1's own books are synthetic-only) — such a row keeps its old
date text, will not dedup against a re-import in the new ISO form, and
`transaction list --gaps` is how an operator finds it.

## Accounts

**An account number lives in exactly one record (decision 9, provisional
I-43).** Before a household can post a transaction, it registers the real
account it belongs to — `account add <label> --kind checking --number 9821`
— once. `<label>` is the household's own short name for that one real
account (`chk-main`, `visa-chase`): lowercase letters, digits and hyphens,
never a registered kind name (`checking`, `savings`, `credit_card`, `loan`)
and never the bank-issued number itself, so a label can never be mistaken
for a kind. `--kind` says which registered kind the account is; `--number`
is its bank- or issuer-assigned identifier, sealed **L5** and never shown
again on any surface — the CLI, the browser, or an export — once it is
stored. Optional fields (`--institution`, `--opened`, `--balance-as-of`,
`--rate`, `--limit`, `--payment-due-day`, `--min-payment`) are written only
when given; the browser's number field is ordinary text with
`autocomplete="off"` — never a password field: it is typed once and never
shown again, so masking it would hide the one look the operator gets at a
value nothing can check afterwards, while `autocomplete` off is what keeps
the browser from storing it and offering it back on some other form.
`account list` shows every label with its kind and institution,
`account show <label>` opens one (the number always reads `(sealed)`), and
`--replace` is how a second `add` under the same label is meant.

Every transaction is filed under a label from then on — `transaction add …
--account chk-main`, `--import FILE --account chk-main` — and its kind is
looked up from the instance, never retyped. `--account-number` and `--kind`
are retired from `transaction add` and `--import`: an unrecognized flag is
refused by name, pointing at `account add`, rather than silently ignored.
There is **no migration** for rows a household already imported before this
change. Those rows keep their own `account_number` record — and they are
filed under the account *kind* as their matter (`checking`), because that is
what `account` meant then. A label may never equal a kind name, so no
instance can ever be registered that reaches them: they stay on disk,
unread, and `transaction list --account checking` says so by name rather
than reporting an empty account. Re-importing the same statement under a
registered label writes the rows again under the label — the same
fingerprint, a different matter — so the old rows and the new ones sit side
by side. v1's books are synthetic-only, and a migration that guessed which
real account a kind-named matter meant would be the household's own record
edited by the tool that is supposed to mirror it.

## Marking an obligation paid

```bash
homestead-ledger obligation paid rent --account chk-main --fingerprint a1b2c3      # today
homestead-ledger obligation paid rent --account chk-main --fingerprint a1b2c3 --on 2026-08-07
homestead-ledger obligation paid rent --account chk-main --fingerprint a1b2c3 --replace
```

`cadence` (`homestead_ledger/cadence.py`) is now a closed set —
`weekly`/`biweekly`/`monthly`/`quarterly`/`yearly`/`once` — and `add_obligation`
refuses anything outside it by name; the server's `<select>` and the CLI's own
help text both list the set from `cadence.CADENCES`, never a copy typed a
second time. ~~Earlier, nothing held `cadence` to anything, because nothing
yet rolled a due date forward by it.~~

`obligation paid <id> --account <label> --fingerprint <fp> [--on YYYY-MM-DD]
[--replace]` (and the browser's *Mark an obligation paid* form) writes a
reference — the labeled account and the transaction's fingerprint, never an
amount — under `(obligations, "paid_by", "<id>.<paid-on>")`, then advances the
obligation's `due_date` by its cadence (`cadence.roll_forward`, which walks
forward from the *due* date, never from the day it was paid).

**A month-end obligation keeps its day.** `add_obligation` records the first
due date's day of month as the obligation's anchor (`(obligations,
"due_day", "<id>")`) and every roll clamps against *that*, so rent due the
31st paid on time each month goes 31 → Feb 28 → **Mar 31** → Apr 30 → **May
31** instead of drifting to the 28th and staying there. The anchor is the
day of month, not "the last day of the month": an obligation due the 30th
stays on the 30th. An obligation written before the anchor existed has none;
it falls back to whatever day its due date currently holds, and
`obligation add --replace` is how to restore it.

**A back-dated payment is recorded, and moves nothing.** `obligation paid
--on <an older date>` than a payment already on file writes its `paid_by`
record and leaves the schedule alone: a due date advances once per *period*,
not once per receipt.

A `once` obligation has no next date: it is marked `resolved` instead, and
`queue`/`/api/queue` stop surfacing it (`obligation show` still reads it —
nothing is deleted). A second `obligation paid` for the same id and date is
refused (`--replace` to record it again) the same way a second `obligation
add` under an occupied id is.

`obligation list` and the Records tab mark a paid obligation `paid ✓ <date>`
by reference — but only while that payment is an answer: once the next due
date arrives, or if the payment on file predates the period now open, the
row reads `last paid <date>` with no tick. A ledger may say "there is a
payment on file" or "this period is paid"; it must never say the second
when it means the first.

An obligation is one record per field at the pack's rungs
(`homestead_ledger/obligations.py`), under the household's own short id
(lowercase letters, digits and hyphens — `rent`, `car-insurance`), which is
what the queue carries; a second `add` under an id already on file is refused
by the store itself, not by a check that another writer could have raced, and
`--replace` is how you mean it; a transaction is grown onto the read-only canonical
books through `books.import_transaction`, the one writer — entered once,
refused on re-entry, never edited ("mirror, not judge"). The browser UI (`ui`)
has a *Records* tab with both forms and both lists, an *Intake* tab that
extracts amounts, dates, merchants and due dates from a pasted bill or receipt
and fills a form with one click, the *Queue*, and *Subscriptions* — the
recurring-charge pass over the real books. Merchant resolution, reconciliation
and the ledger check need `pip install 'homestead-ledger[entity]'` and say so
when it is missing. `--account` names a registered account **instance** — a
label, added with `account add` — never a bare kind name; an unregistered
label is refused rather than quietly grown. An amount is signed from the household's own side on
every kind — money leaving is negative, money arriving is positive — so on a
credit card or a loan a charge is negative and a payment positive, and the
running balance is read back as what is *owed* (`balance.running_balance(...,
liability=True)`). A card or loan statement whose columns are a `Debit`/`Credit`
split is refused unless `--liability-columns CHARGE,PAYMENT` says which column
means which: an issuer's own column names do not say, and guessing would
misstate a debt.

## Tagging a transaction

The books are read-only ("mirror, not judge") — a household still wants to
say things *about* one transaction without ever touching the row itself:
`transaction tag <fingerprint> [--category C] [--note N] [--merchant M]
[--do-not-use] [--replace]` (the browser has the same four fields, on the
Records tab). The fingerprint is what `transaction add`/`--import` already
print and `transaction list` already shows by reference — a transaction must
already be on the books before it can be tagged, and an unknown fingerprint
is refused by name, never by echoing what a lookup happened to find. The
whole fingerprint or a prefix of it (the twelve characters `transaction list`
prints) both work; a prefix that names two rows is refused rather than
resolved to one of them, and the record is keyed by the whole fingerprint
whatever was typed.

- **`--category`** is a short, closed-shape word (lowercase letters, digits
  and hyphens — `groceries`, `medical-copay`): **L3**, so an ordinary one
  renders on the list. A category whose text *contains* a word from a closed,
  hand-reviewed list — health and care, legal process, insolvency, family,
  belief, association, political activity, immigration status; the list
  itself is `PROTECTED_CATEGORY_WORDS` in `homestead_ledger/packs/overlay.py`
  and is the one copy — is written at **L4** instead, automatically: the list
  renders "a category is on file" rather than the word itself, and the real
  word is there only once the transaction's detail is opened. Matching is
  substring, not whole-word, so it over-classifies and never under-classifies.
  **This advisory only ever raises a category's rung, never lowers one** —
  there is no path that takes an already-flagged category back down, the same
  "argue up, never down" rule the engine's own content-shape advisory follows.
- **`--merchant`** confirms a resolved payee name (L3, renders).
- **`--note`** is free text (L4 always — open text can name anything, so it
  is classified at the ceiling from the start, unlike `--category`'s floor):
  it derives ("a note is on file") on the transaction list and renders only
  once the transaction's own detail is opened.
- **`--do-not-use`** (L2) excludes the transaction from the recurring-charge
  pass, from a budget envelope, and — once built — from every sync envelope
  and export: a household's own transfer, a duplicate import, or a row that
  should never shape a pattern. It marks by reference on the list (a
  `do-not-use` flag), never a value read off the field. Transfers and the
  budget pass are later consumers of this same exclusion. It is set, never
  cleared: there is no un-tag path yet, and a `--do-not-use` passed as false
  is refused rather than quietly ignored.

Each of the four fields is its own record, independently gated (I-9): setting
`--category` today does not occupy `--note` for next month, and re-tagging an
already-tagged field needs `--replace` to say so explicitly. A tag never
rewrites, reorders, or removes the transaction it describes.

## Exporting your liabilities

`homestead-ledger schedules show` lists every liability account instance —
`credit_card`, `loan` — on the household's own screen: `checking` and
`savings` never appear here, and the amount fields derive (`"a balance is
on file"`), never the number. `homestead-ledger schedules export [--out
DIR]` composes the same instances into one JSON document — the amounts
themselves this time, plus the date each account was opened, never the
number, and a field that is not on file is left out rather than written
as a null somebody could read as a zero — shows exactly what will be
written, and writes nothing until that is confirmed: a declined
confirmation writes no file, and ledgers nothing either. `DIR` must be
an absolute path under the household root: a relative one means a
different place from every working directory, and the engine will not
create a directory outside the root at all — the document is written
inside the root and you copy it out from there. Both are refused by
name, with nothing written and nothing ledgered. It goes out
through the engine's own `export.export_record` (one artifact, one
`IntegrityLog` row, one `VisibleLog` line, all references and never
content), the same machinery every export on this face uses rather than a
second one built here. `GET /api/schedules` in the browser reads the same
derived-amount rows `schedules show` prints; there is **no export door on
the server** — an export is an operator act at the terminal, confirmed
there, never a click in the browser.

Every export carries this notice, verbatim:

> A list of the household's liabilities as the ledger holds them, for the household's own use. It is not a schedule on any official form, it carries no form number, and the Chapter 13 plan payment is an ordinary obligation here, not a claim.

The Chapter 13 plan payment itself is an ordinary obligation
(`obligation add rent …`-shaped, at the pack's own `L4`) — this module
tracks what a household owes and nothing about a bankruptcy case, a
claim, or a filing (provisional I-44: no drafting, no filing, no official
form language anywhere in this package — `tests/test_i44_no_drafting.py`).

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

Apache-2.0.
