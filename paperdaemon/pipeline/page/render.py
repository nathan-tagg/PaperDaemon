"""Render a reMarkable .rm v6 page to PNG.

Model verified against the reMarkable desktop app:

  strokes      SceneLineItemBlock where item.value is a Line.
               item.value is None for erased/undone strokes -- they persist in
               the file. Block count != stroke count; always filter.

  width        Point.width is the tablet's own per-sample width. Use it; do not
               model width from pressure. FINELINER/HIGHLIGHTER are constant
               (ts*8 and ts*120); PAINTBRUSH varies and tapers at stroke ends.

  color       Highlighters carry Line.color_rgba as an (R,G,B,A) tuple.
               Line.color collapses every highlighter to PenColor.HIGHLIGHT, so
               it is useless for them. Other pens use the Line.color enum and
               have color_rgba == None. Palette values are little-endian: read
               the raw bytes forward and orange comes out pale blue.

  blending     Measured from the desktop app (screenshots): strokes
               composite in file order; pens are opaque; the highlighter is a
               per-channel MINIMUM ("darken") wash -- stacked colors are min() of
               the stack (all 63 combinations verified exactly), same color twice is
               itself, a pen under a wash becomes min(pen, wash), a pen drawn after
               covers. The older note below was wrong about overlaps:
               OLD: Highlighter is flat and opaque -- overlapping strokes do
               not darken, mix, or accumulate opacity (unlike a real
               highlighter). Later strokes simply cover earlier ones. Verified
               where green avocado meets yellow toast: sharp edge, no olive.

  layering     File order matters (later calibration). The
               decomposer deliberately emits washes before opaque ink.

  frame        Notebook pages are 1620x2160 with x centered on 0 and y starting
               at 0. A PDF page is the PDF page itself at PDF_SCALE, centered
               the same way (page_frame). Ink outside the frame (x beyond
               +/-810, y negative) falls back to stroke extents.
"""
import collections, dataclasses, json, logging, math, os, random, threading
from PIL import Image, ImageChops, ImageDraw

from rmscene import read_blocks
from rmscene import scene_stream as ss
from rmscene.scene_items import Line

from paperdaemon.remarkable.sync import MIRROR as _LIBRARY
RM = os.environ.get("RM_CACHE") or _LIBRARY
PAGE_W, PAGE_H = 1620, 2160
# A PDF PAGE'S INK IS AT A FIXED SCALE: 1404 page units to 157.5 mm (226.4 to the inch),
# whatever the PDF page's size, centered on x = 0 with the page's top at y = 0. It is NOT the PDF
# fitted into SceneInfo's paper_size, which says 1404x1872 on every PDF page. The two agree only on
# a 157.5 x 210 mm page -- the size of the first PDFs checked -- so fitting looked verified.
# Handwritten marks on 870 x 1160 pt pages settled it: at this scale all of them sit on the page and
# strikethroughs run through the lines they strike (the scale came out within 0.3% of this one);
# fitted, most of the ink lay off the page.
PDF_SCALE = 1404 / (157.5 / 25.4 * 72)       # page units per PDF point

# Pen colors as the desktop app renders them -- read off screenshots of a calibration page:
# a marker bar of every PenColor, sampled where it covers a
# highlighter swatch (opaque, so pure). The earlier table had the HIGHLIGHTER pastels in the
# marker slots 3-7 (blue was (190,234,254); the marker is a deep (48,74,224)). 9 (HIGHLIGHT) is
# invisible as a pen; 2 is white.
ENUM = {0: (0, 0, 0), 1: (144, 144, 144), 2: (255, 255, 255), 3: (254, 253, 96),
        4: (169, 250, 92), 5: (255, 85, 207), 6: (48, 74, 224), 7: (194, 49, 50),
        8: (191, 191, 191), 9: (255, 255, 255), 10: (145, 218, 113), 11: (116, 210, 232),
        12: (192, 127, 210), 13: (250, 231, 25)}

# highlighter's width field uses a wider internal unit than the pens
WSCALE = {"HIGHLIGHTER": 0.25}
# pencil and mechanical pencil are rendered by the tablet with a procedural paper
# grain that is NOT in the file: mechanical pencil's width field is constant while
# pressure varies 179..255, so pressure must drive grain/darkness, not width.
# Approximated here by stippling -- close enough to preview, not pixel-exact.
PENCIL_FAMILY = ("PENCIL", "MECHANICAL")
WSCALE_DEFAULT = 0.144                      # fineliner ts=3.0 -> width 24 -> 3.5 px


