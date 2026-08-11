"""Transaction identity — a content fingerprint, not an incrementing id.

The build plan's decision: a transaction's identity is `sha256(date, amount,
description, account)`. Re-importing the same bank statement twice — the
ordinary case, not the exceptional one, since a household re-downloads
overlapping date ranges constantly — must compute the *same* id both times, so
`books.import_transaction`'s refusal on an occupied key (I-9) is what makes
re-import idempotent rather than duplicative. Nothing here writes anything;
this module only names a transaction.

The four components are joined with a separator that cannot appear in any of
them by construction (`\\x1f`, ASCII unit separator — not a character a date,
an amount, a description or an account name would ever legitimately contain),
so `("1", "23")` and `("12", "3")` fingerprint differently. A bare
concatenation would not have that property.
"""
from __future__ import annotations

import hashlib

__all__ = ["fingerprint"]

_SEP = "\x1f"


def fingerprint(*, date: str, amount: str, description: str, account: str) -> str:
    """The content fingerprint for one transaction — a sha256 hex digest.

    All four arguments are keyword-only so a call site cannot transpose two
    same-typed strings (`amount` and `description` are both plain text) and
    get a fingerprint that is wrong but looks fine.
    """
    basis = _SEP.join((date, amount, description, account))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
