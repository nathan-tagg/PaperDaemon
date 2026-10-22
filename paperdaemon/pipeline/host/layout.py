r"""Turn a plan in words into boxes on the page, or refuse and say why.

A model is good at structure and poor at spatial relations, and it does not notice when they are wrong. So the
model says WHAT goes on the page and roughly how big, in words, and never says where: the arithmetic happens
here, and two things cannot overlap because the solver lays them out in sequence.

    solve([{"id": "answer", "kind": "text", "size": "medium"},
           {"id": "chart",  "kind": "chart", "size": "large"}], first_free_y=620)

Composition is RELATIVE: "where" is always said in terms of what is already there. A place can be anchored to
any MARK on the page (`near="mark:4"` with a `side`), to an arrow's tip, to a corner, or paired left/right with
another place, and the arithmetic of "beside", "under", "inside" is done here.

A plan that cannot fit comes back with the numbers -- how much room there is, how much was asked for -- rather
than being squeezed until things collide.
"""
import re

# The device's own UI covers the edges of a page. The safe area is absolute from the sides and top, but content
# can stretch below. Defined once, in rm_page.SAFE_AREA.
try:
    from paperdaemon.pipeline.page import SAFE_AREA as SAFE
except Exception:                      # rm_plan alone, without the rmscene stack: same numbers
    SAFE = (-800.0, 160.0, 800.0, 2150.0)

KINDS = ("text", "drawing", "chart", "image", "calendar", "coloring")
# Relative appetite for vertical space. Not pixels: the band is shared out in these proportions,
# so a plan behaves the same on a blank page and on one with two thirds already used.
SIZES = {"small": 1.0, "medium": 2.0, "large": 3.0, "full": 5.0}
# An ANCHORED place (beside a mark, in a corner) has no band to share: its size is a multiple of
# the kind's minimum, capped by the room actually there.
ANCHORED = {"small": 1.0, "medium": 1.8, "large": 2.8, "full": 4.0}
# Below these a thing is not worth putting on the page at all. A chart needs the most: axes, tick labels and a
# legend have to be legible once drawn. A calendar (a month or a week) is built for the portrait safe area --
# seven day cells with the forecast in each -- so it needs most of a blank page. A coloring page is a PAGE:
# portrait, most of the sheet.
MIN_H = {"text": 90.0, "drawing": 240.0, "chart": 320.0, "image": 240.0, "calendar": 1500.0,
         "coloring": 1400.0}
# Width as a multiple of height, for things that are not text. Text always takes the full width.
ASPECT = {"drawing": 1.0, "chart": 1.45, "image": 1.0, "calendar": 1450.0 / 1960.0,
          "coloring": (SAFE[2] - SAFE[0]) / (SAFE[3] - SAFE[1])}   # the safe area's own shape
GAP = 40.0                     # breathing room between two placed things
# A PICTURE STACKED ON THE PAGE HAS ITS OWN SIZE, not a share of the room left: the safe area's full width (half of it
# when the plan asks for it "small"), as tall as its source's shape (ASPECT["image"]: a square source), centered,
# below the reply's words. It is never shrunk to fit the page's height: the page extends below.
IMAGE_SMALL = 0.5


def _own_height(p, band_w):
    """A stacked place's own height when it has one (a picture alone in its row), else None."""
    if p["kind"] != "image" or p["near"] != "stack":
        return None
    w = band_w * (IMAGE_SMALL if p["size"] == "small" else 1.0)
    return w / ASPECT["image"]

INSET = 30.0                   # a corner place stays this far off the safe edge
# LETTERING LIVES IN THE TYPED COLUMN. The app's text block is 1152 wide, centered (pos_x -576); a reply
# written to the safe area's full width would sit out of line with the user's own typed lines. So a text place
# is clipped to this column; the page's own block overrides it when it has one (solve(text_col=...)). Drawings
# and charts keep the safe width.
TEXT_COL = (-576.0, 576.0)
# where a place may ask to go:
#   "stack"      below everything already on the page, in order (the default and the norm)
#   "arrow"      at the tip of the arrow that points at empty paper
#   "left"/"right"  a left and the right that follows it share ONE ROW, side by side ("a sun on the left and a
#                moon on the right")
#   "mark:N"     relative to mark N from show_marks(), on `side`: below/above/left/right/on
#   a corner     "top-left", "top-right", "bottom-left", "bottom-right", or "center"
NEARS = ("stack", "arrow", "left", "right")
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right", "center")
SIDES = ("below", "above", "left", "right", "on")