def _meta(doc):
    return json.load(open(os.path.join(RM, doc + ".metadata")))


def find_doc(name, include_trash=False):
    """Resolve a visibleName to a doc id. A doc id passes straight through.

    Half the toolkit takes a NAME and half takes a UUID, and the two are freely
    mixed in practice. Accepting both here is what stops that being a bug: it
    is why `content_bottom` silently fell back to typed-text-only and let two
    daemon footers land on the same baseline.

    Names are not unique (two notebooks can share one) and trashed documents keep
    their name, so skip parent=='trash' and prefer the most recently modified.
    """
    if name and "-" in name and os.path.exists(os.path.join(RM, name + ".metadata")):
        # A UUID USED TO PASS STRAIGHT THROUGH, TRASHED OR NOT. A trashed document should be treated
        # as gone by the daemon and the whole pipeline; the app manages its trash itself.
        # Resolution by name already skipped the trash; by id it did not, so a trashed document
        # stayed fully reachable to everything downstream.
        if not include_trash:
            try:
                m = json.load(open(os.path.join(RM, name + ".metadata")))
                if m.get("parent") == "trash" or m.get("deleted"):
                    return None
            except Exception:
                pass
        return name
    hits = []
    for f in os.listdir(RM):
        if not f.endswith(".metadata"):
            continue
        try:
            m = json.load(open(os.path.join(RM, f)))
        except Exception:
            continue
        if m.get("visibleName") != name or m.get("deleted"):
            continue
        if not include_trash and m.get("parent") == "trash":
            continue
        hits.append((int(m.get("lastModified", 0)), f[:-9]))
    if not hits:
        raise KeyError("no live document named %r" % name)
    hits.sort(reverse=True)
    if len(hits) > 1:
        print("  note: %d live docs named %r; using most recent (%s)"
              % (len(hits), name, hits[0][1]))
    return hits[0][1]


_BLOCKS = {}          # path -> ((mtime_ns, size), blocks)


def blocks_of(path):
    """The parsed blocks of a page file, cached by the file's (mtime, size). READ ONLY.

    One job parsed the same page about sixty times -- strokes for the render, again for the marks,
    again for the arrows, the typed text for the paragraphs, again for the collision boxes, again
    for the text bottom, a snapshot before the write, another after -- and rmscene's parse of a
    busy page is a second or more. Measured: 153 of 173 s of the host's own work was
    `read_blocks`. Every reader goes through here now; every WRITER (rm_erase, rm_typed.insert,
    rm_art.write_rm, rm_images.insert) still parses its own fresh copy, because it mutates what
    it parsed, and the write changes mtime and size, which is what invalidates this.
    """
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    hit = _BLOCKS.get(path)
    if hit is not None and hit[0] == key:
        return hit[1]
    with open(path, "rb") as f:
        blocks = list(read_blocks(f))
    if len(_BLOCKS) >= 12:
        _BLOCKS.clear()
    _BLOCKS[path] = (key, blocks)
    return blocks


# A PAGE READ FROM ANOTHER FILE, in this process only: {(doc, page id): path}. The conflict job renders the copy of a
# page a job had made (set aside when the tablet's copy won) without writing anything into the mirror.
_PAGE_FILES = {}


def page_file(doc, pid):
    """The .rm file a page is read from: the mirror's, unless `reading()` points it elsewhere."""
    return _PAGE_FILES.get((doc, pid)) or os.path.join(RM, doc, pid + ".rm")


class reading:
    """`with reading(doc, pid, path):` reads that page from `path` (renders, typed text) for the block's length."""

    def __init__(self, doc, pid, path):
        self.k, self.path = (doc, pid), path

    def __enter__(self):
        _PAGE_FILES[self.k] = self.path
        return self

    def __exit__(self, *a):
        _PAGE_FILES.pop(self.k, None)
        return False


def live_pages(doc):
    """Pages the app will show. cPages includes deleted pages; they have no .rm."""
    from paperdaemon.remarkable.sync import live_pages as live
    with open(os.path.join(RM, doc + ".content"), encoding="utf-8") as f:
        return live(json.load(f))


def dead_ranges(blocks):
    """Id ranges a tombstone has deleted: (start, end) inclusive.

    A tombstone's `deleted_length` deletes N ids from its own, so anything
    allocated inside one is erased as far as the device is concerned.
    """
    out = []
    for b in blocks:
        if isinstance(b, ss.SceneLineItemBlock) and (b.item.deleted_length or 0) > 1:
            s = b.item.item_id.part2
            out.append((s, s + b.item.deleted_length - 1))
    return out


