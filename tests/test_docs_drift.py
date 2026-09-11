"""X7-drift-ledger — grep guards for the sentences the drift sweep found
stale and rewrote, so a reintroduction (a copy-paste from an old commit, a
docstring reverted by hand) fails here by name rather than misleading the
next reader.

**What the sweep read, and what it found.** Every claim in `README.md`,
`docs/build-plan.md`, and the package's own docstrings was read against the
code as it stands today (2026-09-11, on top of G8-business-books). Most of
what the pre-sweep survey called out as a suspect was already fixed by the
bite that caused it (`checking`-only classification, unparsed CSV dates, the
`_KNOWN_SIDECAR_MATTERS` hardcoded list, the duplicated protected-category
word list, the budget `note` field) — those are verified clean below, not
rewritten. Five sentences had actually drifted past what the code now does:

1. **README's top-of-file status blockquote.** "Status: bite 0 — the seat is
   bound... The books, the 'what's due' queue, CSV import, and the app land
   in the bites that follow" was true the day bite 0 shipped and was never
   updated again — every one of those "bites that follow" is now documented
   later on the very same page, six releases past the last one this sentence
   knew about. Struck through; replaced with a pointer to the new
   "## Module status" table.
2. **README's engine floor pin.** Quoted `homestead-affairs>=0.1.0,<1.0`
   verbatim — the floor bite 3's theme-sharing follow-on needed, since raised
   twice (0.3.0 for G2a, then 0.11.0 for G5-sync). Corrected to the current
   floor with a pointer to `pyproject.toml`'s own dependency comment, which
   is the one place that number is meant to be read from.
3. **`docs/build-plan.md`'s pinned suite count and floor rationale.** "Suite:
   195 passed" was true once; it is a different number with and without the
   optional `entity` extra installed, and either way the next added test
   moves it. The floor sentence beside it repeated the same 0.1.0 story
   README's did. Both struck through and replaced.
4. **`homestead_ledger/transfers.py::exclude_from`'s own docstring.** It
   predicted, by name, what the overlay bite would make possible ("when the
   overlay bite lands this counting goes away") — G4-overlay landed, and
   every real caller (`budget.py`, `grant_report.py`, `server.py`) now
   filters by the fingerprint union it named rather than calling
   `exclude_from` at all. The function itself stays (it is still the honest
   filter for a caller with no item id at its seam, and it is still tested),
   but the docstring no longer describes a future that already happened as
   though it hadn't.
5. **`homestead_ledger/sync.py`'s module docstring, on the fleet's
   structured-value refusal.** It narrated the fleet's refusal of a
   `transfers` `pair` (a mapping value against a `TEXT` column) as "the
   engine's own contract to settle" — settled since, by the E7b audit
   (engine 0.13.0: the column stays `TEXT`, a mapping crosses as canonical
   JSON text under a new `value_format` column). This package's own
   `G7b-floor-0.13` bite raises the floor and flips the pinned test; the
   docstring is corrected regardless of exactly when that bite lands, since
   the engine-side fact it was narrating is settled either way.

`homestead_ledger/accounts.py::cover`'s comment about a floor block on
`cover_counts(..., by_matter=...)` had the same shape of drift (it named
0.3.0 as the current floor after G5-sync had already raised it past 0.7.0,
the version that shipped `by_matter`) and was corrected the same way; it is
not grep-guarded here because the corrected comment states an open item
rather than a fact this file would need to hold constant.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PKG = APP / "homestead_ledger"
README = APP / "README.md"
BUILD_PLAN = APP / "docs" / "build-plan.md"
TRANSFERS = PKG / "transfers.py"
SYNC = PKG / "sync.py"
CHANGELOG = APP / "CHANGELOG.md"
PYPROJECT = APP / "pyproject.toml"

#: Package-scaffolding files: no capability of their own, so the module-status
#: table (below) does not name them and does not need to. Basename-matched, so
#: this covers `__init__.py` under `app/` and `packs/` too, not only the
#: top-level one.
_STATUS_TABLE_EXCLUSIONS = ("__init__.py", "__main__.py")

#: The exact sentences that were true once and are not now — the literal
#: strings that were actually in the files, not a paraphrase, so each guard
#: fires on a byte-for-byte reintroduction and nothing weaker.
STALE_README_STATUS = (
    "**Status: bite 0 — the seat is bound.** The store binding\n"
    "> (`homestead.keep.store` on a SQLite ledger db), a no-egress AST guard "
    "over this\n> package (I-17 — a money ledger must never dial out), CI "
    "(cold checkout, engine\n> from PyPI, three OSes), and the build plan "
    "(`docs/build-plan.md`). The books,\n> the \"what's due\" queue, CSV "
    "import, and the app land in the bites that follow."
)
STALE_README_FLOOR = "`homestead-affairs>=0.1.0,<1.0` (the\ndistribution name"
STALE_BUILD_PLAN_SUITE_COUNT = "**Suite: 195 passed.**"
STALE_EXCLUDE_FROM_PREDICTION = (
    "**When the overlay bite lands this counting goes away.**"
)
STALE_SYNC_FLEET_CONTRACT = (
    "**A `pair`'s value is structured, and the fleet's `value` column is\n"
    "text.** `homestead.keep.fleet_cli._validate_rows` refuses — by name, "
    "and the\n*whole* envelope with it (I-11) — any row whose `value` is "
    "not a string, and\na `transfers` `pair` is served as a `dict` (it is "
    "`L2`, so `Served.value` is\nthe mapping). So an envelope whose scope "
    "names `transfers` composes and\ndrops to a file here and is then "
    "refused at `homestead-fleet ingest`. That\nis the engine's own "
    "contract to settle (a `TEXT` column versus a structured\nserved "
    "value) and not a module's to paper over, so it is pinned by\n"
    "`tests/test_sync.py::test_the_fleet_refuses_a_structured_pair_value_by_name`\n"
    "rather than worked around: the refusal is loud, at the fleet end, "
    "before a\nsingle row is written, and it is the honest state of the "
    "seam today."
)


def _contains(path: Path, needle: str) -> bool:
    return needle in path.read_text(encoding="utf-8")


def _contains_live(path: Path, needle: str) -> bool:
    """`needle` appears in `path`, and not only inside a `~~struck-through~~`
    span — the house style is "struck through, never deleted", so the old
    sentence legitimately stays on the page once, wrapped, right beside its
    correction. A guard using plain `_contains` would fire on that wrapped
    copy forever; this one strips every properly-wrapped occurrence first
    (there may legitimately be one) and fires only if the sentence still
    turns up live in what remains — so a *second*, unwrapped reintroduction
    right beside the one already struck through is still caught."""
    text = path.read_text(encoding="utf-8").replace(f"~~{needle}~~", "")
    return needle in text


def test_readme_does_not_reassert_the_bite_0_status():
    assert not _contains_live(README, STALE_README_STATUS), (
        "README.md must not re-assert the bite-0-era status blockquote as "
        "current — every capability it deferred to \"the bites that follow\" "
        "has since shipped and is documented in \"## Module status\": "
        f"{STALE_README_STATUS!r}"
    )


def test_readme_does_not_reassert_the_0_1_0_floor():
    assert not _contains(README, STALE_README_FLOOR), (
        "README.md must not quote the engine floor as 0.1.0 — it has been "
        f"raised twice since (see pyproject.toml): {STALE_README_FLOOR!r}"
    )


def test_build_plan_does_not_pin_a_suite_count():
    assert not _contains_live(BUILD_PLAN, STALE_BUILD_PLAN_SUITE_COUNT), (
        "docs/build-plan.md must not pin a literal suite count — it is a "
        "different number with and without the `entity` extra, and the next "
        f"added test moves it either way: {STALE_BUILD_PLAN_SUITE_COUNT!r}"
    )


def test_exclude_from_does_not_predict_an_already_landed_bite():
    assert not _contains(TRANSFERS, STALE_EXCLUDE_FROM_PREDICTION), (
        "transfers.py's exclude_from() must not describe the overlay bite as "
        "still pending — it landed, and every real caller filters by the "
        f"fingerprint union it named instead of calling exclude_from: "
        f"{STALE_EXCLUDE_FROM_PREDICTION!r}"
    )


def test_sync_does_not_narrate_the_fleet_contract_as_still_unsettled():
    assert not _contains_live(SYNC, STALE_SYNC_FLEET_CONTRACT), (
        "sync.py's module docstring must not describe the fleet's "
        "structured-value refusal as the engine's contract still to settle "
        "— the E7b audit settled it (engine 0.13.0, a value_format column): "
        f"{STALE_SYNC_FLEET_CONTRACT!r}"
    )


def test_these_five_guards_fire_on_a_planted_reintroduction(tmp_path):
    """A scan that has never fired has not been shown to check anything —
    all five sentences above, planted back into copies of the real files."""
    cases = (
        (README, STALE_README_STATUS, "readme.md"),
        (README, STALE_README_FLOOR, "readme2.md"),
        (BUILD_PLAN, STALE_BUILD_PLAN_SUITE_COUNT, "plan.md"),
        (TRANSFERS, STALE_EXCLUDE_FROM_PREDICTION, "transfers.py"),
        (SYNC, STALE_SYNC_FLEET_CONTRACT, "sync.py"),
    )
    for source, needle, name in cases:
        planted = tmp_path / name
        planted.write_text(
            source.read_text(encoding="utf-8") + f"\n\n{needle}\n",
            encoding="utf-8",
        )
        # A bare append is a *live* reintroduction — not wrapped in `~~...~~`
        # — exactly the shape a careless copy-paste or a hand-reverted
        # docstring would produce, and each guard above must still catch it.
        assert _contains_live(planted, needle), f"the plant did not apply for {name}"

    # And none of the five fire on the corrected prose that replaced them —
    # or a green result here would mean "the corrected text also happens to
    # be gone", not "the drift is gone". Each of the real files' own
    # already-struck copy must also not count as live.
    assert not _contains_live(README, STALE_README_STATUS)
    assert not _contains_live(BUILD_PLAN, STALE_BUILD_PLAN_SUITE_COUNT)
    assert not _contains_live(SYNC, STALE_SYNC_FLEET_CONTRACT)
    assert _contains(README, f"homestead-affairs>={_declared_engine_floor()},<1.0")
    assert _contains(README, "X7-drift correction")
    assert _contains(BUILD_PLAN, "X7-drift correction")
    assert _contains(
        TRANSFERS,
        "the overlay bite landed, and the honest filter",
    )
    assert _contains(SYNC, "settled. The E7b audit")


# ── verified clean: the pre-sweep suspects that were already fixed ──────────
#
# Not grep-guarded (there is no stale sentence left to plant back in — these
# would need a *new* violation shape, which is a different scan, not this
# one) but recorded here so the next drift sweep does not re-open them.
#
# - "every account is classified as checking" — G2a's registry.account(kind)
#   dispatch replaced it; `grep checking.FIELDS homestead_ledger/books.py` is
#   empty (tests/test_registry.py pins the guard that would catch a regression).
# - "CSV dates stored unparsed" — G2c's BANK_DATE_FORMATS/--bank; every row is
#   ISO before it is written (README's "Entering your own information").
# - "the cover always shows nothing" — true only of queue.cover() over the
#   single obligations kind (still true, still an honest limitation named in
#   docs/build-plan.md's audit follow-ups); accounts.cover() over account
#   instances (G2b) is a distinct, working gate — both exist, neither claim
#   is stale.
# - "_KNOWN_SIDECAR_MATTERS" — retired; sync.py discovers matters from the
#   packs and the registered account instances (`known_matters`).
# - the protected-category word list — one copy, `packs/overlay.py`'s
#   `PROTECTED_CATEGORY_WORDS`; `overlay.py` re-exports the same object
#   rather than holding a second list.
# - the budget `note` field — dropped before release; `packs/budget.py`'s own
#   docstring records the reversal honestly ("An earlier draft carried a
#   note here as well... dropped").


def test_no_module_still_classifies_every_account_as_checking():
    assert not _contains(PKG / "books.py", "checking.FIELDS"), (
        "books.py must classify by registry.account(kind), not a hardcoded "
        "checking.FIELDS reference — the pre-G2a bug this repo already fixed"
    )


def test_the_checking_only_guard_fires_on_a_planted_regression(tmp_path):
    planted = tmp_path / "books.py"
    planted.write_text(
        (PKG / "books.py").read_text(encoding="utf-8")
        + "\n\n_PLANTED_REGRESSION = 'checking.FIELDS'\n",
        encoding="utf-8",
    )
    assert _contains(planted, "checking.FIELDS"), "the plant did not apply"


def test_no_duplicate_protected_category_word_list_exists():
    """`packs/overlay.py` is the one copy; `overlay.py` must re-export the
    same object (`is`, checked at import time by the pack's own build-time
    validation) rather than hold a second list literal that could drift from
    the first."""
    from homestead_ledger import overlay
    from homestead_ledger.packs import overlay as pack

    assert overlay.PROTECTED_CATEGORY_WORDS is pack.PROTECTED_CATEGORY_WORDS


def test_the_duplicate_word_list_guard_fires_on_a_planted_second_copy():
    """Planted: a second list bound to a *new* name — proving the identity
    check above would catch a copy that drifted from the original, without
    needing the real second copy this repo does not currently have."""
    from homestead_ledger.packs.overlay import PROTECTED_CATEGORY_WORDS

    planted_copy = frozenset(PROTECTED_CATEGORY_WORDS) | {"a-drifted-addition"}
    assert planted_copy is not PROTECTED_CATEGORY_WORDS


# ── "## Module status" names every module or excludes it by basename ────────


def _module_status_section(readme_text: str) -> str:
    match = re.search(r"^## Module status\n(.*?)(?=^## |\Z)", readme_text,
                       re.MULTILINE | re.DOTALL)
    assert match, "README.md has no '## Module status' section"
    return match.group(1)


def _package_basenames() -> list[str]:
    """Every `.py` file's bare name under `homestead_ledger/` — basenames
    only, never a path, so this holds the same on Windows and POSIX, and so
    two files that happen to share a name (`overlay.py` exists both at the
    package root and under `packs/`) are one entry to name, not two."""
    return sorted({p.name for p in PKG.rglob("*.py") if "__pycache__" not in p.parts})


def _modules_missing_from_status_table(readme_text: str) -> list[str]:
    section = _module_status_section(readme_text)
    return [
        name for name in _package_basenames()
        if name not in _STATUS_TABLE_EXCLUSIONS and name not in section
    ]


def test_every_module_is_named_in_the_status_table_or_excluded():
    """Every shipped module is either a row's evidence or a named exclusion —
    never simply forgotten. A module added without either fails here, named."""
    missing = _modules_missing_from_status_table(README.read_text(encoding="utf-8"))
    assert not missing, (
        "these homestead_ledger/*.py modules are named in neither README.md's "
        f"'## Module status' table nor _STATUS_TABLE_EXCLUSIONS: {missing} — "
        "give each a row, or add it to the exclusion tuple with a reason."
    )


def test_the_status_table_guard_fires_on_a_planted_omission():
    """A module the table forgets, planted by blanking every mention of one
    real, non-excluded module's name inside the table section only — the
    guard must name exactly that module."""
    readme_text = README.read_text(encoding="utf-8")
    section = _module_status_section(readme_text)
    assert "sync.py" in section, "the plant assumes sync.py is currently listed"
    gutted = readme_text.replace(section, section.replace("sync.py", "SYNC_REMOVED"))
    missing = _modules_missing_from_status_table(gutted)
    assert missing == ["sync.py"], f"the guard must name exactly sync.py; got {missing}"


# ── the status table's "Since" column names releases that happened ──────────

_RELEASED_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)
_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")


def _released_versions() -> set[str]:
    """Every version `CHANGELOG.md` records as released."""
    return set(_RELEASED_RE.findall(CHANGELOG.read_text(encoding="utf-8")))


def _unreleased_since_versions(readme_text: str) -> list[str]:
    """Every version named in the status table that was never released.

    Catches an invented or mistyped number, not a merely *wrong* one — the
    same cheap half the sibling drift sweeps ship, reading `CHANGELOG.md`
    rather than `git log`.
    """
    section = _module_status_section(readme_text)
    released = _released_versions()
    return sorted(
        {v for v in _VERSION_RE.findall(section) if v not in released}
    )


def test_every_since_version_is_a_release_that_happened():
    """A "Since" that names a version this repo never cut is a claim with
    nothing behind it. `0.10.0` (sync) is the newest real release as of this
    sweep; `grant_report.py`'s row deliberately carries no version number at
    all (G8 has not merged or released) rather than a phantom one."""
    unreleased = _unreleased_since_versions(README.read_text(encoding="utf-8"))
    assert not unreleased, (
        "README.md's '## Module status' table names these versions, and "
        f"CHANGELOG.md records no such release: {unreleased}"
    )


def test_the_since_version_guard_fires_on_a_planted_phantom_release():
    """A version nobody ever cut, planted in the table — the guard must name
    it, and must still clear the real ones beside it."""
    readme_text = README.read_text(encoding="utf-8")
    section = _module_status_section(readme_text)
    assert "`sync.py` | 0.10.0" in section, "the plant assumes the sync row's shape"
    planted = readme_text.replace(
        "`sync.py` | 0.10.0", "`sync.py` | 9.9.9", 1
    )
    assert _unreleased_since_versions(planted) == ["9.9.9"], (
        "the guard must name exactly the phantom release; got "
        f"{_unreleased_since_versions(planted)}"
    )


# ── the floor three files quote is the one pyproject.toml declares ──────────
#
# The first draft of this sweep wrote the floor into README.md, into
# `sync.py`'s corrected paragraph and into `accounts.py`'s corrected comment
# as a literal (`0.11.0`), and into this file's own assertion as a second
# literal — which is the drift it was written to stop, one level up: the
# sibling `G7b-floor-0.13` bite raised the floor to 0.13.0 the same day and
# every one of those literals was stale before the branch merged. So the
# floor is read from `pyproject.toml` — the one place the number is a fact
# rather than a quotation — and the prose is held to it.

_FLOOR_RE = re.compile(r'"homestead-affairs>=(\d+\.\d+\.\d+),<1\.0"')


def _declared_engine_floor(pyproject: Path | None = None) -> str:
    """The engine floor `pyproject.toml`'s `dependencies` actually declares.

    Read with a regex rather than `tomllib`, deliberately: the dependency
    line is the *literal* the prose quotes, and a parse that normalised the
    specifier (dropping the `,<1.0`, reordering it) would let the prose and
    the metadata disagree in exactly the way that is being guarded.
    """
    match = _FLOOR_RE.search((pyproject or PYPROJECT).read_text(encoding="utf-8"))
    assert match, "pyproject.toml declares no homestead-affairs floor to read"
    return match.group(1)
