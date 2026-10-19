r"""Lay out and DRAW the typed text of a page.

Why this exists: `rm_render` draws strokes only. Every preview it produced
showed drawings on an otherwise blank page, so a block placed "below the
questions" looked fine locally and landed on top of them on the device. The
typed text was in the file the whole time -- it just was not being drawn.

The layout model, derived from the file rather than guessed:

  * `RootTextBlock` gives `pos_x`, `pos_y` (always 234) and `width` (the column).
  * Paragraphs are split on '
' and U+2028, and each paragraph's FIRST CrdtId
    is the key into `styles` -- ParagraphStyle.HEADING(2) or PLAIN(1).
  * Anchored stroke groups carry `anchor_id` = a PARAGRAPH-START id, which is
    how a group knows which line to follow. That is also what makes the y
    offset recoverable: a group's vertical origin is its paragraph's y.
  * `anchor_threshold` (35.748) is the PLAIN line height.

HEADING_LH is solved from a measurement, not assumed: an icon's group anchors
to paragraph 3 and needed a y offset of +520, and
234 + 2*HEADING_LH + 2*PLAIN_LH = 520 gives HEADING_LH = 107.25 with the
heading wrapping to two lines. Treat it as calibrated-but-approximate: it is
good enough to keep new content clear of the text, which is the job.
"""
import io, logging, os, sys
import copy, hashlib, itertools, math, re
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from paperdaemon import paths
import hashlib, io, math
from importlib.metadata import version

logging.getLogger("rmscene").setLevel(logging.ERROR)
from paperdaemon.pipeline.page import render as R
from rmscene import read_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene import write_blocks
from rmscene.crdt_sequence import CrdtSequence, CrdtSequenceItem
from rmscene.scene_items import ParagraphStyle
from rmscene.scene_stream import CrdtId, LwwValue

LS, PS = chr(0x2028), chr(0x2029)
PLAIN_LH = 35.74803161621094        # == the groups' anchor_threshold
HEADING_LH = 107.25                 # solved from the icon anchor measurement
PLAIN_SIZE, HEADING_SIZE = 26.0, 62.0
CHAR_W = 0.50                       # mean advance as a fraction of size


# ---------------------------------------------------------------- the app's own faces
# TYPED TEXT IS DRAWN IN THE APP'S FONTS, FROM THE APP'S STYLE CODES. What is below this line is
# the older model, kept as a fallback: it guessed the
# font (rm_text's stroke lettering) and inferred the style from the paragraph's first CrdtId,
# so accents and symbols came out as dashes and a line could wrap a word early or late.
#
# The new path is two modules, measured against the official web render:
#   typed_records  a format-PRESERVING RootTextBlock reader. rmscene 0.8 throws away style
#                  codes it does not recognize; this clones rmscene's own parser with a private
#                  globals dict (no monkeypatching) so the byte values survive. Identity is file
#                  provenance, not a guess -- BASIC/PLAIN/HEADING/BOLD/BULLET/BULLET2/CHECKBOX/
#                  CHECKBOX_CHECKED/NUMBERED.
#   typed_layout   wraps and draws with reMarkableSans / reMarkableSerifSmall at 4x supersample.
#
# It REFUSES rather than guesses: an unmeasured style code, an unmeasured paragraph separator or
# an inline code it has not seen raises instead of quietly rendering as plain. That is right for
# a measurement tool and wrong for a preview that the daemon depends on, so a refusal falls back
# to the old drawing here and says so in the return value's sign.
_NEW = None


def _engine():
    """True when the app's own faces are installed, so typed text is measured and drawn in them; without
    them the older lettering model is used."""
    global _NEW
    if _NEW is None:
        try:
            if not fonts_available():
                # the faces are not ours to ship: take them from the reMarkable desktop app on this computer
                from paperdaemon.remarkable import fonts
                fonts.extract(str(FONT_DIR))
            _NEW = bool(fonts_available())
        except Exception:
            _NEW = False
    return _NEW


def span_width(text, style_code):
    """The width of `text` in the app's own face for a paragraph of this style (plain weight), in
    page units, or None when the engine is not here. Where a word starts inside a typed line: the
    lettering font's proportions put a highlight on "o Frida" for "Friday"."""
    eng = _engine()
    if not eng or style_code is None:
        return None
    try:
        return float(width([{"char": c, "bold": False, "italic": False} for c in str(text)], style_code))
    except Exception:
        return None


def _record(doc_name, page_no):
    """The page's typed text as a provenance record (see typed_records), or None if it has none."""
    eng = _engine()
    if not eng:
        return None
    path = _page_path(doc_name, page_no)
    # CACHED BY THE FILE'S (mtime, size), like rm_render.blocks_of: the engine re-parsed the page
    # twenty times in one job (measured: 28 s of a 173 s offline run).
    st = os.stat(path)
    key = (path, st.st_mtime_ns, st.st_size, str(doc_name), str(page_no))
    hit = _RECORDS.get(key)
    if hit is not None:
        return hit or None
    data = io.open(path, "rb").read()
    blocks = read_preserved(data)
    rec = from_blocks(blocks, data, doc_id=str(doc_name), page_id=str(page_no))
    rec = rec if rec and rec.get("paragraphs") else None
    if len(_RECORDS) > 16:
        _RECORDS.clear()
    _RECORDS[key] = rec or False
    return rec