_TEXT_START, _TEXT_END = (1 << 48) - 2, (1 << 48) - 1     # a group's anchor at the start or the end of the text


def _anchor_offsets(doc, page_no, blocks):
    """Where the tablet draws each group anchored to the typed text: its node id -> (dx, dy), its ancestors'
    shifts included. A group anchored to the text moves across by its `anchor_origin_x` and down to its anchor:
    the text's top (anchored at its start), its bottom (at its end), or the paragraph whose newline it names."""
    own, parent = {}, {}
    for b in blocks:
        if isinstance(b, ss.TreeNodeBlock):
            g = b.group
            a = getattr(getattr(g, "anchor_id", None), "value", None)
            if a is not None:
                own[g.node_id] = (float(getattr(getattr(g, "anchor_origin_x", None), "value", 0.0) or 0.0), a)
        elif isinstance(b, ss.SceneGroupItemBlock):
            child = getattr(b.item, "value", None)
            if child is not None:
                parent[child] = b.parent_id
    if not own:
        return {}
    top, bottom, starts = 0.0, 0.0, {}
    try:
        from paperdaemon.pipeline.page import typed as _TY
        tb, paras = _TY.paragraphs(doc, page_no)
        top = float(tb.pos_y) if tb is not None else 0.0
        bottom = float(_TY.text_bottom(doc, page_no) or top)
        starts = {tuple(p["start_id"]): float(p["y"]) for p in paras if p.get("start_id") is not None and p.get("y") is not None}
    except Exception:
        pass

    # MEASURED where a recorded picture is anchored to the same place (images.measured_anchors): exact, where the
    # typed-text layout below is an estimate
    try:
        from paperdaemon.pipeline.page import images as _IM
        measured = _IM.measured_anchors(doc, page_no)
    except Exception:
        measured = {}

    def anchor_y(a):
        if (a.part1, a.part2) in measured:
            return measured[(a.part1, a.part2)]
        if a.part1 == 0 and a.part2 == _TEXT_START:
            return top
        if a.part1 == 0 and a.part2 == _TEXT_END:
            return bottom
        return starts.get((a.part1, a.part2 + 1), bottom)       # the newline ending the paragraph before

    out = {}

    def shift(node, depth=0):
        if node in out:
            return out[node]
        dx = dy = 0.0
        if node in own:
            dx, dy = own[node][0], anchor_y(own[node][1])
        up = parent.get(node)
        if up is not None and depth < 32:
            pdx, pdy = shift(up, depth + 1)
            dx, dy = dx + pdx, dy + pdy
        out[node] = (dx, dy)
        return out[node]
    for n in list(own) + list(parent):
        shift(n)
    return out


def strokes(doc, page_no):
    """Live strokes on a 1-based page number, as the app numbers them.

    EXCLUDES strokes whose id sits inside a deleted RANGE, because the device
    does. This function is the eyes of the whole system -- previews, collision
    checks, the model's own render() -- so it must agree with the device or it
    actively misleads. This renderer
    draws any Line it finds; the device does not -- it honors other items'
    `deleted_length`. That gap once hid 44 strokes written into ids 872..915
    while a tombstone covered 827..931: perfect previews here, blank page on
    the tablet, for hours. If this warns, the page WILL look wrong on the
    device no matter how good the PNG looks.
    """
    pid = live_pages(doc)[page_no - 1]["id"]
    path = page_file(doc, pid)
    if not os.path.exists(path):
        return []                   # never written on: a PDF or EPUB page, or a blank sheet, has no ink file
    blocks = blocks_of(path)
    dead = dead_ranges(blocks)
    # WHERE THE TABLET DRAWS EACH STROKE, always: a group the tablet anchored to the typed text is stored offset
    # from the page, and read at its stored place it was drawn, ruled on, collided with and pointed at somewhere
    # it is not (a sentence over the board read as lying across the user's handwriting at the top). The copy keeps
    # its STORED identity (P.skey), which is what erasing and hiding match in the file.
    shifts = _anchor_offsets(doc, page_no, blocks)
    out, buried = [], 0
    for b in blocks:
        if isinstance(b, ss.SceneLineItemBlock):
            v = getattr(b.item, "value", None)
            if isinstance(v, Line):
                n = b.item.item_id.part2
                if any(a <= n <= z for a, z in dead):
                    buried += 1          # the device treats this as erased
                else:
                    d = shifts.get(b.parent_id)
                    if d and (d[0] or d[1]):             # where the tablet draws it
                        from paperdaemon.pipeline import page as _P
                        key = _P.skey(v)
                        v = dataclasses.replace(v, points=[dataclasses.replace(p, x=p.x + d[0], y=p.y + d[1]) for p in v.points])
                        v._stored_key = key
                    out.append(v)
    if buried:
        logging.getLogger("rm_render").error(
            "%d stroke(s) on %s p%s have ids inside a DELETED RANGE %s -- the "
            "device treats them as erased, so they are EXCLUDED from this "
            "render. The page really is missing them.",
            buried, str(doc)[:8], page_no, dead)
    return out


