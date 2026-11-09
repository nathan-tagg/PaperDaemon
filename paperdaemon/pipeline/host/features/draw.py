"""Drawing: the shape library's elements and figures the model builds part by part."""
import json
import math
from paperdaemon.pipeline import draw as A
from paperdaemon.pipeline.draw import lettering as LT
from paperdaemon.pipeline.draw import shapes as E
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline import host as H


def _element_args(fn, cx, cy, r):
    """Map the model's (cx, cy, r) onto whatever THIS shape actually takes.

    Most library shapes are not (cx, cy, r): they want rx/ry, a size `s`, or box corners, so a uniform call
    either raised or drew nonsense. One center and one radius is the parameter set a model reasons about well,
    so it is adapted here and every name in the registry works.
    """
    import inspect
    names = list(inspect.signature(fn).parameters)
    cx, cy, r = float(cx), float(cy), float(r)
    if names[:3] == ["cx", "cy", "r"]:
        return dict(cx=cx, cy=cy, r=r)
    if names[:4] == ["cx", "cy", "rx", "ry"]:
        return dict(cx=cx, cy=cy, rx=r, ry=r * 1.6)
    if names[:3] == ["cx", "cy", "s"]:
        return dict(cx=cx, cy=cy, s=r)
    if names[:4] == ["cx", "cy", "side", "corner"]:
        return dict(cx=cx, cy=cy, side=r * 2.0, corner=r * 0.35)
    if names[:3] == ["x", "y0", "y1"]:                  # bracket
        return dict(x=cx, y0=cy - r, y1=cy + r)
    if names[:3] == ["x0", "x1", "y"]:                  # rule, underline
        return dict(x0=cx - r, x1=cx + r, y=cy)
    if names[:4] == ["x0", "y0", "x1", "y1"]:           # arrow, frames
        return dict(x0=cx - r, y0=cy - r, x1=cx + r, y1=cy + r)
    return dict(cx=cx, cy=cy, r=r)


def t_element(name, cx, cy, r):
    # THE ICON SET COUNTS AS AN ELEMENT. rm_icons holds 126 Lucide outlines that were only
    # reachable from the chart renderer, so element("cake") failed while the cake sat one module
    # away. An emoji resolves here too -- the icon is what the emoji means, drawn in the tablet's
    # own line vocabulary, instead of the lettering font turning it into a dash.
    name = E.resolve_emoji(name) or name
    # AN ICON DRAWN WITH A FIGURE IS PART OF IT. In the reply that drew the figure, or while the figure is shown
    # back for a fix, the numbers are on the figure's own grid, and the host fits the figure into its box as a
    # whole: placed on the page apart from it, a sun meant for the sky landed on the house's window. It joins the
    # figure's parts, and the figure is drawn again, fitted with it.
    fig = JOB.figure
    if fig and fig.get("op") == len(JOB.ops) and (fig.get("turn") == JOB.turns or JOB.looking):
        res = H._redraw_figure([dict(p) for p in fig["parts"]] + [{"kind": "icon", "name": name, "cx": cx,
                                                                   "cy": cy, "r": r}])
        if res.get("ok"):
            res["note"] = "the %s is a part of the figure (its last), fitted with it" % name
        return res
    # THE HOST KEEPS THE ELEMENT IN ITS BOX. Same reasoning as _fit_paths for a figure: the model
    # chooses WHAT and roughly how big; where -580 is on the page is not its strength. A center
    # outside the step's box becomes the box's center, and a radius wider than the box is clipped.
    box = ((JOB.plan or {}).get("places") or {}).get(H._cur_place())
    if box:
        cx0, cy0, r0 = float(cx), float(cy), float(r)
        r = max(8.0, min(r0, 0.45 * min(box["w"], box["h"])))
        if not (box["x0"] <= cx0 <= box["x1"] and box["y0"] <= cy0 <= box["y1"]):
            cx, cy = box["cx"], box["cy"]
        else:
            cx = min(max(cx0, box["x0"] + r), box["x1"] - r)
            cy = min(max(cy0, box["y0"] + r), box["y1"] - r)
        if (cx, cy, r) != (cx0, cy0, r0):
            H.log("  element kept in its box: (%d,%d) r%d -> (%d,%d) r%d" % (cx0, cy0, r0, cx, cy, r))
    hits = E.find(name)
    if not hits:
        paths = E._icon_paths(name, cx, cy, r)
        if paths:
            H._mark()
            for pth in paths:
                JOB.draw.stroke(pth, width=A.prof_swell(9, 16))
            JOB.ops.append("icon %s at (%d,%d)" % (name, int(cx), int(cy)))
            return dict({"ok": True, "element": name, "paths": len(paths)}, **H._did())
        return dict({"error": "no element %r. Available: %s"
                     % (name, ", ".join(E.icon_names()))}, **H._did())
    entry = hits[0][1] if isinstance(hits[0], tuple) else hits[0]
    fn = entry["fn"]
    polys = fn(**H._element_args(fn, cx, cy, r))
    H._mark()
    for pth in (polys if isinstance(polys[0], list) else [polys]):
        JOB.draw.stroke(pth, width=A.prof_swell(9, 16))
    JOB.ops.append("element %s at (%d,%d)" % (name, int(cx), int(cy)))
    return dict({"ok": True}, **H._did())


