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
BOLD_W = 21                      # the lettering pen is 13; a bold word is drawn this heavy
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
    into the speech. Code ticks come off."""
    lead = line[:len(line) - len(line.lstrip())]
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
        T.text(d, " ".join(w for w, _b, _i in words), x, y, size=size, width=13)
        return
    for k, (w, b, i) in enumerate(words):
        wx = x + (T.measure(" ".join(v for v, _b, _i in words[:k]) + " ", size) if k else 0.0)
        T.text(d, w, wx, y, size=size, width=BOLD_W if b else 13, slant=ITALIC if i else 0.0)


def t_write_line(text, y=None, size=38, align="left", place=None):
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


def t_write_paragraph(lines, start_y=None, size=32, place=None):
    """Several lines of lettering, placed by the host.

    A LINE THAT IS TOO LONG IS WRAPPED, NOT REFUSED. Refusing sent the model round again to
    re-split its own prose -- a turn spent on typesetting, which is the host's job -- and when
    the text then did not fit the box vertically it was refused again. So: wrap every line to the
    box, and if the block is still too tall step the size down (32 -> 28 -> 24) before saying no.
    Only a single word wider than the column is genuinely unwritable.
    """
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
    floor = box["y1"] + int(size) * 0.5 if box else H._safe()[3]

    def fit(sz):
        out = []
        for ln in lines:
            if not ln.strip():
                out.append("")
            elif T.measure(ln, sz) > usable:
                mk = _LIST_MARK.match(ln)
                if mk:
                    # a list item: the rest of it hangs under its first word (spaces, since the
                    # drawing offsets a line by its leading whitespace; never less than the marker)
                    hang = " " * int(math.ceil(T.measure(mk.group(1), sz) / max(1e-6, T.measure(" ", sz))))
                    body = T.wrap(ln[mk.end():], sz, usable - T.measure(hang, sz)) or [ln[mk.end():]]
                    out += [mk.group(1) + body[0]] + [hang + b for b in body[1:]]
                else:
                    out += T.wrap(ln, sz, usable) or [ln]
            else:
                out.append(ln)
        for ln in out:
            if ln.strip() and T.measure(ln, sz) > usable:
                return None, "the word %r is wider than the column at size %d" % (ln[:30], sz)
        return out, None

    chosen, why, rest = None, None, []
    for sz in sorted({int(size), 28}, reverse=True):
        if sz > int(size):
            continue
        wrapped, why = fit(sz)
        if wrapped is None:
            continue
        top = float(start_y) if start_y is not None else (box["y0"] + sz * 1.15 if box else None)
        if top is None:
            return dict({"error": "give start_y or place (a box from your plan)."}, **H._did())
        bad = H._bad_y(top, sz)
        if bad:
            return dict({"error": bad}, **H._did())
        end = top + sz * 1.7 * len(wrapped)
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
        sz = int(size)
        wrapped, why2 = fit(sz)
        if wrapped is None:
            return dict({"error": "%s. NOTHING written." % why2}, **H._did())
        top = float(start_y) if start_y is not None else (box["y0"] + sz * 1.15 if box else H._safe()[1] + sz)
        bad = H._bad_y(top, sz)
        if bad:
            return dict({"error": bad}, **H._did())
        chosen = (sz, top, wrapped)
        H.log("  %d line(s) run %d px past the first screen; the page extends below"
            % (len(wrapped), int(top + sz * 1.7 * len(wrapped) - floor)))
    sz, y, wrapped = chosen
    H._mark()
    x = (box["x0"] if box else col[0]) + pad
    k = 0
    for ln in wrapped:
        if ln.strip():
            n = len(ln.split())                  # wrapping splits at spaces only, so words line up
            H._letter(JOB.draw, flat[k:k + n], x + T.measure(ln[:len(ln) - len(ln.lstrip())], sz), y, sz)
            k += n
        y += sz * 1.7
    JOB.ops.append("paragraph of %d line(s) from y=%d" % (len(wrapped), int(chosen[1])))
    # the notepad records WHAT was written, so a follow-up ("which of those is the shortest?") can see it
    JOB.written.extend(ln for ln in wrapped if ln.strip())
    out = dict({"ok": True, "lines": len(wrapped), "size": sz, "next_free_y": round(y)}, **H._did())
    if sz != int(size):
        out["note"] = "written at size %d so it fits the box" % sz
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
  {"lines": "array", "size": {"type": "number", "optional": True},
   "place": {"type": "string", "optional": True}}, t_write_paragraph),
 ("write_line", "ONE line of lettering when a single line is the whole step (a title, a label, a "
  "date). align left|center|right within the step's box.",
  {"text": "string", "size": {"type": "number", "optional": True},
   "align": {"type": "string", "optional": True}, "place": {"type": "string", "optional": True},
   "y": {"type": "number", "optional": True}}, t_write_line),
]
