r"""Numbers as PATHS, taken from the tablet's own monoline lettering font.

A number that belongs inside an icon has to be drawn the way the icon is drawn. Setting a
typeface over line art never looks like it belongs -- a filled letterform beside a 2px stroke
reads as two drawings, which is why the percentage over the weather icon needed a knockout cut
behind it to be legible at all.

The strokes already exist: `rm_text.G` is the single-stroke font the tablet writes with, glyphs
on a unit grid with the baseline at y=0, cap height at y=1 and y running UP. This turns a run of
them into one SVG path in the unit box a Vega custom symbol is drawn in (y running DOWN), so a
figure can be concatenated onto an icon and stroked at the same width.

    text_path("22%", size=0.5, cx=0.0, cy=0.35)     # -> one path string
"""
from __future__ import annotations

TRACK = 0.13          # the same default tracking rm_text uses


def _g(v):
    s = "%.4f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _font():
    from paperdaemon.pipeline.draw import lettering as rm_text
    return rm_text.G


def measure(text, track=TRACK):
    """Advance width of `text` in cap-height units."""
    G = _font()
    w = 0.0
    for ch in text:
        w += G.get(ch, G.get("-"))[0] + track
    return max(0.0, w - track)


def text_path(text, size, cx=0.0, cy=0.0, track=TRACK):
    """`text` as open polylines, `size` tall (cap height), centered on (cx, cy).

    y is FLIPPED on the way out: the font is drawn with y up and a custom symbol with y down.
    """
    G = _font()
    total = measure(text, track) * size
    x = cx - total / 2.0
    base = cy + size / 2.0            # baseline, in the flipped space
    out = []
    for ch in text:
        adv, strokes = G.get(ch, G.get("-"))
        for poly in strokes:
            if not poly:
                continue
            pts = ["%s %s" % (_g(x + px * size), _g(base - py * size)) for px, py in poly]
            out.append("M " + pts[0] + "".join(" L " + p for p in pts[1:]))
        x += (adv + track) * size
    return " ".join(out)


def fit(text, max_units, track=TRACK):
    """The longest prefix of `text` that fits `max_units` cap-heights, ellipsis if it was cut.

    Real advances from the font, so a caller can guarantee a line never wraps instead of
    estimating an average em and hoping.
    """
    if measure(text, track) <= max_units:
        return text
    dots = ".."      # the font has no ellipsis; two stops is a truncation mark it can draw
    room = max_units - measure(dots, track)
    out = ""
    for ch in text:
        if measure(out + ch, track) > room:
            break
        out += ch
    return (out.rstrip() + dots) if out.strip() else dots


def clock_path(hh, mm, size, cx=0.0, cy=0.0):
    """A clock face SET TO THE TIME, as one path in the same monoline style.

    Typing "19:30 - " in front of an event costs about five characters of a cell that has room
    for a dozen, and a calendar day is read at a glance anyway. A dial says it in the width of
    one glyph.
    """
    import math
    r = size / 2.0
    out = []
    n = 28
    pts = [(cx + r * 0.92 * math.cos(2 * math.pi * i / n),
            cy + r * 0.92 * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
    out.append("M " + " L ".join("%s %s" % (_g(x), _g(y)) for x, y in pts))
    for length, ang in ((0.42, (hh % 12) / 12.0 * 360.0 + mm / 60.0 * 30.0),
                        (0.66, mm / 60.0 * 360.0)):
        a = math.radians(ang)
        out.append("M %s %s L %s %s" % (_g(cx), _g(cy),
                                        _g(cx + r * length * math.sin(a)),
                                        _g(cy - r * length * math.cos(a))))
    return " ".join(out)


def parse_time(s):
    """"19:30" / "7:05 pm" / "0840" -> (hour, minute), or None."""
    import re as _re
    m = _re.match(r"^\s*(\d{1,2})[:.]?(\d{2})?\s*([ap]\.?m\.?)?\s*$", str(s), _re.I)
    if not m:
        return None
    h = int(m.group(1))
    mi = int(m.group(2) or 0)
    ap = (m.group(3) or "").lower()
    if ap.startswith("p") and h < 12:
        h += 12
    if ap.startswith("a") and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return h, mi


# ---------------------------------------------------------------- a figure over an icon
# The icon does not change. Not its size, not its shape. The number goes OVER it, and the icon's
# own strokes STOP SHORT where the number sits rather than running through it -- which is what a
# draughtsman does, and what knocking a white hole in the glyph was a poor imitation of.
#
# Doing that means flattening the glyph to polylines (it arrives as M/L/C/Q/A/Z), cutting every
# segment against the figure's box, and re-emitting what is left.

import math as _m


def _bez3(p0, p1, p2, p3, n=16):
    out = []
    for i in range(1, n + 1):
        t = i / float(n)
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0]
                    + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1]
                    + t * t * t * p3[1]))
    return out


def _bez2(p0, p1, p2, n=12):
    out = []
    for i in range(1, n + 1):
        t = i / float(n)
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return out


