"""Printing a notebook's pages (11-23): the three sizes -- fill, fit, actual -- and how a page is cut onto sheets; the
pages asked for checked against the notebook; a printer Windows does not have refused. (Paper is never used here: a
real print goes through Microsoft Print to PDF to a file, by hand.)"""
import pytest

from paperdaemon import printing as P

LETTER = (5100, 6600, 600)                       # Microsoft Print to PDF, Letter at 600 dpi: the whole sheet printable


def test_fill_covers_the_sheet_with_a_page_of_one_screen_and_runs_a_long_page_on():
    one = P.cuts(1620, 2160, "fill", *LETTER)
    assert len(one) == 1 and one[0][3]                             # covers the sheet (its edges trimmed)
    long = P.cuts(1620, 20030, "fill", *LETTER)
    assert len(long) == 10 and long[0][:2] == (0, 2096) and long[-1][1] == 20030
    assert all(a[1] == b[0] for a, b in zip(long, long[1:]))       # nothing left out, nothing twice
    assert not any(c[3] for c in long)                             # pieces fitted, the short last one centered


def test_fit_puts_every_page_on_one_sheet():
    assert len(P.cuts(1620, 20030, "fit", *LETTER)) == 1
    assert len(P.cuts(1620, 2160, "fit", *LETTER)) == 1


def test_actual_size_is_the_tablets_and_runs_a_long_page_on():
    one = P.cuts(1620, 2160, "actual", *LETTER)
    assert len(one) == 1 and abs(one[0][2] - 600 / 229.0) < 1e-9   # 229 pixels an inch, as on the tablet
    assert len(P.cuts(1620, 20030, "actual", *LETTER)) == 8


def test_the_pages_and_the_printer_are_checked(monkeypatch):
    from paperdaemon.pipeline.page import render as R
    monkeypatch.setattr(P, "printers", lambda: {"printers": ["Office"], "default": "Office"})
    monkeypatch.setattr(R, "live_pages", lambda doc: [{"id": "a"}, {"id": "b"}])
    with pytest.raises(P.PrintError, match="no printer named"):
        P.print_pages("d", [1], "Elsewhere")
    with pytest.raises(P.PrintError, match="pages are 1 to 2"):
        P.check_plan("d", [3], "Office", "fill")
    with pytest.raises(P.PrintError, match="no printer chosen"):
        P.print_pages("d", [1], "")
