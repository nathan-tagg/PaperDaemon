r"""The text of a PDF page and where each line of it sits on the tablet page -- for highlighting.

Highlighting PDF pages works like this: the model tells the host what text to highlight, the host
finds it on the PDF (a simple string match is not robust enough, hence the passes below), then
finds the exact location on the page and places the stroke down.

The text layer is read with pypdfium2: every character with its box.
What the model asks for is found in it in three passes, strictest first --

  1. the same words, after normalizing what a PDF does to text: curly quotes, dashes, ligatures
     (the "fi" in "finish" is one character in many PDFs), soft hyphens, a word hyphenated across a
     line break, line breaks and runs of spaces;
  2. the same letters with every space gone, for letter-spaced headings ("W E E K L Y  N O T E S")
     and PDFs that space words oddly -- only for asks of 8 letters or more, so "the rap" cannot
     land in "therapy";
  3. the closest stretch of letters (difflib, spaces gone), for an ask quoted from memory with a
     word missing or changed, on a text layer whose spacing is wrong -- accepted when three quarters
     of the ask's letters line up inside a stretch no longer than 1.6 times the ask.

A match is returned as one box per LINE it spans, in the page's own frame -- the one the ink lives
in: the PDF page at rm_render.PDF_SCALE (1404 units to 157.5 mm, whatever the page's size), x
centered on 0 and y down from the page's top, exactly as rm_render._paste_source draws it. How the
tablet shows the page (`customZoomScale`, `verticalScroll`) does not move the ink.

    py rm_pdftext.py <file.pdf> <page index> "text to find"      a probe: the hits and their boxes
"""
import difflib
import math
import os
import re
import sys
import glob
import io
import json
import time
import uuid
import zlib

_CACHE = {}
_MAP = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
        "“": '"', "”": '"', "„": '"', "″": '"',
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
        " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
        "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
        "æ": "ae", "œ": "oe"}


def load(path, idx):
    """-> {"text", "boxes": [(l, b, r, t) per character, PDF points], "size": (W, H), "rotation"}."""
    key = (path, os.path.getmtime(path), idx)
    if key in _CACHE:
        return _CACHE[key]
    import pypdfium2 as pf
    from paperdaemon.pdflock import LOCK
    with LOCK:                                       # PDFium is not safe on two threads at once
        pdf = pf.PdfDocument(path)
        try:
            page = pdf[idx]
            tp = page.get_textpage()
            n = tp.count_chars()
            text = tp.get_text_range(0, n) if n else ""
            boxes = [tp.get_charbox(i, loose=True) for i in range(n)]
            out = {"text": text, "boxes": boxes, "size": tuple(page.get_size()), "rotation": page.get_rotation()}
        finally:
            pdf.close()
    # pdfium can give back a text a character longer or shorter than its count (a trailing
    # generated break): the two are kept the same length so an index means one thing
    if len(out["text"]) < len(out["boxes"]):
        out["text"] += " " * (len(out["boxes"]) - len(out["text"]))
    out["text"] = out["text"][:len(out["boxes"])]
    _CACHE[key] = out
    return out


def _stream(text, spaces=True):
    """Text -> (normalized string, index of the original character behind each of its characters).

    Lower case; quotes, dashes, spaces and ligatures to one form; a word hyphenated at a line break
    joined; anything that is not a letter, digit or apostrophe a single space. With spaces=False
    every space goes as well."""
    out, back = [], []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "­":                               # a soft hyphen is not in the words
            i += 1
            continue
        if ch in "-‐‑" and i + 1 < n and text[i + 1] in "\r\n":
            j = i + 1
            while j < n and text[j] in "\r\n ":
                j += 1
            if j < n and text[j].isalpha() and i > 0 and text[i - 1].isalpha():
                i = j                                    # "con-\r\ncept" reads "concept"
                continue
        m = _MAP.get(ch, ch).lower()
        for c in m:
            c = c if (c.isalnum() or c == "'") else " "
            if c == " " and (not spaces or (out and out[-1] == " ") or not out):
                continue
            out.append(c)
            back.append(i)
        i += 1
    while out and out[-1] == " ":
        out.pop()
        back.pop()
    return "".join(out), back


