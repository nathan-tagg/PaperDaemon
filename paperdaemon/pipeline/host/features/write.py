"""Writing words on the page: paragraphs and lines in the typed column or a box of their own."""
import math
import re
from paperdaemon.pipeline.draw import lettering as T
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline import host as H

# LETTERING IN THE TYPED COLUMN STARTS WHERE THE TYPED GLYPHS START: the app insets its glyphs 4 scene units
# from the text block's edge (typed_layout). PAD still applies inside a box that is anchored to ink, where the
# margin keeps the words off a drawing.
TEXT_INSET = 4.0
# MARKDOWN, as the model writes it, drawn the way a page can show it. "**Ad Overload**
# - Users are frustrated ..." would otherwise go onto the page asterisks and all. A bold
# word is a heavier pen, a heading a bold line, an italic one leans; code ticks and heading hashes come off, and
# a "* " bullet is a "- " one. The words themselves are never changed, so wrapping is unchanged.
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_MARK = re.compile(r"`([^`\n]*)`|(?<![\w*])\*(?=\S)([^*\n]*?\S)\*(?![\w*])"
                      r"|(?<![\w_])_(?=\S)([^_\n]*?\S)_(?![\w_])")
_MD_HEAD = re.compile(r"^\s{0,3}#{1,6}\s+")
_MD_ITEM = re.compile(r"^(\s*)[*+]\s+")
_MD_TASK = re.compile(r"^(\s*)(?:[-*+]\s+)?\[([ xX])\]\s+")      # "- [ ] item" is a box to tick
# what starts a LIST ITEM: its wrapped lines hang under the item's first word, not under the marker
# ("Arrange utilities ... (electricity, water, / internet)" would otherwise come back to the margin)
_LIST_MARK = re.compile(r"^(\s*(?:[-•·]|\d{1,2}[.)]|[☐☑☒□])\s+)")
PEN_W = 13                       # the lettering pen's width field (on the tablet: PEN_W / 4 page units of ink)
BOLD_W = 21                      # a bold word is drawn this heavy
ITALIC = 0.22                    # how far an italic glyph leans, in its own height
_DANGLING = set("the a an of to and but or nor in on at for with from by my your his her their our "
                "its that this these those is are was were as than into onto".split())


def _pad_for(box, col):
    """The inset for lettering: the typed glyph inset when the box IS the typed column (or there is
    no box), PAD when it is a box of its own beside something."""
    if box is None:
        return TEXT_INSET
    if abs(box["x0"] - col[0]) < 2.0 and abs(box["x1"] - col[1]) < 2.0:
        return TEXT_INSET
    return H.PAD


def _cur_place():
    """The box of the step the host is on, so a tool called for that step needs no place id."""
    cur = ST.current(JOB.steps or [])
    if cur is not None and cur.get("place"):
        return cur["place"]
    boxes = (JOB.plan or {}).get("places") or {}
    return next(iter(boxes)) if len(boxes) == 1 else None


def _bad_y(y, size):
    """The page has a top (the toolbar covers it) and no bottom: a page scrolls, and the layout runs long content past
    the first screen on purpose, so only a line above the safe top is refused."""
    y = float(y)
    if y < H._safe()[1] + size:
        return ("y=%d is too close to the top (first usable baseline is about "
                "%d). NOTHING written." % (y, H._safe()[1] + size))
    return None


def _place_box(place):
    """The plan's box for `place`, or an error string. Text tools take a place the way chart and
    image do, so "write HELLO inside the box" is arithmetic here, not a guess about x."""
    plan = JOB.plan or {}
    boxes = plan.get("places") or {}
    if not boxes:
        return None, "call plan() first and give the text a place of its own."
    b = boxes.get(str(place))
    if b is None:
        return None, ("no place called %r in your plan. Places: %s."
                      % (place, ", ".join(sorted(boxes)) or "(none)"))
    return b, None


