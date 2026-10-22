"""Drawing harness for reMarkable pages.

One geometry definition, two outputs:
  * render_png()  -- fast local preview using the verified render model, so the
                     artwork can be iterated without touching the tablet
  * write_rm()    -- emit the same strokes into a real page

Supports per-point width profiles (taper), which is the single most important
tool for organic line work -- the .rm format stores width per sample, so a
swelling-and-thinning contour is native, not a hack.
"""
import io, math, os, sys
from PIL import Image, ImageChops, ImageDraw

from paperdaemon import paths
from paperdaemon.pipeline.page import render as R
from rmscene import read_blocks, write_blocks
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import CrdtId
from rmscene.scene_items import Line, Point, Pen, PenColor

def _keep_text_highlights():
    """KEEP THE USER'S TEXT HIGHLIGHTS WHOLE THROUGH ANY WRITE.

    The tablet writes a typed-text highlight (a glyph range) as tags 4 color, 5 text, 6 rectangles, 7 first
    character id, 8 last character id, 9 whether the last is included, 10 color (BGRA). rmscene 0.8 reads up to
    6, skips 7-10 as "data written by a newer format" and writes the range back without them, so every write to
    a page -- ours or the host's, a single typed line -- cut the user's highlights loose from their characters
    and lost their color (it also stripped the highlights written by the assistant). Read
    them, keep them on the range, and write them back in the tablet's order."""
    import rmscene.scene_stream as _ss
    from rmscene.scene_stream import TagType as _TT
    if getattr(_ss, "_text_highlights_kept", False):
        return
    read0, write0 = _ss.glyph_range_from_stream, _ss.glyph_range_to_stream

    def read(stream):
        g = read0(stream)
        if stream.data.check_tag(7, _TT.ID):
            g.first_id = stream.read_id(7)
            g.last_id = stream.read_id(8)
            g.include_last = stream.read_bool(9)
            g.color_rgba = stream.read_color_optional(10)
        return g

    def write(stream, item):
        if getattr(item, "first_id", None) is None:
            return write0(stream, item)
        stream.write_int(4, item.color)
        stream.write_string(5, item.text)
        with stream.write_subblock(6):
            stream.data.write_varuint(len(item.rectangles))
            for r in item.rectangles:
                for v in (r.x, r.y, r.w, r.h):
                    stream.data.write_float64(v)
        stream.write_id(7, item.first_id)
        stream.write_id(8, item.last_id)
        stream.write_bool(9, item.include_last)
        if item.color_rgba is not None:
            stream.write_color(10, item.color_rgba)

    _ss.glyph_range_from_stream, _ss.glyph_range_to_stream = read, write
    _ss._text_highlights_kept = True


_keep_text_highlights()

ORANGE = (255, 195, 140)
YELLOW = (255, 237, 117)
GREEN = (172, 255, 133)
BLUE = (190, 234, 254)
MAGENTA = (242, 158, 255)
GRAY = (199, 199, 198)

WPEN, WHL = 0.144, 0.25          # width-field -> pixels


# ----------------------------------------------------------------- geometry
def bez(p0, c1, c2, p3, n=48):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u*u*u*p0[0] + 3*u*u*t*c1[0] + 3*u*t*t*c2[0] + t*t*t*p3[0],
                    u*u*u*p0[1] + 3*u*u*t*c1[1] + 3*u*t*t*c2[1] + t*t*t*p3[1]))
    return out


def cat(*chunks):
    """Join point lists, dropping duplicated joins."""
    out = []
    for c in chunks:
        if out and c and abs(out[-1][0]-c[0][0]) < 1e-6 and abs(out[-1][1]-c[0][1]) < 1e-6:
            out.extend(c[1:])
        else:
            out.extend(c)
    return out


def arc(cx, cy, rx, ry, a0, a1, n=96):
    return [(cx + rx*math.cos(a0 + (a1-a0)*i/n),
             cy + ry*math.sin(a0 + (a1-a0)*i/n)) for i in range(n + 1)]


def spiral(cx, cy, r0, r1, a0, turns, n=110):
    out = []
    for i in range(n + 1):
        t = i / n
        a = a0 + turns * 2 * math.pi * t
        r = r0 + (r1 - r0) * t
        out.append((cx + r*math.cos(a), cy + r*math.sin(a)))
    return out