def find_spans(text, query, max_hits=12):
    """Where `query` is in `text` -> ([(start, end) original character ranges], how, score)."""
    norm, back = _stream(text)
    q, _ = _stream(query)
    if not q:
        return [], None, 0.0
    spans, at = [], 0
    while len(spans) < max_hits:                          # 1. the same words
        k = norm.find(q, at)
        if k < 0:
            break
        spans.append((back[k], back[k + len(q) - 1] + 1))
        at = k + len(q)
    if spans:
        return spans, "exact", 1.0
    qs, _ = _stream(query, spaces=False)
    if len(qs) >= 8:                                      # 2. the same letters, no spaces
        ns, nback = _stream(text, spaces=False)
        at = 0
        while len(spans) < max_hits:
            k = ns.find(qs, at)
            if k < 0:
                break
            spans.append((nback[k], nback[k + len(qs) - 1] + 1))
            at = k + len(qs)
        if spans:
            return spans, "letters", 1.0
    # 3. the closest stretch of LETTERS -- not of words: a PDF's text layer drops spaces ("One
    # thingthat theteam asks") and adds them inside words ("THE WE EK ... REPO RT") on the same page,
    # so words do not line up and letters do. The ask's letters are
    # aligned against the page's, and the densest stretch no longer than 1.6x the ask wins if it
    # holds three quarters of the ask's letters.
    if len(qs) < 8:
        return [], None, 0.0
    ns, nback = _stream(text, spaces=False)
    sm = difflib.SequenceMatcher(None, ns, qs, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size >= 3]
    best = (0, 0, 0)
    for i, b0 in enumerate(blocks):
        got, hi = 0, b0.a
        for bj in blocks[i:]:
            if bj.a + bj.size - b0.a > 1.6 * len(qs):
                break
            got += bj.size
            hi = bj.a + bj.size
        if got > best[0]:
            best = (got, b0.a, hi)
    score = round(best[0] / float(len(qs)), 3)
    if score >= 0.75:
        return [(nback[best[1]], nback[best[2] - 1] + 1)], "close", score
    return [], None, score


def line_rects(page, start, end):
    """The characters start..end as one rectangle per line, in PDF points (l, b, r, t). A line
    ends at a line break, or where the next character is not on the same baseline band."""
    text, boxes = page["text"], page["boxes"]
    rects, cur = [], None
    for i in range(start, min(end, len(boxes))):
        ch = text[i] if i < len(text) else " "
        l, b, r, t = boxes[i]
        if ch in "\r\n" or r - l <= 0 or t - b <= 0 or ch.isspace():
            if ch in "\r\n" and cur:
                rects.append(cur)
                cur = None
            continue
        if cur and not (b < cur[3] and t > cur[1] and l >= cur[0] - 2):
            rects.append(cur)                             # a new line: no vertical overlap, or back left
            cur = None
        cur = [l, b, r, t] if cur is None else [min(cur[0], l), min(cur[1], b), max(cur[2], r), max(cur[3], t)]
    if cur:
        rects.append(cur)
    return [tuple(x) for x in rects]


def mapper(size):
    """PDF points -> page units: the PDF page at rm_render.PDF_SCALE, x from the page's center,
    y down from its top."""
    from paperdaemon.pipeline.page import render as R
    W, H = size
    s = R.PDF_SCALE
    return lambda x, y: ((x - W / 2.0) * s, (H - y) * s)


def to_page(rect, m):
    (x0, y1), (x1, y0) = m(rect[0], rect[1]), m(rect[2], rect[3])
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def find(path, idx, query, max_hits=12):
    """`query` on page `idx` of the PDF -> {"hits": [{"text", "boxes": [page-unit boxes per line]}],
    "how", "score"}."""
    page = load(path, idx)
    spans, how, score = find_spans(page["text"], query, max_hits)
    m = mapper(page["size"])
    hits = []
    for a, b in spans:
        boxes = [to_page(r, m) for r in line_rects(page, a, b)]
        if boxes:
            hits.append({"text": " ".join(page["text"][a:b].split()), "boxes": boxes})
    return {"hits": hits, "how": how, "score": score, "rotation": page["rotation"]}


