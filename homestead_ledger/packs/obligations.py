"""The obligations pack — bite 2's schema, classified at **import**.

A recurring household obligation's four fields, each declared and classified
here rather than inferred from its name, exactly as `packs/checking.py` does
for a transaction. One schema covers every recurring obligation kind the
household holds — rent, insurance, property tax, vehicle registration, a
subscription — the same way `checking.py` is one schema for every checking
transaction. There is no per-obligation-kind pack; the kind (which bill this
is) is data (the `name` field and the item id it is stored under), not a
schema choice.

    payee / obligation name           → L3  (resolves to a party)
    amount tied to an obligation      → L4  (money category)
    due date                          → L2
    cadence (how often it recurs)     → L2

**Why `due_date` lands on L2, matching bite 1's `date` reasoning exactly.**
`packs/checking.py` classifies a transaction's posting date L2 because it
carries no identity and no protected category on its own (`Rung.L2`'s own
definition) and is never public the way a court calendar is. A due date on a
recurring household obligation is the same shape of fact — a household
schedule, not a public record — so the same reasoning gives the same answer.
Nothing about a due date raises it to L1 (it is posted nowhere public) or to
L3/L4 (it does not itself resolve to a party or carry a money category the
way `amount` does).

**Why `cadence` also lands on L2.** "Monthly" / "quarterly" / "annual" is
descriptive metadata about the household's own schedule — it carries no
identity and no protected category by itself, the same posture `due_date`
has. It is not `amount`'s domain (no money value) and not `name`'s (no
party), so it does not inherit either of their rungs.

**Why `amount` and `name` mirror `checking.py`'s `amount`/`description`
exactly.** An obligation's amount is tied to a specific bill the household
owes, the money category `homestead-rungs.md`'s table calls L4 outright — the
same worked example bite 1 already made concrete. `name` (the payee — "the
electric company", "the landlord") resolves to a party with no protected
category of its own, L3 for the same reason a transaction's payee is.

Each field is a mapping, not a bare rung, for the same reason `checking.py`'s
are: `classify_schema` reads the `"rung"` key and ignores the rest, so the
obligation kind and the justifying sentence travel with the rung as a
reviewable record.

**What this pack does not catch.** `classify_schema` checks that a rung was
*declared*, not that it fits its content — a payee name that happens to leak
a category (a clinic, a named person) is the same open question bite 1's
`checking.py` flags for `description` and does not close here either.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["OBLIGATION", "SCHEMA", "FIELDS"]

OBLIGATION = "obligations"


def _field(rung: Rung, why: str) -> dict[str, Any]:
    return {"rung": rung, "obligation": OBLIGATION, "why": why}


#: The closed obligation schema. Ordered by rung so the ladder reads down the
#: page, exactly as `checking.py`'s does.
SCHEMA: dict[str, dict[str, Any]] = {
    "due_date": _field(
        Rung.L2,
        "a due date alone carries no identity and no protected category "
        "(Rung.L2's own definition) — household schedule, never a public "
        "record the way a court calendar is. Matches packs/checking.py's "
        "`date` reasoning exactly; nothing about a due date argues L1.",
    ),
    "cadence": _field(
        Rung.L2,
        "how often the obligation recurs — descriptive metadata about the "
        "household's own schedule, the same posture `due_date` has: no "
        "identity, no protected category, and not itself a money value or "
        "a party name.",
    ),
    "name": _field(
        Rung.L3,
        "the payee/obligation name — resolves to a party (who is owed), no "
        "protected category of its own. The same posture "
        "packs/checking.py gives a transaction's `description`.",
    ),
    "amount": _field(
        Rung.L4,
        "an amount tied to an obligation is the money category: it "
        "identifies (this specific bill) and carries the category the "
        "household's finances are, the way packs/checking.py's `amount` "
        "does for a transaction. docs/homestead-rungs.md's money table "
        "classifies this L4 directly.",
    ),
}

#: Classified at import (I-11). Removing any field's rung above dies here,
#: naming the field, before this module can be imported by anything else.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