def rot(pts, cx, cy, deg):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x-cx)*ca - (y-cy)*sa, cy + (x-cx)*sa + (y-cy)*ca) for x, y in pts]



def prof_swell(lo, hi, power=1.0):
    """Thin at both ends, thick in the middle -- the Art Nouveau contour."""
    return lambda t: lo + (hi - lo) * (math.sin(math.pi * t) ** power)


def dead_ranges(blocks):
    """Inclusive (start, end) id ranges that a tombstone has deleted.

    `deleted_length = N` deletes N ids from the item's own id, so a single
    tombstone can bury a whole span. Anything allocated inside one is erased as
    far as the device is concerned, however healthy it looks locally.
    """
    out = []
    for b in blocks:
        it = getattr(b, "item", None)
        n = getattr(it, "deleted_length", 0) or 0
        if n > 1:
            start = it.item_id.part2
            out.append((start, start + n - 1))
    return out


def next_free_id(blocks):
    """The first id no item -- live, tombstoned, or a deleted RANGE -- occupies.

    Scans EVERY block with an item, not just strokes: strokes and typed text
    share one author id space, so a stroke tombstone can bury an id that a text
    insert would otherwise reuse. Accounts for both `deleted_length` (a range
    of deleted ids) and `len(value)` (a string item occupies one id per
    character).

    Getting this wrong is silent and total: 44 strokes were once written into
    ids 872..915 while a tombstone covered 827..931, and they never appeared on
    the device while rendering perfectly here.
    """
    end = 0
    for b in blocks:
        # TYPED TEXT TOO. Its characters live in the RootTextBlock's own sequence, not in an item block, so
        # the loop below never saw them -- while the docstring above already said they share this id space.
        # Highlights written here got ids (1,138)..(1,156) on a page whose
        # text runs to (1,5341), the same ids as the user's own characters.
        text = getattr(getattr(b, "value", None), "items", None)
        if text is not None and hasattr(text, "_items"):
            for tid, ti in text._items.items():
                tv = ti.value
                span = max(len(tv) if isinstance(tv, str) else 0, getattr(ti, "deleted_length", 0) or 0, 1)
                end = max(end, tid.part2 + span - 1)
            continue
        it = getattr(b, "item", None)
        if it is None or not hasattr(it, "item_id"):
            # A PICTURE placed on the page (block types 14/15, rmscene's UnreadableBlock) has
            # ids of its own in the same author space; rmscene cannot show them, so read them off
            # the raw bytes -- a stroke written into a picture's id corrupts the sequence.
            raw = getattr(b, "data", None)
            if isinstance(raw, (bytes, bytearray)) and len(raw) > 8:
                try:
                    from paperdaemon.pipeline.page import images as _IM
                    end = max(end, _IM.max_author_id(bytes(raw)))
                except Exception:
                    pass
            continue
        v = getattr(it, "value", None)
        span = max(len(v) if isinstance(v, str) else 0,
                   getattr(it, "deleted_length", 0) or 0, 1)
        end = max(end, it.item_id.part2 + span - 1)
    return end + 1


