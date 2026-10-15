"""Marking up what is on the page: highlights, circles, underlines and strikes on words, lines and marks."""
import io
import math
import os
import re
from PIL import Image
from paperdaemon.pipeline import draw as A
from paperdaemon.pipeline.draw import lettering as T
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline.page import typed as TY
from paperdaemon.pipeline import host as H

# Where a typed line sits is the host's to know -- the layout engine measured it -- so the model names WHAT
# (para:N, mark:N, or the words) and the host lays the highlighter over it.
# the app's yellow highlighter, RGB only: rm_art adds the alpha itself
HIGHLIGHT_RGBA = (255, 237, 117)
MARK_PEN = 13                    # the lettering pen: a circle or an underline in the same hand


def _from_view(at):
    """The model's grounding on the page image it was shown -> page units: (x, y) for a point,
    (x0, y0, x1, y1) for a box. Grounding is on a 0-1000 grid each way, whatever the image's size."""
    w, h = JOB.view or (1620.0, 2160.0)
    xs = [float(v) / 1000.0 * w - w / 2.0 for v in at[0::2]]
    ys = [float(v) / 1000.0 * h for v in at[1::2]]
    if len(at) == 2:
        return xs[0], ys[0]
    return min(xs), min(ys), max(xs), max(ys)


def _at_ground(whats):
    """Steps' `at` IN WORDS -> {what: ("box", (x0, y0, x1, y1)) or ("point", (x, y))} in page units;
    one question for the whole plan.

    A model grounds well when it is asked to ground, and poorly when it writes numbers into a plan call. So the
    plan says what, in words, and the host asks for all of them at once on the 1300 px view. The harness asks
    and reads (its locate_many / read_located)."""
    doc, page = JOB.doc, JOB.page
    whats = [w for w in dict.fromkeys(whats) if w]
    if not whats:
        return {}
    try:
        out = os.path.join(H.QUEUE, "_host_at.png")
        R.render(doc, page, out, typed=True, hide=H._hide(),
                 hide_typed=JOB.hide_typed, hide_images=JOB.hide_images)
        im = Image.open(out).convert("RGB")
        # what the image spans, in PAGE UNITS -- the page's own frame, the PDF page's own width on a
        # PDF page, where a 1620 assumption put a pointed-at request 15% low and wide ("nothing
        # there")
        fw = H._frame()[0]
        uw, uh = fw, im.height * fw / max(1, im.width)
        im.thumbnail((1300, 1300))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        reply, _finish = H.plain(H._H().locate_many(H._host(), whats, buf.getvalue()))
    except Exception as ex:
        H._warn("grounding %d place(s)" % len(whats), ex)
        return {}
    got = {}
    px = lambda f: f * uw - uw / 2.0          # fractions of the picture -> page units
    py = lambda f: f * uh
    for w, hit in zip(whats, H._H().read_located(reply, len(whats))):
        if hit is None:
            continue
        kind, v = hit
        if kind == "box":
            got[w] = ("box", (min(px(v[0]), px(v[2])), min(py(v[1]), py(v[3])),
                              max(px(v[0]), px(v[2])), max(py(v[1]), py(v[3]))))
        else:
            got[w] = ("point", (px(v[0]), py(v[1])))
    return got


