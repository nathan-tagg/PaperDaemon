"""Reading the page for a job: its typed text, ink, pictures and history, and the listing and pictures the model is shown."""
import base64
import io
import json
import os
import re
import time
from PIL import Image
from paperdaemon.notepad import Notepad
from paperdaemon.pipeline import draw as A
from paperdaemon.pipeline import page as ER
from paperdaemon.pipeline.draw import lettering as T
from paperdaemon.pipeline.host import layout as PL
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.host.job import UNSET
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline.page import typed as TY
from paperdaemon.pipeline import host as H


# ------------------------------------------------------------------- tools
def _arrows(doc, page):
    """Arrows on the page, or [] if anything goes wrong. Never fatal."""
    try:
        from paperdaemon.pipeline.page import marks as AR
        return [{"mark": a["id"], "tip": a["tip"], "heading_deg": a["heading_deg"],
                 "points_at_mark": a["points_at"]} for a in AR.arrows(doc, page, hide=H._hide())]
    except Exception:
        return []


def t_page_info():
    """Geometry and what is already there, so it never has to guess."""
    doc, page = JOB.doc, JOB.page
    # Never report "0 strokes" because the read FAILED: a blank page is the case where skip() is right, so a
    # read error would become "nothing was asked". Say it could not be read.
    try:
        strokes = R.strokes(doc, page)
        _h = H._hide()
        if _h:
            from paperdaemon.pipeline import page as _P
            strokes = [L for L in strokes if _P.skey(L) not in _h]
    except Exception as ex:
        return {"error": "could not read the page: %s: %s. Do NOT treat this "
                         "as an empty page." % (type(ex).__name__, str(ex)[:80])}
    bottom = None
    for line in strokes:
        for p in getattr(line, "points", ()):
            if bottom is None or p.y > bottom:
                bottom = p.y
    typed_err = None
    try:
        from paperdaemon.pipeline.page import typed as TY
        # typed text staged for erasing does not count: the reply goes where the page WILL be free
        tb = TY.text_bottom(doc, page, skip=JOB.hide_typed)
        if tb and (bottom is None or tb > bottom):
            bottom = tb
    except Exception as ex:
        # never report a page as empty because the typed text could not be measured: a reply would land on
        # the user's words
        H._warn("typed-text extent", ex)
        typed_err = ("typed text on this page could NOT be measured (%s). first_free_y is the "
                     "bottom of the STROKES only -- typed text may sit BELOW it and you would "
                     "write on top of it. Call render() and LOOK before placing anything, or "
                     "skip() and say the page could not be read."
                     % type(ex).__name__)
    # PICTURES ARE CONTENT: free space measured from strokes and typed text alone would read a picture's area
    # as empty. Pictures staged for removal do not count, like erased ink.
    for pic in H._pictures(doc, page):
        pb = pic["box"][3]
        if bottom is None or pb > bottom:
            bottom = pb
    kind, src, idx = R.source_page(doc, page)
    return {"page": page, "existing_strokes": len(strokes),
            **({"typed_text_warning": typed_err} if typed_err else {}),
            "lowest_content_y": round(bottom) if bottom else None,
            # an empty page is free from the safe area's top, which follows the page's margins
            "first_free_y": round(bottom + 80) if bottom else int(H._safe()[1]),
            "room_left": (bottom is None or bottom + 80 < H._safe()[3] - 40),
            "safe_area": {"x_min": H._safe()[0], "x_max": H._safe()[2],
                          "y_min": H._safe()[1], "y_max": H._safe()[3]},
            # Named places, stated rather than left for the model to infer: the middle of the page is not
            # first_free_y.
            "where": {
                "center": [0, round((H._safe()[1] + H._safe()[3]) / 2)],
                "top_y": round(H._safe()[1] + 60), "middle_y": round((H._safe()[1] + H._safe()[3]) / 2),
                "bottom_y": round(H._safe()[3] - 60),
                "left_x": round(H._safe()[0] + 40), "center_x": 0,
                "right_x": round(H._safe()[2] - 40),
                "top_left": [round(H._safe()[0] + 40), round(H._safe()[1] + 60)],
                "top_right": [round(H._safe()[2] - 40), round(H._safe()[1] + 60)],
                "bottom_left": [round(H._safe()[0] + 40), round(H._safe()[3] - 60)],
                "bottom_right": [round(H._safe()[2] - 40), round(H._safe()[3] - 60)],
                "full_width": round(H._safe()[2] - H._safe()[0]),
                "full_height": round(H._safe()[3] - H._safe()[1])},
            "annotates": ("%s page %s" % (kind, idx)) if kind else None,
            # ARROWS. The user draws one and writes "do it here" or "remove this"; the computed tip is the
            # referent. `points_at: null` means the arrow indicates EMPTY PAPER, which is itself the
            # instruction: put it at `tip`.
            "arrows": H._arrows(doc, page),
            # pictures placed on the page (a chart of yours, or one the user pasted): not strokes,
            # so show_marks does not number them; erase_area removes one whose center is inside
            "pictures": H._pictures(doc, page)}