class Drawing:
    def __init__(self, w=1620, h=2160):
        self.w, self.h = w, h
        self.strokes = []          # (pts, widths, tool, color, rgba)

    # ---- authoring ----
    def stroke(self, pts, width=24, tool=Pen.FINELINER_2,
               color=PenColor.BLACK, rgba=None):
        if len(pts) < 2:
            return
        if callable(width):
            n = len(pts) - 1
            widths = [max(2, int(round(width(i / n)))) for i in range(len(pts))]
        else:
            widths = [int(width)] * len(pts)
        self.strokes.append((pts, widths, tool, color, rgba))

    def hl(self, pts, rgba, width=120):
        self.stroke(pts, width, Pen.HIGHLIGHTER_2, PenColor.HIGHLIGHT, rgba)

    def fill_rows(self, y0, y1, edges, rgba, step=22):
        """Raw scanline fill. Leaves STAIR-STEPPED edges -- prefer fill_region."""
        y = y0
        while y <= y1:
            for xa, xb in edges(y):
                if xb - xa > 6:
                    self.hl([(xa, y), (xb, y)], rgba)
            y += step

    # ---------- polygon fills: smooth edges everywhere, any orientation ----------
    @staticmethod
    def _resample(pts, spacing=6.0, closed=True):
        """Even arc-length spacing, so near-horizontal boundary sections get as
        many samples as steep ones. y-parametrized tracing fails exactly there."""
        loop = pts + [pts[0]] if closed else pts
        out, carry = [loop[0]], 0.0
        for i in range(len(loop) - 1):
            x0, y0 = loop[i]
            x1, y1 = loop[i + 1]
            seg = math.hypot(x1 - x0, y1 - y0)
            if seg < 1e-9:
                continue
            t = (spacing - carry) / seg
            while t <= 1.0:
                out.append((x0 + (x1-x0)*t, y0 + (y1-y0)*t))
                t += spacing / seg
            carry = (carry + seg) % spacing
        return out

    @staticmethod
    def _inset(pts, dist):
        """Offset a closed polygon inward along its normals.

        Direction comes from the polygon's WINDING, not from its centroid. A
        centroid test is only valid for convex shapes: for a crescent -- e.g. a
        hair band wrapping around a face -- the centroid sits in the hole, so the
        normal flips and the offset lands *outside* the shape. That is exactly how
        hair ended up painted across a character's face.
        """
        n = len(pts)
        area2 = 0.0
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            area2 += x0 * y1 - x1 * y0
        sgn = 1.0 if area2 > 0 else -1.0      # CCW -> +1
        out = []
        for i in range(n):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            tx, ty = x2 - x0, y2 - y0
            L = math.hypot(tx, ty) or 1.0
            nx, ny = -ty / L * sgn, tx / L * sgn
            out.append((x1 + nx * dist, y1 + ny * dist))
        return out

    @staticmethod
    def _spans(poly, y):
        xs = []
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if y0 == y1:
                continue
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
        xs.sort()
        return [(xs[i], xs[i+1]) for i in range(0, len(xs) - 1, 2)]

    def fill_poly(self, poly, rgba, step=24, hlw=120, spacing=6.0):
        """Fill any closed polygon with a smooth boundary.

        Traces the boundary inset by half the highlighter width -- so the stroke's
        outer edge lands on the true boundary -- then scanlines the interior with a
        deliberate overlap, so no seam appears between edge and fill.
        """
        if len(poly) < 3:
            return
        half = hlw * WHL / 2.0
        edge = self._resample(self._inset(poly, half), spacing, closed=True)
        if len(edge) >= 2:
            self.hl(edge + [edge[0]], rgba, hlw)
        # interior: inset by 1.5*half (not 2*half) so it overlaps the edge stroke
        inner = self._inset(poly, half * 1.5)
        ys = [p[1] for p in inner]
        y = min(ys)
        while y <= max(ys):
            for a, b in self._spans(inner, y):
                if b - a > 2:
                    self.hl([(a, y), (b, y)], rgba, hlw)
            y += step

    @staticmethod
    def _band_poly(rows, overlap):
        """Closed polygon from (xa, xb, y) rows, extended vertically.

        Bands that start or stop mid-shape (e.g. where a face splits a hair mass
        into two strips) otherwise leave a thin horizontal white seam, because each
        band's traced edge is inset from its own first and last row.
        """
        if len(rows) < 2:
            return None
        a0, b0, y0 = rows[0]
        a1, b1, y1 = rows[-1]
        top = [(a0, y0 - overlap), (b0, y0 - overlap)]
        bot = [(b1, y1 + overlap), (a1, y1 + overlap)]
        return ([top[0]]
                + [(a, yy) for a, b, yy in rows]
                + [bot[0]]
                + [(b, yy) for a, b, yy in reversed(rows)]
                + [top[1]])

    def region_polys(self, y0, y1, edges, res=7, hlw=120):
        """Turn span functions into closed polygons, one per contiguous band."""
        overlap = hlw * WHL / 2.0
        bands, order, polys = {}, [], []
        y = y0
        while y <= y1:
            spans = [s for s in edges(y) if s[1] - s[0] > 2]
            for i, (xa, xb) in enumerate(spans):
                if i not in bands:
                    bands[i] = []
                    order.append(i)
                bands[i].append((xa, xb, y))
            for i in list(bands):
                if i >= len(spans) and bands[i]:
                    p = self._band_poly(bands.pop(i), overlap)
                    if p:
                        polys.append(p)
            y += res
        for i in order:
            if i in bands:
                p = self._band_poly(bands[i], overlap)
                if p:
                    polys.append(p)
        return polys

    def fill_smooth(self, y0, y1, edges, rgba, step=24, hlw=120, res=7):
        for poly in self.region_polys(y0, y1, edges, res, hlw):
            self.fill_poly(poly, rgba, step=step, hlw=hlw)

    def fill_circle(self, cx, cy, r, rgba, step=24, hlw=120, n=64):
        self.fill_poly([(cx + r*math.cos(2*math.pi*k/n),
                         cy + r*math.sin(2*math.pi*k/n)) for k in range(n)],
                       rgba, step=step, hlw=hlw)

    def fill_lens_smooth(self, cx, cy, rx, ry, rgba, deg=0.0, step=22, hlw=120, n=40):
        """Leaf/petal fill with BLUNTED tips.

        Acute corners break polygon insetting: near a sharp tip the local
        half-width falls below the inset distance, the offset polygon inverts into
        a bowtie, and the traced edge sprays outside the shape. Blunting the fill
        avoids it entirely and costs nothing visually, because the pointed tip is
        carried by `outline_lens`, which is a pen stroke and not offset at all.
        """
        half = hlw * WHL / 2.0
        min_hw = half * 1.25                     # never inset more than the shape
        tmax = math.sqrt(max(0.0, 1.0 - min_hw / rx)) if rx > min_hw else 0.0
        if tmax <= 0.02:                         # too small to fill safely
            return
        pts = []
        for k in range(n + 1):
            t = -tmax + 2.0 * tmax * k / n
            pts.append((cx + rx * (1 - t*t), cy + ry * t))
        for k in range(n, -1, -1):
            t = -tmax + 2.0 * tmax * k / n
            pts.append((cx - rx * (1 - t*t), cy + ry * t))
        if deg:
            pts = rot(pts, cx, cy, deg)
        self.fill_poly(pts, rgba, step=step, hlw=hlw)

    def fill_region(self, y0, y1, edges, rgba, step=24, hlw=120, res=8):
        """Fill with SMOOTH edges.

        Grid-aligned horizontal highlighter strokes stair-step along the boundary,
        because each row's round cap lands on a different x. The fix:
        trace the boundary with a curved stroke and fill the interior behind it.

        A highlighter of width field `hlw` covers hlw*WHL units, so the edge
        stroke's centerline is inset by half that -- its outer edge then lands
        exactly on the true boundary.

        edges(y) -> list of (xa, xb) spans. Spans are tracked as bands so each
        band gets its own pair of traced boundary curves.
        """
        half = hlw * WHL / 2.0
        bands = {}          # span index -> list of (xa, xb, y)
        order = []
        y = y0
        while y <= y1:
            spans = [s for s in edges(y) if s[1] - s[0] > 2]
            for i, (xa, xb) in enumerate(spans):
                if i not in bands:
                    bands[i] = []
                    order.append(i)
                bands[i].append((xa, xb, y))
            # break bands that vanished, so they are not bridged across a gap
            for i in list(bands):
                if i >= len(spans) and bands[i]:
                    self._emit_band(bands.pop(i), rgba, half, step, hlw)
            y += res
        for i in order:
            if i in bands and bands[i]:
                self._emit_band(bands[i], rgba, half, step, hlw)

    def _emit_band(self, rows, rgba, half, step, hlw):
        if len(rows) < 2:
            return
        # 1. traced boundary curves -- smooth, no stair-stepping
        left = [(xa + half, y) for xa, xb, y in rows if xb - xa > 2 * half]
        right = [(xb - half, y) for xa, xb, y in rows if xb - xa > 2 * half]
        if len(left) >= 2:
            self.hl(left, rgba, hlw)
            self.hl(right, rgba, hlw)
        # 2. interior scanlines, inset so they never touch the boundary
        last = None
        for xa, xb, y in rows:
            if last is not None and y - last < step:
                continue
            a, b = xa + 2 * half, xb - 2 * half
            if b - a > 6:
                self.hl([(a, y), (b, y)], rgba, hlw)
            last = y
        # 3. cap the ends so the band closes cleanly
        for xa, xb, y in (rows[0], rows[-1]):
            if xb - xa > 2 * half:
                self.hl([(xa + half, y), (xb - half, y)], rgba, hlw)

    def fill_lens(self, cx, cy, rx, ry, rgba, step=20, deg=0.0):
        """Pointed leaf/petal, optionally rotated."""
        pts = []
        y = -ry
        while y <= ry:
            t = y / ry
            hw = rx * (1 - t*t)
            if hw > 6:
                pts.append((cx - hw, cy + y, cx + hw, cy + y))
            y += step
        for xa, ya, xb, yb in pts:
            seg = rot([(xa, ya), (xb, yb)], cx, cy, deg) if deg else [(xa, ya), (xb, yb)]
            self.hl(seg, rgba)

    def outline_lens(self, cx, cy, rx, ry, width=16, deg=0.0, vein=True):
        a = bez((cx, cy - ry), (cx + rx*1.16, cy - ry*0.34),
                (cx + rx*1.16, cy + ry*0.34), (cx, cy + ry), 34)
        b = bez((cx, cy - ry), (cx - rx*1.16, cy - ry*0.34),
                (cx - rx*1.16, cy + ry*0.34), (cx, cy + ry), 34)
        for p in (a, b):
            self.stroke(rot(p, cx, cy, deg) if deg else p, width)
        if vein:
            v = [(cx, cy - ry*0.84), (cx, cy + ry*0.84)]
            self.stroke(rot(v, cx, cy, deg) if deg else v, prof_swell(6, width, 1.0))

    # ---- preview ----
    def paint_strokes(self, ox=None, oy=0.0, scale=1.0):
        """The strokes for the renderer (pipeline/page/paint.py): page x = 0 at `ox` (the canvas's center by default), widths
        from their width fields (the pens' and the highlighter's scales), the pens in their measured colors."""
        from paperdaemon.pipeline.page.paint import drawn, response
        ox = self.w / 2.0 if ox is None else ox
        out = []
        for st in self.strokes:
            pts, widths, tool, color, rgba = st[:5]
            P = [(x * scale + ox, y * scale + oy) for x, y in pts]
            if tool == Pen.HIGHLIGHTER_2:
                out.append((P, [w * WHL * scale for w in widths], "highlighter",
                            tuple(rgba[:3]) if rgba else (255, 237, 117)))
            else:
                attrs = st[5] if len(st) > 5 and isinstance(st[5], dict) else {}
                k, dens = response(tool.name.split("_")[0], [attrs.get("pressure", 190)] * len(P),   # what write_rm stores
                                   [attrs.get("speed", 0)] * len(P))
                out.append((P, drawn([w * WPEN * scale for w in widths], k), "pen", R.ENUM.get(color.value, (0, 0, 0)), dens))
        return out

    def render_png(self, path, progress=None, ss=1):
        """The drawing as a picture, with PaperDaemon's one renderer (pipeline/page/paint.py: as the tablet draws it),
        at the tablet's own pixels, as every page picture is (`ss`: times the size averaged down, when a caller asks).
        progress(f), when given, hears 1.0 when it is drawn."""
        from paperdaemon.pipeline.page.paint import paint
        img = Image.new("RGB", (self.w, self.h), "white")
        paint(img, self.paint_strokes(), ss=ss)
        img.save(path)
        if progress:
            progress(1.0)
        return len(self.strokes)

    # ---- commit ----
    def write_rm(self, doc_name, page_no, dry_run=False, drop_text=False,
                 keep_existing=True, replace_box=None):
        """Write these strokes into a page, after every stroke already on it.

        keep_existing=False REPLACES the page's strokes instead: everything already drawn on it goes. Only for a page
        this program owns outright; never the default, because a page usually carries the user's writing.

        drop_text also removes the page's RootTextBlock -- typed text. Only for
        when the page itself asked for its text to go; it is not recoverable
        from the .rm afterwards, so back the document up first.

        replace_box=(x0, y0, x1, y1) makes that append idempotent: existing
        strokes lying WHOLLY inside the box are dropped first, so re-running
        redraws that one region and leaves the rest of the page untouched.
        Size the box to your own artwork and nothing else.
        """
        doc = R.find_doc(doc_name)
        pid = R.live_pages(doc)[page_no - 1]["id"]
        src = os.path.join(R.RM, doc, pid + ".rm")
        allb = list(read_blocks(io.BytesIO(open(src, "rb").read())))

        def _boxed(b):
            """True if b is a live stroke lying wholly inside replace_box."""
            if replace_box is None:
                return False
            v = getattr(b.item, "value", None)
            if not isinstance(v, Line) or not v.points:
                return False
            x0, y0, x1, y1 = replace_box
            return all(x0 <= p.x <= x1 and y0 <= p.y <= y1 for p in v.points)

        if keep_existing:
            # Keep the originals in their original positions -- order is the
            # render order for pens, so preserving it preserves the page.
            blocks = [b for b in allb
                      if not (isinstance(b, ss.SceneLineItemBlock) and _boxed(b))]
        else:
            blocks = [b for b in allb if not isinstance(b, ss.SceneLineItemBlock)]
        dropped = len(allb) - len(blocks)
        kept = sum(1 for b in blocks if isinstance(b, ss.SceneLineItemBlock))
        kept_lines = sum(1 for b in blocks if isinstance(b, ss.SceneLineItemBlock)
                         and isinstance(getattr(b.item, "value", None), Line))
        text_dropped = 0
        if drop_text:
            keep = [b for b in blocks if not isinstance(b, ss.RootTextBlock)]
            text_dropped = len(blocks) - len(keep)
            blocks = keep
        layer = None
        for b in blocks:
            if isinstance(b, ss.TreeNodeBlock) and b.group.label.value == "Layer 1":
                layer = b.group.node_id
        if layer is None:
            raise RuntimeError("no Layer 1 on that page")
        seq = [80]
        prev = CrdtId(0, 0)
        if kept:
            # Never reuse an id that is already on the page, and hang the new
            # run off the tail of Layer 1's own sequence rather than its head.
            # ACCOUNT FOR RANGE TOMBSTONES. A tombstone with deleted_length=N
            # deletes N ids starting at its own -- so the highest USED id is
            # not max(item_id), it is max(item_id + deleted_length - 1). Taking
            # max(item_id) alone allocates new strokes INSIDE a deleted range,
            # and the device and desktop app then correctly treat them as
            # erased. Our renderer does not check other items' ranges, so the
            # page previews perfectly and is blank on the tablet.
            #
            # Measured: one page carried a tombstone spanning ids 827..931
            # (deleted_length=105). max(item_id) was 871, so 44 strokes were
            # written as 872..915 -- entirely inside it. Invisible on the
            # device, byte-identical in cloud, mirror and the app's own cache,
            # and drawn by rm_render. Re-emitted at id 1632+ the same geometry
            # rendered immediately.
            seq[0] = max(seq[0], next_free_id(blocks) - 1)
            children = [b.item for b in blocks
                        if getattr(b, "parent_id", None) == layer
                        and hasattr(b, "item")]
            lefts = {(c.left_id.part1, c.left_id.part2) for c in children}
            tails = [c for c in children
                     if (c.item_id.part1, c.item_id.part2) not in lefts]
            if len(tails) == 1:
                prev = tails[0].item_id
        for st in self.strokes:
            pts, widths, tool, color, rgba = st[:5]
            # an optional 6th element carries per-stroke point attributes -- the device
            # renders the highlighter's chisel nib from them (calibration)
            attrs = st[5] if len(st) > 5 and isinstance(st[5], dict) else {}
            P = [Point(x=float(x), y=float(y), speed=int(attrs.get("speed", 0)), direction=int(attrs.get("direction", 0)),
                       width=int(widths[i]), pressure=int(attrs.get("pressure", 190)))
                 for i, (x, y) in enumerate(pts)]
            L = Line(color=color, tool=tool, points=P,
                     thickness_scale=(1.0 if tool == Pen.HIGHLIGHTER_2 else 3.0),
                     starting_length=0.0, move_id=None,
                     # (r, g, b), opaque, or (r, g, b, a) as a kept decomp carries it: four values either way
                     color_rgba=(tuple(rgba[:3]) + (tuple(rgba[3:4]) or (255,)) if rgba else None))
            seq[0] += 1
            iid = CrdtId(1, seq[0])
            blocks.append(ss.SceneLineItemBlock(
                parent_id=layer,
                item=CrdtSequenceItem(item_id=iid, left_id=prev,
                                      right_id=CrdtId(0, 0), deleted_length=0,
                                      value=L)))
            prev = iid
        buf = io.BytesIO()
        write_blocks(buf, blocks)
        data = buf.getvalue()
        # ONE round-trip parse, used for both checks below. It was parsed twice -- once for the
        # stroke count, once more for dead_ranges -- and on a busy page a parse is over a second
        # (profiled: dead_ranges alone was 27% of write_rm's time).
        rb_all = list(read_blocks(io.BytesIO(data)))
        rb = [b for b in rb_all
              if isinstance(b, ss.SceneLineItemBlock)
              and isinstance(getattr(b.item, "value", None), Line)]
        want = kept_lines + len(self.strokes)
        if len(rb) != want:
            raise RuntimeError("round-trip lost strokes: %d != %d"
                               % (len(rb), want))
        bad = [b for b in rb if b.item.value.tool == Pen.HIGHLIGHTER_2
               and b.item.value.color_rgba is None]
        if bad:
            raise RuntimeError("round-trip lost %d highlighter colors" % len(bad))
        # REFUSE TO WRITE A BURIED STROKE. A stroke whose id falls inside a
        # tombstone's deleted range is erased on the device and perfect here,
        # which is the most expensive failure this file can produce -- it costs
        # hours precisely because every local check passes. Belt and braces on
        # top of next_free_id(): if the allocator is ever wrong again, this
        # stops the file reaching the page instead of letting it look fine.
        rng = dead_ranges(rb_all)
        buried = [b.item.item_id.part2 for b in rb
                  if any(a <= b.item.item_id.part2 <= z for a, z in rng)]
        if buried:
            raise RuntimeError(
                "REFUSING TO WRITE: %d stroke id(s) fall inside a deleted "
                "range %s -- they would render locally and be invisible on the "
                "device. ids: %s" % (len(buried), rng, buried[:8]))
        if dry_run:
            return dict(strokes=len(self.strokes), kept=kept_lines, dropped=dropped,
                        text_dropped=text_dropped, bytes=len(data),
                        written=False)
        paths.write_atomic(src, data)
        return dict(strokes=len(self.strokes), kept=kept_lines, dropped=dropped,
                    text_dropped=text_dropped, bytes=len(data),
                    written=True, path=src)