def _md_words(line):
    """One line of the model's text -> (the line as it is drawn, [(word, bold, italic)]).

    ITALICS STAY ITALICS, drawn leaning: a role-play turn writes its actions in them, and with the
    asterisks simply taken off "*Steps forward, hand on hilt* I seek only passage" runs the action
    into the speech. Code ticks come off. A typewriter's dash between words, " -- ", is drawn as the dash it
    stands for ("the sweet spot -- cool enough" read as a typed page, not a written one)."""
    lead = line[:len(line) - len(line.lstrip())]
    line = line.replace(" -- ", " — ")
    line = _MD_TASK.sub(lambda m: m.group(1) + ("☐ " if m.group(2) == " " else "☑ "), line)
    line = _MD_ITEM.sub(r"\1- ", line)
    head = bool(_MD_HEAD.match(line))
    line = _MD_HEAD.sub("", line)

    def spans(seg, bold):
        out, at = [], 0
        for m in _MD_MARK.finditer(seg):
            out += [(w, bold, False) for w in seg[at:m.start()].split()]
            inner = next(g for g in m.groups() if g is not None)
            out += [(w, bold, m.group(1) is None) for w in inner.split()]      # group 1 is `code`
            at = m.end()
        return out + [(w, bold, False) for w in seg[at:].split()]
    words, at = [], 0
    for m in _MD_BOLD.finditer(line):
        words += spans(line[at:m.start()], head)
        words += spans(m.group(1) or m.group(2), True)
        at = m.end()
    words += spans(line[at:], head)
    return (lead + " ".join(w for w, _b, _i in words)) if words else "", words


def _mend_breaks(lines):
    """Lines the model broke in mid-sentence, joined back up -- prose only. A line ending on "the", "of", "and"
    never ends a thought, and a long line with no closing punctuation followed by one in lower case is one
    sentence. A line shorter than 40 characters -- a poem's, a list's, a title -- is left exactly as written."""
    out = []
    for ln in lines:
        s = str(ln)
        if out:
            prev = out[-1].rstrip()
            if len(prev) >= 40 and s.strip() and not _LIST_MARK.match(s) and not _LIST_MARK.match(prev):
                last = re.findall(r"[A-Za-z']+$", prev)
                dangling = bool(last) and last[0].lower() in _DANGLING
                runs_on = s.lstrip()[:1].islower() and not re.search(r"[.!?:;,\"'”)\]*_]$", prev)
                if dangling or runs_on:
                    out[-1] = prev + " " + s.strip()
                    continue
        out.append(s)
    return out


def _letter(d, words, x, y, size):
    """[(word, bold, italic)] as one line of lettering from x; a plain line is one run."""
    if not any(b or i for _w, b, i in words):
        T.text(d, " ".join(w for w, _b, _i in words), x, y, size=size, width=PEN_W)
        return
    for k, (w, b, i) in enumerate(words):
        wx = x + (T.measure(" ".join(v for v, _b, _i in words[:k]) + " ", size) if k else 0.0)
        T.text(d, w, wx, y, size=size, width=BOLD_W if b else PEN_W, slant=ITALIC if i else 0.0)


def t_write_line(text, y=None, size=30, align="left", place=None):
    text, words = H._md_words(str(text))
    box = None
    if place is None and y is None:
        place = H._cur_place()               # the step's own box, when the host is walking steps
    if place is not None:
        box, err = H._place_box(place)
        if err:
            return dict({"error": err}, **H._did())
        if y is None:
            y = box["cy"] + int(size) * 0.35        # one line, sitting on the box's center
    if y is None:
        return dict({"error": "give y (the baseline) or place (a box from your plan)."}, **H._did())
    bad = H._bad_y(y, int(size))
    if bad:
        return dict({"error": bad}, **H._did())
    w = T.measure(text, int(size))
    col = H._text_col()
    pad = H._pad_for(box, col)
    usable = (box["x1"] - box["x0"] if box else col[1] - col[0]) - 2 * pad
    if w > usable:
        fit = int(int(size) * usable / max(w, 1.0))
        return dict({"error": "too wide (%d px, max %d%s). NOTHING was written -- "
                              "shorten it or use size %d."
                              % (round(w), round(usable), (" inside place %r" % place) if box else "",
                                 max(12, fit))}, **H._did())
    # Refuse a line this job has already written: the model can batch two writes into one turn without seeing
    # the first result, so the tool itself must refuse the second.
    dup = "line %r" % text[:36]
    for op in JOB.ops:
        if op.startswith(dup):
            return dict({"error": "you have already written that line this job "
                                  "(%s). NOTHING was written again. If it is in "
                                  "the wrong place, clear() and start over."
                                  % op}, **H._did())
    if box:
        x = (box["cx"] - w / 2.0 if align.startswith("cent")
             else box["x1"] - pad - w if align == "right" else box["x0"] + pad)
        if not (box["y0"] <= float(y) <= box["y1"] + 2):
            return dict({"error": "y=%d is outside place %r (y %d..%d). NOTHING written -- leave y "
                                  "out to sit on its center, or give one inside it."
                                  % (int(y), place, int(box["y0"]), int(box["y1"]))}, **H._did())
    else:
        x = ((col[0] + col[1]) / 2.0 - w / 2.0 if align.startswith("cent")
             else col[1] - pad - w if align == "right" else col[0] + pad)
    H._mark()
    H._letter(JOB.draw, words, x + T.measure(text[:len(text) - len(text.lstrip())], int(size)),
            float(y), int(size))
    JOB.ops.append("line %r at y=%d" % (text[:36], int(y)))
    JOB.written.append(text)          # the notepad records WHAT was written
    return dict({"ok": True, "placed_x": round(x), "baseline_y": round(float(y))}, **H._did())