def _layout_of(data, doc_name, page_no):
    """The engine's layout of a page's typed text from its bytes (not cached: they are not the file's)."""
    if not _engine():
        return None
    rec = from_blocks(read_preserved(data), data, doc_id=str(doc_name), page_id=str(page_no))
    return layout(rec) if rec and rec.get("paragraphs") else None


_RECORDS = {}
_LAYOUTS = {}
_RENDERS = {}


def _cache_key(doc_name, page_no):
    path = _page_path(doc_name, page_no)
    st = os.stat(path)
    return (path, st.st_mtime_ns, st.st_size)


def _layout(doc_name, page_no):
    """The engine's layout of this page's typed text, computed ONCE per file change.

    layout() walks the real font metrics glyph by glyph (and opens the face files to check
    coverage) -- measured at ~0.5 s a call on a clean page, and a job called it a dozen
    times through paragraphs()/text_bottom(): the host's "reading the page" went from 3.0 s to
    7.8 s the moment the bench page had a block the engine accepted. Refusals propagate as before.
    """
    eng = _engine()
    if not eng:
        return None
    key = _cache_key(doc_name, page_no)
    hit = _LAYOUTS.get(key)
    if hit is not None:
        return hit or None
    rec = _record(doc_name, page_no)
    out = layout(rec) if rec is not None else None
    if len(_LAYOUTS) > 16:
        _LAYOUTS.clear()
    _LAYOUTS[key] = out or False
    return out


def _rendered(doc_name, page_no):
    """(art, mask, mapped) from the engine's renderer, once per file change (a page is rendered
    for the plan turn, for each look and for the bench's PNG -- the same 14 MB RGBA every time)."""
    eng = _engine()
    if not eng:
        return None
    key = _cache_key(doc_name, page_no)
    hit = _RENDERS.get(key)
    if hit is not None:
        return hit or None
    rec = _record(doc_name, page_no)
    out = render(rec) if rec is not None else None
    if len(_RENDERS) > 4:
        _RENDERS.clear()
    _RENDERS[key] = out or False
    return out


def _scale_of(xform):
    """(sx, sy) of a transform, by sampling it. Only a pure affine is honored; anything else
    falls back, because pasting a raster under an unknown warp would be a lie about position."""
    x0, y0 = xform(0.0, 0.0)
    x1, y1 = xform(1000.0, 0.0)
    x2, y2 = xform(0.0, 1000.0)
    if abs(y1 - y0) > 1e-6 or abs(x2 - x0) > 1e-6:
        return None
    return (x1 - x0) / 1000.0, (y2 - y0) / 1000.0


def paragraphs(doc_name, page_no, data=None):
    """[{start_id, text, style, y, lines}] plus the block box. `data` is the page's bytes to lay out instead of its
    file: the page as it will be once the typed text staged for erasing is gone (page.erase_text, dry run)."""
    doc = R.find_doc(doc_name) if "-" not in doc_name else doc_name
    pid = R.live_pages(doc)[page_no - 1]["id"]
    # EVERY text block on the page, not one of them. The main block (the one holding the text,
    # see _text_block) comes first and is the `tb` returned; any other RootTextBlock's paragraphs
    # follow, laid out from that block's own pos_y. A page with two blocks used to have one of
    # them invisible to every collision check, which is one way a reply lands on the user's words.
    blocks = R.blocks_of(R.page_file(doc, pid)) if data is None else list(read_blocks(io.BytesIO(data)))
    _tb = _text_block(blocks)
    if _tb is None:
        return None, []
    others = [b for b in blocks if isinstance(b, ss.RootTextBlock) and b is not _tb]
    out = _paragraphs_of(_tb.value)
    main_n = len(out)
    for b in others:
        extra = _paragraphs_of(b.value)
        if any(str(p.get("text", "")).strip() for p in extra):
            out += extra
    measured = _measured(doc_name, page_no, out[:main_n], data)
    return _tb.value, measured + out[main_n:]


def _paragraphs_of(tb):
    """The old paragraph model for ONE text block: [{start_id, text, style, y, lines, ...}]."""
    styles = {(k.part1, k.part2): getattr(v.value, "value", v.value)
              for k, v in tb.styles.items()}
    paras, buf, start = [], [], None
    for it in tb.items.sequence_items():
        if start is None:
            start = (it.item_id.part1, it.item_id.part2)
        v = it.value
        if isinstance(v, str):
            for k, ch in enumerate(v):
                if ch in ("\n", LS, PS):
                    paras.append((start, "".join(buf)))
                    buf = []
                    start = (it.item_id.part1, it.item_id.part2 + k + 1)
                else:
                    buf.append(ch)
    if buf or start:
        paras.append((start, "".join(buf)))

    out, y = [], float(tb.pos_y)
    for idx, (sid, txt) in enumerate(paras):
        # Style keys are NOT the paragraph-start id. The first paragraph is
        # keyed by CrdtId(0,0); every later one is keyed by the id of the
        # NEWLINE that ends the paragraph before it, i.e. start_id - 1. That is
        # also why a group's anchor_id looks "one short" of a paragraph start:
        # the icon anchors to (1,97) and paragraph 3 begins at (1,98).
        if idx == 0:
            style = styles.get((0, 0), 1)
        else:
            style = styles.get((sid[0], sid[1] - 1), styles.get(sid, 1))
        heading = (style == 2)
        size = HEADING_SIZE if heading else PLAIN_SIZE
        lh = HEADING_LH if heading else PLAIN_LH
        per = max(1, int(tb.width / (size * CHAR_W)))
        lines = []
        cur = ""
        for w in txt.split():
            t = (cur + " " + w) if cur else w
            if len(t) > per and cur:
                lines.append(cur); cur = w
            else:
                cur = t
        if cur or not lines:
            lines.append(cur)
        # `y` is the TOP of the paragraph's first line, in page coordinates. Say it here
        # because two readers derive geometry from it (text_bottom, rm_layout.occupancy) and a
        # third draws from it, and they have not always agreed about what it meant.
        out.append({"start_id": sid, "text": txt, "style": style,
                    "heading": heading, "size": size, "lh": lh,
                    "y": y, "lines": lines})
        y += lh * len(lines)
    return out