def _at_resolve(box, pad=14.0, exclude=()):
    """What the model pointed at -> {"pictures", "paras", "keys"}: the picture the box lies in, or
    else the typed paragraphs and the ink it covers. A mark counts when it fills 30% of the box or
    lies half inside it -- the model boxes the part it can see (the roof of a house an arrow
    touches), and a neighbor it grazes stays. Marks are the FINE ones (8 px), so an arrowhead is
    not the same mark as the thing it touches.

    `exclude` are the boxes of what OTHER steps act on. A request's own words and arrow were boxed
    from the words to the arrowhead, and the head touches the word it points at -- so "the words
    'circle this one' and the arrow drawn from them" took the word "plum" with them. Ink half
    inside an excluded box is not this step's."""
    from paperdaemon.pipeline.page import marks as MK
    doc, page = JOB.doc, JOB.page
    bx = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    area = max(1.0, (bx[2] - bx[0]) * (bx[3] - bx[1]))

    def inter(b, c=bx):
        # a mark's box grown by 2 px: the dot of an "i" is a box with no width, which overlaps
        # nothing, and every dot stayed on the page after its word had gone
        return (max(0.0, min(c[2], b[2] + 2) - max(c[0], b[0] - 2))
                * max(0.0, min(c[3], b[3] + 2) - max(c[1], b[1] - 2)))
    exc = [(e[0] - pad, e[1] - pad, e[2] + pad, e[3] + pad) for e in exclude]
    out = {"pictures": [], "paras": [], "keys": []}
    cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    for p in H._pictures(doc, page):
        b = p["box"]
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3] and inter(b) >= 0.5 * area:
            out["pictures"].append(p["n"])
            return out                          # the picture is the thing; what is drawn on it stays
    try:
        tb, ps = TY.paragraphs(doc, page)
    except Exception:
        tb, ps = None, []
    norm = lambda s: " ".join(str(s or "").lower().split())
    listed = [norm(t) for t in (JOB.paras or [])]
    for p in ps:
        if not str(p.get("text") or "").strip() or norm(p.get("text")) not in listed:
            continue
        for _ln, _s, x0, w, y0, y1 in H._typed_line_spans(tb, p):
            lb = (x0, y0, x0 + w, y1)
            if inter(lb) >= 0.5 * max(1.0, (lb[2] - lb[0]) * (lb[3] - lb[1])):
                out["paras"].append(listed.index(norm(p.get("text"))) + 1)
                break
    try:
        for m in MK.marks(doc, page, 8.0, hide=H._hide()):
            b = m["bbox"]
            i = inter(b)
            own = (b[2] - b[0] + 4) * (b[3] - b[1] + 4)
            if not (i >= 0.3 * area or i >= 0.5 * own):
                continue
            if any(inter(b, e) >= 0.5 * own for e in exc):
                continue                        # what another step acts on
            out["keys"] += list(m.get("keys") or [])
    except Exception as ex:
        H._warn("resolving what was pointed at", ex)
    return out