def _arc_pts(p0, rx, ry, rot, laf, sf, p1, n=None):
    """SVG endpoint arc -> points, by the spec's own center parameterization."""
    x0, y0 = p0
    x1, y1 = p1
    if rx == 0 or ry == 0 or (abs(x0 - x1) < 1e-12 and abs(y0 - y1) < 1e-12):
        return [p1]
    rx, ry = abs(rx), abs(ry)
    phi = _m.radians(rot)
    cp, sp = _m.cos(phi), _m.sin(phi)
    dx2, dy2 = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1p = cp * dx2 + sp * dy2
    y1p = -sp * dx2 + cp * dy2
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        k = _m.sqrt(lam)
        rx, ry = rx * k, ry * k
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = _m.sqrt(max(0.0, num / den)) if den else 0.0
    if laf == sf:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x0 + x1) / 2.0
    cy = sp * cxp + cp * cyp + (y0 + y1) / 2.0

    def ang(ux, uy, vx, vy):
        d = (_m.hypot(ux, uy) * _m.hypot(vx, vy)) or 1e-12
        c = max(-1.0, min(1.0, (ux * vx + uy * vy) / d))
        a = _m.acos(c)
        return -a if ux * vy - uy * vx < 0 else a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sf and dt > 0:
        dt -= 2 * _m.pi
    elif sf and dt < 0:
        dt += 2 * _m.pi
    if n is None:
        n = max(6, int(abs(dt) / 0.20) + 2)
    out = []
    for i in range(1, n + 1):
        t = t1 + dt * i / float(n)
        out.append((cx + cp * rx * _m.cos(t) - sp * ry * _m.sin(t),
                    cy + sp * rx * _m.cos(t) + cp * ry * _m.sin(t)))
    return out


_PCMD = __import__("re").compile(r"([MLCQAZmlcqaz])")


def flatten(d):
    """Path -> list of polylines. Input is the absolute M/L/C/Q/A/Z rm_icons emits."""
    parts = [q for q in _PCMD.split(d) if q.strip()]
    polys, cur, cx, cy, sx, sy = [], [], 0.0, 0.0, 0.0, 0.0
    i = 0
    while i < len(parts):
        c = parts[i].upper()
        i += 1
        args = []
        if i < len(parts) and parts[i][0] not in "MLCQAZmlcqaz":
            args = [float(v) for v in NUMS.findall(parts[i])]
            i += 1
        if c == "Z":
            if cur:
                cur.append((sx, sy))
            cx, cy = sx, sy
            continue
        if c == "M":
            if cur:
                polys.append(cur)
            cur = [(args[0], args[1])]
            cx, cy = sx, sy = args[0], args[1]
            for j in range(2, len(args) - 1, 2):
                cur.append((args[j], args[j + 1]))
                cx, cy = args[j], args[j + 1]
        elif c == "L":
            for j in range(0, len(args) - 1, 2):
                cur.append((args[j], args[j + 1]))
                cx, cy = args[j], args[j + 1]
        elif c == "C":
            for j in range(0, len(args) - 5, 6):
                pts = _bez3((cx, cy), (args[j], args[j + 1]), (args[j + 2], args[j + 3]),
                            (args[j + 4], args[j + 5]))
                cur.extend(pts)
                cx, cy = pts[-1]
        elif c == "Q":
            for j in range(0, len(args) - 3, 4):
                pts = _bez2((cx, cy), (args[j], args[j + 1]), (args[j + 2], args[j + 3]))
                cur.extend(pts)
                cx, cy = pts[-1]
        elif c == "A":
            for j in range(0, len(args) - 6, 7):
                pts = _arc_pts((cx, cy), args[j], args[j + 1], args[j + 2],
                               int(args[j + 3]), int(args[j + 4]),
                               (args[j + 5], args[j + 6]))
                cur.extend(pts)
                cx, cy = pts[-1]
    if cur:
        polys.append(cur)
    return polys


NUMS = __import__("re").compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _cut(a, b, box):
    """The sub-segments of a->b that lie OUTSIDE box, as a list of (p, q)."""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return [(a, b)]              # parallel and outside: the whole segment survives
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return [(a, b)]
                t0 = max(t0, r)
            else:
                if r < t0:
                    return [(a, b)]
                t1 = min(t1, r)
    if t0 > t1:
        return [(a, b)]
    def at(t):
        return (a[0] + dx * t, a[1] + dy * t)
    out = []
    if t0 > 1e-6:
        out.append((a, at(t0)))
    if t1 < 1 - 1e-6:
        out.append((at(t1), b))
    return out


def clip_out(d, box):
    """Every part of path `d` that falls outside `box`, as one path of polylines."""
    out = []
    for poly in flatten(d):
        run = []
        for a, b in zip(poly, poly[1:]):
            pieces = _cut(a, b, box)
            for p, q in pieces:
                if run and abs(run[-1][0] - p[0]) < 1e-9 and abs(run[-1][1] - p[1]) < 1e-9:
                    run.append(q)
                else:
                    if len(run) > 1:
                        out.append(run)
                    run = [p, q]
        if len(run) > 1:
            out.append(run)
    return " ".join(
        "M " + " L ".join("%s %s" % (_g(x), _g(y)) for x, y in run) for run in out)


def over(icon_d, text, cap=0.58, cx=0.0, cy=0.0, pad=0.10):
    """`text` set over `icon_d`, with the icon's strokes stopping short of it.

    The icon keeps its own geometry exactly; only the strokes that would have run through the
    figure are cut, and they end where the figure begins.
    """
    w = measure(text) * cap
    box = (cx - w / 2.0 - pad, cy - cap / 2.0 - pad * 0.8,
           cx + w / 2.0 + pad, cy + cap / 2.0 + pad * 0.8)
    return clip_out(icon_d, box) + " " + text_path(text, cap, cx, cy)
