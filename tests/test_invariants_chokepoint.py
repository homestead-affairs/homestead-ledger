"""I-16 for the ledger — one chokepoint — and the structural half of "mirror, not judge".

Ported from the engine's `homestead/tests/test_invariants_chokepoint.py`, and it
carries that file's hard-won lesson: banning the literal `.payload` spelling is
not enough. The engine's audit walked its own scan with `getattr(record,
"payload")` — a field read by computed name — and put an SSN on screen, green. So
the rule is a property of the **surface layer**, not of one token: a surface
renders what the gate hands it (`Row.text`, `Served.value`) and reaches around the
gate by *no* spelling.

Two bans, and the second is the ledger's own:

1. **A raw `Classified.payload` is reached only at the payload boundary.** For this
   module that is `books.py` (it serializes a payload to write the canonical
   books) and `balance.py` (arithmetic needs the real number — the engine's own
   deadline arithmetic reaches a payload in its store seam for the same reason).
   Disk and arithmetic are not surfaces (S1-S4). Everywhere else — the app above
   all — a `.payload` read is the gate wired to nothing.

2. **Only `books.py` writes the canonical books.** *This is "mirror, not judge"
   made structural.* The imported transactions are the household's own record;
   the app reflects them and never edits them. The engine's `Canonical` handle
   ships with no write method, but `books.py` writes the `CANONICAL` table through
   the raw adapter to *import* — the operator's-own-tool path. So the promise is
   not "the handle is read-only" (a surface could bypass the handle exactly as
   `books.py` does); it is "nothing but the import names the `CANONICAL` table."
   A surface that writes canonical is a mirror that judged.

The regression fixtures are the important half: they plant every bypass — the
reflection forms and a stray canonical write — in a real surface path and run the
package scan over it, so a passing suite means the enforcement caught the leak,
not that `app/` happens to be clean today.
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "homestead_ledger"

BOOKS = PKG / "books.py"      # serializes a payload to import; the only canonical writer
BALANCE = PKG / "balance.py"  # arithmetic over the household's own numbers — not a surface
#: The payload boundary. Everything else goes through the gate and receives a
#: served, derived form.
ALLOWED_PAYLOAD = {BOOKS, BALANCE}
#: "Mirror, not judge": only the import writes the household's books.
ALLOWED_CANONICAL = {BOOKS}

#: Reflection primitives that read a field without naming it — the forms the
#: engine's audit used to walk past a literal `.payload` scan. A surface has no
#: honest use for any of them.
REFLECTION_CALLS = {
    "getattr", "setattr", "vars", "astuple", "asdict", "attrgetter", "fields",
    "__getattribute__", "__getattr__",
}
REFLECTION_ATTRS = {"__dict__", "__getattribute__", "__getattr__"}


def _modules() -> list[Path]:
    return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


def _is_surface(mod: Path) -> bool:
    return "app" in mod.relative_to(PKG).parts


def _payload_reaches(tree: ast.AST) -> list[int]:
    """Every `.payload` attribute access, by line. A dict key (`{"payload": ...}`)
    is an `ast.Constant`, not an `ast.Attribute`, so serializing a blob is not a
    reach — only `something.payload` is."""
    return [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "payload"
    ]


def _canonical_reaches(tree: ast.AST) -> list[int]:
    """Every reference to the `CANONICAL` table constant, by line — the name of
    the canonical books. A prose mention in a docstring is an `ast.Constant`
    string, not a `Name`/`Attribute`, so only real code that names the table is a
    reach."""
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "CANONICAL":
            hits.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "CANONICAL":
            hits.append(node.lineno)
    return hits


def _reflection_reaches(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            leaf = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if leaf in REFLECTION_CALLS:
                hits.append((node.lineno, leaf))
        elif isinstance(node, ast.Attribute) and node.attr in REFLECTION_ATTRS:
            hits.append((node.lineno, node.attr))
    return hits


def test_i16_only_the_payload_boundary_reaches_a_payload():
    """A module that is neither `books` nor `balance` reaching a payload has
    walked past the one door."""
    offenders = []
    for mod in _modules():
        if mod in ALLOWED_PAYLOAD:
            continue
        for lineno in _payload_reaches(ast.parse(mod.read_text("utf-8"))):
            offenders.append(f"{mod.relative_to(PKG.parent)}:{lineno}")
    assert not offenders, (
        f"a payload is reached outside books.py/balance.py, at {offenders}. "
        "The payload crosses a surface only as a served, derived form; a direct "
        ".payload read is the gate wired to nothing."
    )


def test_i16_the_surface_layer_reaches_no_payload():
    offenders = []
    for mod in _modules():
        if not _is_surface(mod):
            continue
        for lineno in _payload_reaches(ast.parse(mod.read_text("utf-8"))):
            offenders.append(f"{mod.relative_to(PKG.parent)}:{lineno}")
    assert not offenders, f"the surface layer reaches a payload directly at {offenders}."


def test_i16_the_surface_layer_does_not_reflect():
    """Closed as a property, not a spelling: no getattr/vars/__dict__/astuple/
    asdict/fields/attrgetter in `app/`. Those are the by-computed-name reads that
    made `getattr(record, 'payload')` invisible to a literal scan."""
    offenders = []
    for mod in _modules():
        if not _is_surface(mod):
            continue
        for lineno, how in _reflection_reaches(ast.parse(mod.read_text("utf-8"))):
            offenders.append(f"{mod.relative_to(PKG.parent)}:{lineno} {how}")
    assert not offenders, (
        f"the surface layer reflects at {offenders}. A surface renders what the "
        "gate hands it; reflection reads a payload without naming it. No "
        "reflection on a surface."
    )


def test_mirror_not_judge_only_the_import_writes_the_canonical_books():
    """The structural form of "mirror, not judge". Only `books.py` may name the
    `CANONICAL` table; every other module — the app above all — reflects the books
    and never edits them. A surface (or anything else) that writes canonical is a
    mirror that judged, and the read-only `Canonical` handle does not stop it,
    because `books.py` writes by bypassing that handle through the raw adapter."""
    offenders = []
    for mod in _modules():
        if mod in ALLOWED_CANONICAL:
            continue
        for lineno in _canonical_reaches(ast.parse(mod.read_text("utf-8"))):
            offenders.append(f"{mod.relative_to(PKG.parent)}:{lineno}")
    assert not offenders, (
        f"the CANONICAL books are named outside books.py, at {offenders}. Mirror, "
        "not judge: only the import writes the household's own record; everything "
        "else reads it and never edits it."
    )


def _scan_surface_dir(app_dir: Path) -> list[str]:
    offenders = []
    for mod in sorted(app_dir.rglob("*.py")):
        tree = ast.parse(mod.read_text("utf-8"))
        for lineno in _payload_reaches(tree):
            offenders.append(f"{mod.name}:{lineno} .payload")
        for lineno, how in _reflection_reaches(tree):
            offenders.append(f"{mod.name}:{lineno} {how}")
        for lineno in _canonical_reaches(tree):
            offenders.append(f"{mod.name}:{lineno} CANONICAL")
    return offenders


def test_i16_regression_every_bypass_is_caught(tmp_path):
    """Every bypass — the engine audit's reflection forms and a stray canonical
    write — planted in a surface file and run through the real scan. Each must be
    caught, or the guard passes only because `app/` happens to be clean today."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    bypasses = [
        "record.payload",
        'getattr(record, "payload")',
        'getattr(record, "pay" + "load")',
        'record.__dict__["payload"]',
        'vars(record)["payload"]',
        "dataclasses.astuple(record)[1]",
        'dataclasses.asdict(record)["payload"]',
        'operator.attrgetter("payload")(record)',
        "[getattr(record, f.name) for f in dataclasses.fields(record)]",
        "store.insert(CANONICAL, ref, blob)",   # a surface writing the books
    ]
    for i, expr in enumerate(bypasses):
        (app_dir / f"leak_{i}.py").write_text(
            "import dataclasses, operator\n"
            "from homestead.keep.store import CANONICAL\n"
            f"def draw(record, store=None, ref=None, blob=None):\n    return {expr}\n"
        )
    offenders = _scan_surface_dir(app_dir)
    caught = {o.split(":")[0].split(" ")[0] for o in offenders}
    missed = [f"leak_{i}.py" for i in range(len(bypasses)) if f"leak_{i}.py" not in caught]
    assert not missed, (
        f"these bypasses passed the surface scan: {missed}. Each reads a payload "
        "a surface was not handed, or writes a record it may not — none may be "
        "invisible."
    )
