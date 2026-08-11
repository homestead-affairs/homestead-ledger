"""The tkinter view that draws a `Window` — bite 3, ported from
homestead-law's `app/view.py` for the money domain: same shape (cover → list
→ detail, one gated pipeline underneath), only the domain words and the two
list panes change (a matter's queue and its one list become the ledger's
*two* — the checking account's transactions, and the obligations queue).

Thin by construction (I-29): it turns `Window` state into widgets and clicks
into `Window` calls, and holds no domain logic. It draws `Row.text` and
`Served.value` — what the gate handed back — and reaches no `.payload`; the
chokepoint (`tests/test_invariants_chokepoint.py`) makes that a build failure
and also forbids reflection here, so this file only ever renders what it was
served.

It rests on the **cover** (I-21): nothing is drawn until the operator asks,
and the cover shows only the obligation counts that survive re-identification
(`queue.cover`, I-31) — "Nothing is open" whenever nothing survives that
check, which is the honest answer over the single obligation kind bite 2
registers. Opening the checking account composes the accounts→transactions
`S1_LIST` (amounts in their derived L4 form, dates L2, payees L3; the account
number is never a row — L5 has no override, I-13); opening a row's detail
re-serves that one field and the amount renders in full (opening the pane
*is* the purpose declaration). "What's due" composes the obligations queue,
gaps first, then overdue, then soonest (I-8).

**No reveal-expire timer.** I-32's ground is "a reveal does not persist past
the act that asked for it" — `Window.close()` already enforces that by
letting go of the served detail and the working set. law's view adds no timed
expiry on top of that, so this one doesn't either; inventing a timer neither
template has would be scope this bite does not own.

**Bite 4 — real books, with a safe demo fallback.** `run()` opens on the
operator's own store (`store.Canonical()`/`store.Sidecar()`, bound to
`HOMESTEAD_HOME`/`~/.homestead`) whenever it holds anything, so a statement
imported with `--import` actually appears in the list, the detail pane, the
cover, and the what's-due queue. Only when the real store is empty — first
run, nothing imported yet — does the window fall back to a throwaway demo
store (a fresh tmpdir, seeded as `app.demo` always has), so the window is
never blank; the fallback is announced on the cover with `DEMO_BANNER` and
never touches the real store. `compose_store()` is the decision, factored out
of `run()` so it can be driven headlessly (`tests/test_view.py`) without
opening tkinter at all — it returns a `LedgerContext` naming which store won
and why, and `run()` only draws it.

`theme` is applied once, to the root, before any pane is drawn.

`tkinter` is imported inside `run()` so the module stays importable on a
headless box (the suite reads this file; it does not open a display).
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date

from homestead.app import theme
from homestead.keep.rungs import Disposition

from homestead_ledger import registry
from homestead_ledger import queue as queue_mod
from homestead_ledger.app import demo
from homestead_ledger.app.window import Window
from homestead_ledger.packs import checking, obligations
from homestead_ledger.store import Canonical, Sidecar

__all__ = ["run", "compose_store", "LedgerContext", "DEMO_BANNER"]

#: Shown on the cover in place of the ordinary subheading whenever `run()`
#: fell back to the throwaway demo store — the "clearly-visible indicator"
#: piece 1 requires, so demonstration numbers are never mistaken for a real
#: household's books.
DEMO_BANNER = "demonstration data — import a statement with `--import` to see your own books"


@dataclass(frozen=True)
class LedgerContext:
    """Which store `run()` opened the window on, and why. `demo=True` means
    the real store was empty and this is a throwaway fallback seeded by
    `app.demo`; `demo=False` means `canonical`/`sidecar` are the operator's
    own real books. `today` is `date.today()` for the real store, and
    `demo.TODAY` (a fixed reference date) for the demo fallback, matching how
    `app/demo.py` already reckons urgency against a stable date."""

    canonical: Canonical
    sidecar: Sidecar
    today: str
    demo: bool


def _has_real_data(canonical: Canonical, sidecar: Sidecar) -> bool:
    """True the moment the real books hold one transaction for a registered
    account, or the real sidecar holds one record for a registered
    obligation kind. Iterates the registries (I-23) rather than hand-naming
    `"checking"`/`"obligations"`, so a future account or obligation kind is
    picked up with no change here."""
    for account_name in registry.all_accounts():
        if canonical.records(account_name):
            return True
    for kind in registry.all_obligations():
        if sidecar.records(kind):
            return True
    return False


def compose_store() -> LedgerContext:
    """Decide which store the window opens on, and bind it.

    Opens `Canonical()`/`Sidecar()` against whatever `HOMESTEAD_HOME` (or its
    `~/.homestead` default) currently resolves to — the operator's real
    books. If that store holds anything at all, it wins outright and is
    returned untouched: this function never seeds the real store, on any
    path.

    Only when the real store is completely empty does this fall back to a
    fresh throwaway store: a new tmpdir, seeded exactly as `app.demo` seeds
    the window in bite 3 (`demo.seed()` / `demo.seed_obligations()`). The
    fallback redirects `HOMESTEAD_HOME` to that tmpdir before seeding, so the
    operator's real root — checked and found empty just above — is never
    written to.
    """
    canonical = Canonical()
    sidecar = Sidecar()
    if _has_real_data(canonical, sidecar):
        return LedgerContext(
            canonical=canonical, sidecar=sidecar, today=date.today().isoformat(), demo=False,
        )

    # The real store is empty — fall back to a throwaway demo store so the
    # window is never blank on first run. A fresh tmpdir, same posture bite
    # 3's view took for every run; the real root above is left untouched.
    os.environ["HOMESTEAD_HOME"] = tempfile.mkdtemp(prefix="homestead-ledger-demo-")
    demo_canonical = Canonical()
    demo_sidecar = Sidecar()
    demo.seed()
    demo.seed_obligations(demo_sidecar)
    return LedgerContext(
        canonical=demo_canonical, sidecar=demo_sidecar, today=demo.TODAY, demo=True,
    )


def run() -> int:
    import tkinter as tk
    from tkinter import ttk

    ledger = compose_store()
    canonical = ledger.canonical   # the read-only books (I-6) — checking's transactions
    sidecar = ledger.sidecar       # the household's own overlay — obligations live here
    window = Window()
    today = ledger.today

    root = tk.Tk()
    root.title("Homestead Ledger")
    root.minsize(640, 440)
    theme.apply(root)
    content = ttk.Frame(root, padding=24)
    content.pack(fill="both", expand=True)

    def clear() -> None:
        for child in content.winfo_children():
            child.destroy()

    def show_cover() -> None:
        window.close()
        clear()
        ttk.Label(content, text="Homestead Ledger", style="Heading.TLabel").pack(anchor="w")
        subheading = DEMO_BANNER if ledger.demo else "The household's own books."
        ttk.Label(
            content, text=subheading, style="Subheading.TLabel"
        ).pack(anchor="w", pady=(4, 24))
        # The resting cover shows only counts that survive the re-identification
        # check (I-31). Over the single obligation kind bite 2 registers that is
        # nothing, so the cover rests on "Nothing is open" — the queue is there
        # the moment the operator asks for it.
        resting = queue_mod.cover(sidecar, today=today)
        summary = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in resting.items())
        ttk.Label(content, text=summary or "Nothing is open.", style="Muted.TLabel").pack(anchor="w")
        ttk.Button(content, text="What's due", command=show_queue).pack(anchor="w", pady=(24, 0))
        ttk.Button(
            content, text="Open checking account", style="Secondary.TButton", command=show_list,
        ).pack(anchor="w", pady=(8, 0))

    def show_queue() -> None:
        clear()
        # Load the obligations' records into the window so a queue item opens
        # through the same gated detail path as the list — a multi-kind queue
        # would load every obligation kind it spans; bite 2 registers one.
        window.open_list(sidecar.records(obligations.OBLIGATION))
        ttk.Label(content, text="What's due", style="Heading.TLabel").pack(anchor="w")
        subheading = "gaps first, then overdue, then soonest"
        if ledger.demo:
            subheading = f"{subheading} · {DEMO_BANNER}"
        ttk.Label(
            content, text=subheading, style="Subheading.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        items = queue_mod.queue(sidecar, today=today)
        listbox = tk.Listbox(content, height=12)
        theme.style_listbox(listbox)
        listbox.pack(fill="both", expand=True)
        for item in items:
            if item.gap:
                mark = "date unreadable"
            elif item.overdue:
                mark = f"overdue by {abs(item.days_until)}d"
            else:
                mark = f"due in {item.days_until}d"
            listbox.insert("end", f"[{item.rung.value}]  {item.shown}  ·  {mark}")
            listbox.itemconfig("end", foreground=theme.rung_color(item.rung))

        def on_open(_event: object = None) -> None:
            selection = listbox.curselection()
            if selection:
                show_detail(items[selection[0]].ref, back=show_queue)

        listbox.bind("<Double-Button-1>", on_open)
        ttk.Button(content, text="Open", command=on_open).pack(anchor="w", pady=(12, 0))
        ttk.Button(
            content, text="Close", style="Secondary.TButton", command=show_cover,
        ).pack(anchor="w", pady=(4, 0))

    def show_list() -> None:
        clear()
        window.open_list(canonical.records(checking.ACCOUNT))
        ttk.Label(content, text=checking.ACCOUNT, style="Heading.TLabel").pack(anchor="w")
        # one indicator per pane, not per row (I-33): the pane says an L4 is
        # present in its derived form, never a badge on every line — each
        # row's own colour (`theme.rung_color`) is the per-row signal.
        has_l4 = any(row.rung.value == "L4" for row in window.rows)
        subheading = "showing derived · L4 present" if has_l4 else "showing"
        if ledger.demo:
            subheading = f"{subheading} · {DEMO_BANNER}"
        ttk.Label(
            content, text=subheading, style="Subheading.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        listbox = tk.Listbox(content, height=12)
        theme.style_listbox(listbox)
        listbox.pack(fill="both", expand=True)
        rows = window.rows
        for row in rows:
            listbox.insert("end", f"[{row.rung.value}]  {row.text}")
            listbox.itemconfig("end", foreground=theme.rung_color(row.rung))

        def on_open(_event: object = None) -> None:
            selection = listbox.curselection()
            if selection:
                show_detail(rows[selection[0]].ref, back=show_list)

        listbox.bind("<Double-Button-1>", on_open)
        ttk.Button(content, text="Open", command=on_open).pack(anchor="w", pady=(12, 0))
        ttk.Button(
            content, text="Close", style="Secondary.TButton", command=show_cover,
        ).pack(anchor="w", pady=(4, 0))

    def show_detail(ref, back) -> None:
        # `back` is the pane this detail was opened from — the checking list or
        # the queue — so "Back" returns where the operator came from. law's view
        # hard-codes its one list here; the ledger has two panes, so the return
        # target is passed in rather than assumed.
        served = window.open_detail(ref)
        clear()
        ttk.Label(content, text=ref[1], style="Heading.TLabel").pack(anchor="w")
        ttk.Label(content, text=served.rung.value, style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        body = (
            str(served.value)
            if served.disposition is Disposition.RENDER
            else "This record is sealed and is not shown here."
        )
        ttk.Label(content, text=body, wraplength=520, justify="left").pack(anchor="w")
        ttk.Button(
            content, text="Back", style="Secondary.TButton", command=back,
        ).pack(anchor="w", pady=(24, 0))

    show_cover()
    root.mainloop()
    return 0
