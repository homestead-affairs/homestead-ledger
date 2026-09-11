"""Provisional I-44 — this ledger models a Chapter 13 debt schedule and
drafts nothing, files nothing. Two guards, each planted before it is
trusted (a scan that has never fired has not been shown to check anything):

1. **An AST scan.** No reference to `Purpose.DRAFTING`/`Purpose.FILING`
   anywhere in `homestead_ledger/` — `schedules.export()` declares
   `Purpose.EXPORT` and nothing else has any business naming the other two.
2. **A grep guard.** No string in the package or the README names an
   official bankruptcy form or tells the operator to file or "should" do
   anything (a reference, never advice). `schedules.NOTICE` is the one
   place "official form" legitimately appears (it says this is *not* one),
   so the scan strips that exact sentence before searching — the same
   named-exception shape `test_invariants_chokepoint.py` gives
   `books.py`/`balance.py` for the payload boundary.
"""
from __future__ import annotations

import ast
from pathlib import Path

from homestead_ledger import grant_report, schedules
from homestead_ledger.grant_report import GRANT_REPORT_NOTICE
from homestead_ledger.schedules import (
    BUSINESS_INCLUDED_NOTICE,
    BUSINESS_NONE_NOTICE,
    BUSINESS_NOTICE,
    NOTICE,
)

#: The carve-out's whole exemption: **every notice sentence this package
#: puts in front of a household**, listed one by one and anchored to its
#: exact value, never to the name it happens to be bound to (see
#: `_without_the_notice`). Grown by G8-business-books from one sentence to
#: five — the liability schedule's own notice, the three sentences it
#: appends about business-owned accounts (each true in exactly one state,
#: `schedules.BUSINESS_SENTENCES`), and the allowable-use report's own.
PERMITTED_NOTICES = (
    NOTICE,
    BUSINESS_NOTICE,
    BUSINESS_NONE_NOTICE,
    BUSINESS_INCLUDED_NOTICE,
    GRANT_REPORT_NOTICE,
)

PKG = Path(__file__).resolve().parent.parent / "homestead_ledger"
README = PKG.parent / "README.md"


def _modules() -> list[Path]:
    return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


# ── guard 1: no Purpose.DRAFTING / Purpose.FILING anywhere ──────────────────

_BANNED_PURPOSES = {"DRAFTING", "FILING"}


def _drafting_or_filing_reaches(tree: ast.AST) -> list[int]:
    """Every `DRAFTING`/`FILING` name — attribute, bare name, or import
    alias — by line, so both `Purpose.DRAFTING` and a bare imported
    `FILING` are caught, not only the fully qualified spelling."""
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _BANNED_PURPOSES:
            hits.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id in _BANNED_PURPOSES:
            hits.append(node.lineno)
        elif isinstance(node, ast.alias) and node.name in _BANNED_PURPOSES:
            hits.append(node.lineno)
    return hits


def test_i44_no_drafting_or_filing_purpose_anywhere_in_the_package():
    offenders = []
    for mod in _modules():
        for lineno in _drafting_or_filing_reaches(ast.parse(mod.read_text("utf-8"))):
            offenders.append(f"{mod.relative_to(PKG.parent)}:{lineno}")
    assert not offenders, (
        f"Purpose.DRAFTING or Purpose.FILING is reached at {offenders}. "
        "This ledger models a Chapter 13 debt schedule and drafts nothing "
        "(provisional I-44) — schedules.export() declares Purpose.EXPORT "
        "and nothing else may declare the other two."
    )


def test_i44_ast_guard_fires_on_a_planted_drafting_purpose(tmp_path):
    planted = tmp_path / "leak_drafting.py"
    planted.write_text(
        "from homestead.keep.rungs import Purpose\n"
        "PURPOSE = Purpose.DRAFTING\n",
        "utf-8",
    )
    assert _drafting_or_filing_reaches(ast.parse(planted.read_text()))


def test_i44_ast_guard_fires_on_a_planted_filing_purpose(tmp_path):
    planted = tmp_path / "leak_filing.py"
    planted.write_text(
        "from homestead.keep.rungs import Purpose\n"
        "def do():\n    return Purpose.FILING\n",
        "utf-8",
    )
    assert _drafting_or_filing_reaches(ast.parse(planted.read_text()))


