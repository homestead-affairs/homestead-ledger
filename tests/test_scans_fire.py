"""X7-drift-ledger — the meta-scan: every AST/grep-guard helper this suite
carries has been shown to catch something, by a test that *calls it*.

*A scan that has never fired has not been shown to check anything* is the
repo's own rule (`tests/test_i44_no_drafting.py`'s docstring says it in so
many words, and every `_offenders`/`_reaches`/`_unproven` helper here follows
it). This file is that rule turned into a test that reads the *other* test
files: it finds every module-level helper in ``tests/`` that is shaped like a
violation-scanner and asserts that some planted-violation test in the *same
file* runs that helper — directly, or through another helper it calls.

This file is not a fresh design: it is the sibling drift sweeps' own meta-scan
(`homestead-health`'s `tests/test_scans_fire.py`, and the engine's on
`claude/engine-drift`), copied for its shape and re-grounded against this
repo's own test files. The discovery rule and the plant rule below are
theirs, verified here rather than re-derived, because a meta-scan that
disagreed between repos about what counts as "planted" would be exactly the
kind of drift this sweep exists to close.

**Discovery is structural, not a naming convention.** A rule that only
matched a leading underscore or a stem list would miss a public
`check_payload_reach(...)` (an AST-walking scan spelled the way a helper
meant to be imported is spelled) and a grep-shaped `forbidden_word_hits(path)`
that reads a file and asks `"payload" in text` with no `ast` and no matching
stem at all — both are planted below, alongside the real thing. So the rule
is what a scan *does*:

* it parses or walks source (`ast.parse`, `ast.walk`), **or**
* it matches text with a pattern (`re.search`/`findall`/`finditer`/`match`/
  `fullmatch`/`compile`, or a module-level compiled pattern's `.search(…)`),
  **or**
* it reads a file's text (`.read_text()`/`.read_bytes()`) *and* asks a
  membership question of it (`x in text`, `x not in parts`) — the grep shape
  with no regex in it, which `tests/test_i44_no_drafting.py`'s NOTICE-strip
  guard and `tests/test_docs_drift.py`'s `_contains` both are.

The name stems and the `_is_` prefix are kept on top of that, not instead of
it: they still catch helpers that hand their work to a caller. Discovery is a
union, so it is strictly wider than either half alone.

**Having a plant means a plant test calls the scan.** A test called
`test_the_guard_fires` that never touches the guard has not fired it — the
word in a test's name is not the evidence. A helper counts as planted only
when a `test_*` function whose name or docstring carries `plant`, `fires` or
`catches` reaches it — through the module's own helpers as well as directly,
so a plant that calls a wrapper has exercised the parser underneath it too.
Both halves are planted below: the name-only plant test (a counter-example
that must still be reported) and the call-through-a-helper case (which must
not).

**Honest about what it still cannot see.** A helper that reaches `ast.parse`
through an alias (`from ast import parse as p`), one that shells out to
`grep`, or one whose whole check is a comparison of two already-read strings
with no membership test and no pattern, is outside the rule above. Closing
those needs an interpreter, not a reader; this scan is the AST-grep half, not
a promise that it sees everything a scan could be shaped like. Scans written
inline in a test body rather than as a helper are invisible to it too.
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

#: Word-stems the repo's own scan helpers already use, split on "_" so
#: `_record_synced_offenders`-style names (offenders is the *last* word) and
#: `_reads_a_jsonl_path_with_bare_json_loads`-style names (reads is the
#: *first*) both match without over-firing on unrelated names.
_NAME_TOKENS = frozenset(
    {"scan", "scans", "reads", "calls", "offenders", "uses", "check", "checks",
     "guard", "guards"}
)

#: The convention this repo actually uses for "this scan was shown to fire on
#: a planted violation" — read off the real test names and docstrings, not
#: guessed. The word is necessary; calling the scan is what makes it count.
_PLANT_WORDS = ("plant", "fires", "catches")

#: Pattern-matching methods. Matched on the attribute name alone, so both
#: `re.search(...)` and a module-level `_STRIKE_RE.finditer(...)` count — a
#: compiled pattern is the same scan with the compile hoisted.
_MATCH_CALLS = frozenset(
    {"search", "findall", "finditer", "match", "fullmatch", "compile"}
)

#: Reading a repo file's text. The grep half of a grep-shaped scan.
_TEXT_READS = frozenset({"read_text", "read_bytes"})


def _calls_in(node: ast.AST):
    """Every `Call` anywhere inside `node`."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            yield sub


