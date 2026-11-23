"""PRINTING A NOTEBOOK'S PAGES (11-23, the maintainer: Ctrl+P in the page editor; the printers Windows has; this page,
a range or the whole notebook; a size -- fill, fit, actual size; how many sheets it comes to, said before printing).
Each page is drawn by PaperDaemon's renderer, the whole page as the tablet draws it, one pixel a page unit, and
printed through Windows' own printing (the spooler and GDI, called directly: no other program is driven to do it).

THE SIZES, every piece centered on its sheet (the maintainer: "If its small, fill should also center the print"):
  fill    the page fills the sheet -- a page of one tablet screen covers the printable area, its edges trimmed where the
          paper's shape differs; a longer page runs on at the sheet's full width, a sheet's height of it at a time
  fit     each page shrunk onto one sheet, however long
  actual  as big as on the tablet (229 pixels an inch), never wider than the sheet; a longer page runs on"""
import ctypes
import math
import os
import tempfile
from ctypes import wintypes

SIZES = ("fill", "fit", "actual")
TABLET_DPI = 229.0                                # a Paper Pro page: 1620 x 2160 pixels, 7.07 x 9.43 inches
PRINTER_ENUM_LOCAL, PRINTER_ENUM_CONNECTIONS = 0x2, 0x4
HORZRES, VERTRES, LOGPIXELSX = 8, 10, 88
HALFTONE, SRCCOPY, DIB_RGB_COLORS = 4, 0x00CC0020, 0
SLIVER = 0.02                                     # a piece this much past a sheet stays on it, shrunk a little


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


def _gdi():
    gdi = ctypes.WinDLL("gdi32")
    gdi.CreateDCW.restype = gdi.CreateICW.restype = wintypes.HDC
    gdi.CreateDCW.argtypes = gdi.CreateICW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
    gdi.StartDocW.argtypes = [wintypes.HDC, ctypes.POINTER(_DOCINFO)]
    for fn in ("StartPage", "EndPage", "EndDoc", "AbortDoc", "DeleteDC"):
        getattr(gdi, fn).argtypes = [wintypes.HDC]
    gdi.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi.StretchDIBits.argtypes = [wintypes.HDC] + [ctypes.c_int] * 8 + [ctypes.c_void_p, ctypes.c_void_p,
                                                                       wintypes.UINT, wintypes.DWORD]
    return gdi


def paper(printer):
    """The printer's printable area and resolution -> (width, height, pixels an inch), asked of it without printing (an
    information context)."""
    gdi = _gdi()
    ic = gdi.CreateICW("WINSPOOL", printer, None, None)
    if not ic:
        raise PrintError("the printer %r could not be opened" % printer)
    try:
        return gdi.GetDeviceCaps(ic, HORZRES), gdi.GetDeviceCaps(ic, VERTRES), gdi.GetDeviceCaps(ic, LOGPIXELSX) or 600
    finally:
        gdi.DeleteDC(ic)


def _rows(height, rows):
    """[(top, bottom)] cutting `height` into pieces of `rows`, a sliver at the end kept on the last."""
    out, top = [], 0
    while top < height:
        bottom = min(height, int(round(top + rows)))
        if height - bottom <= rows * SLIVER:
            bottom = height
        out.append((top, bottom))
        top = bottom
    return out


def cuts(width, height, size, pw, ph, dpi):
    """A page picture `width` x `height` on a sheet of printable `pw` x `ph` device pixels at `dpi` -> [(top, bottom,
    scale, cover)], one a sheet: the rows of the picture it holds, device pixels a picture pixel, and whether it covers
    the sheet (its edges trimmed) rather than fitting inside it."""
    if size == "fit":
        return [(0, height, min(pw / float(width), ph / float(height)), False)]
    if size == "actual":
        s = min(dpi / TABLET_DPI, pw / float(width))
        rows = ph / s
        if height <= rows * (1 + SLIVER):
            return [(0, height, min(s, ph / float(height)), False)]
        return [(a, b, min(s, ph / float(b - a)), False) for a, b in _rows(height, rows)]
    # fill
    if height <= width * 4.0 / 3.0 * (1 + SLIVER):      # a page of one tablet screen covers the sheet
        return [(0, height, max(pw / float(width), ph / float(height)), True)]
    s = pw / float(width)
    return [(a, b, min(s, ph / float(b - a)), False) for a, b in _rows(height, ph / s)]