def test_i44_ast_guard_fires_on_a_drafting_purpose_planted_in_schedules_py(tmp_path):
    """The real module, copied and edited — the shape the leak would
    actually arrive in: `schedules.export()` already names a `Purpose`, so
    the one-character change from `EXPORT` to `DRAFTING` is the whole of it.
    A guard shown to fire only on a two-line fixture has not been shown to
    fire on the file it exists to watch."""
    planted = tmp_path / "schedules.py"
    source = (PKG / "schedules.py").read_text("utf-8")
    assert "Purpose.EXPORT" in source
    planted.write_text(source.replace("Purpose.EXPORT", "Purpose.DRAFTING"), "utf-8")
    assert _drafting_or_filing_reaches(ast.parse(planted.read_text("utf-8")))
    assert not _drafting_or_filing_reaches(ast.parse(source))


def test_i44_ast_guard_is_quiet_on_the_one_declared_purpose(tmp_path):
    """`Purpose.EXPORT` must not itself trip the guard."""
    honest = tmp_path / "honest.py"
    honest.write_text(
        "from homestead.keep.rungs import Purpose\n"
        "PURPOSE = Purpose.EXPORT\n",
        "utf-8",
    )
    assert _drafting_or_filing_reaches(ast.parse(honest.read_text())) == []


# ── guard 2: no official-form / "you should" language ───────────────────────

FORBIDDEN_PHRASES = (
    "Schedule A/B",
    "Schedule D",
    "Schedule E/F",
    "Schedule J",
    "Form 106",
    "Form B",
    "Official Form",
    "official form",
    "means test",
    "file with the court",
    "you should",
)


def _without_the_notice(text: str) -> str:
    """`text` with every `PERMITTED_NOTICES` sentence removed — five named
    exceptions now (G8-business-books added four), the same shape
    `test_invariants_chokepoint.py`'s `ALLOWED_PAYLOAD` takes for the
    payload boundary.

    Two removal passes per sentence: the README quotes a notice verbatim,
    one contiguous run a plain `.replace(notice, "")` finds directly; in
    `schedules.py` and `grant_report.py` the string literal is written as
    several concatenated pieces across several lines, so it never appears
    as one contiguous run in the *source* text — for that shape this blanks
    the source lines of the assignment instead, by line number, before the
    plain replace runs.

    **The carve-out is anchored to the sentence, not to the name.** An
    assignment is blanked only when its literal value is *exactly* one of
    `PERMITTED_NOTICES` — the name it is bound to is not consulted at all,
    since keying on the name `NOTICE` would hand any module a name that
    turns the scan off for whatever it says (and would equally have missed
    `GRANT_REPORT_NOTICE`, which is bound to a different one).
    """
    out = text
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        lines = out.splitlines(keepends=True)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not any(
                isinstance(t, ast.Name) for t in node.targets
            ):
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError, TypeError):
                continue
            if value not in PERMITTED_NOTICES:
                continue
            for i in range(node.lineno - 1, node.end_lineno):
                lines[i] = "\n"
        out = "".join(lines)
    for notice in PERMITTED_NOTICES:
        out = out.replace(notice, "")
    return out


def _phrase_hits(text: str) -> list[str]:
    """Exact, case-sensitive matches only. `FORBIDDEN_PHRASES` is spelled
    the way a real occurrence would be (`Form B`, not `form b`) — matching
    case-insensitively would also catch "the schedule decision" (contains
    "schedule d") and "the form beside" (contains "form b"), ordinary prose
    already in this package that this guard has no business flagging."""
    checked = _without_the_notice(text)
    return [phrase for phrase in FORBIDDEN_PHRASES if phrase in checked]


def test_i44_no_official_form_or_advice_language_in_the_package():
    offenders = []
    for mod in _modules():
        hits = _phrase_hits(mod.read_text("utf-8"))
        if hits:
            offenders.append(f"{mod.relative_to(PKG.parent)}: {hits}")
    assert not offenders, (
        f"forbidden language found at {offenders}. This package tracks a "
        "debt schedule; it never names an official form or number, and it "
        "never tells the operator what they should do (a reference, never "
        "advice)."
    )


def test_i44_no_official_form_or_advice_language_in_the_readme():
    hits = _phrase_hits(README.read_text("utf-8"))
    assert not hits, f"README.md contains forbidden language: {hits}"


