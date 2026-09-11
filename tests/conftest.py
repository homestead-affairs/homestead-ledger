"""Shared test fixtures.

Bite 2b's account instances (`accounts.py`) mean a transaction can no longer
be posted, or a statement imported, against a bare kind name — every test
that used to write `account_number="9821"` and rely on the implicit
`checking` default now needs a registered account *instance* first. This
fixture is the one place that setup lives, rather than copy-pasted into
every test file the change touches.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def make_account():
    """`make_account(kind, *, number="9821", label=None) -> label`.

    Writes the instance through the real `accounts.add_account`, into
    whatever `Sidecar`/`HOMESTEAD_HOME` is bound when it is *called* — the
    caller's own `monkeypatch.setenv("HOMESTEAD_HOME", …)` must already have
    run, exactly as every other store-touching fixture in this suite
    requires. `label` defaults to `f"{kind}-t"`, distinct from every
    registered kind name (I-43's own refusal would catch a collision) and
    short enough to read in a failure message.
    """
    from homestead_ledger import accounts
    from homestead_ledger.store import Sidecar

    def _make(kind: str, *, number: str = "9821", label: str | None = None) -> str:
        # A default label from the kind's own name: hyphenated, never an
        # underscore (the id shape has no underscore — `credit_card` becomes
        # `credit-card-t`).
        label = label or f"{kind.replace('_', '-')}-t"
        accounts.add_account(Sidecar(), label, kind=kind, number=number)
        return label

    return _make
