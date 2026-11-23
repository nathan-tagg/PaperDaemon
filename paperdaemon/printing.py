"""PRINTING A NOTEBOOK'S PAGES (11-23, the maintainer: Ctrl+P in the page editor; the printers Windows has; this page,
a range or the whole notebook). Each page is drawn by PaperDaemon's renderer, the whole page as the tablet draws it,
one pixel a page unit, and printed through Windows' own printing (the spooler and GDI, called directly: no other
program is driven to do it). A page fills the sheet's printable width; a page written past its first screen runs on
over as many sheets as it takes, never shrunk to one."""
import ctypes
import os
import tempfile
from ctypes import wintypes

PRINTER_ENUM_LOCAL, PRINTER_ENUM_CONNECTIONS = 0x2, 0x4
HORZRES, VERTRES = 8, 10
HALFTONE, SRCCOPY, DIB_RGB_COLORS = 4, 0x00CC0020, 0


class _DOCINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_int), ("lpszDocName", wintypes.LPCWSTR), ("lpszOutput", wintypes.LPCWSTR),
                ("lpszDatatype", wintypes.LPCWSTR), ("fwType", wintypes.DWORD)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class _PRINTER_INFO_4(ctypes.Structure):
    _fields_ = [("pPrinterName", wintypes.LPWSTR), ("pServerName", wintypes.LPWSTR), ("Attributes", wintypes.DWORD)]


class PrintError(Exception):
    pass


def printers():
    """The printers Windows has, and its default -> {"printers": [names], "default": name or None}."""
    winspool = ctypes.WinDLL("winspool.drv")
    flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    need, count = wintypes.DWORD(0), wintypes.DWORD(0)
    winspool.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(need), ctypes.byref(count))
    names = []
    if need.value:
        buf = ctypes.create_string_buffer(need.value)
        if winspool.EnumPrintersW(flags, None, 4, buf, need, ctypes.byref(need), ctypes.byref(count)):
            infos = ctypes.cast(buf, ctypes.POINTER(_PRINTER_INFO_4))
            names = [infos[i].pPrinterName for i in range(count.value) if infos[i].pPrinterName]
    size = wintypes.DWORD(0)
    winspool.GetDefaultPrinterW(None, ctypes.byref(size))
    default = None
    if size.value:
        b = ctypes.create_unicode_buffer(size.value)
        if winspool.GetDefaultPrinterW(b, ctypes.byref(size)):
            default = b.value
    return {"printers": names, "default": default if default in names else (names[0] if names else None)}


def sheets_of(width, height, sheet_w=None, sheet_h=None):
    """A page picture `width` x `height` -> [(top, bottom)] rows of it, one a sheet: A SCREEN OF THE TABLET A SHEET.
    A page of one screen (3:4, or within a sliver of it) is one sheet, fitted whole; a page written past its first
    screen runs on, a screen's height of it a sheet, each fitted the same. (`sheet_w`, `sheet_h` are not needed: every
    sheet is fitted to its paper as it is printed.)"""
    screen = width * 4.0 / 3.0
    if height <= screen * 1.02:
        return [(0, height)]
    out, top = [], 0
    while top < height:
        bottom = min(height, int(round(top + screen)))
        if height - bottom < screen * 0.02:                  # (not a sheet for a sliver at the end)
            bottom = height
        out.append((top, bottom))
        top = bottom
    return out


def _print_images(images, printer, title, output=None):
    """PIL pictures printed on `printer`, each on its sheets (sheets_of), as one print job named `title` (`output`: a
    file the printer writes to instead -- a check through Microsoft Print to PDF, nothing on paper)."""
    gdi = ctypes.WinDLL("gdi32")
    gdi.CreateDCW.restype = wintypes.HDC
    gdi.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
    gdi.StartDocW.argtypes = [wintypes.HDC, ctypes.POINTER(_DOCINFO)]
    for fn in ("StartPage", "EndPage", "EndDoc", "AbortDoc", "DeleteDC"):
        getattr(gdi, fn).argtypes = [wintypes.HDC]
    gdi.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi.StretchDIBits.argtypes = [wintypes.HDC] + [ctypes.c_int] * 8 + [ctypes.c_void_p, ctypes.c_void_p,
                                                                       wintypes.UINT, wintypes.DWORD]
    dc = gdi.CreateDCW("WINSPOOL", printer, None, None)
    if not dc:
        raise PrintError("the printer %r could not be opened" % printer)
    sheets = 0
    try:
        di = _DOCINFO(ctypes.sizeof(_DOCINFO), title, output, None, 0)
        if gdi.StartDocW(dc, ctypes.byref(di)) <= 0:
            raise PrintError("the printer %r did not start the job" % printer)
        try:
            pw, ph = gdi.GetDeviceCaps(dc, HORZRES), gdi.GetDeviceCaps(dc, VERTRES)
            for im in images:
                im = im.convert("RGB")
                w, h = im.size
                for top, bottom in sheets_of(w, h, pw, ph):
                    part = im.crop((0, top, w, bottom))
                    pw_, ph_ = part.size
                    scale = min(pw / float(pw_), ph / float(ph_))
                    dw, dh = int(pw_ * scale), int(ph_ * scale)
                    stride = (pw_ * 3 + 3) & ~3
                    raw = part.tobytes("raw", "BGR", stride, 1)       # rows padded to 4 bytes, top row first
                    bmi = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), pw_, -ph_, 1, 24, 0, 0, 0, 0, 0, 0)
                    if gdi.StartPage(dc) <= 0:
                        raise PrintError("the printer %r refused a page" % printer)
                    gdi.SetStretchBltMode(dc, HALFTONE)
                    got = gdi.StretchDIBits(dc, (pw - dw) // 2, 0, dw, dh, 0, 0, pw_, ph_, raw, ctypes.byref(bmi),
                                            DIB_RGB_COLORS, SRCCOPY)
                    gdi.EndPage(dc)
                    if got == 0:
                        raise PrintError("a page could not be sent to the printer %r" % printer)
                    sheets += 1
            gdi.EndDoc(dc)
        except Exception:
            gdi.AbortDoc(dc)
            raise
    finally:
        gdi.DeleteDC(dc)
    return sheets


def print_pages(doc, pages, printer, title=None, output=None):
    """Pages `pages` (numbers from 1) of `doc` printed on `printer` -> {"pages": n, "sheets": m}. Each page drawn whole by
    PaperDaemon's renderer, one pixel a page unit."""
    from PIL import Image
    from .pipeline.page import render as R
    if not printer:
        raise PrintError("no printer chosen")
    if printer not in printers()["printers"]:
        raise PrintError("Windows has no printer named %r" % printer)
    total = len(R.live_pages(doc))
    pages = [int(n) for n in pages]
    if not pages or any(n < 1 or n > total for n in pages):
        raise PrintError("pages are 1 to %d" % total)
    images = []
    with tempfile.TemporaryDirectory(prefix="pd-print-") as tmp:
        for n in pages:
            out = os.path.join(tmp, "page-%d.png" % n)
            R.render(doc, n, out, blank_ok=True)
            with Image.open(out) as im:
                images.append(im.convert("RGB"))
    if title is None:
        from .remarkable import library
        title = str((library.items().get(doc) or {}).get("visibleName") or "PaperDaemon")
    return {"pages": len(pages), "sheets": _print_images(images, printer, title, output)}