def _pictures(doc, page, hidden_too=False):
    try:
        from paperdaemon.pipeline.page import images as IM
        hidden = JOB.hide_images or []
        def _hid(box):
            return any(all(abs(float(a) - float(b)) < 1.5 for a, b in zip(box, hb)) for hb in hidden)
        placed = IM.placements(doc, page)
        out = []
        ims = IM.items(doc, page)
        taken = [tuple(im["box"]) for im in ims if not im.get("anchored")]
        for i, im in enumerate(ims):
            if _hid(im["box"]) and not hidden_too:
                continue
            rec = IM.record_for(im, placed, taken) or {}
            out.append({"n": i + 1, "box": [round(v) for v in im["box"]], "asset": im.get("name"), "path": im.get("path"),
                        "made_by": "this system" if rec else "the user",
                        "what": rec.get("type"), "title": rec.get("title"), "spec": rec.get("spec"),
                        **({"position": "approximate"} if im.get("approx_y") else {})})
        return out
    except Exception:
        return []


def _text_col(doc=None, page=None):
    """The typed column of THIS page -- the app's own text block if it has one, else the default.
    Lettering is kept to it: a reply wider than the typed lines looks out of alignment."""
    if JOB.text_col:
        return tuple(JOB.text_col)
    try:
        tb, _ps = TY.paragraphs(doc or JOB.doc, page or JOB.page)
        if tb is not None and tb.width:
            x0 = float(tb.pos_x)
            x1 = x0 + float(tb.width)
            if x1 - x0 >= 400:
                return (max(H._safe()[0], x0), min(H._safe()[2], x1))
    except Exception:
        pass
    return PL.TEXT_COL


def _typed_boxes(doc, page):
    """One bbox per line of typed text, in page coordinates, so a place beside a mark can be kept
    off the words as well as off the ink: where each line will be once the staged erasures are made."""
    out = []
    try:
        from paperdaemon.pipeline.draw import lettering as _T
        tb, ps = TY.paragraphs(doc, page)
        moved = H._reflow()
        needles = [ER._normalize(s)[0] for s in (JOB.hide_typed or []) if s]
        for n_, p in enumerate(ps or ()):
            if needles and any(n and n in ER._normalize(p.get("text") or "")[0] for n in needles):
                continue                         # staged for erasing: not an obstacle
            dy = moved.get(n_, 0.0)
            for i, line in enumerate(p["lines"]):
                if not line.strip():
                    continue
                # measured the way the renderer measures, so the box matches the drawn line
                widths = p.get("line_widths") or []
                if i < len(widths) and widths[i] > 0:
                    # the engine's own measurement of this line, in the app's metrics
                    x0 = (p.get("line_x") or [float(tb.pos_x)] * len(widths))[i]
                    w, x0 = widths[i], float(x0)
                else:
                    w, x0 = _T.measure(line, p["size"], 0.11), float(tb.pos_x)
                y0, y1 = H._line_ink(p, i)
                out.append((x0, y0 + dy, x0 + w, y1 + dy))
    except Exception as ex:
        H._warn("typed-text line boxes", ex)
    return out


def _reflow():
    """{paragraph index in TY.paragraphs(): how far it moves} once this job's staged typed erasures are made (the
    tablet lays its text out again, so what follows an erased paragraph moves up). {} when none are staged."""
    if not JOB.hide_typed or not JOB.doc:
        return {}
    try:
        return TY.reflow(JOB.doc, JOB.page, list(JOB.hide_typed))
    except Exception as ex:
        H._warn("laying the typed text out without the staged erasures", ex)
        return {}


def _line_ink(p, i):
    """(top, bottom) of line i's INK. A paragraph's y is the TOP of its first line, not a baseline
    (rm_typed.draw sets glyphs on y + size)."""
    top = float(p["y"]) + i * float(p["lh"])
    return top + 0.15 * p["size"], top + 1.40 * p["size"]


