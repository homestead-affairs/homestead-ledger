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
G8-business-books and X7-drift-ledger; the first ten landed, the last three
have not (G7b waits on an engine release that has not shipped; G8 has
merged but not released; this bite cannot strike itself before its own PR
merges), and all thirteen must be named here.
"""
from __future__ import annotations

import re
from pathlib import Path

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
)
UNLANDED_BITES = ("G7b-floor-0.13", "G8-business-books", "X7-drift-ledger")


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
    release version, named by what it is missing."""
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


def test_every_ledger_bite_the_plan_names_has_an_entry():
    """Landed or not, each one is named. The unlanded ones are how a reader
    tells "nothing outstanding" from "nobody wrote it down"."""
    text = PLAN_FACE.read_text(encoding="utf-8")
    absent = [
        name for name in LANDED_BITES + UNLANDED_BITES if name not in text
    ]
    assert not absent, (
        "these ledger bites are named in the Homestead · Affairs plan and "
        f"nowhere in docs/PLAN-affairs-face.md: {absent}"
    )


def test_no_unlanded_bite_is_struck_through():
    """The wishful strike, held against the three bites that have not
    landed: G7b waits on an engine release that has not shipped; G8 has
    merged but is not yet released; this bite cannot strike itself before
    its own PR merges."""
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
            "**G8-business-books** ledger `feat:`",
            "~~**G8-business-books** ledger `feat:`~~ (#99, released 9.9.9)",
            1,
        ),
        encoding="utf-8",
    )
    text = planted.read_text(encoding="utf-8")
    assert _bites_struck_through(text, UNLANDED_BITES) == ["G8-business-books"], (
        "the plant did not apply, or the guard cannot see a struck bite name"
    )
