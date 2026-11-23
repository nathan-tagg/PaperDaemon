"""Printing a notebook's pages (11-23): a screen of the tablet a sheet; the pages asked for checked against the
notebook; a printer Windows does not have refused. (Paper is never used here: a real print goes through Microsoft
Print to PDF to a file, by hand.)"""
import pytest

from paperdaemon import printing as P


def test_a_screen_of_the_tablet_is_a_sheet():
    assert P.sheets_of(1620, 2160) == [(0, 2160)]                  # a page of one screen, fitted whole
    assert P.sheets_of(1620, 2200) == [(0, 2200)]                  # a sliver past it stays on the one sheet
    long = P.sheets_of(1620, 16883)                                # the Tools page: a screen a sheet, in order
    assert len(long) == 8 and long[0] == (0, 2160) and long[-1][1] == 16883
    assert all(a == b for (_, a), (b, _) in zip(long, long[1:]))   # nothing left out, nothing twice


def test_the_pages_and_the_printer_are_checked(monkeypatch):
    from paperdaemon.pipeline.page import render as R
    monkeypatch.setattr(P, "printers", lambda: {"printers": ["Office"], "default": "Office"})
    monkeypatch.setattr(R, "live_pages", lambda doc: [{"id": "a"}, {"id": "b"}])
    with pytest.raises(P.PrintError, match="no printer named"):
        P.print_pages("d", [1], "Elsewhere")
    with pytest.raises(P.PrintError, match="pages are 1 to 2"):
        P.print_pages("d", [3], "Office")
    with pytest.raises(P.PrintError, match="no printer chosen"):
        P.print_pages("d", [1], "")