def boxes_in(path, idx, box):
    """The text lines inside a page-unit box (a pointed-at region) -> page-unit boxes per line."""
    page = load(path, idx)
    m = mapper(page["size"])
    inside = []
    for i, bx in enumerate(page["boxes"]):
        l, b, r, t = bx
        if r - l <= 0 or t - b <= 0:
            continue
        x0, y0, x1, y1 = to_page(bx, m)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
            inside.append(i)
    if not inside:
        return []
    return [to_page(r, m) for r in line_rects(page, inside[0], inside[-1] + 1)]


def word_at(path, idx, x, y, reach=18.0):
    """The WORD at a page-unit point (what an arrow points at, where "circle this" means a word) ->
    (its text, its page-unit box), or None when no letter lies within `reach` of the point."""
    page = load(path, idx)
    m = mapper(page["size"])
    text, best = page["text"], None
    for i, bx in enumerate(page["boxes"]):
        if not (text[i].isalnum() and bx[2] - bx[0] > 0 and bx[3] - bx[1] > 0):
            continue
        x0, y0, x1, y1 = to_page(bx, m)
        d = math.hypot(max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1))
        if d <= reach and (best is None or d < best[0]):
            best = (d, i)
    if best is None:
        return None
    a = b = best[1]
    while a > 0 and (text[a - 1].isalnum() or text[a - 1] in "'’-"):
        a -= 1
    while b + 1 < len(text) and (text[b + 1].isalnum() or text[b + 1] in "'’-"):
        b += 1
    rs = [to_page(page["boxes"][k], m) for k in range(a, b + 1) if page["boxes"][k][2] > page["boxes"][k][0]]
    return text[a:b + 1], (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


def text_of(path, idx, limit=3000):
    """The page's words, as the model is shown them: one line per PDF line, runs of spaces one."""
    t = load(path, idx)["text"].replace("\r\n", "\n").replace("\r", "\n")
    t = "\n".join(" ".join(ln.split()) for ln in t.split("\n") if ln.strip())
    return t[:limit]


# -------------------------------------------------------------------- on the tablet
def source(doc, page_no):
    """A notebook page's PDF, if it is a PDF page -> (path, index) or None."""
    from paperdaemon.pipeline.page import render as R
    kind, path, idx = R.source_page(doc, page_no)
    if kind != "pdf" or path is None or idx is None:
        return None
    return path, int(idx)


# ==================================================================================================
# Put PICTURES on the tablet directly: a PDF-backed document, one image per page.
#
# The other way to get a chart onto a page is to decompose it into pen strokes (rm_paint,
# UI mode) and write those into a notebook page. That is the right thing when the chart has to
# live INSIDE an existing notebook next to the user's ink, because a notebook page (.rm) cannot
# carry a raster at all. But when a page IS the picture -- a calendar, a week, a map, a chart
# sheet -- a PDF document shows the render itself:
#
#     * exact: every pixel of the render, no OCR, no thin-gray rule dropped, no stroke budget
#     * instant: no decomposition (a 1300-px page traces in 1-20 s; a PDF page is written in ms)
#     * true color: the device shows the PDF's colors, not the six pen colors
#     * annotatable: ink goes on top in its own layer, exactly as on any PDF
#     * but: the picture is not strokes. It cannot be erased with the pen, cannot be edited,
#       and cannot be appended to a notebook that already exists -- a PDF document is its own
#       document, in a folder, with as many pages as it has images.
#
# The device lays a PDF page's ink at a fixed 1404 units to 157.5 mm, whatever the page's size
# (rm_render.PDF_SCALE). So a page authored at
# 157.5 x 210 mm is exactly 1404 x 1872 device pixels, and an image rendered at that size lands
# pixel for pixel. That is what this module does: it fits each picture onto a white 1404 x 1872 canvas,
# writes a PDF with one such page per picture (FlateDecode, no JPEG ringing on line art), stages
# the document the way the app would (.content, .metadata, .pagedata, a blank .rm per page derived
# from a real device page), and pushes it to the cloud with rm_cloud.push_new_doc.
#
#     import rm_pdfdoc as PD
#     doc = PD.make_doc("Charts", ["a.png", "b.png"], folder="Reports")
#     # -> {"doc": uuid, "pages": 2, "pdf": ..., "pushed": {...}}
#
# `images` may be paths or PIL images; `captions` (optional, one per image) are set at the foot of
# the page in the tablet's own lettering (RemarkableMono). `folder` is a uuid or a name path.
# `dry_run=True` stages and reports without uploading. Re-running with the same `doc` restages
# that document in place (page ids kept positionally) and pushes with push_doc.
#
# Command line:
#     python rm_pdfdoc.py --name "Charts" --folder Reports a.png b.png [--dry-run]
# ==================================================================================================

HERE = os.path.dirname(os.path.abspath(__file__))
from paperdaemon.remarkable.sync import MIRROR as _LIBRARY
MIRROR = os.environ.get("RM_CACHE") or _LIBRARY
PAGE_W, PAGE_H = 1404, 1872            # device pixels of this module's 157.5 x 210 mm page
PT_W, PT_H = 157.5 / 25.4 * 72, 210.0 / 25.4 * 72     # the same page in PDF points (3:4)
from paperdaemon import paths
FONT_TTF = os.path.join(paths.generated_fonts_dir(), "RemarkableMono-Regular.ttf")


# ------------------------------------------------------------------ pages
def _open(im):
    from PIL import Image
    if isinstance(im, str):
        return Image.open(im).convert("RGB")
    return im.convert("RGB")


def safe_top():
    """The top of this module's page's safe area, in its pixels."""
    try:
        from paperdaemon.pipeline import page as P
        return int(round(P.safe_area((PAGE_W, PAGE_H))[1]))
    except Exception:                          # without the rmscene stack: the same margin, scaled
        return int(round(115.0 * PAGE_W / 1620.0))


def page_image(im, margin=36, caption=None, caption_px=26, top=None):
    """One white 1404 x 1872 page with the picture fitted inside the margins.

    The picture keeps its aspect and is centered horizontally; vertically it sits at `top` px if
    given, else centered (a chart sheet reads better a little above center, so the caller can
    pass top=). A caption, if any, is lettered at the foot in the tablet font.
    """
    from PIL import Image, ImageDraw, ImageFont
    im = _open(im)
    page = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    cap_h = (caption_px + 18) if caption else 0
    # THE TOP IS BELOW THE TABLET'S TOOLBAR: a document page is shown fitted to the screen as a
    # notebook page is, so its safe area's top (rm_page.safe_area) is where the picture may start
    head = max(margin, safe_top())
    avail_w, avail_h = PAGE_W - 2 * margin, PAGE_H - head - margin - cap_h
    s = min(avail_w / float(im.width), avail_h / float(im.height))
    w, h = max(1, int(round(im.width * s))), max(1, int(round(im.height * s)))
    if abs(s - 1.0) > 1e-6:
        im = im.resize((w, h), Image.LANCZOS)
    x = (PAGE_W - w) // 2
    y = head + (avail_h - h) // 2 if top is None else max(head, int(top))
    page.paste(im, (x, y))
    if caption:
        d = ImageDraw.Draw(page)
        try:
            font = ImageFont.truetype(FONT_TTF, caption_px)
        except Exception:
            font = ImageFont.load_default()
        tw = d.textlength(caption, font=font)
        d.text(((PAGE_W - tw) / 2.0, PAGE_H - margin - caption_px - 4), caption,
               fill=(70, 70, 70), font=font)
    return page


# ------------------------------------------------------------------ the PDF
def _predict(buf, columns, colors):
    """PNG `Up` prediction over the rows, which is what /Predictor 12 in a PDF means.

    Flate on raw scan lines cannot see that a page is mostly one color repeated down the sheet;
    with the row above subtracted first it compresses three to four times smaller. It is lossless.
    """
    import numpy as np
    w = columns * colors
    a = np.frombuffer(buf, np.uint8).reshape(-1, w)
    prev = np.vstack([np.zeros((1, w), np.uint8), a[:-1]])
    d = (a.astype(np.int16) - prev.astype(np.int16)).astype(np.uint8)
    return np.hstack([np.full((a.shape[0], 1), 2, np.uint8), d]).tobytes()


def _encode(im, quality=92, max_err=8, mode="auto"):
    """One page -> (extra PDF image-dict entries, stream bytes).

    A PAGE IS ONE OF TWO THINGS and the right codec is not the same for both. A RENDER -- pen
    strokes, a chart, line art -- has a handful of distinct colors, so an /Indexed palette is
    EXACT and small, and JPEG would ring along every hairline. A PHOTOGRAPH has tens of thousands,
    so a palette bands its gradients and JPEG is both smaller and truer to it. Which one a page is
    gets MEASURED rather than assumed: quantize to 256 and look at the error. Under `max_err` at
    the 99th percentile the palette IS the picture; over it, the page is photographic.

    Measured over the 315-page decomposer gallery: 307 MB as raw Flate, 74 MB this way.
    """
    from PIL import Image
    import numpy as np
    if mode != "jpeg":
        q = im.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE)
        if mode == "indexed":
            ok = True
        else:
            a = np.asarray(im, np.uint8).astype(np.int16)
            b = np.asarray(q.convert("RGB"), np.uint8).astype(np.int16)
            ok = float(np.percentile(np.abs(b - a).max(axis=2), 99)) <= max_err
        if ok:
            pal = list((q.getpalette() or [])[:768])
            pal = bytes(pal + [0] * (768 - len(pal)))
            data = zlib.compress(_predict(q.tobytes(), im.width, 1), 9)
            return (("/ColorSpace [/Indexed /DeviceRGB 255 <%s>] /Filter /FlateDecode "
                     "/DecodeParms << /Predictor 12 /Colors 1 /BitsPerComponent 8 /Columns %d >>"
                     % (pal.hex(), im.width)), data)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=quality, subsampling=0, optimize=True)
    return ("/ColorSpace /DeviceRGB /Filter /DCTDecode", b.getvalue())


