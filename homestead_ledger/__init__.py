"""homestead-ledger — the household's own books, on the shared homestead engine.

Mirror, not judge: this module reflects the household's money. It never edits a
transaction and never authors a financial judgment — the record layer is the
engine's (`homestead.keep`, published as `homestead-affairs`), and the app writes
only to the sidecar overlay.
"""