def _typed_line_spans(tb, p):
    """[(line text, start offset in the paragraph, x0, width, y_top, y_bottom)] for one paragraph."""
    out, pos, text = [], 0, str(p.get("text") or "")
    widths, xs = p.get("line_widths") or [], p.get("line_x") or []
    for i, line in enumerate(p.get("lines") or []):
        start = text.find(line.strip(), pos) if line.strip() else pos
        start = pos if start < 0 else start
        pos = start + len(line.strip())
        if not line.strip():
            continue
        w = widths[i] if i < len(widths) and widths[i] > 0 else T.measure(line, p["size"], 0.11)
        x0 = float(xs[i]) if i < len(xs) else float(tb.pos_x)
        y0, y1 = H._line_ink(p, i)
        out.append((line, start, x0, float(w), y0, y1))
    return out


# ------------------------------------------------------------- pointing, not numbering
# The model binds what it sees on the page image to a place far better than to a number in a list, so a step
# may carry `at`: the model's grounding on the page image, which the host resolves on the page.
def _frame():
    """This job's page frame in page units, (width, height): 1620 x 2160 on a notebook page; on a
    PDF page, the PDF page at rm_render.PDF_SCALE (1404 x 1872 only for a 157.5 x 210 mm page). A
    render fills the frame, so an image pixel maps to page units by the ratio of the sizes."""
    if JOB.frame is UNSET:
        try:
            JOB.frame = tuple(float(v) for v in R.page_frame(JOB.doc, JOB.page))
        except Exception:
            JOB.frame = (1620.0, 2160.0)
    return JOB.frame


def _drawing():
    """A fresh draft in this job's page frame, so its preview lies on the page render at the same scale."""
    return A.Drawing(*[int(round(v)) for v in H._frame()])


def _pdf_page():
    """This job's page as a PDF page -> (path, index), or None. Looked up once a job.
    Highlighting a PDF is the likeliest highlight there is, and a PDF's words are in its text
    layer, not in the typed text: rm_pdftext finds them and says where each line is."""
    if JOB.pdf_page is UNSET:
        try:
            from paperdaemon.pipeline.page import pdf as PT
            JOB.pdf_page = PT.source(JOB.doc, JOB.page)
        except Exception as ex:
            H._warn("reading the page's PDF", ex)
            JOB.pdf_page = None
    return JOB.pdf_page


def _new_since_last_job(doc, page, paras, ms):
    """-> ([para numbers], ["mark:N" / "mark:A..B"]) added since this system last committed to the
    page, from the page history's latest snapshot (taken just before that commit, so it holds the
    page as that job found it). Nothing when the page has no history: then everything is new."""
    from paperdaemon.pipeline import page as _P
    ents = _P.entries(doc, page)
    JOB.page_history, JOB.new_mark_ids = bool(ents), []
    if not ents:
        return [], []
    last = ents[0]["path"]
    base = last[:-5] if last.endswith(".json") else last        # entries give the stamp, no extension
    last, old_paras, rm_ = base + ".json", [], base + ".rm"
    if os.path.exists(rm_):
        blocks = R.blocks_of(rm_)
        for b in blocks:                                # every text block, as TY.paragraphs reads them
            if isinstance(b, TY.ss.RootTextBlock):
                old_paras += [p.get("text", "") for p in TY._paragraphs_of(b.value)]
    norm = lambda s: " ".join(str(s or "").split()).lower()
    had = set(norm(t) for t in old_paras if str(t).strip())
    new_p = [i for i, t in enumerate(paras or [], 1) if str(t).strip() and norm(t) not in had]
    old_sigs = set(s.get("sig") for s in (_P.load(last).get("strokes") or []))
    fresh = [m for m in ms if m.get("owner") == "yours" and not (set(m.get("sigs") or []) & old_sigs)]
    new_m, ids = [], [m["id"] for m in fresh]
    JOB.new_mark_ids = ids
    for i in ids:                                      # consecutive numbers as one range
        if new_m and new_m[-1][1] == i - 1:
            new_m[-1][1] = i
        else:
            new_m.append([i, i])
    return new_p, [("mark:%d" % a) if a == b else ("mark:%d..%d" % (a, b)) for a, b in new_m]