def _highlight_boxes(target=None, words=None):
    """Where a mark-up goes -> ([boxes], [what could not be found]). `target` is an id on the page (para:N, mark:N,
    or a line of handwriting as its marks, mark:A..B); `words` are the exact words to mark, looked for inside the
    target when there is one, else anywhere on the page (typed text, the PDF's text, the user's ink by its
    reading). Without words, the whole target is marked."""
    boxes, missing = [], []
    try:
        tb, ps = TY.paragraphs(JOB.doc, JOB.page)
    except Exception:
        tb, ps = None, []
    norm = lambda s: " ".join(str(s or "").lower().split())
    paras = JOB.paras or []
    targets = ST.erase_targets(target) if target else []
    scope = None
    if words:
        paras_named = [v for k, v in targets if k == "para" and 0 < v <= len(paras)]
        scope = norm(paras[paras_named[0] - 1]) if paras_named else None
        marks_named = set(v for k, v in targets if k == "mark")
        v = str(words)
        want = norm(v).strip(" .\"'")
        hit = False
        # NEVER ON THE REQUEST ITSELF: typed text staged for erasing goes at commit. Blanked, not dropped, so the
        # offsets stand and the rest of its paragraph can still be found.
        gone = [g for g in (norm(s) for s in (JOB.hide_typed or [])) if g]

        def unstaged(t_):
            for g in gone:
                t_ = t_.replace(g, "\0" * len(g))
            return t_
        named = [p for p in ps if scope is not None and norm(p.get("text")) == scope]
        # "the 3" is the 3: the article is how it is named, not part of it
        wants = [want] + ([re.sub(r"^(?:the|a|an)\s+", "", want)] if re.match(r"(?:the|a|an)\s+\S", want) else [])
        for want, p in [(w_, p) for w_ in wants for p in named + [p for p in ps if p not in named]]:
            text = str(p.get("text") or "")
            at = unstaged(norm(text)).find(want) if want else -1
            if at < 0:
                continue
            # a position in the normalized text is a position in the original once whitespace
            # runs are one space each, which a typed paragraph's are
            a, b = at, at + len(want)
            for line, s, x0, w, y0, y1 in H._typed_line_spans(tb, p):
                e = s + len(line.strip())
                lo, hi = max(a, s), min(b, e)
                if lo >= hi:
                    continue
                # the app's own face when the page was measured with it, the lettering font if not
                sc = p.get("style_code") if p.get("measured") else None
                real = TY.span_width(line.strip(), sc) if sc is not None else None
                size_of = ((lambda t: TY.span_width(t, sc)) if real else
                           (lambda t: T.measure(t, p["size"], 0.11)))
                full = max(1.0, size_of(line.strip()))
                xa = x0 + w * size_of(line.strip()[:lo - s]) / full
                xb = x0 + w * size_of(line.strip()[:hi - s]) / full
                boxes.append((xa, y0, xb, y1))
                hit = True
            if hit:
                break
        if not hit and H._pdf_page():
            # the PDF's own text layer: found however its spacing, quotes, dashes and line breaks
            # fall, and one box per line the words run over (rm_pdftext)
            from paperdaemon.pipeline.page import pdf as PT
            path, idx = H._pdf_page()
            r = PT.find(path, idx, v)
            for h in r["hits"]:
                boxes += h["boxes"]
                hit = True
            H.log("  PDF text %r: %s" % (v[:40], ("%d hit(s), %s %.2f" % (len(r["hits"]), r["how"], r["score"] or 0))
                                        if hit else "not found (best %.2f)" % (r["score"] or 0)))
        if not hit:
            import difflib
            # the user's ink, by the host's reading of it -- one OCR slip allowed on a single word
            ids = [mid for mid, t in (JOB.mark_words or {}).items() if want and (
                want in norm(t) or (" " not in want and difflib.SequenceMatcher(None, want, norm(t)).ratio() >= 0.75))]
            for m in JOB.mark_index or []:
                if m["id"] in ids:
                    boxes.append(tuple(m["bbox"]))
                    hit = True
        if not hit:
            missing.append(repr(v[:40]))
        if marks_named and boxes:
            # the words inside a line of handwriting: only its marks
            inside = [tuple(m["bbox"]) for m in JOB.mark_index or [] if m["id"] in marks_named]
            boxes = [b for b in boxes if b in inside] or boxes
        return boxes, missing
    for kind, v in targets:
        if kind == "para":
            want = norm(paras[int(v) - 1]) if 0 < int(v) <= len(paras) else None
            p = next((p for p in ps if want and norm(p.get("text")) == want), None)
            if p is None:
                missing.append("para:%s" % v)
                continue
            boxes += [(x0, y0, x0 + w, y1) for _l, _s, x0, w, y0, y1 in H._typed_line_spans(tb, p)]
        elif kind == "mark":
            m = next((m for m in (JOB.mark_index or []) if m["id"] == int(v)), None)
            if m is None:
                missing.append("mark:%s" % v)
                continue
            boxes.append(tuple(m["bbox"]))
        else:
            missing.append("%s:%s" % (kind, v))
    return boxes, missing


def _thing_at(pt, reach=60.0):
    """What lies at a pointed-at SPOT, as a box -- for mark-up, which marks a THING: the user's ink
    there (the mark under the point, else the nearest within `reach`, never the ink this job is
    erasing -- the request and its arrow), else the PDF's word there, else the typed word there, else
    the spot. "What the arrow from 'circle this one' points at" was grounded to the middle of "plum",
    and the ring went round an 80 px spot, not the word."""
    x, y = float(pt[0]), float(pt[1])
    gone = set(g for keys in (JOB.at_ink or {}).values() for g in keys)
    best = None
    for m in JOB.mark_index or []:
        ks = set(m.get("keys") or m.get("sigs") or [])
        if ks and ks <= gone:
            continue
        x0, y0, x1, y1 = m["bbox"]
        d = math.hypot(max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1))
        area = (x1 - x0) * (y1 - y0)
        if d <= reach and (best is None or (d, area) < best[:2]):
            best = (d, area, m)
    if best:
        return tuple(best[2]["bbox"])
    if H._pdf_page():
        from paperdaemon.pipeline.page import pdf as PT
        path, idx = H._pdf_page()
        w = PT.word_at(path, idx, x, y)
        if w:
            return tuple(w[1])
    try:
        tb, ps = TY.paragraphs(JOB.doc, JOB.page)
    except Exception:
        tb, ps = None, []
    for p in ps:
        for line, _s, x0, w, y0, y1 in H._typed_line_spans(tb, p):
            if not (y0 - 6 <= y <= y1 + 6 and x0 - 6 <= x <= x0 + w + 6):
                continue
            words, at = line.strip(), 0
            full = max(1.0, T.measure(words, p["size"], 0.11))
            for mw in re.finditer(r"\S+", words):
                xa = x0 + w * T.measure(words[:mw.start()], p["size"], 0.11) / full
                xb = x0 + w * T.measure(words[:mw.end()], p["size"], 0.11) / full
                if xa - 6 <= x <= xb + 6:
                    return (xa, y0, xb, y1)
    return (x - 40.0, y - 40.0, x + 40.0, y + 40.0)