class PlanError(ValueError):
    """A plan that cannot be laid out. The message is written for the model to act on."""


def _mark_ref(near):
    m = re.fullmatch(r"\s*mark\s*[-:#=]?\s*(\d+)\s*", str(near or ""), re.I)
    return int(m.group(1)) if m else None


def _check(places):
    if not places:
        raise PlanError("a plan needs at least one place. What goes on the page?")
    seen = set()
    for i, p in enumerate(places):
        if not isinstance(p, dict):
            raise PlanError("place %d is not an object. Each place needs id, kind and size." % i)
        pid = str(p.get("id") or "").strip()
        if not pid:
            raise PlanError("place %d has no id. Give each one a short name like 'answer'." % i)
        if pid in seen:
            raise PlanError("two places are both called %r. Give them different ids." % pid)
        seen.add(pid)
        if p.get("kind") not in KINDS:
            raise PlanError("place %r has kind %r. Use one of: %s."
                            % (pid, p.get("kind"), ", ".join(KINDS)))
        if p.get("size") in (None, ""):
            p["size"] = "medium"          # left out three times in a row on one job; medium is the sane default
        if p.get("size") not in SIZES:
            raise PlanError("place %r has size %r. Use one of: %s."
                            % (pid, p.get("size"), ", ".join(SIZES)))
        near = str(p.get("near") or "stack").strip().lower().replace("_", "-").replace(" ", "-")
        if near in ("center", "middle"):
            near = "center"
        p["near"] = near
        if near not in NEARS and near not in CORNERS and _mark_ref(near) is None:
            raise PlanError("place %r has near %r. Use one of: %s, a corner (%s), or 'mark:N' "
                            "for a mark from show_marks()."
                            % (pid, near, ", ".join(NEARS), ", ".join(CORNERS)))
        side = str(p.get("side") or "below").strip().lower()
        side = {"under": "below", "beneath": "below", "over": "above", "inside": "on",
                "in": "on", "within": "on", "beside": "right", "next-to": "right"}.get(side, side)
        if side not in SIDES:
            raise PlanError("place %r has side %r. Use one of: %s." % (pid, side, ", ".join(SIDES)))
        p["side"] = side


def _overlap(a, b):
    return not (a["x1"] <= b["x0"] or b["x1"] <= a["x0"]
                or a["y1"] <= b["y0"] or b["y1"] <= a["y0"])


def _dict_box(b):
    if isinstance(b, dict):
        return b
    return {"x0": float(b[0]), "y0": float(b[1]), "x1": float(b[2]), "y1": float(b[3])}


def _box(pid, kind, cx, y0, h, band_w, safe, text_col=TEXT_COL):
    """One box, centered horizontally unless it is text, which spans the width.

    A picture never gets taller than its aspect allows; whitespace below is the honest outcome.
    """
    if kind in ("text", "chart", "calendar"):
        # CHARTS AND CALENDARS TAKE THE FULL SAFE WIDTH: height follows from width, so one planned into a short
        # band is still full width, only shorter. In a paired left/right row `band_w` is already the row's half.
        if kind == "text":
            # the band this text was given, clipped to the typed column (a half-row place keeps
            # its half; a full-width one becomes exactly the column)
            x0, x1 = max(text_col[0], cx - band_w / 2.0), min(text_col[1], cx + band_w / 2.0)
            if x1 - x0 < 200:
                x0, x1 = text_col
        else:
            x0, x1 = cx - band_w / 2.0, cx + band_w / 2.0
        if kind != "text":
            h = min(h, band_w / ASPECT[kind])
    else:
        h = min(h, band_w / ASPECT[kind])
        w = min(band_w, h * ASPECT[kind])
        x0, x1 = cx - w / 2.0, cx + w / 2.0
    # EVERY kind slides back inside the safe area (a full-width box centered on an arrow tip would otherwise
    # cross the edge).
    if x0 < safe[0]:
        x0, x1 = safe[0], safe[0] + (x1 - x0)
    if x1 > safe[2]:
        x0, x1 = safe[2] - (x1 - x0), safe[2]
    return _finish(pid, kind, x0, y0, x1, y0 + h)


def _finish(pid, kind, x0, y0, x1, y1):
    return {"id": pid, "kind": kind,
            "x0": round(x0, 1), "y0": round(y0, 1), "x1": round(x1, 1), "y1": round(y1, 1),
            "cx": round((x0 + x1) / 2.0, 1), "cy": round((y0 + y1) / 2.0, 1),
            "w": round(x1 - x0, 1), "h": round(y1 - y0, 1)}