# ---------------------------------------------------------------- color, and a preview of strokes

def lab(rgb):
    """sRGB (0-255) -> CIE L*a*b* under D65, the decomposer's color math."""
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(v) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    def g_(t):
        return t ** (1 / 3.0) if t > 0.008856 else 7.787 * t + 16 / 116.0
    fx, fy, fz = g_(x), g_(y), g_(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def to_drawing(strokes, w, h, pad=24, ss=1):
    """A Drawing whose canvas is exactly the box (plus pad), for render_png.

    render_png treats page x=0 as the CENTER of its canvas, so strokes at
    x in [0, w] are shifted left by half the canvas. `ss` supersamples points
    and widths together for antialiasing; the width MODEL is unchanged.
    """
    cw, ch = int((w + 2 * pad) * ss), int((h + 2 * pad) * ss)
    d = Drawing(cw, ch)
    dx, dy = -cw / 2.0 + pad * ss, float(pad * ss)
    for pts, widths, tool, color, rgba in strokes:
        d.strokes.append(([(x * ss + dx, y * ss + dy) for x, y in pts],
                          [wd * ss for wd in widths], tool, color, rgba))
    return d


def preview(strokes, w, h, out, pad=24, ss=1, progress=None):
    """Strokes in a w x h box (x from 0 at the box's left) as a picture with `pad` around it, drawn by the one
    renderer at the tablet's own pixels, as every page picture is."""
    d = Drawing(int(w + 2 * pad), int(h + 2 * pad))
    d.strokes = [([(x + pad, y + pad) for x, y in st[0]],) + tuple(st[1:5]) for st in strokes]
    img = Image.new("RGB", (d.w, d.h), "white")
    from paperdaemon.pipeline.page.paint import paint
    paint(img, d.paint_strokes(ox=0.0), ss=ss)
    img.save(out)
    if progress:
        progress(1.0)
    return out
