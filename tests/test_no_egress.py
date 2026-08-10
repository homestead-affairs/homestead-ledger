"""homestead-ledger holds private money data — it must never dial out (I-17).

An AST sweep over **this package's own** modules: no network module imported, and
no `eval`/`exec`/`compile`/`__import__` that could smuggle one past the import
scan. A money ledger is the canonical "holds private data, must not egress" case.

Scope note: this guards `homestead_ledger`'s own code. The pinned engine
(`homestead.keep`, published as `homestead-affairs`) is import-pure itself and
tested in its own suite; it is not re-scanned here. Ported from the fleet's
`marching-arts/tests/test_no_egress.py`, which is the vendorable AST scanner.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parent.parent / "homestead_ledger"

# Network / outbound modules. `asyncio` is not here — it is not itself egress.
NET = {
    "socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp",
    "websockets", "urllib3", "socketserver", "ftplib", "telnetlib",
    "smtplib", "xmlrpc", "poplib", "imaplib", "nntplib",
}
DYNAMIC = {"eval", "exec", "compile", "__import__"}


def _modules() -> list[Path]:
    return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


def _toplevel_and_nested_imports(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("mod", _modules(), ids=lambda p: p.name)
def test_no_network_import(mod: Path):
    hits = NET & _toplevel_and_nested_imports(ast.parse(mod.read_text(encoding="utf-8")))
    assert not hits, f"{mod.name} imports network module(s): {sorted(hits)}"


@pytest.mark.parametrize("mod", _modules(), ids=lambda p: p.name)
def test_no_dynamic_exec(mod: Path):
    bad: list[str] = []
    for node in ast.walk(ast.parse(mod.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in DYNAMIC):
            bad.append(node.func.id)
    assert not bad, f"{mod.name} uses dynamic exec/import: {sorted(set(bad))}"