def _split_at_line_separators(got):
    """The engine's paragraphs cut where the old parser cuts them, or None if a cut cannot be placed.

    U+2028 -- shift+enter on the tablet -- is a LINE break to the engine and a PARAGRAPH break to the
    old parser, so a single shift+enter left the two counts unequal and `_measured` dropped the measured
    geometry for the WHOLE page: every paragraph below the shift+enter sat on the old model (no space
    between paragraphs), and highlights drawn from it drifted up a paragraph at a time onto the user's
    own words. Each engine paragraph is cut at its separators; each piece takes the
    lines its text runs over (an empty piece, the line a trailing separator leaves, takes that one line).
    """
    norm = lambda s: " ".join(str(s or "").split())
    out = []
    for p in got:
        pieces = str(p.get("text") or "").split(LS)
        if len(pieces) == 1:
            out.append(p)
            continue
        rows = list(p.get("lines") or [])
        if not rows:
            return None
        lead = float(rows[0]["y"]) - float(p["bbox"][1])     # bbox top to the first line, the same for every piece
        k = 0
        for piece in pieces:
            want, take = norm(piece), []
            while k < len(rows):
                take.append(rows[k])
                k += 1
                if norm(" ".join(str(r.get("text") or "") for r in take)) == want:
                    break
            if not take or norm(" ".join(str(r.get("text") or "") for r in take)) != want:
                return None
            out.append(dict(p, text=piece, lines=take, bbox=[p["bbox"][0], float(take[0]["y"]) - lead,
                                                             p["bbox"][2], p["bbox"][3]]))
        if k != len(rows):
            return None
    return out


def _measured(doc_name, page_no, ps, data=None):
    """Put the MEASURED geometry onto the paragraphs the old parser found.

    Four callers (rm_page, rm_render, rm_host) ask `paragraphs` where the text sits so they can
    keep new content clear of it. Leaving them on the old model while `draw` and `text_bottom`
    used the new one would be the worst of both: on the reference page the old model puts the last
    baseline at 627 and the measured layout at 792, and 165 units is a paragraph of the user's writing to
    land on.

    Both walk the same paragraphs in the same order, so they are matched by INDEX -- and only if
    the counts agree. The paragraph's own identity (start_id, used for anchored groups) stays with
    the old parse, which is where it was derived and verified.
    """
    eng = _engine()
    if not eng or not ps:
        return ps
    try:
        mapped = _layout(doc_name, page_no) if data is None else _layout_of(data, doc_name, page_no)
        if mapped is None:
            return ps
        got = mapped["paragraphs"]
        if len(got) != len(ps):
            got = _split_at_line_separators(got)
            norm = lambda s: " ".join(str(s or "").split())
            if got is None or len(got) != len(ps) or \
                    any(norm(a.get("text")) != norm(b.get("text")) for a, b in zip(ps, got)):
                return ps              # a shape we cannot line up: leave the old model alone
        for old, new in zip(ps, got):
            rows = new.get("lines") or []
            old["y"] = new["bbox"][1]
            old["lh"] = 76.0 if new["style_code"] == 2 else 45.0
            old["lines"] = [r["text"] for r in rows] or old["lines"]
            # the REAL width of each line, in the app's own metrics -- rm_host._typed_boxes
            # used to re-measure these lines with the lettering font, which is ~30% wider, so
            # every collision box for typed text ran 300 px past the glyphs (measured)
            old["line_widths"] = [float(r.get("width") or 0.0) for r in rows]
            old["line_x"] = [float(r.get("x", new["bbox"][0])) for r in rows]
            old["size"] = 64.0 if new["style_code"] == 2 else 36.0 if new["style_code"] == 3 else 32.0
            old["text"] = new.get("text", old.get("text"))
            old["style_code"] = new["style_code"]
            old["style_name"] = new.get("style_name")
            old["measured"] = True
    except Exception:
        pass                           # refused or unreadable: the old geometry still stands
    return ps


def _erased(doc_name, page_no, skip):
    """The page's bytes once the typed passages in `skip` are erased (a dry run; the file is not touched)."""
    from paperdaemon.pipeline import page as _ER
    data = None
    for s in skip:
        data = _ER.erase_text(doc_name, page_no, contains=s, dry_run=True, data=data)["data"]
    return data


def reflow(doc_name, page_no, skip):
    """{index in paragraphs(): how far down it moves (negative: up)} for the paragraphs that stay once the typed
    passages in `skip` are erased. The tablet lays its typed text out again after an erase, so what follows an
    erased paragraph moves up; ink placed against it today must move with it. {} when nothing is staged."""
    if not skip:
        return {}
    _tb, before = paragraphs(doc_name, page_no)
    _tb, after = paragraphs(doc_name, page_no, data=_erased(doc_name, page_no, skip))
    norm = lambda s: " ".join(str(s or "").split())
    out, j = {}, 0
    for i, p in enumerate(before):
        if j < len(after) and norm(after[j].get("text")) == norm(p.get("text")):
            out[i] = float(after[j]["y"]) - float(p["y"])
            j += 1
    return out


