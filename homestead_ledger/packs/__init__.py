"""homestead-ledger's schema packs — closed, classified-at-import field lists.

Mirrors `homestead_law.packs`: a pack declares an account kind's fields and
their rungs (`homestead.keep.rungs.classify_schema`, run at module import), so
an unclassified field is a build failure rather than a runtime surprise.
`checking` is the one pack bite 1 builds — savings and credit-card accounts
are the next account kinds, not built here (the same "one pack proves the
seam" posture homestead-law took with custody alone).
"""
