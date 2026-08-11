"""The recurring-charge detector — pure, stdlib-only, `today`-injected.

Re-derived as knowledge from `safe-app-store/apps/private-ledger/src/
private_ledger/subscriptions.py` (`docs/build-plan.md`'s reuse map), not
copied: same pipeline, re-expressed against this bite's own interface and
without that module's dependence on a `category` field.

**CRITICAL — this module is a pure function over the data a caller already
has.** It takes plain `(date, amount, description)` tuples and an injected
`today`; it does not read `store`, `books`, or `balance`, does not reach a
`.payload`, imports nothing from `homestead` or `homestead_ledger`, and
imports no network module and calls no `eval`/`exec`/`__import__`. That is
not a style preference — it is what lets `tests/test_invariants_chokepoint.py`
and `tests/test_no_egress.py` stay green with **no change to either guard's
allow-list**: a module that never touches the store or a canonical payload
has nothing for either scan to catch.

Pipeline:
  1. Consider only outflows (`amount < 0`). Normalize the merchant from the
     description — lowercase, collapse whitespace, strip store numbers,
     ref/auth/confirmation codes, and embedded dates (`'NETFLIX #1234'` /
     `'NETFLIX 07/24'` → `'netflix'`).
  2. Exclude a housing/rent/mortgage/debt/loan payment — recurring, but not a
     subscription — by matching those words against the **description**
     (this module has no `category` field to check instead).
  3. Group by normalized merchant, then cluster within a group by amount
     tolerance (`max(5%, $1)`) so a price hike does not split one
     subscription in two. If no cluster alone qualifies, fall back to the
     whole merchant group as one variable/usage-metered subscription.
  4. Infer cadence from the median gap between sorted charge dates, bucketed
     to `weekly` / `monthly` / `quarterly` / `annual` (`docs/build-plan.md`'s
     cadence set — no `biweekly` bucket, unlike the predecessor). Require
     **≥3 occurrences** (**≥2 for annual**, where history is thin by nature).
  5. Score confidence by blending interval regularity and amount stability;
     drop anything below `min_confidence`.
  6. Derive `next_expected`, `monthly_equivalent`, `annualized`, and a status
     of `active` or `possibly_cancelled` (lapsed a full interval past when
     the next charge was expected).
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Sequence

__all__ = ["RecurringCharge", "normalize_merchant", "detect_recurring"]

# ── merchant normalization ───────────────────────────────────────────────────

_DATE_RE = re.compile(r"\b\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,4})?\b")   # MM/DD, YYYY-MM-DD, ...
_STORE_NUM_RE = re.compile(r"#\s*\w+")                              # '#1234'
_CODE_KW_RE = re.compile(
    r"\b(?:ref|auth|authorization|conf|confirmation|trace|txn|trans|invoice|inv|id|no)\b"
    r"[:#]?\s*\w*",
    re.IGNORECASE,
)

#: Recurring, but not a subscription (`docs/build-plan.md`'s exclusion set).
#: Matched against the raw description — this module has no `category`
#: field, unlike its private-ledger ancestor.
_EXCLUDED_DESCRIPTION_RE = re.compile(r"hous|rent|mortgage|debt|loan", re.IGNORECASE)

# ── cadence buckets (build-plan's set: no biweekly) ──────────────────────────

_CADENCE_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("weekly", 5, 9),
    ("monthly", 25, 35),
    ("quarterly", 80, 100),
    ("annual", 350, 380),
)
_MIN_OCCURRENCES = {"annual": 2}   # every other cadence defaults to 3
_DEFAULT_MIN_OCCURRENCES = 3

_DAYS_PER_YEAR = 365.25
_DAYS_PER_MONTH = _DAYS_PER_YEAR / 12.0

#: Fraction of amount variation above which a subscription is reported as a
#: range rather than a fixed amount.
_VARIABLE_AMOUNT_CV = 0.05
#: Confidence blend: interval regularity weighs more than amount stability —
#: a subscription's date is the stronger signal than its (sometimes usage
#: metered) price.
_INTERVAL_WEIGHT = 0.65
_AMOUNT_WEIGHT = 0.35


def normalize_merchant(description: str) -> str:
    """Collapse a raw statement description to a stable merchant identity.

    `'NETFLIX #1234'` and `'NETFLIX 07/24'` both become `'netflix'`: any
    token carrying a digit (a store number, an auth code, an embedded date)
    is dropped, and what remains is the alphabetic core of the name.
    """
    text = (description or "").lower()
    text = _DATE_RE.sub(" ", text)
    text = _STORE_NUM_RE.sub(" ", text)
    text = _CODE_KW_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9&\s]", " ", text)   # punctuation to spaces; keep '&'
    tokens = [t for t in text.split() if not any(ch.isdigit() for ch in t)]
    return " ".join(tokens).strip()


def _as_date(value: Any) -> date | None:
    """`value` as a `date`, or `None` if it is not one and does not parse as
    an ISO `YYYY-MM-DD` string. Never raises — an unparseable date on one
    transaction drops that transaction from consideration rather than
    failing the whole detection pass; the queue (`queue.py`) is where an
    unparseable date becomes a surfaced gap for a household's own
    obligations. A statement transaction with a bad date is simply not
    usable evidence here."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@dataclass(frozen=True)