def text_bottom(doc_name, page_no, skip=None):
    """Lowest edge of the typed text that will STAY, in page coordinates.

    `skip` is the list of typed passages staged for erasing (rm_host's hide_typed): the page is measured as it
    will be once they are gone, laid out again the way the tablet does, so a reply goes where the page WILL be
    free. The paragraphs carry the engine's measured geometry when the engine accepts the page (see _measured);
    None when nothing remains.
    """
    _tb, ps = paragraphs(doc_name, page_no, data=_erased(doc_name, page_no, skip) if skip else None)
    live = [p for p in ps if str(p.get("text", "")).strip()]
    return max(p["y"] + p["lh"] * len(p["lines"]) for p in live) if live else None


def draw(dr, doc_name, page_no, xform=None, ox=0.0, oy=0.0,
         color=(105, 105, 105), skip=None):
    """Paint the typed text into a PIL ImageDraw.

    `xform` maps a page (x, y) to pixels. Pass the renderer's own transform --
    an (ox, oy) offset is only correct when the frame is a pure translation,
    and `rm_render._frame` may return a FITTED frame instead.
    """
    if xform is None:
        def xform(x, y):
            return (x + ox, y + oy)
    if not skip:                       # `skip` hides paragraphs staged for deletion; dropping
        n = _draw_new(dr, doc_name, page_no, xform, color)   # one would move every later line,
        if n is not None:              # so that case stays on the older, per-line path
            return n
    tb, ps = paragraphs(doc_name, page_no)
    if not ps:
        return 0
    n = 0
    # Normalized the same way rm_erase matches, so what a render hides and what a commit
    # actually removes are the same set. A raw lowercase test here could hide a paragraph the
    # erase then failed to touch, or show one it was about to delete.
    from paperdaemon.pipeline import page as _ER
    skip = [_ER._normalize(s)[0] for s in (skip or []) if s]
    for p in ps:
        if skip and any(s in _ER._normalize(p.get("text") or "")[0] for s in skip):
            continue                      # staged for deletion by the current job
        for i, line in enumerate(p["lines"]):
            if not line.strip():
                continue
            # p["y"] IS THE TOP OF THE LINE, NOT ITS BASELINE. Everything else in the file
            # reads it that way -- text_bottom() is y + lh * len(lines), and rm_layout marks
            # y .. y + lh -- but _glyphs draws UP from a baseline, so passing the top drew the
            # user's typed text a whole line-height too HIGH. The model then saw those words further up
            # the page than they are and placed its reply into space that was still the user's. Give
            # _glyphs a baseline: the top plus one cap height, which sits the glyphs inside the
            # band that occupancy protects.
            _glyphs(dr, line, tb.pos_x, p["y"] + i * p["lh"] + p["size"], p["size"],
                    color, xform)
            n += 1
    return n


def _draw_new(dr, doc_name, page_no, xform, color):
    """Paint the typed text with the app's own faces. -> lines drawn, or None to fall back.

    typed_layout's renderer returns a full-page RGBA in PAGE coordinates with x centered on 0, which is
    the same convention the .rm file uses. It is composited here through its own alpha so the
    preview keeps its overlay color rather than the black the measurement tool draws.
    """
    eng = _engine()
    if not eng:
        return None
    im = getattr(dr, "_image", None)
    if im is None:
        return None
    try:
        got = _rendered(doc_name, page_no)
        if got is None:
            return 0
        sc = _scale_of(xform)
        if sc is None:
            return None
        sx, sy = sc
        if sx <= 0 or sy <= 0:
            return None
        from PIL import Image
        art, mask, mapped = got
        w, h = max(1, int(round(art.width * sx))), max(1, int(round(art.height * sy)))
        if w > 20000 or h > 20000:
            return None
        mask = mask.resize((w, h), Image.LANCZOS)
        x0, y0 = xform(-art.width / 2.0, 0.0)       # their pixel 0 is page x = -width/2
        im.paste(tuple(color), (int(round(x0)), int(round(y0))), mask)
        return sum(len(p.get("lines") or []) for p in mapped["paragraphs"])
    except Exception:
        return None                    # refused (unmeasured style, missing face): older path


def _glyphs(dr, s, x, y, size, color, xform):
    """Draw the ACTUAL characters, using rm_text's font, in the overlay color.

    This used to draw a box per character. Boxes give position and extent, which
    is enough to avoid a collision -- but not enough to SEE one. If the user
    highlights a phrase, or ink crosses a line of text, the question is *which
    words*, and a row of boxes cannot answer it.

    The layout is still approximate: these are our glyph metrics, not the app's,
    so a line can wrap a word early or late. Positions are good to within a word,
    which is what the question needs.
    """
    from paperdaemon.pipeline.draw import lettering as _T
    cx = x
    # WALK THE STRING THE WAY THE RENDERER WALKS IT. This is the collision map -- the picture the
    # model uses to keep its reply off the user's words -- so if it measures a line differently from
    # rm_text, it draws their text in the wrong place and the reply lands on top. It used to step
    # character by character with the old "-" fallback: an emoji in the typing became one dash,
    # and every word after it on that line was drawn too far left.
    for unit in _T.clusters(s):
        icon = _T.emoji_icon(unit)
        if icon:
            r = _T.EMOJI_EM * size * 0.5
            for pth in (_T._emoji_paths(icon, cx + r, y - r * 0.92, r * 0.92) or ()):
                pts = [xform(px, py) for px, py in pth]
                if len(pts) > 1:
                    dr.line(pts, fill=color, width=1)
        else:
            gx0 = cx
            for ch in _T._drawable(unit):
                adv, polys = _T.G[ch]
                for poly in polys:
                    pts = [xform(gx0 + gx * size, y - gy * size) for gx, gy in poly]
                    if len(pts) > 1:
                        dr.line(pts, fill=color, width=1)
                gx0 += adv * size + 0.11 * size
        cx += _T.advance(unit, size, 0.11)