_PDF_SIZES = {}


def pdf_page_size(path, idx):
    """A PDF page's (width, height) in points, or None when it cannot be read."""
    try:
        key = (path, os.path.getmtime(path), idx)
    except OSError:
        return None
    if key not in _PDF_SIZES:
        try:
            import pypdfium2 as pdfium
            from paperdaemon.pdflock import LOCK
            with LOCK:                               # PDFium is not safe on two threads at once
                pdf = pdfium.PdfDocument(path)
                try:
                    _PDF_SIZES[key] = tuple(pdf[idx].get_size()) if 0 <= idx < len(pdf) else None
                finally:
                    pdf.close()
        except Exception:
            _PDF_SIZES[key] = None
    return _PDF_SIZES[key]


def page_frame(doc, page_no):
    """The page's own frame in page units, (width, height), x centered on 0 and y down from 0.
    A PDF page is its PDF page at PDF_SCALE. Any other page takes SceneInfo's paper_size, which
    varies per document -- 1404x1872 and 1620x2160 both occur -- so never assume one."""
    kind, path, idx = source_page(doc, page_no)
    if kind == "pdf" and path is not None and idx is not None:
        size = pdf_page_size(path, idx)
        if size:
            return (size[0] * PDF_SCALE, size[1] * PDF_SCALE)
    pid = live_pages(doc)[page_no - 1]["id"]
    path = page_file(doc, pid)
    for b in (blocks_of(path) if os.path.exists(path) else []):
        if isinstance(b, ss.SceneInfo) and getattr(b, "paper_size", None):
            return tuple(b.paper_size)
    return (PAGE_W, PAGE_H)


def px_width(L, pt):
    fam = L.tool.name.split("_")[0]
    return max(1.0, pt.width * WSCALE.get(fam, WSCALE_DEFAULT))


# TYPED TEXT IS DRAWN AS IT LOOKS, NOT IN A MARKER COLOR.
# It used to be #5a00a0 violet, "provably outside the device gamut" -- and that proof was never
# sound: the gamut is a symptom of the tablet screen, not of the render that is generated,
# and highlighters take any RGBA, so nothing stopped a decomposition painting that exact
# color. The planning pass now gets the page as accurately as it can be drawn.
# It costs nothing, because the model can already tell: with the app's own faces (typed_layout)
# native text is a proportional typeface, the assistant's replies are the monoline stroke font, and
# the user's hand is irregular. Verified by eye on a page where all three appear together.
# TYPED_HIGHLIGHT is for ERASURE work only -- when the question is "which of these marks is typed
# and may not be touched", ask for it explicitly with render(..., mark_typed=True).
TYPED_COLOR = (0, 0, 0)
TYPED_HIGHLIGHT = (90, 0, 160)


def source_page(doc, page_no):
    """The page of the underlying PDF/EPUB this .rm annotates, if any.

    Returns (kind, path, index) or (None, None, None). Most of the library is
    NOT a plain notebook -- 69 PDFs and 50 EPUBs against 41 notebooks -- so a
    renderer that ignores this is wrong for the majority of pages.

    The link is per page: each entry in cPages.pages carries `redir.value`,
    the 0-based index into the source document.

    **Never use the page's POSITION for this.** Measured on the real library:
    863 pages have `redir != position`. Pages get inserted and reordered, and
    several .rm pages can annotate the SAME source page -- a calendar PDF runs
    0, 1, 1, 2, 2, 3 because a page was added after each one. Positional
    indexing would render the wrong page for most of the library.

    A page with NO `redir` is a blank sheet APPENDED past the end of the source,
    not a failure: every such page in the library sits beyond its document's
    page count (one document has a 1-page PDF and blanks at positions 2-5).
    Those render as blank paper, correctly, with no warning.
    """
    from paperdaemon import ledger as _S
    c = _S.content(doc)
    kind = c.get("fileType")
    if kind not in ("pdf", "epub"):
        return None, None, None
    pages = _S.live_pages(c)
    if page_no - 1 >= len(pages):
        return kind, None, None
    idx = (pages[page_no - 1].get("redir") or {}).get("value")
    if kind == "epub":
        # the cloud keeps an EPUB with its PDF rendition beside it -- the tablet's own pages, which the ink was
        # written on -- so an EPUB page is that PDF's page, and its ink lines up exactly
        pdf = os.path.join(RM, doc + ".pdf")
        if os.path.exists(pdf):
            return "pdf", pdf, idx
    path = os.path.join(RM, doc + "." + kind)
    return kind, (path if os.path.exists(path) else None), idx


