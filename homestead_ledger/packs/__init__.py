"""homestead-ledger's schema packs — closed, classified-at-import field lists.

Mirrors `homestead_law.packs`: a pack declares an account kind's fields and
their rungs (`homestead.keep.rungs.classify_schema`, run at module import), so
an unclassified field is a build failure rather than a runtime surprise.
`checking`, `savings`, `credit_card` and `loan` are the four account packs
built so far (bites 1 and 2a) — each declares the same four transaction
fields at the same settled rungs (`date` L2, `description` L3, `amount` L4,
`account_number` L5), plus whatever extra fields its own statement shape
needs (`loan`'s `principal`/`interest`). Each also declares `LIABILITY`: a
bool, read live by `registry.AccountType.liability`, that says which side of
the household's sign convention the kind is on — `amount` (and, for a
liability kind, a servicer's split `principal`/`interest`) is signed from the
household's own side everywhere: money leaving is negative, money arriving is
positive; on a liability kind that is "a charge is negative, a payment or
credit is positive," and its running balance is reported as *owed*
(`balance.running_balance`). `obligations` is bite 2's schema for a recurring
household bill — one schema for every obligation kind (rent, insurance, a
subscription), the way each account pack is one schema for every transaction
its own kind of account holds.
"""