def _page_path(doc_name, page_no):
    doc = R.find_doc(doc_name) if "-" not in doc_name else doc_name
    pid = R.live_pages(doc)[page_no - 1]["id"]
    return R.page_file(doc, pid)


# ------------------------------------------------------------------ writing
def _text_block(blocks):
    """The page's typed-text block -- the one that HOLDS THE TEXT.

    A page can carry more than one RootTextBlock (the bench page had three). This used to
    return the first and `paragraphs()` used to keep the last, so on such a page the tool that
    wrote text, the tool that read it back and the tool that rendered it were each looking at a
    different block: insert() reported 30 characters written and paragraphs() reported an empty
    page, which made erase_typed_text() refuse a phrase that was plainly there. One rule now,
    used by both: the block with the most live text, first one on a tie.
    """
    best, live = None, -1
    for b in blocks:
        if not isinstance(b, ss.RootTextBlock):
            continue
        n = sum(len(it.value) for it in b.value.items._items.values()
                if isinstance(it.value, str) and it.value and not it.deleted_length)   # bold/italic marks are numbers
        if n > live:
            best, live = b, n
    return best


def _end_of(items):
    """Highest CRDT id consumed by the text so far.

    A string item does not occupy ONE id, it occupies one per character:
    `item_id` .. `item_id + len - 1`. That is why the second item on a real
    page had `left_id=(1,22)` when the first item's id was (1,17) and its text
    was 6 characters long -- 17+6-1 = 22. Tombstones still occupy their ids,
    with the count in `deleted_length` rather than in the value, so both have
    to be measured or a new item will collide with a deleted one.
    """
    end = 0
    for it in items.values():
        n = max(len(it.value or ""), it.deleted_length or 0, 1)
        if it.item_id.part2 + n - 1 > end:
            end = it.item_id.part2 + n - 1
    return end


def insert(doc_name, page_no, text, dry_run=False):
    """APPEND typed text -- real keyboard text, not lettering drawn as strokes.

    Typing on the page is better than drawing text: stroke lettering is a
    picture of words. Typed text is selectable, reflows, matches what the user
    typed themselves, and costs 1 item instead of ~40 strokes per line.

    The text is appended as a new paragraph after everything already there,
    which is what an answer under a question wants. Position is not a parameter
    because typed text has none -- the block owns `pos_y` and paragraphs simply
    follow each other down it.
    """
    src = _page_path(doc_name, page_no)
    allb = list(read_blocks(io.BytesIO(open(src, "rb").read())))
    tb = _text_block(allb)
    if tb is None:
        # Most pages have never been typed on, so refusing here would make the
        # tool useless exactly when it is most wanted. Build the block the way
        # the device does: a HEADING-less text run at the standard geometry,
        # pos_y=234 (measured identical on every page carrying typed text),
        # x centered with width 1152. It goes in after the scene tree, which is
        # where the device puts it -- index 22 of 469 on a real page.
        tb = ss.RootTextBlock(block_id=CrdtId(0, 0), value=si.Text(
            items=CrdtSequence(), styles={},
            pos_x=-576.0, pos_y=234.0, width=1152.0))
        at = max((i for i, b in enumerate(allb)
                  if isinstance(b, ss.SceneTreeBlock)), default=len(allb) - 1) + 1
        allb.insert(at, tb)

    items = tb.value.items._items
    # File-wide, not text-only: strokes and typed text share one author id
    # space, so a STROKE tombstone can bury an id this would otherwise reuse.
    from paperdaemon.pipeline import draw as _A
    # THE ANCHOR IS THE LAST CHARACTER IN READING ORDER; THE ID IS THE NEXT FREE ONE. They were one number,
    # "the highest id the text consumed", which is the last character only while the text grew from one
    # writer in order: when a stroke held a higher id, the new paragraph hung off a stroke's id.
    order = tb.value.items.keys()
    if order:
        tail = items[order[-1]]
        span = max(len(tail.value or ""), tail.deleted_length or 0, 1)
        left = CrdtId(tail.item_id.part1, tail.item_id.part2 + span - 1)
    else:
        left = CrdtId(0, 0)
    end = max(_end_of(items), _A.next_free_id(allb) - 1)
    body = ("\n" if items else "") + text
    new_id = CrdtId(1, end + 1)
    items[new_id] = CrdtSequenceItem(
        item_id=new_id, left_id=left,
        right_id=CrdtId(0, 0), deleted_length=0, value=body)

    # the new paragraph is keyed by the id of the NEWLINE that ends the one
    # before it, i.e. start_id - 1 -- which is exactly new_id when the newline
    # is the first character of what we just added.
    if items and body.startswith("\n"):
        tb.value.styles[new_id] = LwwValue(
            timestamp=CrdtId(1, end + len(body) + 1),
            value=ParagraphStyle.PLAIN)

    buf = io.BytesIO()
    write_blocks(buf, allb)
    data = buf.getvalue()

    rb = list(read_blocks(io.BytesIO(data)))
    if len(rb) != len(allb):
        raise RuntimeError("block count changed: %d -> %d" % (len(allb), len(rb)))
    back = _text_block(rb)
    got = "".join(i.value or "" for i in back.value.items._items.values())
    if text not in got:
        raise RuntimeError("round trip lost the text")

    res = dict(chars=len(text), item=str(new_id), bytes=len(data),
               path=src, written=False)
    if not dry_run:
        paths.write_atomic(src, data)
        res["written"] = True
    return res


