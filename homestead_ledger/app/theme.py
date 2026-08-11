"""A stdlib-only `ttk.Style` theme — the "don't-look-like-Win98" pass.

Bite 3 lands the theme in the ledger first; the follow-on noted in
`docs/build-plan.md` hoists it into the engine (`homestead`) once it has
proven itself here, so both `homestead-law` and `homestead-ledger` draw from
one shared copy. Until that PR set lands, this file is the only copy, and it
is written so lifting it is a `git mv`, not a rewrite: no import of anything
under `homestead_ledger` except the rung enum, and `apply(root)` is the one
entry point a view calls.

**Stdlib only.** `tkinter`/`tkinter.font`/`tkinter.ttk` and nothing else —
this file is scanned by both `tests/test_no_egress.py` (no network import)
and `tests/test_invariants_chokepoint.py` (it lives under `app/`, so no
`.payload`, no reflection, no `CANONICAL`). It reaches no household data at
all: colours and fonts are the whole of what it knows.

**What "theme" means here:**

* the `clam` base (the only stock ttk theme that takes flat, borderless
  styling instead of fighting it — the platform-native themes render a
  bevelled 1998 button no matter what `configure()` is handed),
* a real proportional font, picked from a short cross-platform preference
  list and falling back to Tk's own default rather than assuming a name that
  may not be installed,
* generous padding and flat widgets (no bevels, no drop shadows),
* a restrained, warm-neutral palette, and
* **per-rung colour** (`rung_color`) for the one place a view draws more than
  one rung side by side — a list pane's rows (I-33: one indicator per pane,
  never a badge duplicated per row, so colour is the *row's* signal, not an
  additional one). `L1` and `L2` read as quiet, ambient fact; `L3` reads as
  plain ink (a party is named, nothing alarming about that); `L4` is a warm
  amber — protected/derived content draws the eye, the way a highlighted
  ledger line does. `L5` is never drawn (the gate drops it before a view ever
  gets a row), so its entry exists only for a future surface that might need
  to name the rung in text, never to colour a shown value.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from homestead.keep.rungs import Rung

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime tkinter import
    import tkinter as tk
    from tkinter import ttk

__all__ = [
    "apply", "rung_color", "style_listbox",
    "BACKGROUND", "SURFACE", "INK", "MUTED", "BORDER", "ACCENT", "AMBER", "DANGER",
    "RUNG_COLORS", "FONT_PREFERENCES",
]

# ── palette — a restrained, warm-neutral set, not the stock system grey ─────
BACKGROUND = "#f6f4ef"   # the window's own ground: warm off-white, not stark
SURFACE = "#ffffff"      # a raised panel/listbox surface against BACKGROUND
INK = "#22262e"          # body text — near-black, never pure #000
MUTED = "#6b7280"        # quiet grey — ambient fact, the resting cover's tone
BORDER = "#dcd6c9"       # hairline separators, flat-widget outlines
ACCENT = "#3c6e58"       # the one accent: buttons, the open pane's affordance
ACCENT_HOVER = "#2f5846"
AMBER = "#b5791b"        # the warm amber L4 draws the eye with
DANGER = "#a23b3b"       # reserved for L5's entry below; never painted onto a value

#: Per-rung colour for a list pane's rows (I-33 — one indicator per pane; the
#: row's own colour *is* that indicator, not a second one). `L5` never reaches
#: a row (the gate drops it before a `Row` exists) so this entry is unused by
#: any current view — kept so a future surface that names a rung in text has
#: one place to ask, rather than re-deriving the mapping.
RUNG_COLORS: dict[Rung, str] = {
    Rung.L1: MUTED,   # a public record, ambient — quiet grey
    Rung.L2: MUTED,   # household activity, no protected category — quiet grey
    Rung.L3: INK,     # resolves to a party — plain ink, nothing alarming
    Rung.L4: AMBER,   # protected/derived — the one colour that should stand out
    Rung.L5: DANGER,  # sealed; never drawn on any surface (I-13's no-override)
}

#: Preference order for the body font — proportional, legible, and present on
#: at least one of the three CI platforms without asking the operator to
#: install anything. Probed at runtime against what Tk actually has
#: (`tkinter.font.families()`); the first hit wins, and Tk's own
#: `TkDefaultFont` family is the fallback if none of these are installed, so
#: the theme never raises for a missing font.
FONT_PREFERENCES: tuple[str, ...] = (
    "Segoe UI", "Helvetica Neue", "SF Pro Text", "Noto Sans",
    "Liberation Sans", "DejaVu Sans", "Helvetica", "Arial",
)


def _pick_family(root: "tk.Misc") -> str:
    """The first available name in `FONT_PREFERENCES`, or Tk's own default
    font's family if none of them are installed. Reads only the font table
    Tk itself exposes — no filesystem probing, nothing outside stdlib."""
    import tkinter.font as tkfont

    available = set(tkfont.families(root))
    for name in FONT_PREFERENCES:
        if name in available:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


def rung_color(rung: Rung) -> str:
    """The colour a rung draws in, on the one surface (a list pane) that
    shows more than one rung at once. Unknown input is not this theme's to
    guess at — every real `Rung` is covered, so a `KeyError` here means a
    caller is holding something that never came from `serve()`."""
    return RUNG_COLORS[rung]


def style_listbox(listbox: "tk.Listbox") -> None:
    """`tk.Listbox` is a classic (pre-ttk) widget — `ttk.Style` has no reach
    into it — so a view styles one directly through this helper rather than
    repeating the same options at every call site. Flat, borderless, and on
    the theme's own surface colour; `activestyle="none"` drops the
    underline-on-hover Tk draws by default, which reads as a stray edit mark
    on a read-only list."""
    listbox.configure(
        background=SURFACE, foreground=INK,
        selectbackground=ACCENT, selectforeground=SURFACE,
        highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
        borderwidth=0, relief="flat", activestyle="none",
    )


def apply(root: "tk.Misc") -> "ttk.Style":
    """Configure every `ttk` style this app's views use, and the root
    window's own background (a `ttk.Frame` on a stock-grey root still shows
    grey at the edges the frame doesn't cover). Returns the `Style` handle in
    case a caller wants to layer something further — no view in this bite
    needs to.

    Idempotent: safe to call more than once on the same root (re-`configure`
    is how `ttk.Style` is meant to be driven; there is no "already applied"
    state to guard)."""
    from tkinter import ttk

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        # The only stock theme whose widgets actually take flat/borderless
        # styling — the platform-native themes (aqua, vista, alt, default)
        # draw their own bevels over whatever `configure()` is handed.
        style.theme_use("clam")

    family = _pick_family(root)
    body = (family, 11)
    heading = (family, 21, "bold")
    subheading = (family, 12)
    muted_body = (family, 11)

    root.configure(background=BACKGROUND)

    style.configure(".", background=BACKGROUND, foreground=INK, font=body)
    style.configure("TFrame", background=BACKGROUND)
    style.configure("TLabel", background=BACKGROUND, foreground=INK, font=body)
    style.configure("Heading.TLabel", font=heading, foreground=INK)
    style.configure("Subheading.TLabel", font=subheading, foreground=MUTED)
    style.configure("Muted.TLabel", font=muted_body, foreground=MUTED)
    style.configure("Rung.TLabel", font=muted_body, foreground=MUTED)

    style.configure(
        "TButton", font=body, padding=(16, 9), relief="flat", borderwidth=0,
        background=ACCENT, foreground=SURFACE,
    )
    style.map(
        "TButton",
        background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)],
        foreground=[("disabled", MUTED)],
    )

    style.configure(
        "Secondary.TButton", font=body, padding=(16, 9), relief="flat",
        borderwidth=1, background=SURFACE, foreground=INK,
    )
    style.map(
        "Secondary.TButton",
        background=[("active", BACKGROUND)],
        bordercolor=[("!disabled", BORDER)],
    )

    return style