def _walks_source(node: ast.AST) -> bool:
    """True if the body calls `ast.parse(...)` or `ast.walk(...)` — the shape
    of a scan that reads source rather than trusting an already-parsed tree."""
    return any(
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "ast"
        and call.func.attr in ("parse", "walk")
        for call in _calls_in(node)
    )


def _matches_text(node: ast.AST) -> bool:
    """True if the body runs a pattern over text — `re.search(...)`, a
    compiled pattern's `.finditer(...)`, or a bare `compile(...)`."""
    for call in _calls_in(node):
        if isinstance(call.func, ast.Attribute) and call.func.attr in _MATCH_CALLS:
            return True
        if isinstance(call.func, ast.Name) and call.func.id == "compile":
            return True
    return False


def _reads_file_text(node: ast.AST) -> bool:
    """True if the body reads a file's text itself."""
    return any(
        isinstance(call.func, ast.Attribute) and call.func.attr in _TEXT_READS
        for call in _calls_in(node)
    )


def _tests_membership(node: ast.AST) -> bool:
    """True if the body asks `x in y` / `x not in y` anywhere — the grep
    question, once the text is in hand."""
    return any(
        isinstance(sub, ast.Compare)
        and any(isinstance(op, (ast.In, ast.NotIn)) for op in sub.ops)
        for sub in ast.walk(node)
    )


def _is_fixture(node: ast.FunctionDef) -> bool:
    """`@pytest.fixture` — setup, not a scan, whatever it reads."""
    return any("fixture" in ast.dump(dec) for dec in node.decorator_list)


def _is_scan_helper(node: ast.FunctionDef) -> bool:
    """A module-level helper counts as a scan/guard if it is shaped like one
    (walks source, matches a pattern, or reads a file and asks a membership
    question of it) or its name carries one of the repo's own stems.

    Deliberately *not* conditioned on a leading underscore: a public
    `check_payload_reach` is the same scan with a different name.
    """
    name = node.name
    if name.startswith("test_") or name.startswith("__"):
        return False
    if _is_fixture(node):
        return False
    if name.startswith("_is_"):
        return True
    if _NAME_TOKENS & set(name.strip("_").split("_")):
        return True
    return (
        _walks_source(node)
        or _matches_text(node)
        or (_reads_file_text(node) and _tests_membership(node))
    )