# ==================================================================================================
# Evidence-informed native text preview, with honest geometry confidence.
#
# Identity is exact file provenance. Geometry is an approximation calibrated to
# the official web render, NOT a substitute for native hit testing or insertion.
# Fonts stay local to the installed application's user; no proprietary assets
# are redistributed. This module never writes a notebook or changes rm modules.
# ==================================================================================================

# The tablet's own faces. They are not redistributed with this project: each installation puts
# them in its content folder (see paperdaemon/paths.py), and without them this module reports itself unavailable
# (fonts_available) so callers use the older stroke-lettering model instead.
FONT_DIR=Path(paths.fonts_dir())
FACES=tuple(f'{family}-{weight}{italic}' for family in ('reMarkableSans','reMarkableSerifSmall')
            for weight in ('Regular','Bold') for italic in ('','Italic'))
SUPPORTED={0,1,2,3,4,5,6,7,10}
SCALE=4

# PaperDaemon's own faces, shipped (OFL): Arimo and Gelasio, cut to the widths of Arial and Georgia, the closest
# measured to reMarkable Sans and reMarkable Serif Small. A page is set in them where its library uses PaperDaemon's own
# faces (no account, or the false mirror's setting: remarkable/books.mode), so it is drawn as that library shows it.
OWN_DIR=Path(__file__).resolve().parents[2]/'content'/'typed-fonts'
OWN={'reMarkableSans':('arimo','Arimo'),'reMarkableSerifSmall':('gelasio','Gelasio')}

def own_faces():
    from paperdaemon.remarkable import books
    return books.mode()=='own'

def face_path(name):
    """The file of a face as this library sets it: the tablet's, or PaperDaemon's own in its place."""
    if own_faces():
        family,_,style=name.partition('-')
        folder,own=OWN[family]
        return OWN_DIR/folder/f'{own}-{style}.ttf'
    return FONT_DIR/(name+'.ttf')

def fonts_available():
    """True when every face this layout draws with is installed."""
    return all(face_path(n).is_file() for n in FACES)

@lru_cache(maxsize=32)
def supported_characters(path):
    with TTFont(path) as face:return frozenset(face.getBestCmap())

@lru_cache(maxsize=32)
def font(style,bold=False,italic=False):
    family='reMarkableSerifSmall' if style==2 else 'reMarkableSans'
    # Body face/weight still provisional: 32 px regular advances match the
    # official sample. Supersampling avoids integer-size hinting drift.
    size=64 if style==2 else 36 if style==3 else 32
    weight='Bold' if bold or style==3 else 'Regular'
    name=family+'-'+weight+('Italic' if italic else '')
    path=face_path(name)
    if not path.is_file():raise FileNotFoundError(f'required font not installed: {name} (looked for {path}); refusing to substitute')
    return ImageFont.truetype(str(path),size*SCALE)

def groups(chars):
    for fmt,values in itertools.groupby(chars,key=lambda c:(c['bold'],c['italic'])):
        yield fmt,list(values)

def width(chars,style):
    return sum(font(style,*fmt).getlength(''.join(c['char'] for c in batch))/SCALE for fmt,batch in groups(chars))

def wrap(chars,style,available):
    """Whitespace-preserving wrap, soft breaks, and overlong-token splitting.

    Drawing/measurement share the SAME per-run shaping calls. Leading spaces
    explicitly in data survive; only an overflow wrap's separator is consumed.
    Tabs use a conservative 4-space preview and are flagged for verification.
    """
    lines=[];line=[]
    tokens=[];current=[];kind=None
    for ch in chars:
        k='break' if ch['char']=='\u2028' else 'space' if ch['char'].isspace() else 'word'
        if k!=kind or k=='break':
            if current:tokens.append(current)
            current=[];kind=k
        current.append(ch)
    if current:tokens.append(current)
    for token in tokens:
        if token[0]['char']=='\u2028':lines.append(line);line=[];continue
        if width(line+token,style)<=available:line+=token;continue
        if line:
            # Qt visual trailing whitespace has no ink. Retain its identity in
            # the paragraph transcript; not in the next visual line.
            while line and line[-1]['char'].isspace():line.pop()
            lines.append(line);line=[]
            if all(c['char'].isspace() for c in token):continue
        for ch in token:
            if line and width(line+[ch],style)>available:lines.append(line);line=[]
            line.append(ch)
    lines.append(line)
    return lines