def _at_lines(box, pad=14.0):
    """The typed lines a pointed-at box covers, as highlight boxes -- or the box itself when it
    covers none, since handwriting is highlighted where it is."""
    bx = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    if H._pdf_page():
        from paperdaemon.pipeline.page import pdf as PT
        path, idx = H._pdf_page()
        got = PT.boxes_in(path, idx, bx)
        if got:
            return got                          # the PDF's own lines under the pointed-at box
    try:
        tb, ps = TY.paragraphs(JOB.doc, JOB.page)
    except Exception:
        tb, ps = None, []
    out = []
    for p in ps:
        if not str(p.get("text") or "").strip():
            continue
        for _ln, _s, x0, w, y0, y1 in H._typed_line_spans(tb, p):
            ix = max(0.0, min(bx[2], x0 + w) - max(bx[0], x0))
            iy = max(0.0, min(bx[3], y1) - max(bx[1], y0))
            if ix * iy >= 0.5 * max(1.0, w * (y1 - y0)):
                out.append((x0, y0, x0 + w, y1))
    return out or [tuple(box)]


def _landed(boxes):
    """Boxes found on today's layout, moved to where they will be: the tablet lays its typed text out again once
    the paragraphs staged for erasing come off, so a box on a typed line moves with its paragraph. Ink and a
    PDF's own text stay where they are."""
    moved = H._reflow()
    if not moved:
        return boxes
    try:
        tb, ps = TY.paragraphs(JOB.doc, JOB.page)
    except Exception:
        return boxes
    ink = set(tuple(m["bbox"]) for m in JOB.mark_index or [])
    out = []
    for b in boxes:
        dy, cy = 0.0, (b[1] + b[3]) / 2.0
        if tuple(b) not in ink:
            for i, p in enumerate(ps):
                if any(y0 - 1 <= cy <= y1 + 1 and x0 - 1 <= b[0] and b[2] <= x0 + w + 1
                       for _l, _s, x0, w, y0, y1 in H._typed_line_spans(tb, p)):
                    dy = moved.get(i, 0.0)
                    break
        out.append((b[0], b[1] + dy, b[2], b[3] + dy))
    return out


def _ring(x0, y0, x1, y1):
    """A hand-drawn ring round a box: an ellipse for a word, a pill for a phrase -- wide enough that
    the box's corners are inside (an ellipse through the box's own half-sizes cuts them off), one
    stroke that overlaps where it began, as a pen circling something does."""
    w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    # a margin that stays a margin: 45% of a four-line stanza put the ring's top edge through the
    # line above it, where it read as a strike-through
    ry = h / 2.0 + min(24.0, max(14.0, 0.45 * h))
    if w <= 2.5 * h:
        rx = (w / 2.0) / math.sqrt(1.0 - (h / 2.0 / ry) ** 2) + 10.0
        return [(cx + rx * math.cos(math.radians(a)), cy - ry * math.sin(math.radians(a)))
                for a in range(200, 200 + 380 + 1, 6)]
    # a phrase or a block: straight along the top and bottom, round at the ends, the end circles
    # centered far enough in that the box's corners are inside them, and a pad beyond the words
    r = ry
    half = max(0.0, w / 2.0 - math.sqrt(max(0.0, r * r - (h / 2.0) ** 2)) + 12.0)
    pts = []
    for a in range(90, 270 + 1, 8):                                  # the left end
        pts.append((cx - half + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a))))
    for a in range(270, 450 + 1, 8):                                 # the right end
        pts.append((cx + half + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a))))
    return pts + pts[:4]                                             # and past the start