# THE REPLY'S SIZE IS THE TYPED TEXT'S: lettering at 26 stands as tall as the typed body text, and its lines, 1.7 sizes
# apart, run at the typed lines' own pitch (45), so the user's lines and the reply's read as one column
def _body():
    """(size, line pitch, room between paragraphs, a line's top to its baseline) the replies are written at: THE TYPED
    TEXT'S OWN (page.typed: body_measure) -- the lettering's lowercase INK as tall as a plain typed paragraph's, its
    lines 45 apart and 25 more between paragraphs, its first baseline where a typed paragraph's would be, so the room
    between the user's typed text and the reply is a typed paragraph's, always (the handwritten replies match the typed
    paragraphs' size and spacing, exactly).
    BY THE INK, NOT THE LINE: a typed letter's ink stops at its outline, a lettered one's runs half the pen past its
    centerline on each side. Set by the centerline (x-height / T.XH, 27.7), the reply's lowercase ink stood 2 units
    taller and its capitals nearly half again the typed ones -- larger, and set by the ink (22.3), it is the same height.
    The pen's line on the tablet is its width field / 4 page units (render.WSCALE_DEFAULT, measured on the tablet)."""
    from paperdaemon.pipeline.page import render as R
    from paperdaemon.pipeline.page import typed as TY
    xh, lead, gap, base = TY.body_measure()
    return (xh - PEN_W * R.WSCALE_DEFAULT) / T.XH, lead, gap, base


def _under_answered(height, x0, x1):
    """The top of a reply's first line right under what the current step answers -- the lowest typed paragraph or
    handwritten line it names that stays on the page -- when the free paper there, down to the next thing on the
    page or another place of this job, holds `height`; else None.

    A REPLY GOES UNDER WHAT IT ANSWERS. Stacked below everything, an answer went under a note to someone at the
    foot of the page, a screen and a half below its own question, with white paper between them."""
    from paperdaemon.pipeline import page as ER
    from paperdaemon.pipeline.page import typed as TY
    cur = ST.current(JOB.steps or [])
    if not cur or not JOB.doc:
        return None
    rf = (JOB.plan or {}).get("reflow") or {}
    others = [tuple(o) for o in (rf.get("obstacles") or [])]
    ends, kept = [], None
    for a in cur.get("answers") or []:
        kind, _, n = str(a).partition(":")
        try:
            n = int(n)
        except ValueError:
            continue
        if kind == "para":
            if kept is None:
                _tb, ps = TY.paragraphs(JOB.doc, JOB.page)
                ps = ps or []
                gone = (ER.staged_paragraphs([p.get("text") or "" for p in ps], JOB.hide_typed)
                        if JOB.hide_typed else set())
                kept = [(i, p) for i, p in enumerate(ps) if str(p.get("text", "")).strip()]
                moved = H._reflow()
            if 1 <= n <= len(kept) and kept[n - 1][0] not in gone:
                i, p = kept[n - 1]
                ends.append((H._line_ink(p, max(0, len(p["lines"]) - 1))[1] + moved.get(i, 0.0), 25))
        elif kind == "line" and (JOB.ink_lines or {}).get(n):
            b = JOB.ink_lines[n][2]
            if any(o[0] < b[2] and o[2] > b[0] and o[1] < b[3] and o[3] > b[1] for o in others):   # still there
                ends.append((float(b[3]), 40))
    if not ends:
        return None
    end, gap = max(ends)
    top = end + gap
    others += [(q["x0"], q["y0"], q["x1"], q["y1"]) for k, q in ((JOB.plan or {}).get("places") or {}).items()
               if k != cur.get("place")]
    below = [o[1] for o in others if o[1] >= top - 1 and o[0] < x1 and o[2] > x0]
    return top if (min(below) - 40 if below else float("inf")) - top >= height else None