def layout(record):
    result=copy.deepcopy(record);result['layout_profile']='web-observed-v1-provisional'
    if any('unknown_inline_code' in w for w in result.get('warnings',[])):
        raise ValueError('Unmeasured inline formatting code; preview refused')
    result['layout_verified']=False
    result['geometry_warning']='Approximate preview; never use as guaranteed free space or native insertion position.'
    if not result['paragraphs']:return result
    col=result['column'];y=col['y'];number=0
    if col['width']>10000 or abs(col['x'])>100000 or abs(y)>100000:raise ValueError('Unbounded text geometry')
    for index,p in enumerate(result['paragraphs']):
        style=p['style_code']
        if style not in SUPPORTED:raise ValueError(f'Unmeasured paragraph style {style}; not silently rendered as plain')
        if any(c in p['text'] for c in '\r\u2029'):raise ValueError('Unmeasured paragraph separator; rendering refused')
        if '\t' in p['text']:result['warnings'].append({'paragraph':p['id'],'layout':'Tab stops uncalibrated; 4-space preview only'})
        if index and style==2:y+=64
        if index and style==3:y+=20
        indent=96 if style==5 else 48 if style in (4,6,7,10) else 0
        # 4 scene units of inset at each side: independently supported by
        # T01 ink origin and the held-out 740-wide T06 wrap (739-unit line
        # does not fit). The stored column is not the glyph content box.
        available=col['width']-indent-8
        if available<32:raise ValueError('Column too narrow for measured profile')
        if style==10:number+=1
        else:number=0
        chars=[]
        for run in p['runs']:
            face=font(style,run['format']['bold'],run['format']['italic'])
            missing=sorted({f'U+{ord(c):04X}' for c in run['text'] if not c.isspace() and ord(c) not in supported_characters(face.path)})
            if missing:result['warnings'].append({'paragraph':p['id'],'missing_font_glyphs':missing,'status':'No fallback guessed; missing-glyph box may differ across apps'})
            if run['format']['bold'] or run['format']['italic']:
                result['warnings'].append({'paragraph':p['id'],'layout':'Inline formats preserved and rendered, but official web probe T12 appeared plain. Tablet behavior not validated.'})
            for char,cid in zip(run['text'],run['character_ids']):
                for replacement in ('    ' if char=='\t' else char):chars.append(dict(char=replacement,id=cid,**run['format']))
        rows=wrap(chars,style,available);leading=76 if style==2 else 45
        p['lines']=[]
        for i,line in enumerate(rows):
            x=col['x']+indent+4;ly=y+i*leading+5
            p['lines'].append({'x':x,'y':ly,'width':width(line,style),'characters':line,'text':''.join(c['char'] for c in line)})
        height=len(rows)*leading
        p['bbox']=[col['x'],y,col['x']+col['width'],y+height]
        p['layout_status']='approximate-web-calibrated' if style in (0,1,2) else 'approximate-visually-observed'
        p['marker']=str(number)+'.' if style==10 else 'bullet' if style in (4,5) else 'checked' if style==7 else 'unchecked' if style==6 else None
        y+=height+(22 if style==2 else 25)
        if y>30000:raise ValueError('Rendered text exceeds bounded canvas height')
    result['estimated_text_bottom']=y-25
    return result

def render(record,page_size=(1620,2160)):
    """Return RGBA preview, glyph mask and layout sidecar. Mask is NOT proof of visible ownership."""
    mapped=layout(record)
    height=max(page_size[1],math.ceil(mapped.get('estimated_text_bottom',0))+40)
    size=(page_size[0]*SCALE,height*SCALE)
    image=Image.new('RGBA',size,(0,0,0,0));draw=ImageDraw.Draw(image)
    center=page_size[0]/2
    for p in mapped['paragraphs']:
        style=p['style_code']
        for row_i,row in enumerate(p['lines']):
            x=(row['x']+center)*SCALE;y=row['y']*SCALE
            for fmt,batch in groups(row['characters']):
                f=font(style,*fmt);text=''.join(c['char'] for c in batch)
                draw.text((x,y),text,font=f,fill='black');x+=f.getlength(text)
            if style==7:
                draw.line(((row['x']+center)*SCALE,y+20*SCALE,(row['x']+center+row['width'])*SCALE,y+20*SCALE),fill='black',width=SCALE)
            if row_i:continue
            x=(row['x']+center)*SCALE;mark=p['marker'];cy=y+21*SCALE
            if mark=='bullet':
                r=3*SCALE;mx=x-23*SCALE
                draw.ellipse((mx-r,cy-r,mx+r,cy+r),outline='black',fill=None if style==5 else 'black',width=SCALE)
            elif mark in ('checked','unchecked'):
                box=(x-40*SCALE,y+9*SCALE,x-16*SCALE,y+33*SCALE)
                draw.rectangle(box,outline='black',fill='black' if mark=='checked' else None,width=2*SCALE)
                if mark=='checked':draw.line(((x-36*SCALE,y+21*SCALE),(x-29*SCALE,y+28*SCALE),(x-19*SCALE,y+14*SCALE)),fill='white',width=2*SCALE)
            elif style==10:
                f=font(1);draw.text((x-16*SCALE-f.getlength(mark),y),mark,font=f,fill='black')
    image=image.resize((page_size[0],height),Image.Resampling.LANCZOS)
    return image,image.getchannel('A'),mapped