class RecurringCharge:
    """One detected recurring charge — the public shape `detect_recurring`
    returns."""

    merchant: str
    cadence: str
    amount: float | None
    amount_range: tuple[float, float] | None
    occurrences: int
    last_charge: str
    next_expected: str
    monthly_equivalent: float
    annualized: float
    confidence: float
    status: str


@dataclass(frozen=True)
class _Charge:
    charge_date: date
    amount_abs: float


def _classify_cadence(median_gap: float) -> str | None:
    for name, lo, hi in _CADENCE_BUCKETS:
        if lo <= median_gap <= hi:
            return name
    return None


def _confidence(gaps: list[int], amounts: list[float]) -> float:
    """Blend interval regularity and amount stability into `0..1`."""
    if gaps:
        mean_gap = statistics.fmean(gaps)
        gap_cv = statistics.pstdev(gaps) / mean_gap if mean_gap else 1.0
    else:
        gap_cv = 1.0
    interval_score = max(0.0, 1.0 - gap_cv)

    mean_amt = statistics.fmean(amounts)
    amt_cv = statistics.pstdev(amounts) / mean_amt if mean_amt else 0.0
    amount_score = max(0.0, 1.0 - amt_cv)

    blended = _INTERVAL_WEIGHT * interval_score + _AMOUNT_WEIGHT * amount_score
    return max(0.0, min(1.0, blended))


def _cluster_by_amount(charges: list[_Charge]) -> list[list[_Charge]]:
    """Split a merchant's charges into amount clusters. Adjacent amounts
    within `max(5%, $1)` of one another stay together, so a price hike or FX
    drift does not fracture one subscription; genuinely distinct plans
    separate."""
    ordered = sorted(charges, key=lambda c: c.amount_abs)
    clusters: list[list[_Charge]] = [[ordered[0]]]
    for charge in ordered[1:]:
        reference = clusters[-1][-1].amount_abs
        tolerance = max(0.05 * reference, 1.0)
        if charge.amount_abs - reference <= tolerance:
            clusters[-1].append(charge)
        else:
            clusters.append([charge])
    return clusters