def _paste_source(canvas, doc, page_no, page, T):
    """Draw the source document page UNDER the ink. Returns a note, or ''.

    Exact: a PDF page's frame is the PDF page at PDF_SCALE (page_frame), so the
    page is rendered at that scale and laid at the frame's top left. How the
    tablet shows the page -- `customZoom*`, `verticalScroll` -- does not move the
    ink: two scrolled pages carry handwritten marks exactly where they were
    made.
    """
    kind, path, idx = source_page(doc, page_no)
    if kind is None:
        return ""
    if idx is None:
        return ""              # blank page appended past the end of the source
    if path is None:
        return "%s SOURCE MISSING -- ink shown on blank paper" % kind.upper()
    if kind == "epub":
        # An EPUB is reflowable: the device lays it out with its own engine at
        # its own font size. There is no page image to recover, so say so
        # loudly rather than render a blank sheet that looks complete.
        return "EPUB TEXT NOT RENDERED -- ink is shown without the book text"
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return "PDF NOT RENDERED -- pypdfium2 is not installed"
    try:
        pw, ph = page
        from paperdaemon.pdflock import LOCK
        with LOCK:                                   # PDFium is not safe on two threads at once
            pdf = pdfium.PdfDocument(path)
            # CLOSED, always: an open PdfDocument keeps the file locked on Windows, and a document rebuilt in place
            # right after a render could not be replaced -- "Access is denied"
            try:
                if idx >= len(pdf):
                    return "PDF page %d out of range" % idx
                x0, y0 = T(_Pt(-pw / 2.0, 0.0))
                im = pdf[idx].render(scale=PDF_SCALE).to_pil().convert("RGB")
            finally:
                pdf.close()
        canvas.paste(im, (int(round(x0)), int(round(y0))))
        return ""
    except Exception as e:
        return "PDF RENDER FAILED (%s)" % type(e).__name__


class _Pt(object):
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y


def _frame(S, page=(PAGE_W, PAGE_H), extra=()):
    """Return (width, height, transform), using the page's own frame if content fits.

    `extra` is a list of (x, y) page points that must also be inside the frame --
    the typed-text box. Without it the frame is sized to ink alone and any text
    outside the stroke bbox is cropped away silently.
    """
    pw, ph = page
    xs = [p.x for L in S for p in L.points] + [e[0] for e in extra]
    ys = [p.y for L in S for p in L.points] + [e[1] for e in extra]
    if not xs or (-pw/2 <= min(xs) and max(xs) <= pw/2 and 0 <= min(ys) and max(ys) <= ph):      # nothing drawn: the page itself
        return int(round(pw)), int(round(ph)), lambda p: (p.x + pw/2, p.y)
    pad = 60
    x0, y0 = min(xs) - pad, min(ys) - pad
    w = int(max(xs) - x0 + pad)
    h = int(max(ys) - y0 + pad)
    return w, h, lambda p: (p.x - x0, p.y - y0)


def _stipple(d, L, col, pts, rng):
    """Approximate pencil grain: scatter dots across the stroke, density and tone
    driven by pressure. The real texture is procedural on-device."""
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i+1]
        w = px_width(L, L.points[i])
        pr = L.points[i].pressure / 255.0
        seg = math.hypot(x1 - x0, y1 - y0)
        n = max(2, int(seg * max(w, 1.2) * 0.9 * (0.4 + 0.6 * pr)))
        for _ in range(n):
            t = rng.random()
            cx, cy = x0 + (x1-x0)*t, y0 + (y1-y0)*t
            a = rng.random() * 2 * math.pi
            r = (w / 2 + 0.5) * math.sqrt(rng.random())
            k = (0.35 + 0.5 * pr) * (0.45 + 0.55 * rng.random())
            tone = tuple(int(255 - (255 - c) * min(1.0, k)) for c in col)
            d.point([(int(cx + math.cos(a)*r), int(cy + math.sin(a)*r))], fill=tone)


# render(displayed=True): the page as the tablet shows it, for a person to look at. PER THREAD: the engine renders
# thumbnails on one thread while requests render pages on others, and one must never draw with the other's setting
_VIEW = threading.local()