def _ink_runs(ms, words):
    """The marks in reading order, as runs: a LINE OF THE USER'S WRITING (their words in one row, each
    read by OCR, no wider a gap than a few letters -- another column is not the same line) is one run, and
    every other mark is a run of its own. The listing names a line as line:N."""
    def same_line(a, b):
        h = max(a["bbox"][3] - a["bbox"][1], b["bbox"][3] - b["bbox"][1], 1)
        return (a.get("row") == b.get("row") and a["owner"] == b["owner"] == "yours"
                and words.get(a["id"]) and words.get(b["id"])
                and b["bbox"][0] - a["bbox"][2] <= 2.5 * h)

    def stop(a, b):
        # its PUNCTUATION: a full stop, a comma, a closing quote after a word -- tiny, unread, a letter's gap
        # on -- belongs to the line, so it comes off with it
        h = max(a["bbox"][3] - a["bbox"][1], 1)
        return (a.get("row") == b.get("row") and a["owner"] == b["owner"] == "yours"
                and words.get(a["id"]) and not words.get(b["id"])
                and b["bbox"][2] - b["bbox"][0] <= 0.4 * h and b["bbox"][3] - b["bbox"][1] <= 0.5 * h
                and b["bbox"][0] - a["bbox"][2] <= 1.0 * h)
    runs = []
    for m in ms:
        if runs and (same_line(runs[-1][-1], m) or stop(runs[-1][-1], m)):
            runs[-1].append(m)
        else:
            runs.append([m])
    return runs


def _run_reading(run, words):
    """What a run of ink says: its marks' readings in order (punctuation marks have none)."""
    return " ".join(words[m["id"]] for m in run if words.get(m["id"]))