def plan(doc, pages, printer, size):
    """How many sheets printing `pages` of `doc` on `printer` at `size` comes to -> {"sheets", "per_page"}."""
    from .pipeline.page import render as R
    size = size if size in SIZES else "fill"
    pw, ph, dpi = paper(printer)
    per = []
    for n in pages:
        w, h = R.frame_size(doc, n)
        per.append(len(cuts(w, h, size, pw, ph, dpi)))
    return {"sheets": sum(per), "per_page": per}


def _print_images(images, printer, title, size="fill", output=None):
    """PIL pictures printed on `printer` at `size`, each on its sheets (cuts), every piece centered, as one print job
    named `title` (`output`: a file the printer writes to instead -- a check through Microsoft Print to PDF)."""
    gdi = _gdi()
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
            dpi = gdi.GetDeviceCaps(dc, LOGPIXELSX) or 600
            for im in images:
                im = im.convert("RGB")
                w, h = im.size
                for top, bottom, scale, cover in cuts(w, h, size, pw, ph, dpi):
                    part = im.crop((0, top, w, bottom))
                    if cover:                              # the sheet covered: what runs past it, trimmed evenly
                        cw, ch = min(w, int(math.floor(pw / scale))), min(bottom - top, int(math.floor(ph / scale)))
                        x0, y0 = (w - cw) // 2, ((bottom - top) - ch) // 2
                        part = part.crop((x0, y0, x0 + cw, y0 + ch))
                    sw, sh = part.size
                    dw, dh = min(pw, int(round(sw * scale))), min(ph, int(round(sh * scale)))
                    stride = (sw * 3 + 3) & ~3
                    raw = part.tobytes("raw", "BGR", stride, 1)       # rows padded to 4 bytes, top row first
                    bmi = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), sw, -sh, 1, 24, 0, 0, 0, 0, 0, 0)
                    if gdi.StartPage(dc) <= 0:
                        raise PrintError("the printer %r refused a page" % printer)
                    gdi.SetStretchBltMode(dc, HALFTONE)
                    got = gdi.StretchDIBits(dc, (pw - dw) // 2, (ph - dh) // 2, dw, dh, 0, 0, sw, sh, raw,
                                            ctypes.byref(bmi), DIB_RGB_COLORS, SRCCOPY)
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


def _check(doc, pages, printer):
    from .pipeline.page import render as R
    if not printer:
        raise PrintError("no printer chosen")
    if printer not in printers()["printers"]:
        raise PrintError("Windows has no printer named %r" % printer)
    total = len(R.live_pages(doc))
    pages = [int(n) for n in pages]
    if not pages or any(n < 1 or n > total for n in pages):
        raise PrintError("pages are 1 to %d" % total)
    return pages


def check_plan(doc, pages, printer, size):
    """plan(), its pages and printer checked first."""
    return plan(doc, _check(doc, pages, printer), printer, size)


def print_pages(doc, pages, printer, size="fill", title=None, output=None):
    """Pages `pages` (numbers from 1) of `doc` printed on `printer` at `size` -> {"pages": n, "sheets": m}. Each page
    drawn whole by PaperDaemon's renderer, one pixel a page unit."""
    from PIL import Image
    from .pipeline.page import render as R
    pages = _check(doc, pages, printer)
    size = size if size in SIZES else "fill"
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
    return {"pages": len(pages), "sheets": _print_images(images, printer, title, size, output)}