def _clamp(x0, y0, x1, y1, safe):
    """Slide a box back inside the safe area without changing its size."""
    if x0 < safe[0]:
        x0, x1 = safe[0], safe[0] + (x1 - x0)
    if x1 > safe[2]:
        x0, x1 = safe[2] - (x1 - x0), safe[2]
    if y0 < safe[1]:
        y0, y1 = safe[1], safe[1] + (y1 - y0)
    if y1 > safe[3]:
        y0, y1 = safe[3] - (y1 - y0), safe[3]
    return x0, y0, x1, y1


def _anchored(p, anchor, side, safe, obstacles, what):
    """A box of the place's appetite on `side` of `anchor`, shrunk until it clears the obstacles.

    `anchor` is a bbox dict; `what` names it for the refusal. side="on" is the anchor itself, inset
    a little -- "write HELLO inside this box", "color in the circle" -- and is never shrunk.
    """
    kind, pid = p["kind"], p["id"]
    if side == "on":
        w, h = anchor["x1"] - anchor["x0"], anchor["y1"] - anchor["y0"]
        d = min(w, h) * 0.08
        return _finish(pid, kind, anchor["x0"] + d, anchor["y0"] + d, anchor["x1"] - d, anchor["y1"] - d)
    want = MIN_H[kind] * ANCHORED[p["size"]]
    acx = (anchor["x0"] + anchor["x1"]) / 2.0
    acy = (anchor["y0"] + anchor["y1"]) / 2.0
    tried = None
    h = want
    while h >= MIN_H[kind] - 1e-6:
        if kind == "text":
            if side == "right":
                x0, x1 = anchor["x1"] + GAP, safe[2]
            elif side == "left":
                x0, x1 = safe[0], anchor["x0"] - GAP
            else:
                x0, x1 = safe[0], safe[2]
            w = x1 - x0
        else:
            w = min(h * ASPECT[kind], safe[2] - safe[0])
            if side == "right":
                x0 = anchor["x1"] + GAP
            elif side == "left":
                x0 = anchor["x0"] - GAP - w
            else:
                x0 = acx - w / 2.0
            x1 = x0 + w
        if side == "below":
            y0 = anchor["y1"] + GAP
        elif side == "above":
            y0 = anchor["y0"] - GAP - h
        else:
            y0 = acy - h / 2.0
        y1 = y0 + h
        if w >= 60 and x0 >= safe[0] - 1e-6 and x1 <= safe[2] + 1e-6:
            x0, y0, x1, y1 = _clamp(x0, y0, x1, y1, safe)
            box = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
            # the anchor itself is an obstacle too: a box "above" a mark near the top of the page must not be
            # clamped down onto it
            hit = [o for o in obstacles + [anchor] if _overlap(box, o)]
            if not hit:
                return _finish(pid, kind, x0, y0, x1, y1)
            tried = hit
        h *= 0.85
    room = {"right": safe[2] - anchor["x1"] - GAP, "left": anchor["x0"] - safe[0] - GAP,
            "below": safe[3] - anchor["y1"] - GAP, "above": anchor["y0"] - safe[1] - GAP}[side]
    raise PlanError(
        "there is no room %s %s for %r: %d px of clear page that way and a %s %s needs at least "
        "%d px%s. Choose another side, ask for it smaller, or erase something first."
        % (side if side in ("below", "above") else ("to the %s of" % side), what, pid,
           max(0, int(room)), p["size"], kind, int(MIN_H[kind]),
           (" -- and something else is already there" if tried else "")))


def _corner(p, near, safe, obstacles):
    kind, pid = p["kind"], p["id"]
    h = MIN_H[kind] * ANCHORED[p["size"]]
    while h >= MIN_H[kind] - 1e-6:
        w = (safe[2] - safe[0]) / 2.0 if kind == "text" else min(h * ASPECT[kind], safe[2] - safe[0])
        if near == "center":
            cx, cy = (safe[0] + safe[2]) / 2.0, (safe[1] + safe[3]) / 2.0
            x0, y0 = cx - w / 2.0, cy - h / 2.0
            x0, y0, x1, y1 = _clamp(x0, y0, x0 + w, y0 + h, safe)
            box = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
            if not any(_overlap(box, o) for o in obstacles):
                return _finish(pid, kind, x0, y0, x1, y1)
        else:
            x0 = safe[0] + INSET if near.endswith("left") else safe[2] - INSET - w
            y0 = safe[1] + INSET if near.startswith("top") else safe[3] - INSET - h
            # SLIDE past whatever already sits in the corner (often the typed request itself, across the top):
            # the corner is then the first clear spot below it.
            for _ in range(8):
                x0, y0, x1, y1 = _clamp(x0, y0, x0 + w, y0 + h, safe)
                box = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
                hit = [o for o in obstacles if _overlap(box, o)]
                if not hit:
                    return _finish(pid, kind, x0, y0, x1, y1)
                if near.startswith("top"):
                    y0 = max(o["y1"] for o in hit) + GAP
                    if y0 + h > safe[3]:
                        break
                else:
                    y0 = min(o["y0"] for o in hit) - GAP - h
                    if y0 < safe[1]:
                        break
        h *= 0.85
    raise PlanError("the %s of the page is not clear enough for %r: something is already there. "
                    "Erase it first, or put %r somewhere else." % (near.replace("-", " "), pid, pid))