def _part_paths(part):
    """One drawing primitive -> polyline points. Python owns the curves."""
    k = (part.get("kind") or "").lower()
    g = lambda n, d=0.0: float(part.get(n, d) or 0.0)
    if k == "icon":
        # a library shape or icon by name, on the figure's own grid like every other part
        name = str(part.get("name") or "").strip()
        name = E.resolve_emoji(name) or name
        cx, cy, r = g("cx"), g("cy"), g("r") or 20.0
        hits = E.find(name) if name else []
        if hits:
            fn = (hits[0][1] if isinstance(hits[0], tuple) else hits[0])["fn"]
            polys = fn(**_element_args(fn, cx, cy, r))
            return [list(p) for p in (polys if isinstance(polys[0], list) else [polys])]
        paths = E._icon_paths(name, cx, cy, r) if name else None
        if not paths:
            raise ValueError("no icon named %r" % name)
        return [list(p) for p in paths]
    if k == "text":
        # A LABEL, lettered in the pipeline's own face on the figure's grid, like every other part (a "labeled diagram
        # of the water cycle" came out mute: the figure had no part that could carry a word). x, y: the baseline's
        # left end; anchor center or right puts the middle or the right end there; size: the capital height
        words = " ".join(str(part.get("text") or "").split())
        if not words:
            raise ValueError("a text part needs text")
        size = max(12.0, min(120.0, g("size", 28.0) or 28.0))
        anchor = str(part.get("anchor") or "left").lower()
        d = A.Drawing()
        kw = dict(size=size, seed=7, angle=g("angle", 0.0))
        if anchor == "center":
            LT.center(d, words, g("x"), g("y"), **kw)
        elif anchor == "right":
            LT.right(d, words, g("x"), g("y"), **kw)
        else:
            LT.text(d, words, g("x"), g("y"), **kw)
        return [[(float(px), float(py)) for px, py in s[0]] for s in d.strokes if len(s[0]) >= 2]
    if k == "line":
        return [[(g("x1"), g("y1")), (g("x2"), g("y2"))]]
    if k == "rect":
        x1, y1, x2, y2 = g("x1"), g("y1"), g("x2"), g("y2")
        return [[(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]]
    if k == "polyline":
        pts = [(float(p[0]), float(p[1])) for p in (part.get("points") or [])
               if len(p) >= 2]
        return [pts] if len(pts) >= 2 else []
    if k in ("circle", "ellipse", "arc"):
        rx = g("rx") or g("r")
        ry = g("ry") or g("r") or rx
        a0 = math.radians(g("start", 0.0)) if k == "arc" else 0.0
        a1 = math.radians(g("end", 360.0)) if k == "arc" else 2 * math.pi
        n = max(16, int(abs(a1 - a0) / (2 * math.pi) * 96))
        pts = [(g("cx") + rx * math.cos(a0 + (a1 - a0) * i / n),
                g("cy") + ry * math.sin(a0 + (a1 - a0) * i / n))
               for i in range(n + 1)]
        return [pts]
    return []


def _word_box(paths, size):
    """The box a label's strokes fill, grown by a gap of the capital height's third: the room its words need."""
    xs = [p[0] for pth in paths for p in pth]
    ys = [p[1] for pth in paths for p in pth]
    gap = max(6.0, 0.35 * size)
    return (min(xs) - gap, min(ys) - gap, max(xs) + gap, max(ys) + gap)


def _exit(p, q, boxes):
    """`p` inside one of the boxes and `q` beyond it -> the point on the way from p to q just outside that box; None
    when p is in no box, or q is inside it too."""
    for x0, y0, x1, y1 in boxes:
        if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
            continue
        if x0 <= q[0] <= x1 and y0 <= q[1] <= y1:
            return None
        dx, dy = q[0] - p[0], q[1] - p[1]
        ts = [(e - p[0]) / dx for e in (x0, x1) if dx] + [(e - p[1]) / dy for e in (y0, y1) if dy]
        ts = [t for t in ts if 0 < t <= 1]
        return (p[0] + dx * min(ts), p[1] + dy * min(ts)) if ts else None
    return None


def _off_the_words(paths, kinds, boxes):
    """A line or polyline that ends inside a label's words is cut at the label's edge, a little short of it: a leader
    drawn through its own label ("Chloroplast" struck through by the line that pointed at it) stops where the word
    begins. The words themselves and the shapes are left alone."""
    if not boxes:
        return paths
    out = []
    for pth, kind in zip(paths, kinds):
        if kind in ("line", "polyline") and len(pth) >= 2:
            pth = list(pth)
            for end, nxt in ((0, 1), (-1, -2)):
                hit = _exit(pth[end], pth[nxt], boxes)
                if hit:
                    pth[end] = hit
        out.append(pth)
    return out


def _fit_paths(paths, box, fill=0.9):
    """Scale (aspect kept) and center a figure's paths into `box`. None if there is nothing to fit
    or the figure is degenerate (a point). A figure already inside the box and at least a third of
    its size is left alone -- the model may have meant exactly that."""
    pts = [p for pth in paths for p in pth]
    if not pts or box is None:
        return None
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    w, h = x1 - x0, y1 - y0
    if w < 1e-6 and h < 1e-6:
        return None
    bw, bh = box["x1"] - box["x0"], box["y1"] - box["y0"]
    inside = x0 >= box["x0"] - 2 and x1 <= box["x1"] + 2 and y0 >= box["y0"] - 2 and y1 <= box["y1"] + 2
    if inside and (w >= bw / 3.0 or h >= bh / 3.0):
        return None
    k = min(bw * fill / max(w, 1e-6), bh * fill / max(h, 1e-6))
    if inside and k > 1.0:
        k = min(k, 1.0) if (w >= bw / 3.0 or h >= bh / 3.0) else k
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    tx, ty = (box["x0"] + box["x1"]) / 2.0, (box["y0"] + box["y1"]) / 2.0
    out = []
    for pth in paths:
        out.append([(tx + (p[0] - cx) * k, ty + (p[1] - cy) * k) for p in pth])
    H.log("  figure fitted to its box: scale %.2f, moved (%d, %d)" % (k, tx - cx, ty - cy))
    return out


def t_draw_figure(parts):
    """Draw something by SAYING WHAT IT IS MADE OF.

    Asked for a bicycle, the model does not have to produce a smooth circle -- it has to know that a bicycle is
    two wheels of equal size, a frame between them, handlebars and a seat. That is structure, which it is good
    at; the code turns each part into geometry.

    It is ONE call for the whole figure: many calls in one turn, with no feedback between them, drift.
    """
    # shown back for a fix, a figure is drawn again in ITS box: the step it was drawn for has closed, and the
    # step the host is on may have a box of its own
    return H._draw_figure(parts, (JOB.figure or {}).get("place") if JOB.looking else H._cur_place())


def _redraw_figure(parts):
    """The figure drawn last, drawn again from `parts` in its own box (a fix, or an icon joining it)."""
    fig = JOB.figure
    del JOB.draw.strokes[fig["at"]:]
    JOB.ops.pop()
    if JOB.marks:
        JOB.marks.pop()
    JOB.last_figure = None
    return H._draw_figure(parts, fig.get("place"))


# A PART'S INK, by the name the model gives it -- the tablet's own pen colors; "red apples" were drawn black. A color
# the tablet has no pen for is drawn in the nearest one it has: an "orange" fox was drawn black
_INKS = {"black": "BLACK", "gray": "GRAY", "white": "WHITE", "yellow": "YELLOW",
         "green": "GREEN", "pink": "PINK", "blue": "BLUE", "red": "RED", "cyan": "CYAN", "magenta": "MAGENTA",
         "orange": "RED", "brown": "BLACK", "purple": "MAGENTA", "violet": "MAGENTA", "teal": "CYAN",
         "turquoise": "CYAN", "gold": "YELLOW", "navy": "BLUE", "silver": "GRAY", "lime": "GREEN"}


def _ink(name):
    k = _INKS.get(str(name or "").strip().lower())
    return getattr(A.PenColor, k) if k else A.PenColor.BLACK


def _onto_page(paths):
    """A figure kept where it was drawn, moved (never scaled) just far enough to lie inside the page's safe area."""
    x0, y0, x1, y1 = H._safe()
    xs = [p[0] for pth in paths for p in pth]
    ys = [p[1] for pth in paths for p in pth]
    dx = (x0 - min(xs)) if min(xs) < x0 else ((x1 - max(xs)) if max(xs) > x1 else 0.0)
    dy = (y0 - min(ys)) if min(ys) < y0 else ((y1 - max(ys)) if max(ys) > y1 else 0.0)
    if not dx and not dy:
        return paths
    return [[(p[0] + dx, p[1] + dy) + tuple(p[2:]) for p in pth] for pth in paths]


def _draw_figure(parts, place):
    if not isinstance(parts, list) or not parts:
        return dict({"error": "parts must be a non-empty list of "
                              "{kind, ...} objects"}, **H._did())
    # REFUSE AN IDENTICAL REDRAW: a revision that re-emits the same part list changes nothing, so the next
    # drawing has to differ from the last.
    if JOB.looks >= H.DRAW_ROUNDS:
        return dict({"error": "you have had your %d rounds on this drawing and "
                              "it is not getting better, only different. Stop "
                              "redrawing. If it is good enough, commit() and "
                              "done() with an honest note. If it is not, "
                              "skip() and say what you could not get right -- "
                              "a blank page beats a bad drawing."
                              % H.DRAW_ROUNDS}, **H._did())
    key = json.dumps(parts, sort_keys=True)
    if key == JOB.last_figure:
        return dict({"error": "this is EXACTLY the figure you just drew. You "
                              "said what was wrong with it -- change those "
                              "parts. Different numbers, not the same list."},
                    **H._did())
    JOB.last_figure = key
    H._mark()
    JOB.figure = {"parts": [dict(p) for p in parts if isinstance(p, dict)],
                     "at": len(JOB.draw.strokes), "op": None, "place": place, "turn": JOB.turns}
    drawn, bad, paths_all, inks, kinds, words = 0, [], [], [], [], []
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            bad.append("part %d is not an object" % i)
            continue
        try:
            paths = H._part_paths(part)
        except Exception as ex:
            bad.append("part %d (%s): %s" % (i, part.get("kind"), str(ex)[:60]))
            continue
        if not paths:
            bad.append("part %d: unknown or empty kind %r" % (i, part.get("kind")))
            continue
        paths_all += [list(pth) for pth in paths]
        inks += [_ink(part.get("color"))] * len(paths)
        kind = str(part.get("kind") or "").lower()
        kinds += [kind] * len(paths)
        if kind == "text":
            words.append(_word_box(paths, float(part.get("size") or 28.0)))
    paths_all = _off_the_words(paths_all, kinds, words)
    # THE HOST FITS THE FIGURE TO ITS BOX. The numbers the model sends are taken as a sketch on its own grid:
    # the whole figure is scaled (aspect kept) and centered into the box the plan gave this step, so its
    # coordinates need only be consistent with each other. Without a box the page's safe area is the box.
    box = ((JOB.plan or {}).get("places") or {}).get(place)
    # A FIGURE ADDED ONTO A DRAWING ALREADY ON THE PAGE (its step's side "on" a mark) stays where the model put it,
    # never scaled: it is told where that drawing's parts are and draws in the page's own numbers, and fitting it into
    # the drawing's box -- scaled up and centered -- took the apples off the tree, put a hat on a snowman's body and a
    # chimney inside the wall. A hat sits above the head, outside the drawing's box, so "near" is within one drawing's
    # size of it; only a figure far from it (made on a grid of its own) is fitted as any other.
    step = next((q for q in (JOB.steps or []) if q.get("place") == place), None)
    onto = bool(step and str(step.get("side") or "").lower() == "on" and str(step.get("near") or "").lower().startswith("mark"))
    if onto and box and paths_all:
        xs = [p[0] for pth in paths_all for p in pth]
        ys = [p[1] for pth in paths_all for p in pth]
        reach = max(box["w"], box["h"])
        onto = (min(xs) <= box["x1"] + reach and max(xs) >= box["x0"] - reach
                and min(ys) <= box["y1"] + reach and max(ys) >= box["y0"] - reach)
    if onto:
        paths_all = _onto_page(paths_all)
        H.log("  figure kept where it was drawn, onto %s" % step.get("near"))
    else:
        fitted = H._fit_paths(paths_all, box)
        if fitted is not None:
            paths_all = fitted
    for pth, ink in zip(paths_all, inks):
        ys = [p[1] for p in pth]
        if min(ys) < H._safe()[1] or max(ys) > H._safe()[3]:
            bad.append("a part runs off the page (y %d..%d, page is %d..%d)"
                       % (min(ys), max(ys), H._safe()[1], H._safe()[3]))
            continue
        JOB.draw.stroke(pth, width=A.prof_swell(7, 12), color=ink)
        drawn += 1
    if not drawn:
        return dict({"error": "nothing was drawn", "problems": bad[:6]}, **H._did())
    JOB.ops.append("figure of %d part(s)" % drawn)
    JOB.figure["op"] = len(JOB.ops)      # set AFTER the append
    listing = ["%d:%s" % (i, (p.get("kind") or "?"))
               for i, p in enumerate(JOB.figure["parts"])]
    return dict({"ok": True, "parts_drawn": drawn, "problems": bad[:6] or None,
                 "parts": listing,
                 "note": "render() and LOOK at it. To fix ONE thing use "
                         "edit_figure -- you do not have to redraw the whole "
                         "figure to move an eye socket."}, **H._did())


def t_edit_figure(changes):
    """Change SOME parts of the figure you drew, leaving the rest alone.

    draw_figure is ONE call and ONE op, so undo_last(1) takes the whole figure; this is how to say "the
    eyes are too high" without re-emitting all of it.

    changes: [{"index": 3, "cy": 720}, {"index": 7, "delete": true}]
    Anything you do not mention keeps its current value.
    """
    fig = JOB.figure
    if not fig:
        return dict({"error": "no figure drawn yet -- use draw_figure first"},
                    **H._did())
    if fig["op"] != len(JOB.ops):
        return dict({"error": "you have drawn other things since this figure, "
                              "so its parts can no longer be edited in place. "
                              "clear() and draw it again."}, **H._did())
    if not isinstance(changes, list) or not changes:
        return dict({"error": "changes must be a list of {index, ...} objects"},
                    **H._did())

    parts = [dict(p) for p in fig["parts"]]
    applied, bad = [], []
    for ch in changes:
        if not isinstance(ch, dict) or "index" not in ch:
            bad.append("every change needs an index")
            continue
        i = int(ch["index"])
        if not 0 <= i < len(parts):
            bad.append("no part %d (there are %d)" % (i, len(parts)))
            continue
        if ch.get("delete"):
            parts[i] = None
            applied.append("deleted %d" % i)
            continue
        for k, v in ch.items():
            if k not in ("index", "delete"):
                parts[i][k] = v
        applied.append("%d: %s" % (i, ", ".join(k for k in ch if k != "index")))
    parts = [p for p in parts if p]
    if not applied:
        return dict({"error": "nothing applied", "problems": bad[:6]}, **H._did())
    if not parts:
        return dict({"error": "that would delete every part. Use clear() if "
                              "you mean to start over."}, **H._did())

    # rewind just this figure, then lay the amended one down
    res = H._redraw_figure(parts)
    if res.get("ok"):
        res["applied"] = applied
        res["problems"] = (res.get("problems") or []) + bad[:4] or None
        res["note"] = ("changed %d part(s), the rest are untouched. render() "
                       "and look." % len(applied))
    return res


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("element", "Draw ONE small solved shape or icon -- a mark, not a picture -- at cx, cy with radius r, "
             "inside your box. An emoji works as a name (a fire draws a flame). Names: "
             + ", ".join(E.icon_names()),
  {"name": "string", "cx": "number", "cy": "number", "r": "number"}, t_element),
 ("draw_figure", "DRAW something yourself by listing the parts it is made of: lines, circles, "
  "ellipses, arcs, rectangles, polylines, icons by name (a sun, a star) as parts like the others, and text "
  "for the words a diagram carries (a label by each part it names, a title). "
  "One call for the whole figure, every part of it, inside your box. A house is a box and a triangle; "
  "a bicycle is two circles and a frame; a labeled diagram is its shapes, its arrows, and a text part by each. "
  "Coordinates are page coordinates: x from the page's center "
  "(0), y from its top (larger y is further DOWN), within the page's size as the page states it.",
  {"parts": H.PART_SCHEMA}, t_draw_figure),
 ("edit_figure", "Change SOME parts of the figure you drew, leaving the rest alone -- e.g. "
  "[{\"index\":3,\"cy\":720},{\"index\":7,\"delete\":true}]. Part numbers come back from "
  "draw_figure.", {"changes": {"type": "array", "items": {"type": "object"}}}, t_edit_figure),
]