def test_i44_notice_carries_the_one_permitted_official_form_mention():
    """The carve-out is not vacuous: `NOTICE` really does say "official
    form", and stripping it really does remove that occurrence — otherwise
    the two tests above would be passing for the wrong reason."""
    assert "official form" in NOTICE
    assert "official form" not in _without_the_notice(NOTICE)


def test_i44_grep_guard_fires_on_each_planted_phrase(tmp_path):
    for i, phrase in enumerate(FORBIDDEN_PHRASES):
        planted = tmp_path / f"leak_{i}.py"
        planted.write_text(f'MSG = "this concerns {phrase} in some way"\n', "utf-8")
        assert _phrase_hits(planted.read_text()), f"the guard missed {phrase!r}"


def test_i44_notice_carve_out_spans_every_sentence_this_package_shows():
    """The exemption is a list of sentences, and the list is exactly the
    sentences the package can put in front of a household — pinned so a
    future trim is a visible, deliberate change, not a quiet narrowing
    nobody meant, and so a *new* notice cannot ride in on an old name."""
    assert len(PERMITTED_NOTICES) == 5
    assert len(set(PERMITTED_NOTICES)) == 5  # each sentence is distinct
    # Every sentence `schedules.export()` can append is one of them: the
    # tuple is not allowed to fall behind the module it exempts.
    for sentence in schedules.BUSINESS_SENTENCES:
        assert sentence in PERMITTED_NOTICES


def test_i44_every_permitted_notice_strips_cleanly():
    """Each sentence is exempted the same way `schedules.NOTICE` already
    is: present in the raw text, absent once stripped — checked one by one,
    since a tuple proved on its first member has not been shown to hold for
    the rest."""
    for notice in PERMITTED_NOTICES:
        assert notice in f"see: {notice}"
        assert notice not in _without_the_notice(f"see: {notice}")
    # The allowable-use report carries its own "official form" disclaimer
    # (it is not `schedules.NOTICE` with a sentence appended — that sentence
    # describes a liability schedule, which this document is not), written
    # across several source lines, so both removal passes have to reach it.
    assert "official form" in GRANT_REPORT_NOTICE
    assert "official form" not in _without_the_notice(GRANT_REPORT_NOTICE)
    assert "official form" not in _phrase_hits(
        Path(grant_report.__file__).read_text("utf-8")
    )


def test_i44_grep_guard_fires_on_a_notice_constant_not_in_the_tuple(tmp_path):
    """The carve-out quotes five sentences; it does not exempt a *name*.

    Before this was anchored, any `NOTICE = …` assignment in the package had
    its whole source span blanked before the scan ran, so a module could
    carry court-filing language inside a constant with that name and the
    guard would never see it. One more `NOTICE`-named constant — one no
    bite added to `PERMITTED_NOTICES` — must still fire, or the carve-out
    has quietly become "any constant named NOTICE" again."""
    planted = tmp_path / "leak_notice.py"
    planted.write_text(
        'NOTICE = (\n'
        '    "you should file with the court using Form 106 before the "\n'
        '    "hearing"\n'
        ')\n',
        "utf-8",
    )
    assert sorted(_phrase_hits(planted.read_text())) == [
        "Form 106", "file with the court", "you should",
    ]


def test_i44_stripping_the_notice_leaves_a_second_occurrence_standing(tmp_path):
    """The strip removes the quoted sentence, not the phrase. A *second*
    "official form" somewhere else in the README — the shape a later
    paragraph drifting into court-form language would take — still fires."""
    readme_like = (
        "Every export carries this notice, verbatim:\n\n"
        f"> {NOTICE}\n\n"
        "Print the result onto the official form before the hearing.\n"
    )
    assert _phrase_hits(readme_like) == ["official form"]


def test_i44_grep_guard_ignores_incidental_lowercase_lookalikes():
    """A case-insensitive scan would flag ordinary prose already in this
    package — "the schedule decision" contains "schedule d", "the form
    beside" contains "form b". Neither is the phrase this guard watches
    for, and case-sensitive matching says so."""
    lookalikes = "the schedule decision needs a fresh read; the form beside it stays put"
    assert _phrase_hits(lookalikes) == []


def test_i44_grep_guard_is_quiet_on_clean_prose(tmp_path):
    clean = tmp_path / "clean.py"
    clean.write_text(
        '"""A schedule is a household record, on file for its own use."""\n',
        "utf-8",
    )
    assert _phrase_hits(clean.read_text()) == []