def solve(places, first_free_y=None, safe=SAFE, arrow_tip=None, marks=None, obstacles=None,
          text_col=None, fixed=None, screen=None):
    """places -> boxes. Raises PlanError if it cannot.

    `fixed` are boxes that are already decided -- a picture being redone in its old place, an item of this job
    that has already landed -- and the stacked rows go round them the way they go round an anchored place.
    `obstacles` alone does not do that: the stacked band is empty by construction of `first_free_y`, which a
    redone picture's place need not be (its old picture was erased).

    `first_free_y` is what page_info() reports: the top of the empty part of the page. Stacked places go below
    it, in order, and never over what is already there.

    `marks` maps a mark number (from show_marks()) to its bbox, for near="mark:N". `obstacles` is every bbox
    already on the page -- marks, pictures, typed text -- so that a place put beside a mark does not land on its
    neighbor.

    A place with near="arrow" is centered on `arrow_tip` instead of being stacked: an arrow the user drew is an
    instruction about position.

    THE SCREEN IS A PAGE'S WHOLE FACE. A full coloring page alone in the plan takes `screen` -- the page frame
    the tablet shows without scrolling, measured on the device as x -810..810, y 0..2160 -- and not the safe
    area: it is the page, so neither the toolbar's line nor what is already written moves it.
    """
    _check(places)
    if (screen and len(places) == 1 and places[0]["kind"] == "coloring" and places[0]["size"] == "full"
            and places[0]["near"] == "stack"):
        return {places[0]["id"]: _finish(places[0]["id"], "coloring", *(float(v) for v in screen))}
    top = max(float(first_free_y if first_free_y is not None else safe[1]), safe[1])
    bottom = float(safe[3])
    band_h, band_w = bottom - top, safe[2] - safe[0]
    marks = {int(k): _dict_box(v) for k, v in (marks or {}).items()}
    obstacles = [_dict_box(o) for o in (obstacles or [])]
    tcol = tuple(text_col) if text_col else TEXT_COL

    pinned = [p for p in places if p["near"] == "arrow"]
    if pinned and arrow_tip is None:
        raise PlanError("place %r asks to go at an arrow, but this page has no arrow on it. "
                        "Use near='stack'." % pinned[0]["id"])
    if len(pinned) > 1:
        raise PlanError("only one place can sit at the arrow; %d asked to."
                        % len(pinned))
    anchored = [p for p in places if _mark_ref(p["near"]) is not None or p["near"] in CORNERS]
    stacked = [p for p in places if p not in pinned and p not in anchored]
    boxes, out = [], {}

    if pinned:
        p = pinned[0]
        kind = p["kind"]
        h = max(MIN_H[kind], band_h * SIZES[p["size"]] / 5.0)
        cy = float(arrow_tip[1])
        y0 = min(max(cy - h / 2.0, safe[1]), bottom - h)
        b = _box(p["id"], kind, float(arrow_tip[0]), y0, h, band_w, safe, tcol)
        boxes.append(b)
        out[p["id"]] = b

    for p in anchored:
        mid = _mark_ref(p["near"])
        if mid is not None:
            if mid not in marks:
                raise PlanError("place %r is anchored to mark %d, but the marks on this page are "
                                "numbered %s. Call show_marks() and use a number from it."
                                % (p["id"], mid, (", ".join(str(k) for k in sorted(marks)) or "(none)")))
            anchor = marks[mid]
            others = [o for o in obstacles if not _same(o, anchor)] + boxes
            b = _anchored(p, anchor, p["side"], safe, others, "mark %d" % mid)
        else:
            b = _corner(p, p["near"], safe, obstacles + boxes)
        boxes.append(b)
        out[p["id"]] = b

    if stacked:
        # THE WORDS ABOVE THE PICTURE: a stacked picture goes after the places that are not pictures
        stacked.sort(key=lambda q: 1 if _own_height(q, band_w) is not None else 0)
        # ROWS: a "left" place and the "right" place that follows it share a row; everything else
        # is a row of its own. A row's appetite is its largest member's.
        rows, i = [], 0
        while i < len(stacked):
            p = stacked[i]
            if (p["near"] in ("left", "right") and i + 1 < len(stacked)
                    and stacked[i + 1]["near"] in ("left", "right")
                    and stacked[i + 1]["near"] != p["near"]):
                pair = [p, stacked[i + 1]]
                pair.sort(key=lambda q: 0 if q["near"] == "left" else 1)
                rows.append(pair)
                i += 2
            else:
                rows.append([p])
                i += 1
        own = lambda row: _own_height(row[0], band_w) if len(row) == 1 else None
        need = sum(own(row) or max(MIN_H[p["kind"]] for p in row) for row in rows) + GAP * (len(rows) - 1)
        # THE PAGE EXTENDS BELOW. A reMarkable page scrolls, and extending it is preferred to refusing or
        # adding a page: the places get their minimum heights, stacked from the first free line down.
        if need > band_h:
            bottom = top + need
            band_h = need
        slack = band_h - need
        total_w = sum(max(SIZES[p["size"]] for p in row) for row in rows if own(row) is None) or 1.0
        y = top
        half = (band_w - GAP) / 2.0
        # STACKED ROWS GO AROUND THE ANCHORED BOXES, not through them: an anchored box is an obstacle to the
        # stack like any other content, so a row that would cross one is moved below it, and the rows after it
        # follow.
        fixed = list(boxes) + [_dict_box(f) for f in (fixed or [])]
        for row in rows:
            h = own(row) or (max(MIN_H[p["kind"]] for p in row) + slack * (max(SIZES[p["size"]] for p in row) / total_w))
            for _ in range(8):
                hit = [b for b in fixed if b["y0"] < y + h and b["y1"] > y]
                if not hit:
                    break
                y = max(b["y1"] for b in hit) + GAP
            if y + h > bottom:
                # pushed down past a fixed box: shrink into what is left if the row still gets its
                # minimum, and otherwise the page extends below (it scrolls), as it does for the stack; a picture
                # keeps its own size
                if own(row) is None:
                    h = max(bottom - y, max(MIN_H[p["kind"]] for p in row))
                bottom = max(bottom, y + h)
            if len(row) == 1:
                p = row[0]
                cx = 0.0
                if p["near"] == "left":
                    cx = safe[0] + half / 2.0
                elif p["near"] == "right":
                    cx = safe[2] - half / 2.0
                b = _box(p["id"], p["kind"], cx, y, h, half if p["near"] in ("left", "right") else band_w, safe, tcol)
                boxes.append(b)
                out[p["id"]] = b
            else:
                for p, cx in zip(row, (safe[0] + half / 2.0, safe[2] - half / 2.0)):
                    b = _box(p["id"], p["kind"], cx, y, h, half, safe, tcol)
                    boxes.append(b)
                    out[p["id"]] = b
            y += h + GAP

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _overlap(boxes[i], boxes[j]):
                raise PlanError(
                    "%r and %r would overlap. Anchor them to different things, stack them, or ask "
                    "for fewer things." % (boxes[i]["id"], boxes[j]["id"]))
    return out


def _same(a, b):
    return all(abs(float(a[k]) - float(b[k])) < 0.5 for k in ("x0", "y0", "x1", "y1"))


def covered(box, strokes, need=1):
    """Did anything actually land inside this box? Counts strokes with a point inside it, so a planned place
    that stayed empty is a gap the host can see."""
    n = 0
    for s in strokes:
        for x, y in _points(s):
            if box["x0"] <= x <= box["x1"] and box["y0"] <= y <= box["y1"]:
                n += 1
                break
        if n >= need:
            return True
    return False


def _points(s):
    """(x, y) pairs from a stroke in EITHER form: a draft stroke is the plain tuple rm_art builds, (pts,
    widths, tool, color, rgba), with pts a list of (x, y); a stroke read back off a committed page is an
    rmscene object with .points carrying .x/.y."""
    pts = getattr(s, "points", None)
    if pts is not None:
        return [(p.x, p.y) for p in pts]
    if isinstance(s, (tuple, list)) and s and isinstance(s[0], (tuple, list)):
        return [(p[0], p[1]) for p in s[0]]
    return []
