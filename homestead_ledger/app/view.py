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

Synthetic data only (`app.demo`), in a throwaway store, until bite 4 wires a
real import — so running this never writes a real household's books. `theme`
is applied once, to the root, before any pane is drawn.

`tkinter` is imported inside `run()` so the module stays importable on a
headless box (the suite reads this file; it does not open a display).
"""
from __future__ import annotations

import os
import tempfile

from homestead.keep.rungs import Disposition

from homestead_ledger import queue as queue_mod
from homestead_ledger.app import demo, theme
from homestead_ledger.app.window import Window
from homestead_ledger.packs import obligations
from homestead_ledger.store import Canonical, Sidecar


def run() -> int:
    import tkinter as tk
    from tkinter import ttk

    # A throwaway root, so running the view never touches a real household
    # store — the same posture law's and the engine's `view.run()` take.
    os.environ.setdefault("HOMESTEAD_HOME", tempfile.mkdtemp(prefix="homestead-ledger-demo-"))
    canonical = Canonical()   # the read-only books (I-6) — checking's transactions
    sidecar = Sidecar()       # the household's own overlay — obligations live here
    demo.seed()
    demo.seed_obligations(sidecar)
    window = Window()
    today = demo.TODAY   # synthetic data; the real app would use date.today()

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
        ttk.Label(
            content, text="The household's own books.", style="Subheading.TLabel"
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
        ttk.Label(
            content, text="gaps first, then overdue, then soonest", style="Subheading.TLabel",
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
        window.open_list(canonical.records(demo.ACCOUNT))
        ttk.Label(content, text=demo.ACCOUNT, style="Heading.TLabel").pack(anchor="w")
        # one indicator per pane, not per row (I-33): the pane says an L4 is
        # present in its derived form, never a badge on every line — each
        # row's own colour (`theme.rung_color`) is the per-row signal.
        has_l4 = any(row.rung.value == "L4" for row in window.rows)
        ttk.Label(
            content,
            text="showing derived · L4 present" if has_l4 else "showing",
            style="Subheading.TLabel",
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