def page_image(doc, page, note):
    """The page as it stands, with the pending draft composited on top."""
    out = os.path.join(H.QUEUE, "_host_view.png")
    try:
        _t = time.time()
        R.render(doc, page, out, typed=True, hide=H._hide(),
                 hide_typed=JOB.hide_typed, hide_images=JOB.hide_images)
        H.log("  render: %.1fs" % (time.time() - _t))
        base = Image.open(out).convert("RGB")
        render_failed = None
    except Exception as ex:
        # a failed render is never a blank sheet: that would tell the model the page is empty
        H._warn("page render", ex)
        render_failed = ("THE PAGE COULD NOT BE RENDERED (%s). The image below is BLANK because "
                         "of that failure, NOT because the page is empty. Do not place anything "
                         "by looking at it -- say so and stop." % type(ex).__name__)
        base = Image.new("RGB", (1620, 2160), "white")
    for _im in JOB.images or []:
        # a pending picture, where commit() will put it -- under the draft ink, like the device
        try:
            _x0, _y0, _x1, _y1 = _im["box"]
            _fw, _fh = H._frame()
            _sx, _sy = base.width / _fw, base.height / _fh
            _pic = Image.open(_im["png"]).convert("RGB").resize(
                (max(1, int((_x1 - _x0) * _sx)), max(1, int((_y1 - _y0) * _sy))))
            base.paste(_pic, (int((_x0 + _fw / 2.0) * _sx), int(_y0 * _sy)))
        except Exception as ex:
            # the picture it just inserted, missing from the picture of the page
            H._warn("compositing an inserted image", ex)
    if JOB.ops and JOB.draw.strokes:
        draft_path = os.path.join(H.QUEUE, "_host_draft.png")
        JOB.draw.render_png(draft_path)
        d = Image.open(draft_path).convert("RGB").resize(base.size)
        mask = d.convert("L").point(lambda v: 255 if v < 250 else 0)
        base = Image.composite(d, base, mask)
    if not H.VISION:
        # read the full-size composite: the thumbnail is too small for OCR
        full = os.path.join(H.QUEUE, "_host_view_full.png")
        try:
            base.save(full, "PNG")
        except Exception:
            full = out
        text = H.describe_page(doc, page) + H._H().describe(H._host(), full)
    # what the image spans, in page units, so the model's grounding on it maps back (_from_view) --
    # in the page's own frame (a PDF page's own width, at rm_render.PDF_SCALE)
    _fw = H._frame()[0]
    JOB.view = (_fw, base.height * _fw / max(1, base.width))
    base.thumbnail((1300, 1300))
    # Write the COMPOSITE back over the plain render, so anything inspecting the file sees what the model saw.
    try:
        base.save(out, "PNG")
    except Exception as ex:
        H._warn("saving the page view", ex)
    if render_failed:
        note = render_failed + "\n\n" + note
    if not H.VISION:
        return {"role": "user", "content": note + "\n\n" + text}
    buf = io.BytesIO()
    base.save(buf, "PNG")
    return {"role": "user", "content": [
        {"type": "text", "text": note},
        {"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}}]}


def image_message(path, note):
    """Any PNG as a user message the model can look at."""
    if not H.VISION:
        return {"role": "user", "content": note + "\n\n" + H._H().describe(H._host(), path)}
    im = Image.open(path).convert("RGB")
    im.thumbnail((1300, 1300))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return {"role": "user", "content": [
        {"type": "text", "text": note},
        {"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}}]}


def describe_png(path):
    """The page (or any render) as text: OCR lines with positions, for a model that cannot see."""
    from paperdaemon import reader
    rows, err = None, None
    try:
        rows = reader.lines_of(reader.read_picture(path, scale=2))      # at 1x the 34-px lettering reads as nothing
    except Exception as ex:
        err = ex
    if rows is None:
        return ("THE PAGE, READ BY OCR: the reader failed (%s). Trust the typed text above if there "
                "is any; if there is none, call page_info() and decide from its counts." % str(err)[:60])
    try:
        with Image.open(path) as im:
            iw, ih = im.size
    except Exception:
        iw, ih = 1620, 2160
    fw, fh = H._frame() if JOB.doc else (1620.0, 2160.0)
    sx, sy = fw / max(1, iw), fh / max(1, ih)
    out = []
    for r in rows[:60]:
        x = int(r["x"] * sx - fw / 2.0)
        y = int((r["y"] + r["h"]) * sy)
        size = max(8, int(r["h"] * sy))
        out.append("  y=%4d x=%5d size~%2d  %s" % (y, x, size, r["text"][:120]))
    if not out:
        return "THE PAGE, READ BY OCR: nothing legible -- blank, or only marks that are not text."
    return ("THE PAGE, READ BY OCR (page coordinates: x -810..810 with 0 at the center, y 0 at "
            "the top; each line is its baseline, left edge and approximate size):\n" + "\n".join(out))


def describe_page(doc, page):
    """The typed text of the page, verbatim, before the OCR of the ink. Never guesses."""
    try:
        from paperdaemon.pipeline.page import typed as TY
        tb, paras = TY.paragraphs(doc, page)
    except Exception:
        paras = []
    L = []
    rows = [p for p in (paras or []) if str(p.get("text", "")).strip()]
    if rows:
        L.append("TYPED TEXT ON THE PAGE (exact, the user typed this):")
        for p in rows:
            L.append("  y=%4d  %s" % (int(p.get("y") or 0), str(p["text"]).strip()[:300]))
        L.append("")
    return "\n".join(L)


def job_context(doc, page, name):
    """Everything the decision turn needs, AS TEXT: the typed paragraphs verbatim and numbered, the ink
    as numbered marks with their owner and extent, the arrows, the pictures, the free space. The
    picture of the page goes with it. The model reads text exactly and pictures approximately, and
    an id cannot be misquoted."""
    L = ["This is %s page %s. It changed, which is why you were woken. Today is %s; the time is %s."
         % (name, page, time.strftime("%A %d %B %Y"), time.strftime("%H:%M"))]
    try:
        numbers = dict((p["id"], i + 1) for i, p in enumerate(R.live_pages(doc)))
    except Exception:
        numbers = {}
    pad = Notepad(doc).read(page_id=JOB.page_id, numbers=numbers)
    if pad:
        # HISTORY, NOT A SOURCE: an earlier answer may have been wrong. Another page's entry never settles
        # this page; this page's own entries are its history, which a notebook's system prompt may rule on.
        L += ["", "THIS NOTEBOOK'S NOTEPAD (what earlier jobs in this notebook were asked and did, "
                  "newest last, each under the page it was on -- a record of what was done, NOT a "
                  "source of facts: what an earlier job wrote may have been wrong; look facts up. "
                  "What another page asked or answered never settles a request on THIS page):", pad]
    paras = []
    _t = time.time()
    try:
        _tb, ps = TY.paragraphs(doc, page)
        paras = [str(p.get("text", "")).strip() for p in ps if str(p.get("text", "")).strip()]
    except Exception as ex:
        H._warn("reading the typed text", ex)
        L += ["", "THE TYPED TEXT COULD NOT BE READ (%s) -- if the picture shows typed words, do not "
                  "place anything over them; say so." % type(ex).__name__]
    _t_paras, _t = time.time() - _t, time.time()
    JOB.paras = paras
    JOB.listing = dict(("para:%d" % (i + 1), {"owner": "user", "text": t}) for i, t in enumerate(paras[:ST.ERASE_RANGE["para"]]))
    # EVERY ID THE LISTING PRINTS IS ONE THE TOOLS' erase ENUM HOLDS (rm_steps.ERASE_IDS): what lies
    # beyond its ranges is counted, not numbered
    if paras:
        L += ["", "TYPED PARAGRAPHS ON THE PAGE, the typed text, one each (its id: para:N):"]
        L += ["  para:%d  %s" % (i + 1, t[:500]) for i, t in enumerate(paras[:ST.ERASE_RANGE["para"]])]
        if len(paras) > ST.ERASE_RANGE["para"]:
            L.append("  ... and %d more typed paragraphs below these" % (len(paras) - ST.ERASE_RANGE["para"]))
    else:
        L += ["", "TYPED PARAGRAPHS: none."]
    if H._pdf_page():
        # A PDF PAGE: its words are in the PDF, not in the typed text. Shown line by line so a
        # highlight can quote them; the host finds the quote in the PDF's text layer (rm_pdftext).
        try:
            from paperdaemon.pipeline.page import pdf as PT
            path_, idx_ = H._pdf_page()
            L += ["", "THIS IS A PDF PAGE (page %d of the PDF). ITS TEXT, line by line -- to highlight, quote "
                      "the words exactly:" % (idx_ + 1),
                  PT.text_of(path_, idx_, 2500)]
        except Exception as ex:
            H._warn("reading the PDF text", ex)
    try:
        from paperdaemon.pipeline.page import marks as MK
        ms = MK.marks(doc, page, 30.0, hide=H._hide())
    except Exception as ex:
        H._warn("indexing the ink", ex)
        ms = []
    JOB.mark_index = ms
    try:
        from paperdaemon.pipeline import page as _P
        JOB.keys_before = set(_P.skey(l) for l in R.strokes(doc, page))
    except Exception:
        JOB.keys_before = set()
    # WHAT EACH MARK SAYS, read by the host (OCR), so the model names a word it sees by its id (mark:3,
    # line:2) rather than by a position in a list.
    _t_marks, _t = time.time() - _t, time.time()
    words = H._mark_words(doc, page, ms)
    JOB.mark_words = words
    _t_words, _t = time.time() - _t, time.time()
    def _made(m):
        # this system's own ink says what it is and when it was made, so a request that makes it obsolete
        # ("make the house bigger") can be seen to
        md = m.get("made") or {}
        if m["owner"] != "mine" or not md.get("what"):
            return ""
        t_ = time.localtime(md.get("at") or 0)
        when = (time.strftime("%H:%M", t_) if time.strftime("%Y%m%d", t_) == time.strftime("%Y%m%d")
                else time.strftime("%b %d", t_))
        return " (%s, %s)" % (md["what"][:60], when)
    # THE LISTING'S IDs ARE THE ONES THE TOOLS TAKE. A line of the user's handwriting is ONE entry, line:N;
    # every other mark is mark:N. The word "line" and the word "mark" are the same in the heading, the entry and
    # the id.
    JOB.ink_lines = {}
    entry_of = {}                                  # mark id -> the id of the entry that lists it
    if ms:
        L += ["", "INK ON THE PAGE -- LINES of the user's handwriting (its id: line:N) and other ink MARKS (its "
                  "id: mark:N; each word of a line is a mark too, numbered with it). 'yours' = the user drew "
                  "it, 'mine' = this system did, with what it was:"]
        i_, shown, unlisted = 0, 0, 0
        for run in H._ink_runs(ms, words):
            if shown >= 40:
                break
            i_ += len(run)
            if len(run) >= 2:
                if len(JOB.ink_lines) >= ST.ERASE_RANGE["line"]:
                    unlisted += len(run)
                    continue
                n_ = len(JOB.ink_lines) + 1
                box_ = (min(m["bbox"][0] for m in run), min(m["bbox"][1] for m in run),
                        max(m["bbox"][2] for m in run), max(m["bbox"][3] for m in run))
                JOB.ink_lines[n_] = (run[0]["id"], run[-1]["id"], box_)
                JOB.listing["line:%d" % n_] = {"owner": "user", "text": H._run_reading(run, words)}
                for m in run:
                    entry_of[m["id"]] = "line:%d" % n_
                    if m["id"] <= ST.ERASE_RANGE["mark"]:
                        JOB.listing["mark:%d" % m["id"]] = {"owner": "user", "text": words.get(m["id"], "")}
                L.append("  line:%d  yours, one line of %d words, x %d..%d, y %d..%d, reads %r (%s)"
                         % (n_, sum(1 for m in run if words.get(m["id"])), box_[0], box_[2], box_[1], box_[3],
                            H._run_reading(run, words)[:160],
                            ", ".join(("mark:%d %r" % (m["id"], words.get(m["id"], ".")[:24]))
                                      if m["id"] <= ST.ERASE_RANGE["mark"] else repr(words.get(m["id"], ".")[:24])
                                      for m in run)))
            else:
                m = run[0]
                if m["id"] > ST.ERASE_RANGE["mark"]:
                    unlisted += 1
                    continue
                entry_of[m["id"]] = "mark:%d" % m["id"]
                JOB.listing["mark:%d" % m["id"]] = {"owner": "user" if m["owner"] == "yours" else "system",
                                                    "text": words.get(m["id"], "")}
                L.append("  mark:%d  %s%s, %d stroke%s, x %d..%d, y %d..%d%s"
                         % (m["id"], m["owner"], _made(m), m["count"], "" if m["count"] == 1 else "s",
                            m["bbox"][0], m["bbox"][2], m["bbox"][1], m["bbox"][3],
                            (", reads %r" % words[m["id"]][:60]) if words.get(m["id"]) else ""))
            shown += 1
        unlisted += len(ms) - i_
        if unlisted:
            L.append("  ... and %d more marks, not numbered here (point at them with at)" % unlisted)
    else:
        L += ["", "INK: none."]
    # WHAT IS NEW since this system last worked on the page: what woke it, and what the rulings must cover.
    try:
        new_p, _new_m = H._new_since_last_job(doc, page, paras, ms)
    except Exception as ex:
        H._warn("comparing the page with the last job's", ex)
        new_p = []
    JOB.new_paras = new_p
    new_refs = ["para:%d" % i for i in new_p if i <= ST.ERASE_RANGE["para"]]
    for i in JOB.new_mark_ids or []:        # by the ids the listing gave them
        r_ = entry_of.get(i)
        if r_ and r_ not in new_refs:
            new_refs.append(r_)
    if not JOB.page_history:
        # a page this system has never worked on: everything the user put on it is new
        new_refs = ["para:%d" % i for i in range(1, min(len(paras), ST.ERASE_RANGE["para"]) + 1)]
        for m in ms:
            r_ = entry_of.get(m["id"])
            if r_ and r_ not in new_refs and m.get("owner") == "yours":
                new_refs.append(r_)
    JOB.new_refs = list(new_refs)
    if new_refs:
        L.append(("NEW SINCE THIS SYSTEM LAST WORKED ON THIS PAGE" if JOB.page_history else
                  "NEW (this system has not worked on this page before)") +
                 " -- what woke you, each to be ruled, and answered or carried out (a turn in a conversation or a "
                 "role-play is answered in kind): " + ", ".join(new_refs))
    arr = H._arrows(doc, page)
    if arr:
        L.append("ARROWS, as the host's detector guesses them (your own eyes are better -- say where "
                 "with at): " + "; ".join(
            "mark:%s points at %s (tip x %d, y %d)"
            % (a["mark"], ("mark:%s" % a["points_at_mark"]) if a.get("points_at_mark") is not None
               else "empty paper", a["tip"][0], a["tip"][1]) for a in arr))
    pics = H._pictures(doc, page)
    JOB.pictures = pics
    for p in pics[:ST.ERASE_RANGE["picture"]]:
        JOB.listing["picture:%d" % p["n"]] = {"owner": "system" if p.get("made_by") == "this system" else "user",
                                              "text": p.get("title") or p.get("what") or ""}
    if pics:
        # WHAT EACH PICTURE IS, not just where: a picture this system made carries its spec, and redoing it is a
        # step with near="picture:N".
        L += ["", "PICTURES on the page (its id: picture:N; to change one of yours, a step with "
                  "replaces=\"picture:N\" -- redrawn in its place, the old one off):"]
        for p in pics[:ST.ERASE_RANGE["picture"]]:
            if p.get("made_by") == "this system" and p.get("what"):
                L.append("  picture:%d  a %s YOU made%s, x %d..%d, y %d..%d -- its spec: %s"
                         % (p["n"], p["what"], (" titled %r" % p["title"]) if p.get("title") else "",
                            p["box"][0], p["box"][2], p["box"][1], p["box"][3],
                            json.dumps(H._as_shown(p.get("spec")))[:400]))
            else:
                L.append("  picture:%d  %s picture, x %d..%d, y %d..%d"
                         % (p["n"], "the user's" if p.get("made_by") == "the user" else "a",
                            p["box"][0], p["box"][2], p["box"][1], p["box"][3]))
        if len(pics) > ST.ERASE_RANGE["picture"]:
            L.append("  ... and %d more pictures, not numbered here" % (len(pics) - ST.ERASE_RANGE["picture"]))
    # WHAT THE NOTEPAD SAYS WAS DONE HERE, AND IS GONE: the host knows exactly what of this system's is on
    # the page, so it says when nothing is.
    if pad and re.search(r"^## .*, THIS page\s*$", pad, re.M) \
            and not any(m.get("owner") in ("mine", "mixed") for m in ms) \
            and not any(p.get("made_by") == "this system" for p in pics):
        L += ["", "NOTHING THIS SYSTEM MADE IS ON THIS PAGE NOW. Whatever the notepad says an earlier "
                  "job wrote or drew here is gone, so every request on this page is unanswered."]
    info = H.t_page_info()
    col = H._text_col(doc, page)
    JOB.text_col = col
    # WHERE THE HOST'S READING TIME GOES, per phase, so a slow job points at one of them
    H.log("  read the page: text %.1fs, marks %.1fs, ink words %.1fs, arrows+pictures+info %.1fs"
        % (_t_paras, _t_marks, _t_words, time.time() - _t))
    low = info.get("lowest_content_y")
    L += ["", "FREE SPACE: %s. The text column is x %d..%d."
          % (("everything on the page ends at y=%d; below that is free" % low) if low
             else "the page is blank", col[0], col[1])]
    # THE LAST WORD BEFORE THE DECISION: the notebook's system prompt comes first, then the four calls.
    if JOB.sprompt:
        L += ["", "THIS NOTEBOOK HAS ITS OWN SYSTEM PROMPT (the end of your instructions). Apply it "
                  "first: it decides before anything on this page does."]
    L += ["", "NOW DECIDE, with exactly one call:",
          "  skip(note)                       nothing on the page asks you for anything, or this notebook's "
          "system prompt says to leave the page alone",
          "  answer(answers, lines, rulings)  the whole job is words",
          "  ask(lines)                       a request cannot be done without something only the user can "
          "tell you (ASKING)",
          "  plan(steps, rulings)             anything else, or several things"]
    return "\n".join(L)


def _mark_words(doc, page, marks):
    """{mark id: what OCR reads inside it} for the marks that read as words. Empty when the page
    has no ink of the user's, or the reader finds nothing / fails (never fatal)."""
    if not any(m.get("owner") == "yours" for m in marks):
        return {}
    try:
        from paperdaemon import reader
        out = os.path.join(H.QUEUE, "_host_ocr.png")
        R.render(doc, page, out, typed=False, hide=H._hide())
        ws = reader.read_picture(out, scale=2)
        fw, fh = H._frame()
        with Image.open(out) as im:
            sx, sy = fw / max(1, im.width), fh / max(1, im.height)
    except Exception as ex:
        H._warn("reading the ink", ex)
        return {}
    found = {}
    for w in ws:
        cx = (w["x"] + w["w"] / 2.0) * sx - fw / 2.0
        cy = (w["y"] + w["h"] / 2.0) * sy
        for m in marks:
            b = m["bbox"]
            if b[0] - 12 <= cx <= b[2] + 12 and b[1] - 12 <= cy <= b[3] + 12:
                found.setdefault(m["id"], []).append((w["x"], w["text"]))
                break
    out_words = dict((k, " ".join(t for _x, t in sorted(v))) for k, v in found.items())
    # A SECOND LOOK AT WHAT THE PAGE PASS MISSED: a word-sized mark with no reading gets its own crop at 3x,
    # which is how the OCR engine reads small lettering best. Bounded: the user's marks only, word-shaped, at
    # most eight of them.
    todo = [m for m in marks if m.get("owner") == "yours" and m["id"] not in out_words
            and 2 <= m["count"] <= 80 and (m["bbox"][2] - m["bbox"][0]) <= 700
            and (m["bbox"][3] - m["bbox"][1]) <= 220][:8]
    if todo:
        try:
            from paperdaemon import reader
            with Image.open(out) as im:
                page = im.convert("RGB")
                for m in todo:
                    b = m["bbox"]
                    box_ = (max(0, int((b[0] + fw / 2.0 - 30) / sx)), max(0, int((b[1] - 30) / sy)),
                            min(page.width, int((b[2] + fw / 2.0 + 30) / sx)),
                            min(page.height, int((b[3] + 30) / sy)))
                    if box_[2] - box_[0] < 8 or box_[3] - box_[1] < 8:
                        continue                        # a mark off the rendered page: nothing to read
                    crop = page.crop(box_)
                    ws2 = reader.read_picture(crop, scale=3) or reader.read_picture(crop, scale=4)   # small marks read better larger
                    if ws2:
                        out_words[m["id"]] = " ".join(w["text"] for w in sorted(ws2, key=lambda w: w["x"]))
        except Exception as ex:
            H._warn("reading a mark up close", ex)
    return out_words
