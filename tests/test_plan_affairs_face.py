"""X7-drift-ledger — `docs/PLAN-affairs-face.md` may only strike a bite
through once it has actually landed, and the proof is a PR number **and** a
release version sitting right there in the text. A strikethrough with no
`#NN` beside it is exactly the wishful "surely this landed" this file exists
to forbid; a strikethrough with a PR number and no release is the subtler
version of the same claim — every bite here merged one PR ahead of the
release-please PR that actually cut its version, so "merged" and "shipped"
are two different facts and the face states both.

The other direction is guarded too: a face that silently drops a bite that
has *not* landed reads as if nothing is outstanding. The ledger bites the
Homestead · Affairs plan names are W0-LEDGER, G2a-account-packs,
G2c-importer-dates, G2b-account-instances, G3-cadence-paidby, G4-overlay,
G4-transfers, G4-budget, G4-schedules-export, G5-sync, G7b-floor-0.13,
G8-business-books and X7-drift-ledger; twelve have landed (G8 as #45 and
G7b as #47, both released together in 0.11.0, which #46 cut), and only
X7-drift-ledger has not — this bite cannot strike itself before its own PR
merges. All thirteen must be named here.

Every struck PR number is also cross-checked against this repo's own
`git log --first-parent`, so a number typed from memory fails rather than
reading as proof. That check skips itself where there is no usable history
to read (an sdist, a depth-1 checkout), because a guard that turns red on a
shallow clone gets deleted rather than fixed.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests._scans import terms_found

APP = Path(__file__).resolve().parent.parent
PLAN_FACE = APP / "docs" / "PLAN-affairs-face.md"

_STRIKE_RE = re.compile(r"~~(.*?)~~", re.DOTALL)
_PR_RE = re.compile(r"#\d+")
_RELEASE_RE = re.compile(r"released\s+\d+\.\d+\.\d+")

#: How far past a `~~...~~` span to look for its `(#NN, released ...)` tail —
#: generous enough for this file's longest struck bite's trailing note. The
#: window alone is *not* narrow enough on its own: two short struck lines a
#: few lines apart could otherwise let one borrow the other's evidence, so
#: the tail is cut at whichever comes first — this many characters, the end
#: of the paragraph, or the start of the next strikethrough.
_TAIL_WINDOW = 400

#: Every ledger bite the plan names, and whether it has landed. The unlanded
#: ones are the point: a face with no row for a bite is not a face that says
#: the bite has not started — it is one that has forgotten it.
LANDED_BITES = (
    "W0-LEDGER", "G2a-account-packs", "G2c-importer-dates",
    "G2b-account-instances", "G3-cadence-paidby", "G4-overlay",
    "G4-transfers", "G4-budget", "G4-schedules-export", "G5-sync",
    "G7b-floor-0.13", "G8-business-books",
)
UNLANDED_BITES = ("X7-drift-ledger",)


def _struck_blocks(text: str) -> list[tuple[str, str]]:
    """Every `~~...~~` span, paired with its own tail — where this file's
    convention puts `(#NN, released X.Y.Z — "...")`. The tail stops at the
    paragraph break or the next strikethrough, whichever is nearer, so no
    bite can borrow its neighbour's evidence."""
    matches = list(_STRIKE_RE.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        stop = min(m.end() + _TAIL_WINDOW, len(text))
        if i + 1 < len(matches):
            stop = min(stop, matches[i + 1].start())
        paragraph_end = text.find("\n\n", m.end())
        if paragraph_end != -1:
            stop = min(stop, paragraph_end)
        blocks.append((m.group(1), text[m.end():stop]))
    return blocks


def _strikes_missing_evidence(text: str) -> list[str]:
    """Every struck bite whose tail does not carry both a PR number and a
    release version, named by what it is missing.

    There is no second accepted shape. G9d-inline-scans proposed one -- a
    branch striking an open item *it* recorded, with "PR number filled in by
    the orchestrator" in place of the number -- and it was refused on audit
    (2026-09-11): an exemption keyed on a phrase is an exemption any future
    sweep can type, and "a document does not mark its own landing" is the
    whole rule this file is. A bite that closed an open item on its branch
    leaves the bullet **unstruck** with a dated "built on <branch>" note, and
    a `docs:` follow-up strikes it once the PR number and the release exist
    -- the same course `homestead-law` took for the identical case on the
    same day."""
    missing = []
    for struck, tail in _struck_blocks(text):
        lacks = []
        if not _PR_RE.search(tail):
            lacks.append("PR number")
        if not _RELEASE_RE.search(tail):
            lacks.append("release version")
        if lacks:
            missing.append(f"{struck.strip()[:60]!r} lacks {lacks}")
    return missing


def _bites_struck_through(text: str, names: tuple[str, ...]) -> list[str]:
    """Which of `names` appear inside a `~~...~~` span."""
    struck_text = "\n".join(struck for struck, _ in _struck_blocks(text))
    return [name for name in names if name in struck_text]


def test_every_struck_bite_names_a_pr_number_and_a_release():
    """The house rule, run for real: a strikethrough without a PR number and
    a release version right after it is not proof anything shipped."""
    text = PLAN_FACE.read_text(encoding="utf-8")
    assert _struck_blocks(text), "docs/PLAN-affairs-face.md has no struck-through bites yet"
    missing = _strikes_missing_evidence(text)
    assert not missing, (
        "these struck-through bites in docs/PLAN-affairs-face.md do not carry "
        f"their evidence in the text right after the strikethrough: {missing}"
    )


def test_the_evidence_guard_fires_on_a_strikethrough_missing_either_half(tmp_path):
    """A scan that has never fired has not been shown to check anything. Two
    plants, one per half — a struck bite with a release and no PR number, and
    one with a PR number and no release — so neither half of the rule can be
    dropped without this failing."""
    planted = tmp_path / "PLAN-planted.md"
    planted.write_text(
        "~~a bite claimed landed~~ (released 9.9.9, but the PR number was forgotten)\n"
        "\n"
        "~~a bite claimed shipped~~ (#99 — merged, but it has not been released)\n"
        "\n"
        "~~a bite that really landed~~ (#98, released 9.9.8 — both halves present.)\n",
        encoding="utf-8",
    )
    missing = _strikes_missing_evidence(planted.read_text(encoding="utf-8"))
    assert len(missing) == 2, f"both defective strikes must be named; got {missing}"
    assert "PR number" in missing[0] and "release version" in missing[1], missing
    assert "really landed" not in "".join(missing), (
        "and the well-formed strike must not be reported, or the guard is "
        "crying wolf on the shape it exists to accept"
    )


def test_a_branch_may_not_strike_the_open_item_it_closed_itself(tmp_path):
    """Planted: the exemption this guard refused. A bite that closed an open
    item *it* recorded, striking it on its own branch with "PR number filled
    in by the orchestrator" where the number belongs, still claims a landing
    the tree cannot show -- so it is reported, exactly like any other strike
    missing its evidence. The honest shape (left unstruck, with a dated
    "built on <branch>" note) is planted beside it and must not be."""
    planted = tmp_path / "PLAN-planted.md"
    planted.write_text(
        "~~an open item this branch closed~~ (closed by G9d-inline-scans "
        "(this branch; PR number filled in by the orchestrator))\n"
        "\n"
        "- **an open item this branch built** (2026-09-11: built on "
        "`claude/ledger-inline-scans`; the orchestrator strikes it with the "
        "PR number and the release.)\n",
        encoding="utf-8",
    )
    missing = _strikes_missing_evidence(planted.read_text(encoding="utf-8"))
    assert len(missing) == 1 and "PR number" in missing[0] and "release version" in missing[0], (
        "a self-closure strike names neither a PR nor a release and must be "
        f"reported for both; got {missing}"
    )
    assert "built" not in "".join(missing), (
        "the unstruck note is not a strike and must not be reported at all"
    )


def test_the_two_g9d_open_items_are_named_and_unstruck():
    """The refusal, held against the real document. The inline-scan and
    duplicated-chokepoint items were built on `claude/ledger-inline-scans`
    and have no PR number and no release, so they stay named and unstruck
    until a `docs:` follow-up carries both."""
    text = PLAN_FACE.read_text(encoding="utf-8")
    struck = "\n".join(struck for struck, _ in _struck_blocks(text))
    for item in ("Inline scans the meta-scan cannot see",
                 "Duplicated chokepoint scans"):
        assert item in text, f"{item!r} is an open item and must stay named"
        assert item not in struck, (
            f"{item!r} is struck through with no PR number and no release: a "
            "document does not mark its own landing"
        )


def test_every_ledger_bite_the_plan_names_has_an_entry():
    """Landed or not, each one is named. The unlanded ones are how a reader
    tells "nothing outstanding" from "nobody wrote it down"."""
    text = PLAN_FACE.read_text(encoding="utf-8")
    all_bites = LANDED_BITES + UNLANDED_BITES
    named = set(terms_found(text, all_bites))
    absent = sorted(set(all_bites) - named)
    assert not absent, (
        "these ledger bites are named in the Homestead · Affairs plan and "
        f"nowhere in docs/PLAN-affairs-face.md: {absent}"
    )


def test_no_unlanded_bite_is_struck_through():
    """The wishful strike, held against the one bite that has not landed:
    this one, which cannot strike itself before its own PR merges."""
    text = PLAN_FACE.read_text(encoding="utf-8")
    wishful = _bites_struck_through(text, UNLANDED_BITES)
    assert not wishful, (
        f"{wishful} have not landed and must not be struck through — a face "
        "that strikes a bite before its PR merges is the drift this file guards"
    )
    # And the landed ones are struck, or the check above proves nothing: a
    # file with no strikethroughs at all would pass it trivially.
    assert _bites_struck_through(text, LANDED_BITES) == list(LANDED_BITES)


def test_the_wishful_strike_guard_fires_on_a_planted_early_strikethrough(tmp_path):
    """Planted: the unlanded G8 bite struck through, exactly as an
    over-eager follow-up commit would leave it once the release-please PR
    merges. The guard must name it."""
    planted = tmp_path / "PLAN-early-strike.md"
    planted.write_text(
        PLAN_FACE.read_text(encoding="utf-8").replace(
            "**X7-drift-<repo>**",
            "~~**X7-drift-ledger**~~ (#99, released 9.9.9)",
            1,
        ),
        encoding="utf-8",
    )
    text = planted.read_text(encoding="utf-8")
    assert _bites_struck_through(text, UNLANDED_BITES) == ["X7-drift-ledger"], (
        "the plant did not apply, or the guard cannot see a struck bite name"
    )


# ── every struck PR number is a merge this repo's history records ───────────


def _struck_pr_numbers(text: str) -> list[str]:
    """Every `#NN` in a struck bite's own evidence tail, deduplicated and
    sorted numerically — the claims this face makes about what merged."""
    found = {pr for _, tail in _struck_blocks(text) for pr in _PR_RE.findall(tail)}
    return sorted(found, key=lambda pr: int(pr[1:]))


def _merged_pr_numbers() -> set[str] | None:
    """Every `#NN` this repo's history records as a merged pull request, or
    `None` when there is no usable history to read.

    Read off every reachable commit, **not** `--first-parent`. On `main`
    those are the same set, and first-parent is the tidier read; on a branch
    that has merged `main` back in they are not — `main`'s own merge commits
    arrive as *second* parents, so a first-parent walk from a branch head
    reports every PR merged since the branch point as nonexistent. That is a
    guard that fails hardest exactly when a branch is most up to date, which
    is backwards. Only a GitHub merge commit's subject reads "Merge pull
    request #NN", so widening the walk adds no false positives.

    `None` (rather than an empty set) is the honest answer for an sdist or a
    depth-1 checkout — an empty set would read as "no PR ever merged" and
    fail every struck bite at once.
    """
    import subprocess

    try:
        done = subprocess.run(
            ["git", "log", "--format=%s"],
            cwd=APP, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git
        return None
    if done.returncode != 0:
        return None
    subjects = done.stdout.splitlines()
    if len(subjects) < len(LANDED_BITES):
        return None  # shallow: fewer commits than there are bites to prove
    return {
        pr
        for subject in subjects
        if subject.startswith("Merge pull request ")
        for pr in _PR_RE.findall(subject)
    }


def test_every_struck_pr_number_is_a_merge_this_repo_records():
    """A PR number typed from memory is the same wishful claim a bare
    strikethrough is, one level down. Each one must be a merge commit on
    `main`'s first-parent line."""
    import pytest

    merged = _merged_pr_numbers()
    if merged is None:
        pytest.skip("no usable git history here (sdist or shallow checkout)")

    claimed = _struck_pr_numbers(PLAN_FACE.read_text(encoding="utf-8"))
    assert claimed, "no struck bite names a PR number yet"
    unknown = [pr for pr in claimed if pr not in merged]
    assert not unknown, (
        "docs/PLAN-affairs-face.md strikes bites through on these PR numbers "
        f"and this repo's first-parent history records no such merge: {unknown}"
    )


def test_the_pr_cross_check_fires_on_a_planted_invented_pr_number():
    """Planted: a struck bite crediting a PR nobody opened. The check must
    name exactly that number, and must still clear the real ones beside it —
    a guard that reported everything would be as useless as one that
    reported nothing."""
    import pytest

    merged = _merged_pr_numbers()
    if merged is None:
        pytest.skip("no usable git history here (sdist or shallow checkout)")

    text = PLAN_FACE.read_text(encoding="utf-8")
    planted = text.replace("(#43, released 0.10.0", "(#9901, released 0.10.0", 1)
    assert planted != text, "the plant assumes G5-sync's evidence tail's shape"

    claimed = _struck_pr_numbers(planted)
    assert [pr for pr in claimed if pr not in merged] == ["#9901"]