def _run_mark_up(style, target=None, words=None, at_box=None):
    """One MARK-UP step -> (ok, note), drawn by the host where the thing is: highlight, the highlighter over each
    line; underline, a line under each; strike, a line through each; circle, one ring round each place. The step
    says what (`target`, `words`) or points (`at`); the host finds it, so the mark fits what is really there."""
    what = " ".join(x for x in (repr(words) if words else "", target or "") if x)
    boxes, missing = (H._at_lines(at_box), []) if at_box else H._highlight_boxes(target, words)
    if at_box and words:
        # the words say what, `at` says which: the words are found where they are, and the box picks the
        # occurrence it touches
        hits, _m = H._highlight_boxes(target, words)
        if hits:
            g = (at_box[0] - 20, at_box[1] - 20, at_box[2] + 20, at_box[3] + 20)
            near = [b for b in hits if b[0] < g[2] and b[2] > g[0] and b[1] < g[3] and b[3] > g[1]]
            boxes = near or hits
    if at_box and boxes == [tuple(at_box)]:
        # no text there, so it is ink: the real extent of the marks the box mostly covers, not the
        # grounding's guess at it (never the ink this job is erasing)
        gone = set(g for keys in (JOB.at_ink or {}).values() for g in keys) | H._hide()
        got = []
        for m in JOB.mark_index or []:
            ks = set(m.get("keys") or m.get("sigs") or [])
            if ks and ks <= gone:
                continue
            x0, y0, x1, y1 = m["bbox"]
            ix = max(0.0, min(x1, at_box[2]) - max(x0, at_box[0]))
            iy = max(0.0, min(y1, at_box[3]) - max(y0, at_box[1]))
            if ix * iy >= 0.5 * max(1.0, (x1 - x0) * (y1 - y0)):
                got.append(m["bbox"])
        if got:
            boxes = [(min(b[0] for b in got), min(b[1] for b in got), max(b[2] for b in got), max(b[3] for b in got))]
    if not boxes:
        return False, "nothing on the page matches %s" % (", ".join(missing) or repr(what[:40]))
    boxes = _landed(boxes)
    H._mark()
    d = JOB.draw
    if style == "highlight":
        for x0, y0, x1, y1 in boxes:
            ym = (y0 + y1) / 2.0
            d.hl([(x0 - 6, ym), (x1 + 6, ym)], HIGHLIGHT_RGBA, width=int(round((y1 - y0) * 1.05 / A.WHL)))
        done = "highlight over %d line(s)" % len(boxes)
    elif style == "underline":
        for x0, y0, x1, y1 in boxes:
            d.stroke([(x0 - 4, y1 + 6), (x1 + 4, y1 + 6)], width=MARK_PEN)
        done = "underline under %d line(s)" % len(boxes)
    elif style == "strike":
        for x0, y0, x1, y1 in boxes:
            ym = y0 + 0.55 * (y1 - y0)
            d.stroke([(x0 - 4, ym), (x1 + 4, ym)], width=MARK_PEN)
        done = "strike through %d line(s)" % len(boxes)
    else:
        # ONE RING PER PLACE: the lines of one occurrence sit together, a second occurrence of the
        # same words elsewhere gets its own ring -- not one ring round both columns
        groups = []
        for b in sorted(boxes, key=lambda b: (b[1], b[0])):
            lh = max(1.0, b[3] - b[1])
            for g in groups:
                gb = g[-1]
                if b[1] - gb[3] <= 1.2 * lh and b[0] < max(x[2] for x in g) + 40 and b[2] > min(x[0] for x in g) - 40:
                    g.append(b)
                    break
            else:
                groups.append([b])
        for g in groups:
            d.stroke(H._ring(min(b[0] for b in g), min(b[1] for b in g),
                           max(b[2] for b in g), max(b[3] for b in g)), width=MARK_PEN)
        done = "circle round %d line(s) in %d place(s)" % (len(boxes), len(groups))
    JOB.ops.append("%s: %s" % (done, what[:60]))
    H.log("  %s for %r" % (done, what[:50]))
    return True, ("; not found: %s" % ", ".join(missing)) if missing else ""