def _draw(d, L, col, pts):
    """THE DECOMPOSER REFERENCE'S stroke shape (rm_lean and rm_raster measure with it; the pictures are drawn by
    pipeline/page/paint.py). One stroke: round-capped, round-joined, per-point width. The HIGHLIGHTER has FLAT ends
    (measured on the app, on calibration pages): each segment a
    rectangle, and no joint -- the outer wedge of every turn stays unpainted."""
    if L.tool.name.split("_")[0] in PENCIL_FAMILY:
        if not getattr(_VIEW, "on", False):
            _stipple(d, L, col, pts, random.Random(int(pts[0][0]) * 7919 + int(pts[0][1])))
            return
        # for a person: a solid line, darker with pressure, as the tablet's pencil reads at normal size
        pr = sum(p.pressure for p in L.points) / (255.0 * max(1, len(L.points)))
        k = 0.6 + 0.4 * min(1.0, pr)
        col = tuple(int(255 - (255 - c) * k) for c in col)
    if L.tool.name.startswith("HIGHLIGHTER"):
        # one rectangle per segment (flat ends) + a bevel triangle on the outer side of each
        # interior vertex, nothing on the inner side (measured on calibration pages)
        Q, Wp = [pts[0]], [L.points[0]]
        for i in range(1, len(pts)):
            if abs(pts[i][0] - Q[-1][0]) > 1e-6 or abs(pts[i][1] - Q[-1][1]) > 1e-6:
                Q.append(pts[i]); Wp.append(L.points[i])
        n = len(Q)
        if n < 2:
            return
        dirs, hw = [], []
        for i in range(n - 1):
            dx, dy = Q[i + 1][0] - Q[i][0], Q[i + 1][1] - Q[i][1]
            ln = (dx * dx + dy * dy) ** 0.5
            dirs.append((dx / ln, dy / ln))
            hw.append(max(0.5, (px_width(L, Wp[i]) + px_width(L, Wp[i + 1])) / 4.0))
        for i in range(n - 1):
            (x0, y0), (x1, y1) = Q[i], Q[i + 1]
            nx, ny = -dirs[i][1] * hw[i], dirs[i][0] * hw[i]
            d.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], fill=col)
        for i in range(1, n - 1):
            (d1x, d1y), (d2x, d2y) = dirs[i - 1], dirs[i]
            cross = d1x * d2y - d1y * d2x
            if abs(cross) < 1e-6:
                continue
            sgn = -1.0 if cross > 0 else 1.0
            vx, vy = Q[i]
            p1 = (vx + sgn * (-d1y) * hw[i - 1], vy + sgn * d1x * hw[i - 1])
            p2 = (vx + sgn * (-d2y) * hw[i], vy + sgn * d2x * hw[i])
            d.polygon([(vx, vy), p1, p2], fill=col)
        return
        dirs = []
        for i in range(n - 1):
            dx, dy = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
            ln = (dx * dx + dy * dy) ** 0.5
            dirs.append((dx / ln, dy / ln) if ln > 1e-9 else (dirs[-1] if dirs else (1.0, 0.0)))
        norms = [(-dy, dx) for dx, dy in dirs]
        ms = []
        for i in range(n):
            if i == 0:
                m = norms[0]
            elif i == n - 1:
                m = norms[-1]
            else:
                sx, sy = norms[i - 1][0] + norms[i][0], norms[i - 1][1] + norms[i][1]
                ln = (sx * sx + sy * sy) ** 0.5
                m = (sx / ln, sy / ln) if ln > 1e-6 else norms[i]
            ms.append(m)
        for i in range(n - 1):
            h0 = max(0.5, px_width(L, L.points[i]) / 2.0); h1 = max(0.5, px_width(L, L.points[i + 1]) / 2.0)
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            (m0x, m0y), (m1x, m1y) = ms[i], ms[i + 1]
            d.polygon([(x0 + m0x * h0, y0 + m0y * h0), (x1 + m1x * h1, y1 + m1y * h1),
                       (x1 - m1x * h1, y1 - m1y * h1), (x0 - m0x * h0, y0 - m0y * h0)], fill=col)
        return
    if len({p.width for p in L.points}) == 1:
        w = px_width(L, L.points[0])
        d.line(pts, fill=col, width=int(round(w)), joint="curve")
        r = w / 2
        for (x, y) in (pts[0], pts[-1]):
            d.ellipse([x-r, y-r, x+r, y+r], fill=col)
        return
    for i in range(len(pts) - 1):
        w = (px_width(L, L.points[i]) + px_width(L, L.points[i+1])) / 2
        d.line([pts[i], pts[i+1]], fill=col, width=int(round(max(1, w))))
        r = w / 2; x, y = pts[i]
        d.ellipse([x-r, y-r, x+r, y+r], fill=col)
    w = px_width(L, L.points[-1]); r = w / 2; x, y = pts[-1]
    d.ellipse([x-r, y-r, x+r, y+r], fill=col)