def _module_helpers(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Every module-level, non-test function in one tests module, by name."""
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("test_")
    }


def _scan_helpers(source: str) -> list[str]:
    """Every module-level scan-helper function name in one tests module."""
    helpers = _module_helpers(ast.parse(source))
    return sorted(name for name, node in helpers.items() if _is_scan_helper(node))


def _direct_calls(node: ast.AST, known: dict[str, ast.FunctionDef]) -> set[str]:
    """The module's own helpers this node calls by bare name."""
    return {
        call.func.id
        for call in _calls_in(node)
        if isinstance(call.func, ast.Name) and call.func.id in known
    }


def _helpers_the_plants_exercise(source: str) -> set[str]:
    """Every helper reachable from a planted-violation test in this module.

    A test counts as a plant test when its name or docstring carries one of
    `_PLANT_WORDS`; from there the reach is transitive through the module's
    own helpers, because a plant that calls a wrapper has exercised the
    helper underneath it just as surely as if it had called it by hand.
    """
    tree = ast.parse(source)
    helpers = _module_helpers(tree)
    reached: set[str] = set()
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
            continue
        haystack = f"{node.name} {ast.get_docstring(node) or ''}".lower()
        if not any(word in haystack for word in _PLANT_WORDS):
            continue
        pending = list(_direct_calls(node, helpers))
        while pending:
            name = pending.pop()
            if name in reached:
                continue
            reached.add(name)
            pending.extend(_direct_calls(helpers[name], helpers))
    return reached


def _unplanted_scan_helpers(source: str) -> list[str]:
    """The scan helpers in one tests module that no planted-violation test in
    the same module ever calls."""
    exercised = _helpers_the_plants_exercise(source)
    return [name for name in _scan_helpers(source) if name not in exercised]


def _offenders() -> list[str]:
    """Every tests/*.py file that defines a scan helper no plant test in the
    same file calls."""
    offenders = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == "test_scans_fire.py":
            continue  # this file's own helpers are proven below, not here
        unplanted = _unplanted_scan_helpers(path.read_text(encoding="utf-8"))
        if unplanted:
            offenders.append(f"{path.name}: {unplanted}")
    return offenders


def test_every_scan_helper_has_a_planted_violation_test():
    """The house rule, run for real: no `tests/*.py` file may carry an
    AST/grep-guard helper that no planted-violation test in the same file
    actually runs."""
    offenders = _offenders()
    assert not offenders, (
        "these test files define a scan helper (it walks source, matches a "
        "pattern, or reads a file and asks a membership question of it — or "
        f"its name carries one of {sorted(_NAME_TOKENS)}) that no test naming "
        "plant/fires/catches ever calls — a scan that has never fired has not "
        f"been shown to check anything: {offenders}"
    )


# ── the discovery half, planted twice: AST-shaped and grep-shaped ────────────


def _write(tmp_path: Path, name: str, body: str) -> str:
    """A fake tests module on disk, read back the way `_offenders()` reads a
    real one."""
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def test_the_meta_scan_finds_an_ast_shaped_scan_whatever_it_is_named(tmp_path):
    """Planted: a scan that walks `ast` under a **public** name. A rule that
    required a leading underscore would miss `check_payload_reach` — the same
    scan, spelled the way a helper meant to be imported is spelled — and its
    missing plant would go unreported."""
    source = _write(
        tmp_path,
        "test_planted_ast_shaped_scan.py",
        "import ast\n"
        "\n"
        "def check_payload_reach(source):\n"
        "    return [n for n in ast.walk(ast.parse(source))\n"
        "            if isinstance(n, ast.Attribute) and n.attr == 'payload']\n"
        "\n"
        "def test_nothing_reaches_a_payload():\n"
        "    assert not check_payload_reach('x = 1\\n')\n",
    )

    assert _scan_helpers(source) == ["check_payload_reach"], (
        "an ast.parse/ast.walk scan must be found under any name, public or "
        f"private; got {_scan_helpers(source)}"
    )
    assert _unplanted_scan_helpers(source) == ["check_payload_reach"], (
        "and with no planted-violation test in the file it must be reported"
    )


def test_the_meta_scan_finds_a_grep_shaped_scan(tmp_path):
    """Planted: a scan with no `ast` in it at all — `path.read_text()` and an
    `in`. The repo has this shape already (`test_i44_no_drafting.py`'s
    NOTICE-strip guard), and a discovery rule that only knew about `ast`
    would clear a file whose only guard is this shape."""
    source = _write(
        tmp_path,
        "test_planted_grep_shaped_scan.py",
        "def forbidden_word_hits(path):\n"
        "    return 'payload' in path.read_text(encoding='utf-8')\n"
        "\n"
        "def test_no_module_says_payload(tmp_path):\n"
        "    probe = tmp_path / 'm.py'\n"
        "    probe.write_text('x = 1\\n', encoding='utf-8')\n"
        "    assert not forbidden_word_hits(probe)\n",
    )

    assert _scan_helpers(source) == ["forbidden_word_hits"], (
        "a read_text()+`in` scan is a scan; the name carries none of the "
        f"repo's stems, which is the point. Got {_scan_helpers(source)}"
    )
    assert _unplanted_scan_helpers(source) == ["forbidden_word_hits"]


def test_a_fixture_is_not_mistaken_for_a_scan(tmp_path):
    """The other side of the same honesty: `@pytest.fixture` setup that reads
    a file must not be reported, or the meta-scan cries wolf on every suite
    that stages a tmp household."""
    source = _write(
        tmp_path,
        "test_planted_fixture_only.py",
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def household(tmp_path):\n"
        "    (tmp_path / 'seed').write_text('x', encoding='utf-8')\n"
        "    return 'seed' in (tmp_path / 'seed').read_text(encoding='utf-8')\n"
        "\n"
        "def test_it(household):\n"
        "    assert household\n",
    )
    assert _scan_helpers(source) == []


# ── the plant half: naming a test "fires" is not having fired ────────────────


def test_the_plant_check_requires_the_plant_test_to_call_the_scan(tmp_path):
    """The counter-example, planted. A file whose only "plant" is a test
    *named* `test_the_scan_fires` and whose body never touches the scan must
    still be reported — a plant word in a name is not a plant."""
    source = _write(
        tmp_path,
        "test_planted_name_only_plant.py",
        "import ast\n"
        "\n"
        "def _payload_reaches(tree):\n"
        "    return [n for n in ast.walk(tree)\n"
        "            if isinstance(n, ast.Attribute) and n.attr == 'payload']\n"
        "\n"
        "def test_the_scan_fires_on_a_planted_violation():\n"
        "    '''Says it plants. Plants nothing.'''\n"
        "    assert True\n",
    )

    assert _scan_helpers(source) == ["_payload_reaches"]
    assert _unplanted_scan_helpers(source) == ["_payload_reaches"], (
        "a plant test that never calls the scan has not fired it; the word in "
        "the test's name is not the evidence"
    )


def test_a_plant_that_calls_the_scan_through_a_helper_clears_it(tmp_path):
    """And not over-strict: a real plant might call a wrapper rather than the
    parser underneath it. Reaching a helper through another helper is having
    exercised it, so neither may be reported."""
    source = _write(
        tmp_path,
        "test_planted_indirect_plant.py",
        "import ast\n"
        "\n"
        "def _payload_reaches(tree):\n"
        "    return [n for n in ast.walk(tree)\n"
        "            if isinstance(n, ast.Attribute) and n.attr == 'payload']\n"
        "\n"
        "def _offenders_in(source):\n"
        "    return _payload_reaches(ast.parse(source))\n"
        "\n"
        "def test_the_scan_catches_a_planted_reach():\n"
        "    assert _offenders_in('y = r.payload\\n')\n",
    )

    assert _scan_helpers(source) == ["_offenders_in", "_payload_reaches"]
    assert _unplanted_scan_helpers(source) == [], (
        "both the wrapper and the helper it calls were exercised by the plant"
    )


def test_the_plant_check_does_not_fire_on_a_real_guarded_file():
    """The whole thing against a real file of this repo's:
    `tests/test_i44_no_drafting.py` defines two scans (the AST guard over
    `Purpose.DRAFTING`/`Purpose.FILING`, and the NOTICE-carve-out grep guard)
    and plants both, so the meta-scan must clear it — or it would be crying
    wolf on the very files it exists to clear."""
    source = (TESTS_DIR / "test_i44_no_drafting.py").read_text(encoding="utf-8")
    assert _scan_helpers(source), "test_i44_no_drafting.py is expected to define scan helpers"
    assert _unplanted_scan_helpers(source) == []
