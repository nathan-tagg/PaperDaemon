"""The links on a PDF's pages: where each one is on its page and where it goes -- another page of the same PDF, or a
web address. The viewer lays them over the page so a tap follows them, as the tablet does; and a PDF with no
outline gets its chapters from the links on its contents pages (chapters.py).

Read with PDFium under pdflock.LOCK (it is not safe on two threads at once). Positions are fractions of the page
(0..1 from the top left), so they fit the picture of the page at any size.
"""
import ctypes

from paperdaemon.pdflock import LOCK


def _page_links(pd, idx):
    """[{"box": (x0, y0, x1, y1) as fractions of the page from its top left, "page": target pdf index | None,
    "uri": str | None}] for one page of an open pypdfium2 document. Caller holds LOCK."""
    import pypdfium2.raw as pdfium_c
    page = pd[idx]
    try:
        w, h = page.get_size()
        out = []
        pos = ctypes.c_int(0)
        link = pdfium_c.FPDF_LINK()
        while pdfium_c.FPDFLink_Enumerate(page.raw, ctypes.byref(pos), ctypes.byref(link)):
            rect = pdfium_c.FS_RECTF()
            if not pdfium_c.FPDFLink_GetAnnotRect(link, ctypes.byref(rect)):
                continue
            target, uri = None, None
            dest = pdfium_c.FPDFLink_GetDest(pd.raw, link)
            if not dest:
                action = pdfium_c.FPDFLink_GetAction(link)
                if action:
                    kind = pdfium_c.FPDFAction_GetType(action)
                    if kind == pdfium_c.PDFACTION_GOTO:
                        dest = pdfium_c.FPDFAction_GetDest(pd.raw, action)
                    elif kind == pdfium_c.PDFACTION_URI:
                        n = pdfium_c.FPDFAction_GetURIPath(pd.raw, action, None, 0)
                        if n > 1:
                            buf = ctypes.create_string_buffer(n)
                            pdfium_c.FPDFAction_GetURIPath(pd.raw, action, buf, n)
                            uri = buf.value.decode("utf-8", "replace")
            if dest:
                i = pdfium_c.FPDFDest_GetDestPageIndex(pd.raw, dest)
                target = int(i) if i >= 0 else None
            if target is None and not uri:
                continue
            x0, x1 = sorted((rect.left, rect.right))
            y0, y1 = sorted((rect.bottom, rect.top))
            out.append({"box": (max(0.0, x0 / w), max(0.0, 1 - y1 / h), min(1.0, x1 / w), min(1.0, 1 - y0 / h)),
                        "page": target, "uri": uri})
        return out
    finally:
        page.close()


def on_page(pdf_path, idx):
    """The links on page `idx` (0-based, of the PDF file)."""
    import pypdfium2
    with LOCK:
        pd = pypdfium2.PdfDocument(pdf_path)
        try:
            if not 0 <= idx < len(pd):
                return []
            return _page_links(pd, idx)
        finally:
            pd.close()


def _columns(links, gap=0.12):
    """Each link's column: the links' left edges grouped where they leave a gap wider than `gap` of the page."""
    xs = sorted(l["box"][0] for l in links)
    starts = [xs[0]] if xs else []
    for a, b in zip(xs, xs[1:]):
        if b - a > gap:
            starts.append(b)
    return [sum(1 for s in starts if l["box"][0] >= s) - 1 for l in links]


def _reading_order(links):
    """Links in reading order: column by column, each top to bottom (a row's title before its page number)."""
    cols = _columns(links)
    return [l for _c, l in sorted(zip(cols, links), key=lambda cl: (cl[0], round(cl[1]["box"][1], 3), cl[1]["box"][0]))]


def contents(pd, first=40, least=5, steady=0.9):
    """Chapters from a PDF's contents pages, for a PDF with no outline: among its first pages, a contents page holds at
    least `least` links to later pages, and read in order (column by column, top to bottom) their targets climb
    through the book (`steady` of them at least: an index or a page of cross-references jumps about). Each link's
    words are the chapter's title, its target the chapter's page. -> [(title, pdf page index, level)] in the book's
    order, or []. Caller holds LOCK."""
    out, seen = [], set()
    for idx in range(min(first, len(pd))):
        links = _reading_order([l for l in _page_links(pd, idx) if l["page"] is not None and l["page"] > idx])
        if len(links) < least:
            continue
        t = [l["page"] for l in links]
        if sum(1 for a, b in zip(t, t[1:]) if b >= a) / float(len(t) - 1) < steady:
            continue
        page = pd[idx]
        try:
            w, h = page.get_size()
            tp = page.get_textpage()
            try:
                cols = _columns(links)
                left = {}
                for c, l in zip(cols, links):
                    left[c] = min(left.get(c, 1.0), l["box"][0])
                for c, l in zip(cols, links):
                    x0, y0, x1, y1 = l["box"]
                    title = " ".join(tp.get_text_bounded(left=x0 * w, bottom=(1 - y1) * h, right=x1 * w,
                                                         top=(1 - y0) * h).split())
                    if not title or l["page"] in seen:
                        continue
                    seen.add(l["page"])
                    # indented further than its column's leftmost link: one level down
                    out.append((title[:120], l["page"], 1 if x0 - left[c] > 0.03 else 0))
            finally:
                tp.close()
        finally:
            page.close()
    return sorted(out, key=lambda c: c[1])
