"""S1 — the window's surface state, mirroring homestead-law's
`tests/test_window.py` shape. `Window` composes through `serve()` and
calculates nothing: no rung is compared here, no `.payload` is reached — the
crossing already happened by the time a `Row` or a `Served` exists.
"""
from __future__ import annotations

from homestead.keep.rungs import Classified, Disposition, Rung

from homestead_ledger.app.window import Row, Window


def _classified_records():
    return [
        (("checking", "date", "t1"), Classified(Rung.L2, "2026-08-01")),
        (("checking", "description", "t1"), Classified(Rung.L3, "Whole Foods", derived="a payee is on file")),
        (("checking", "amount", "t1"), Classified(Rung.L4, "-84.23", derived="a debit is on file")),
        (("checking", "account_number", "t1"), Classified(Rung.L5, "9821")),
    ]


def test_the_window_rests_on_the_cover_before_anything_opens():
    window = Window()
    assert window.state == "cover"
    assert window.rows == []
    assert window.detail is None


def test_open_list_renders_l1_l2_l3_and_derives_l4_and_drops_l5():
    window = Window()
    rows = window.open_list(_classified_records())

    by_ref = {row.ref: row for row in rows}
    assert by_ref[("checking", "date", "t1")].text == "2026-08-01"
    assert by_ref[("checking", "date", "t1")].rung is Rung.L2
    assert by_ref[("checking", "description", "t1")].text == "Whole Foods"
    assert by_ref[("checking", "amount", "t1")].text == "a debit is on file"
    assert by_ref[("checking", "amount", "t1")].rung is Rung.L4
    assert ("checking", "account_number", "t1") not in by_ref
    assert window.state == "list"


def test_open_list_never_shows_a_raw_l4_amount():
    window = Window()
    rows = window.open_list(_classified_records())
    amount_row = next(r for r in rows if r.ref[1] == "amount")
    assert "84.23" not in amount_row.text


def test_open_detail_renders_the_l4_payload():
    window = Window()
    window.open_list(_classified_records())
    served = window.open_detail(("checking", "amount", "t1"))
    assert served.disposition is Disposition.RENDER
    assert served.value == "-84.23"
    assert window.state == "detail"


def test_open_detail_still_denies_l5():
    window = Window()
    window.open_list(_classified_records())
    served = window.open_detail(("checking", "account_number", "t1"))
    assert served.disposition is Disposition.DENY
    assert served.value is None


def test_close_returns_to_the_cover_and_lets_go_of_the_working_set():
    window = Window()
    window.open_list(_classified_records())
    window.open_detail(("checking", "amount", "t1"))
    window.close()

    assert window.state == "cover"
    assert window.rows == []
    assert window.detail is None


def test_rows_is_a_copy_a_view_cannot_mutate_the_surface():
    window = Window()
    rows = window.open_list(_classified_records())
    rows.append(Row(ref=("x", "y", "z"), rung=Rung.L1, text="planted"))
    assert len(window.rows) != len(rows)
