"""Shared scan helpers three or more test modules call.

Kept out of any one `test_*.py` file on purpose: `tests/test_scans_fire.py`'s
meta-scan only proves a helper planted by a *plant test in the same file* --
a helper shared by a dozen files would need to live somewhere, and copying it
into each file instead is exactly the drift G9d-inline-scans closed
(`docs/PLAN-affairs-face.md`, "Inline scans the meta-scan cannot see" /
"Duplicated chokepoint scans").

This module is not a `test_*.py` file, so it holds no plant tests of its own
and the meta-scan's same-file rule cannot reach it. It is swept all the same
(`tests/test_scans_fire.py::_unplanted_shared_scan_helpers`, added on audit
2026-09-11): every scan helper defined here must be reached by a
planted-violation test *somewhere* in `tests/`, because
`_global_scan_helper_names()` uses these helpers to clear inline scans across
the suite and a helper that can excuse a test but can never be made to fire
would be the one scan in the repo proving nothing. Each importing module also
keeps its own real plant -- a specific forbidden or required value, planted
and asserted caught through this helper -- so the shape stays proven where it
is relied on and not only once in the abstract.
"""
from __future__ import annotations


def terms_found(haystack, terms):
    """Every one of `terms` present in `haystack` -- the I-15 grep half of a
    scan. `haystack` is whatever the caller already read (a log line, an
    export document, a file's raw bytes) and `terms` the values it must, or
    must not, carry once they have left L1-L3. Works for `str` or `bytes`,
    whichever the caller read; the caller decides presence or absence."""
    return [term for term in terms if term in haystack]