def t_write_paragraph(lines, start_y=None, size=None, place=None):
    """Several lines of lettering, placed by the host, at the typed text's size and spacing (_body): each string of
    `lines` a paragraph, as each line typed on the tablet with Enter is.

    A LINE THAT IS TOO LONG IS WRAPPED, NOT REFUSED. Refusing sent the model round again to
    re-split its own prose -- a turn spent on typesetting, which is the host's job -- and when
    the text then did not fit the box vertically it was refused again. So: wrap every line to the
    box, and if the block is still too tall it goes on below at the same size (the page extends).
    THE SIZE NEVER STEPS DOWN to fit: an answer near the foot of the page written smaller than the
    rest read as wrong. Only a single word wider than the column is genuinely unwritable.
    """
    body, lead, gap, base = _body()
    size = float(size) if size else body

    def pitch(sz):                                        # lines and paragraphs apart at size sz
        return lead * sz / body, gap * sz / body

    def tall(rows, sz):                                   # baseline of the first row to that of the row after the last
        p, g = pitch(sz)
        return p * len(rows) + g * sum(1 for i, (_r, new) in enumerate(rows) if new and i)
    if isinstance(lines, str):
        lines = [lines]
    md = [H._md_words(str(l)) for l in H._mend_breaks(lines or [])]
    lines = [ln for ln, _w in md]
    flat = [tok for _ln, ws in md for tok in ws]          # every word in order, with its weight
    if not [l for l in lines if l.strip()]:
        return dict({"error": "lines is empty."}, **H._did())
    box = None
    if place is None and start_y is None:
        place = H._cur_place()
    if place is not None:
        box, err = H._place_box(place)
        if err:
            return dict({"error": err}, **H._did())
    col = H._text_col()
    pad = H._pad_for(box, col)
    usable = (box["x1"] - box["x0"] if box else col[1] - col[0]) - 2 * pad
    floor = box["y1"] + size * 0.5 if box else H._safe()[3]

    def fit(sz):
        """-> ([(row, starts a paragraph)], None), or (None, why)."""
        out = []
        for ln in lines:
            if not ln.strip():
                rows = [""]
            elif T.measure(ln, sz) > usable:
                mk = _LIST_MARK.match(ln)
                if mk:
                    # a list item: the rest of it hangs under its first word (spaces, since the
                    # drawing offsets a line by its leading whitespace; never less than the marker)
                    hang = " " * int(math.ceil(T.measure(mk.group(1), sz) / max(1e-6, T.measure(" ", sz))))
                    rest_ = T.wrap(ln[mk.end():], sz, usable - T.measure(hang, sz)) or [ln[mk.end():]]
                    rows = [mk.group(1) + rest_[0]] + [hang + b for b in rest_[1:]]
                else:
                    rows = T.wrap(ln, sz, usable) or [ln]
            else:
                rows = [ln]
            out += [(r, j == 0) for j, r in enumerate(rows)]
        for ln, _new in out:
            if ln.strip() and T.measure(ln, sz) > usable:
                return None, "the word %r is wider than the column at size %d" % (ln[:30], sz)
        return out, None

    chosen, why, rest = None, None, []
    moved = None                                          # the top the reply moved up to, under what it answers
    for sz in (size,):
        wrapped, why = fit(sz)
        if wrapped is None:
            continue
        # the first baseline as far below the box's top as a typed line's below its own (the box starts where the next
        # typed paragraph would: intake's gap 25 under typed text)
        top = float(start_y) if start_y is not None else (box["y0"] + base * sz / body if box else None)
        if start_y is None and box is not None:
            under = _under_answered(base * sz / body + tall(wrapped, sz), box["x0"], box["x1"])
            if under is not None and under + base * sz / body < top - 1:
                H.log("  written under what it answers (y %d), not below everything else (y %d)"
                      % (int(under), int(box["y0"])))
                top = under + base * sz / body
                moved = under
        if top is None:
            return dict({"error": "give start_y or place (a box from your plan)."}, **H._did())
        bad = H._bad_y(top, sz)
        if bad:
            return dict({"error": bad}, **H._did())
        end = top + tall(wrapped, sz)
        if end <= floor:
            chosen = (sz, top, wrapped)
            break
        why = ("%d lines from y=%d would end at %d, past the bottom of %s (%d)"
               % (len(wrapped), int(top), int(end), ("place %r" % place) if box else "the safe area",
                  int(floor)))
    if chosen is None:
        # THE REPLY IS NOT SHORTENED TO FIT. A reply is only shortened when there is a space
        # requirement, and a longer one extends the bottom of the page rather than starting a new
        # page. A reMarkable page scrolls: _safe()[3] is where the first
        # screen's safe area ends, not where the page does. So the words go on at the asked size,
        # straight down, and the page extends beneath them.
        sz = size
        moved = None                                      # (written where the box is, below everything)
        wrapped, why2 = fit(sz)
        if wrapped is None:
            return dict({"error": "%s. NOTHING written." % why2}, **H._did())
        top = float(start_y) if start_y is not None else (box["y0"] + base * sz / body if box else H._safe()[1] + sz)
        bad = H._bad_y(top, sz)
        if bad:
            return dict({"error": bad}, **H._did())
        chosen = (sz, top, wrapped)
        H.log("  %d line(s) run %d px past the first screen; the page extends below"
            % (len(wrapped), int(top + tall(wrapped, sz) - floor)))
    sz, y, wrapped = chosen
    H._mark()
    x = (box["x0"] if box else col[0]) + pad
    k = 0
    p_, g_ = pitch(sz)
    for i, (ln, new) in enumerate(wrapped):
        if new and i:
            y += g_                              # a new paragraph: the room the tablet leaves after one
        if ln.strip():
            n = len(ln.split())                  # wrapping splits at spaces only, so words line up
            H._letter(JOB.draw, flat[k:k + n], x + T.measure(ln[:len(ln) - len(ln.lstrip())], sz), y, sz)
            k += n
        y += p_
    if moved is not None:
        # THE PLACE IS WHERE THE WORDS WENT: the plan's box moves with them, so what checks the plan afterward looks
        # where they are. Left where it was planned, a reply written under its question was reported "nothing landed
        # in the box", and the job was marked FAILED, with a retry box, its answer on the page
        box["y0"], box["y1"] = float(moved), max(float(moved) + 1.0, float(y))
    JOB.ops.append("paragraph of %d line(s) from y=%d" % (len(wrapped), int(chosen[1])))
    # the notepad records WHAT was written, so a follow-up ("which of those is the shortest?") can see it
    JOB.written.extend(ln for ln, _new in wrapped if ln.strip())
    out = dict({"ok": True, "lines": len(wrapped), "size": round(sz, 1), "next_free_y": round(y)}, **H._did())
    if y > H._safe()[3]:
        JOB.extends_to = max(JOB.extends_to or 0, int(y))
        out["note"] = ("the last lines sit below the first screen (down to y=%d); the page scrolls"
                       % int(y))
    return out


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("write_paragraph", "The words for a write step: lines in reading order, at the length the step "
  "deserves. The host puts them in the step's box and wraps any line that is too long; words that "
  "run past the first screen extend the page below (it scrolls).",
  {"lines": "array", "place": {"type": "string", "optional": True}}, t_write_paragraph),
 ("write_line", "ONE line of lettering when a single line is the whole step (a title, a label, a "
  "date). align left|center|right within the step's box.",
  {"text": "string", "size": {"type": "number", "optional": True},
   "align": {"type": "string", "optional": True}, "place": {"type": "string", "optional": True},
   "y": {"type": "number", "optional": True}}, t_write_line),
]


def _stage_checkbox(targets, checked=False):
    """A CHECKBOX STEP: the user's own typed paragraphs (`targets`, their ids) made the tablet's checkboxes, ticked
    when `checked`, at commit (typed.restyle). Only typed text has the tablet's checkboxes: an id that is ink, or not
    on the page, is named in the note and left as it is. A typed list asked to be a checklist was drawn again beside
    itself; now its own paragraphs take the boxes, which tick on the tablet. -> (ok, note)."""
    from rmscene.scene_items import ParagraphStyle
    style = ParagraphStyle.CHECKBOX_CHECKED if checked else ParagraphStyle.CHECKBOX
    done, missing = [], []
    for t in targets or []:
        item = (JOB.listing or {}).get(t) or {}
        text = str(item.get("text") or "").strip()
        if not t.startswith("para:") or not text:
            missing.append(t)
            continue
        JOB.restyle_typed.append((text, int(style)))
        done.append(t)
    if not done:
        return False, "no typed paragraph to make a checkbox (%s)" % ", ".join(missing or ["none named"])
    note = "%d typed paragraph(s) made checkboxes%s" % (len(done), ", ticked" if checked else "")
    if missing:
        note += "; not typed text, left as it is: %s" % ", ".join(missing)
    return True, note