def _detect_one(charges: list[_Charge], merchant: str, today: date) -> RecurringCharge | None:
    """One set of same-merchant charges into a `RecurringCharge`, or `None`
    if they are too few or too irregular to call a subscription."""
    ordered = sorted(charges, key=lambda c: c.charge_date)
    dates = [c.charge_date for c in ordered]
    if len(dates) < 2:
        return None

    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    gaps = [g for g in gaps if g > 0]   # same-day duplicates contribute no interval
    if not gaps:
        return None

    median_gap = statistics.median(gaps)
    cadence = _classify_cadence(median_gap)
    if cadence is None:
        return None

    occurrences = len(dates)
    if occurrences < _MIN_OCCURRENCES.get(cadence, _DEFAULT_MIN_OCCURRENCES):
        return None

    amounts = [c.amount_abs for c in ordered]
    mean_amount = statistics.fmean(amounts)
    amount_cv = statistics.pstdev(amounts) / mean_amount if mean_amount else 0.0
    variable = amount_cv > _VARIABLE_AMOUNT_CV

    interval = int(round(median_gap))
    last_charge = dates[-1]
    next_expected = last_charge + timedelta(days=interval)

    # Lapsed: already a full interval past the next expected charge.
    status = "possibly_cancelled" if today > next_expected + timedelta(days=interval) else "active"

    return RecurringCharge(
        merchant=merchant,
        cadence=cadence,
        amount=None if variable else round(statistics.median(amounts), 2),
        amount_range=(round(min(amounts), 2), round(max(amounts), 2)) if variable else None,
        occurrences=occurrences,
        last_charge=last_charge.isoformat(),
        next_expected=next_expected.isoformat(),
        monthly_equivalent=round(mean_amount * _DAYS_PER_MONTH / median_gap, 2),
        annualized=round(mean_amount * _DAYS_PER_YEAR / median_gap, 2),
        confidence=round(_confidence(gaps, amounts), 3),
        status=status,
    )


def _detect_for_merchant(
    charges: list[_Charge], merchant: str, today: date, min_confidence: float,
) -> list[RecurringCharge]:
    """Detect subscriptions within one merchant. Amount clusters are tried
    first (two real plans at the same merchant separate cleanly); if no
    cluster qualifies, fall back to the whole group as one
    variable/usage-metered subscription."""
    found: list[RecurringCharge] = []
    for cluster in _cluster_by_amount(charges):
        charge = _detect_one(cluster, merchant, today)
        if charge is not None and charge.confidence >= min_confidence:
            found.append(charge)
    if not found:
        charge = _detect_one(charges, merchant, today)
        if charge is not None and charge.confidence >= min_confidence:
            found.append(charge)
    return found


def detect_recurring(
    transactions: Sequence[tuple[Any, float, str]],
    *,
    today: date,
    min_confidence: float = 0.5,
) -> list[RecurringCharge]:
    """Detect recurring charges in `transactions` — each a plain `(date,
    amount, description)` tuple; `date` is a `datetime.date` or an ISO
    `YYYY-MM-DD` string, `amount` is signed (negative = outflow). `today` is
    injected, not read from the clock, so the same transactions always yield
    the same detections (`today`-injected, per `docs/build-plan.md`).

    Deterministic: the result depends only on `transactions`, `today`, and
    `min_confidence`. Returns nothing this module was not handed — no store,
    no books, no balance are read.
    """
    groups: dict[str, list[_Charge]] = {}
    for entry in transactions:
        charge_date_raw, amount, description = entry
        if amount is None or amount >= 0:          # inflows and zeroes are not charges
            continue
        if _EXCLUDED_DESCRIPTION_RE.search(description or ""):
            continue                                 # housing/rent/mortgage/debt/loan
        merchant = normalize_merchant(description)
        if not merchant:
            continue
        parsed = _as_date(charge_date_raw)
        if parsed is None:
            continue
        groups.setdefault(merchant, []).append(_Charge(parsed, abs(float(amount))))

    charges: list[RecurringCharge] = []
    for merchant, group in groups.items():
        charges.extend(_detect_for_merchant(group, merchant, today, min_confidence))

    # Deterministic order: biggest annual commitment first, then merchant name.
    charges.sort(key=lambda c: (-c.annualized, c.merchant))
    return charges