def _page_obj(i):
    """The object number write_pdf gives page i (0-based): the Pages object is 1, then each page
    writes its image, its content and itself -- so a link can point at a page not yet written."""
    return 4 + 3 * i


def _annots(links):
    """PDF link annotations for one page: [((x0, y0, x1, y1) in page pixels, target page 0-based)] ->
    the page dictionary's /Annots entry. Each is a GoTo to the whole target page (the tablet follows
    internal links, so an index page can send each entry to its page)."""
    if not links:
        return ""
    sx, sy = PT_W / PAGE_W, PT_H / PAGE_H
    out = []
    for (x0, y0, x1, y1), target in links:
        out.append("<< /Type /Annot /Subtype /Link /Rect [%.2f %.2f %.2f %.2f] /Border [0 0 0] "
                   "/A << /S /GoTo /D [%d 0 R /Fit] >> >>"
                   % (x0 * sx, PT_H - y1 * sy, x1 * sx, PT_H - y0 * sy, _page_obj(target)))
    return " /Annots [%s]" % " ".join(out)


def write_pdf(pages, out_path, encode="auto", links=None):
    """A minimal PDF: one image per page, each filling a 3:4 page.

    Written by hand rather than through PIL's PDF plugin, which stores every RGB page as JPEG --
    ringing on every hairline of a chart. `encode` picks the codec PER PAGE (see _encode):
    "auto" measures the page, "indexed" forces the lossless palette, "jpeg" forces JPEG, and
    "flate" is the original raw-RGB stream. `pages` may be a generator: each page is encoded as
    it arrives, so a 315-page document never holds more than one decoded page in memory.
    `links` = {page index: [((x0, y0, x1, y1) in the page's 1404 x 1872 pixels, target page index)]}
    makes those boxes tappable links to other pages of the same document.
    """
    objs = []                                   # object bodies, 1-based

    def add(body):
        objs.append(body)
        return len(objs)

    pages_id = 1
    objs.append(None)                           # placeholder for the Pages object
    page_refs = []
    for n, im in enumerate(pages):
        im = _open(im)
        if im.size != (PAGE_W, PAGE_H):
            im = page_image(im)
        if encode == "flate":
            extra, raw = "/ColorSpace /DeviceRGB /Filter /FlateDecode", zlib.compress(im.tobytes(), 9)
        else:
            extra, raw = _encode(im, mode=encode)
        img_id = add(("<< /Type /XObject /Subtype /Image /Width %d /Height %d "
                      "/BitsPerComponent 8 %s /Length %d >>"
                      % (im.width, im.height, extra, len(raw))).encode("latin-1")
                     + b"\nstream\n" + raw + b"\nendstream")
        content = ("q %.3f 0 0 %.3f 0 0 cm /Im0 Do Q" % (PT_W, PT_H)).encode("latin-1")
        cont_id = add(("<< /Length %d >>" % len(content)).encode("latin-1")
                      + b"\nstream\n" + content + b"\nendstream")
        page_id = add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.3f %.3f] "
                       "/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R%s >>"
                       % (pages_id, PT_W, PT_H, img_id, cont_id, _annots((links or {}).get(n)))).encode("latin-1"))
        assert page_id == _page_obj(n)
        page_refs.append(page_id)
    objs[0] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
               % (" ".join("%d 0 R" % k for k in page_refs), len(page_refs))).encode("latin-1")
    cat_id = add(("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode("latin-1"))

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(("%d 0 obj\n" % i).encode("latin-1"))
        out.write(body)
        out.write(b"\nendobj\n")
    xref = out.tell()
    out.write(("xref\n0 %d\n" % (len(objs) + 1)).encode("latin-1"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(("%010d 00000 n \n" % off).encode("latin-1"))
    out.write(("trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
               % (len(objs) + 1, cat_id, xref)).encode("latin-1"))
    from paperdaemon import paths as _paths
    _paths.write_atomic(out_path, out.getvalue())
    return out_path


# ------------------------------------------------------------------ staging
def resolve_folder(spec):
    """A folder uuid, or a name path like 'Reports' or 'Work/Reports', looked up by name."""
    if not spec:
        return ""
    if len(spec) == 36 and spec.count("-") == 4:
        return spec
    folders = {}
    for f in glob.glob(os.path.join(MIRROR, "*.metadata")):
        try:
            md = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if md.get("type") == "CollectionType" and md.get("parent") != "trash":
            folders[os.path.basename(f)[:-9]] = (md.get("visibleName", ""), md.get("parent", ""))
    parent, uid = "", None
    for part in [p for p in spec.split("/") if p.strip()]:
        hits = [u for u, (name, par) in folders.items()
                if name.lower() == part.strip().lower() and par == parent]
        if not hits:
            raise KeyError("no folder %r under %r" % (part, parent or "(root)"))
        uid = hits[0]
        parent = uid
    return uid


def find_template():
    """The blank .rm of a PDF page: the app's own template (pipeline/rm-templates/blank-pdf-page.rm, a device PDF
    page with its content stripped), never a page borrowed from the user's library. Every PDF page's SceneInfo says
    paper_size 1404x1872, whatever the PDF page's size; that is all it describes. -> (path, bytes)."""
    from paperdaemon.pipeline import TEMPLATES
    path = os.path.join(TEMPLATES, "blank-pdf-page.rm")
    with open(path, "rb") as f:
        return path, f.read()


def stage(name, pdf_path, folder="", doc=None, page_ids=None):
    """Write the document's files into the mirror. Returns (doc uuid, {page_no: page id})."""
    from paperdaemon.remarkable import library as P
    from paperdaemon.pipeline.page import render as R
    import pypdfium2 as pdfium
    from paperdaemon.pdflock import LOCK
    with LOCK:                                       # PDFium is not safe on two threads at once
        _pdf = pdfium.PdfDocument(pdf_path)
        try:
            n_pages = len(_pdf)
            # the first page's frame, as the device lays its ink (1404 x 1872 for this module's own pages)
            fw, fh = (int(round(v * R.PDF_SCALE)) for v in _pdf[0].get_size())
        finally:
            _pdf.close()
    parent = resolve_folder(folder)
    _, blank = find_template()
    doc = doc or str(uuid.uuid4())
    ddir = os.path.join(MIRROR, doc)
    os.makedirs(ddir, exist_ok=True)
    page_ids = dict((int(k), v) for k, v in (page_ids or {}).items())
    for old in glob.glob(os.path.join(ddir, "*.rm")):      # a restage starts from blank pages
        os.remove(old)
    pages, idxv = [], "ba"
    for i in range(1, n_pages + 1):
        pid = page_ids.get(i) or str(uuid.uuid4())
        page_ids[i] = pid
        pages.append({"id": pid, "idx": {"timestamp": "1:2", "value": idxv},
                      "redir": {"timestamp": "1:2", "value": i - 1},
                      "template": {"timestamp": "1:2", "value": "Blank"}})
        idxv = P.next_idx(idxv)
        paths.write_atomic(os.path.join(ddir, pid + ".rm"), blank)
    with open(pdf_path, "rb") as f:
        data = f.read()
    paths.write_atomic(os.path.join(MIRROR, doc + ".pdf"), data)
    content = {
        "cPages": {"lastOpened": {"timestamp": "1:1", "value": page_ids[1]},
                   "original": {"timestamp": "1:1", "value": n_pages}, "pages": pages},
        "coverPageNumber": 0, "customZoomCenterX": 0, "customZoomCenterY": fh // 2,
        "customZoomOrientation": "portrait", "customZoomPageHeight": fh,
        "customZoomPageWidth": fw, "customZoomScale": 1,
        "documentMetadata": {"title": name}, "extraMetadata": {},
        "fileType": "pdf", "fontName": "", "formatVersion": 2, "lineHeight": -1,
        "orientation": "portrait", "pageCount": n_pages, "pageTags": [],
        "sizeInBytes": str(len(data)), "tags": [], "textAlignment": "justify",
        "textScale": 1, "zoomMode": "bestFit"}
    try:
        # rebuilt in place: the tags are the user's, and stay (a page's tag while that page is still there)
        was = json.load(open(os.path.join(MIRROR, doc + ".content"), encoding="utf-8"))
        content["tags"] = was.get("tags") or []
        content["pageTags"] = [t for t in was.get("pageTags") or [] if t.get("pageId") in [p["id"] for p in pages]]
    except (OSError, ValueError):
        pass
    now = str(int(time.time() * 1000))
    metadata = {"createdTime": now, "lastModified": now, "lastOpened": now, "lastOpenedPage": 0,
                "new": False, "parent": parent, "pinned": False, "source": "",
                "type": "DocumentType", "visibleName": name}
    paths.write_json_atomic(os.path.join(MIRROR, doc + ".content"), content)
    paths.write_json_atomic(os.path.join(MIRROR, doc + ".metadata"), metadata)
    paths.write_atomic(os.path.join(MIRROR, doc + ".pagedata"), "Blank\n" * n_pages)
    return doc, page_ids


def make_doc(name, images, folder="", captions=None, out_dir=None, dry_run=False, doc=None,
             page_ids=None, tops=None):
    """Render, stage and push. Returns a dict with the doc uuid, page count, pdf path, push result."""
    from paperdaemon.remarkable import sync as C
    out_dir = out_dir or os.path.join(paths.state_dir(), "rm-pdfdoc")
    os.makedirs(out_dir, exist_ok=True)
    pages = []
    for i, im in enumerate(images):
        cap = captions[i] if captions and i < len(captions) else None
        top = tops[i] if tops and i < len(tops) else None
        pages.append(page_image(im, caption=cap, top=top))
    safe = "".join(ch if ch.isalnum() else "-" for ch in name)[:40]
    pdf = write_pdf(pages, os.path.join(out_dir, safe + ".pdf"))
    doc, page_ids = stage(name, pdf, folder, doc=doc, page_ids=page_ids)
    res = {"doc": doc, "pages": len(pages), "pdf": pdf, "page_ids": page_ids,
           "bytes": os.path.getsize(pdf)}
    # new to the cloud -> create; already there -> update in place. The cloud decides, not the
    # mirror: a staged-but-never-pushed document must still be CREATED.
    pushed = C.push_new_doc(doc, dry_run=dry_run)
    if isinstance(pushed, dict) and "already exists" in str(pushed.get("error", "")):
        pushed = C.push_doc(doc, dry_run=dry_run)
    res["pushed"] = pushed
    return res