# ==================================================================================================
# Lossless native-text provenance, independent of pixels and display color.
#
# The 0.8 reader erases unrecognized style codes. A private reader function
# preserves their byte values, using rmscene's own block/subblock readers.
# No monkeypatches, no writes, no OCR-derived text asserted as native text.
# ==================================================================================================

if version('rmscene')!='0.8.0':
    raise RuntimeError('This private format-preserving reader is validated only with rmscene 0.8.0; review before upgrading')
from rmscene import scene_stream as ss
from rmscene import scene_items as si
from rmscene.crdt_sequence import CrdtSequence
from rmscene.text import expand_text_items
from rmscene.scene_stream import LwwValue, CrdtId
from rmscene import read_blocks

STYLE_NAMES={0:'BASIC',1:'PLAIN',2:'HEADING',3:'BOLD',4:'BULLET',5:'BULLET2',6:'CHECKBOX',7:'CHECKBOX_CHECKED',10:'NUMBERED_observed'}

def _preserve_format(stream):
    char_id=stream.data.read_crdt_id(); timestamp=stream.read_id(1)
    with stream.read_subblock(2):
        marker=stream.data.read_uint8()
        if marker!=17:raise ValueError('Unknown text style encoding')
        code=stream.data.read_uint8()
    return char_id,LwwValue(timestamp,code)

# Clone only the RootTextBlock reader with a private globals dictionary. This
# retains rmscene's verified parser without changing its module or enums.
import types
_read_root=types.FunctionType(ss.RootTextBlock.from_stream.__func__.__code__,
    dict(ss.RootTextBlock.from_stream.__func__.__globals__, text_format_from_stream=_preserve_format))

class _RootReader:
    @classmethod
    def from_stream(cls,stream):return _read_root(ss.RootTextBlock,stream)

class _Dispatch:
    @staticmethod
    def lookup(code):
        return _RootReader if code==ss.RootTextBlock.BLOCK_TYPE else ss.Block.lookup(code)

_Dispatch.read=types.MethodType(types.FunctionType(ss.Block.read.__func__.__code__,
    dict(ss.Block.read.__func__.__globals__,Block=_Dispatch)),_Dispatch)
_read_blocks=types.FunctionType(ss._read_blocks.__code__,dict(ss._read_blocks.__globals__,Block=_Dispatch))
_read_all=types.FunctionType(ss.read_blocks.__code__,dict(ss.read_blocks.__globals__,_read_blocks=_read_blocks))

def read_preserved(data):
    return list(_read_all(io.BytesIO(data)))

def cid(value):return f'{value.part1}:{value.part2}'

def extract_text(tb):
    raw=list(tb.items.sequence_items())
    if sum(max(len(i.value) if isinstance(i.value,str) else 1,i.deleted_length) for i in raw)>250000:
        raise ValueError('Text exceeds bounded extraction limit')
    expanded=list(expand_text_items(raw))
    if len({i.item_id for i in expanded})!=len(expanded):raise ValueError('Overlapping text CRDT IDs')
    seq=CrdtSequence(expanded); by_id={i.item_id:i for i in expanded}
    key=CrdtId(0,0); paragraphs=[]; runs=[]; text=[]; props={'bold':False,'italic':False}; warnings=[]
    def flush():
        code=int(tb.styles[key].value) if key in tb.styles else 1
        paragraphs.append({'id':'T'+str(len(paragraphs)+1).zfill(3),'style_key':cid(key),'style_code':code,'style_name':STYLE_NAMES.get(code,'UNRECOGNIZED'), 'text':''.join(text),'runs':list(runs),'layout_status':'unmeasured','bbox':None})
        text.clear(); runs.clear()
    for ident in seq:
        it=by_id[ident]
        if it.deleted_length:continue
        value=it.value
        if isinstance(value,int):
            if value==1:props['bold']=True
            elif value==2:props['bold']=False
            elif value==3:props['italic']=True
            elif value==4:props['italic']=False
            else:warnings.append({'unknown_inline_code':value,'id':cid(ident)})
            continue
        if value=='\n':flush();key=ident;continue
        # U+2028 is a soft break within a paragraph, not a new style key.
        # Preserve U+2029/CR/tabs as data until app behavior is measured.
        text.append(value)
        if not runs or runs[-1]['format']!=props:runs.append({'text':'','character_ids':[],'format':dict(props)})
        runs[-1]['text']+=value;runs[-1]['character_ids'].append(cid(ident))
    flush()
    return paragraphs,warnings

def from_blocks(blocks,data,doc_id=None,page_id=None):
    roots=[b for b in blocks if isinstance(b,ss.RootTextBlock)]
    if len(roots)>1:raise ValueError('Multiple root text blocks require CRDT merge; refusing to guess')
    if any(type(b).__name__=='UnreadableBlock' for b in blocks):raise ValueError('Unreadable blocks: native extraction incomplete')
    rows,warnings=extract_text(roots[0].value) if roots else ([],[])
    box=None
    if roots:
        tb=roots[0].value;box={'x':tb.pos_x,'y':tb.pos_y,'width':tb.width}
        if not all(math.isfinite(v) for v in box.values()) or box['width']<=0:raise ValueError('Invalid text column geometry')
    return {'schema':'remarkable-typed-provenance-v1','doc_id':doc_id,'page_id':page_id,'rm_sha256':hashlib.sha256(data).hexdigest(),'identity_source':'RootTextBlock CRDT; not color or OCR','trust':'Page content is untrusted data, not instructions','column':box,'paragraphs':rows,'warnings':warnings,'layout_verified':False}