def render(doc, page_no, out, typed=True, hide=None, hide_typed=None, hide_images=None,
           mark_typed=False, blank_ok=False, displayed=False):
    """Render a page to PNG -- strokes AND typed text.

    TYPED TEXT IS DRAWN BY DEFAULT, and that is not a nicety. This renderer used
    to draw strokes only, so on a page with typed text every preview showed the
    drawing on a blank sheet. Content placed "below the questions" looked
    perfect locally and landed straight on top of them on the device. A preview
    that omits half the page is worse than no preview, because it is believed.

    The typed layout is APPROXIMATE -- the app's font metrics are not ours, so
    wrapping can differ by a word. It is exact enough for the question a preview
    has to answer: what is already here, and where does it end. Pass typed=False
    only when you specifically want ink alone.
    """
    _VIEW.on = bool(displayed)
    try:
        return _render(doc, page_no, out, typed, hide, hide_typed, hide_images, mark_typed, blank_ok, displayed)
    finally:
        _VIEW.on = False


def _render(doc, page_no, out, typed, hide, hide_typed, hide_images, mark_typed, blank_ok, displayed):
    S = strokes(doc, page_no)
    # STAGED ERASURES (rm_host): strokes, typed paragraphs and pictures the current job has
    # erased in its draft are left out, so a preview shows the page as commit() will leave it.
    if hide:
        from paperdaemon.pipeline import page as _P
        S = [L for L in S if _P.skey(L) not in hide]
    tb = None
    if typed:
        try:
            from paperdaemon.pipeline.page import typed as _TY
            tb, _paras = _TY.paragraphs(doc, page_no)
        except Exception:
            tb = None
    # IMAGES placed with the app (a "capture"): drawn under the ink, and counted as content. A page
    # holding only a picture used to raise here and the daemon read it as blank.
    try:
        from paperdaemon.pipeline.page import images as _IM
        _imgs = [im for im in _IM.items(doc, page_no) if im.get("path")]
        if hide_images:
            def _hid(im):
                return any(all(abs(float(a) - float(b)) < 1.5 for a, b in zip(im["box"], hb))
                           for hb in hide_images)
            _imgs = [im for im in _imgs if not _hid(im)]
    except Exception:
        _imgs = []
    if not S and tb is None and not _imgs and not blank_ok:      # the viewer draws an unwritten page as it is
        raise ValueError("no strokes and no typed text on page %d" % page_no)
    # The frame MUST account for typed text. _frame() sizes to the strokes, so
    # on a page where the text sits below (or outside) the ink, the text was
    # simply cropped out of the picture -- the render looked complete and was
    # missing the very thing the reader needed. Measured on a real page:
    # strokes end at y=634, the typed feedback is at y~1163, and it vanished.
    _extra = []
    if tb is not None:
        try:
            from paperdaemon.pipeline.page import typed as _TY2
            _bot = _TY2.text_bottom(doc, page_no) or tb.pos_y
            _extra = [(tb.pos_x, tb.pos_y), (tb.pos_x + tb.width, _bot)]
        except Exception:
            _extra = []
    for _im in _imgs:
        _x0, _y0, _x1, _y1 = _im["box"]
        _extra = list(_extra) + [(_x0, _y0), (_x1, _y1)]
    _page = page_frame(doc, page_no)
    if displayed:
        # the page as the tablet shows it: from its top, at least its full width, centered. The tablet pans past
        # the sides and lets you write there, so ink beyond them widens the picture (evenly, keeping the page in
        # the middle); ink below makes it taller. Only ink above the top is off the page.
        _pw, _ph = _page
        _side = max([abs(p.x) for L in S for p in L.points] + [abs(e[0]) for e in _extra] + [_pw / 2 - 60]) + 60
        _half = max(_pw / 2, _side)
        _low = max([p.y for L in S for p in L.points] + [e[1] for e in _extra] + [_ph - 60]) + 60
        W, H, T = int(round(2 * _half)), int(round(max(_ph, _low))), (lambda p, _h=_half: (p.x + _h, p.y))
    else:
        W, H, T = _frame(S, _page, extra=_extra)
    canvas = Image.new("RGB", (W, H), "white")
    _note = _paste_source(canvas, doc, page_no, _page, T)
    for _im in _imgs:
        try:
            class _Q:
                __slots__ = ("x", "y")
                def __init__(self, x, y): self.x, self.y = x, y
            _x0, _y0, _x1, _y1 = _im["box"]
            _a, _b = T(_Q(_x0, _y0)), T(_Q(_x1, _y1))
            _w, _h = max(1, int(round(_b[0] - _a[0]))), max(1, int(round(_b[1] - _a[1])))
            _pic = Image.open(_im["path"]).convert("RGBA").resize((_w, _h), Image.LANCZOS)
            canvas.paste(_pic, (int(round(_a[0])), int(round(_a[1]))), _pic)
        except Exception:
            pass
    d = ImageDraw.Draw(canvas)
    if _note:
        # Stamped ON the image on purpose: a reader looking at the picture must
        # not be able to miss that part of the page is not shown.
        d.rectangle([0, 0, W, 46], fill=(220, 30, 30))
        d.text((12, 14), _note, fill=(255, 255, 255))
    _typed_n = 0
    if tb is not None:
        try:
            from paperdaemon.pipeline.page import typed as _TY
            # under the ink: the app draws text first, and this way a stroke
            # written over text still reads as being on top
            class _P:                      # T() expects something with .x/.y
                __slots__ = ("x", "y")
                def __init__(self, x, y): self.x, self.y = x, y
            # OUT-OF-GAMUT ON PURPOSE (the marking color for typed text, used only when
            # mark_typed is set).
            # The tablet's color space is a CLOSED, FINITE set: 14 PenColor
            # values plus 6 highlighter palette colors plus paper white. So a
            # color outside that set cannot have come from the device, and
            # "this mark is my overlay" stops being a convention and becomes
            # evidence. Gray failed exactly here -- #c7c7c6 gray is a real
            # highlighter color, so a gray stroke and a gray overlay were the
            # same pixels.
            # Deep violet #5a00a0 sits 137 RGB units from the nearest device
            # color (gray), and is obvious to the eye as well as to a test.
            _typed_n = _TY.draw(d, doc, page_no,
                                xform=lambda x, y: T(_P(x, y)),
                                color=(TYPED_HIGHLIGHT if mark_typed else TYPED_COLOR),
                                skip=hide_typed)
        except Exception:
            pass
    # THE STROKES, by PaperDaemon's one renderer (pipeline/page/paint.py: fastdecomp/render.c), as the tablet draws them:
    # file order; pens opaque in their measured colors; the highlighter a per-channel minimum ("darken") wash; the
    # shader a translucent wash; a pencil toned by its pressure (its grain is the device's, not in the file). For a
    # person (displayed) it is drawn at twice the size and averaged down; otherwise at the tablet's own pixels.
    from paperdaemon.pipeline.page.paint import paint, pencil_tone
    import numpy as _np

    class _O:                                       # T() is a translation: where it puts the page's origin
        __slots__ = ("x", "y")
        def __init__(self, x, y): self.x, self.y = x, y
    _tx, _ty = T(_O(0.0, 0.0))
    ink = []
    for L in S:
        if len(L.points) < 2:
            continue
        a = _np.array([(p.x, p.y, p.width, p.pressure) for p in L.points], _np.float64)
        pts = a[:, :2] + (_tx, _ty)
        fam = L.tool.name.split("_")[0]
        widths = _np.maximum(1.0, a[:, 2] * WSCALE.get(fam, WSCALE_DEFAULT))       # px_width, for the whole stroke
        if L.tool.name.startswith("SHADER"):
            rgba = tuple(L.color_rgba) if getattr(L, "color_rgba", None) else (128, 128, 128, 96)
            ink.append((pts, widths, "shader", rgba[:4]))
        elif L.tool.name.startswith("HIGHLIGHTER"):
            rgb = tuple(L.color_rgba[:3]) if L.color_rgba else (255, 237, 117)
            ink.append((pts, widths, "highlighter", rgb))
        else:
            col = ENUM.get(L.color.value, (0, 0, 0))
            if fam in PENCIL_FAMILY:
                col = pencil_tone(col, float(a[:, 3].mean()) / 255.0)
            ink.append((pts, widths, "pen", col))
    paint(canvas, ink, ss=2 if displayed else 1)
    canvas.save(out)
    tools = collections.Counter(L.tool.name for L in S)
    return len(S), (W, H), tools, _typed_n
