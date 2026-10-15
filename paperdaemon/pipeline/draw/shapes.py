r"""Solved drawing elements — the library, so a shape is designed once.

The point: "draw a leaf" should not restart from bezier control points every
time. Each entry here is a shape that has already been drawn, looked at, and
kept. Search the registry first; only design from scratch when nothing fits.

Every element is a plain function returning a POLYGON (a list of (x, y)) in page
coordinates, so it composes with everything in `rm_art`:
clip it, offset it, fill behind it, rotate it. Nothing here draws to a Drawing
itself — placement and pen choice stay with the caller.

Adding one is the whole point, not an afterthought:

    register("leaf-simple", leaf_simple, tags="leaf plant foliage",
             note="lens with pointed tips; rx is half-LENGTH, ry half-THICKNESS")

and write down what the user said about it in `notes`. A rejected variant is worth
keeping too, with why — that is how the library stops repeating a mistake.
"""
import math
import os
import re
import sys
from paperdaemon.pipeline.draw import arc, bez, cat, rot

def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _cr_seg(p0, p1, p2, p3, n=14, alpha=0.5):
    """One centripetal Catmull-Rom span, as a cubic bezier."""
    e = 1e-6
    d1 = max(dist(p0, p1), e) ** alpha
    d2 = max(dist(p1, p2), e) ** alpha
    d3 = max(dist(p2, p3), e) ** alpha
    d1s, d2s, d3s = d1 * d1, d2 * d2, d3 * d3
    A, B = 2 * d1s + 3 * d1 * d2 + d2s, 3 * d1 * (d1 + d2)
    c1 = ((p2[0] * d1s - p0[0] * d2s + A * p1[0]) / B,
          (p2[1] * d1s - p0[1] * d2s + A * p1[1]) / B)
    A2, B2 = 2 * d3s + 3 * d3 * d2 + d2s, 3 * d3 * (d3 + d2)
    c2 = ((p1[0] * d3s - p3[0] * d2s + A2 * p2[0]) / B2,
          (p1[1] * d3s - p3[1] * d2s + A2 * p2[1]) / B2)
    return bez(p1, c1, c2, p2, n)


def crom(P, closed=True, n=14, alpha=0.5):
    """Smooth curve through anchors. Closed by default."""
    P = list(P)
    ext = ([P[-1]] + P + [P[0], P[1]]) if closed else ([P[0]] + P + [P[-1]])
    out = []
    for i in range(len(ext) - 3):
        seg = _cr_seg(ext[i], ext[i + 1], ext[i + 2], ext[i + 3], n, alpha)
        out = cat(out, seg) if out else seg
    return out


def ell(cx, cy, rx, ry=None, n=96):
    return arc(cx, cy, rx, ry if ry is not None else rx, 0, 2 * math.pi, n)


def lumpy(cx, cy, r, n=9, amp=0.075, phase=0.0, sq=1.0):
    """A closed near-circle with gentle lumps -- ice cream, foliage, a head."""
    pts = []
    for k in range(n):
        a = phase + 2 * math.pi * k / n
        rr = r * (1 + amp * math.sin(3.0 * a + phase * 2.3)
                  + amp * 0.6 * math.cos(2.0 * a - phase))
        pts.append((cx + rr * math.cos(a), cy + rr * sq * math.sin(a)))
    return crom(pts, n=16)


def rrect(x0, y0, x1, y1, r, n=18):
    return cat(arc(x1 - r, y0 + r, r, r, -math.pi / 2, 0, n),
               arc(x1 - r, y1 - r, r, r, 0, math.pi / 2, n),
               arc(x0 + r, y1 - r, r, r, math.pi / 2, math.pi, n),
               arc(x0 + r, y0 + r, r, r, math.pi, 1.5 * math.pi, n)) \
           + [(x1 - r, y0)]


def star(cx, cy, r, ri=0.42, n=5, rot_deg=-90.0):
    pts = []
    for k in range(2 * n):
        a = math.radians(rot_deg + 180.0 * k / n)
        rr = r if k % 2 == 0 else r * ri
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts + [pts[0]]


def heart(cx, cy, s, n=90):
    out = []
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) \
            - math.cos(4 * t)
        out.append((cx + x * s / 16.0, cy - y * s / 17.0))
    return out


def band(center, hw, closed=True):
    """Offset a centerline into a closed ribbon. hw is a width or f(t in 0..1).

    Tapering hw to 0 gives a cone (horn, ray, petal, leaf). Nothing here is
    ever inset for filling, so an acute tip is safe.
    """
    left, right = [], []
    for p, (nx, ny, t) in zip(center, _normals(center)):
        h = hw(t) if callable(hw) else hw
        left.append((p[0] + nx * h, p[1] + ny * h))
        right.append((p[0] - nx * h, p[1] - ny * h))
    out = left + right[::-1]
    return out + [out[0]] if closed else out


def _normals(center):
    """Unit left-normals and arc-length fractions along a polyline."""
    n = len(center)
    L = [0.0]
    for i in range(1, n):
        L.append(L[-1] + dist(center[i - 1], center[i]))
    tot = L[-1] or 1.0
    out = []
    for i, p in enumerate(center):
        if i == 0:
            tx, ty = center[1][0] - p[0], center[1][1] - p[1]
        elif i == n - 1:
            tx, ty = p[0] - center[i - 1][0], p[1] - center[i - 1][1]
        else:
            tx = center[i + 1][0] - center[i - 1][0]
            ty = center[i + 1][1] - center[i - 1][1]
        m = math.hypot(tx, ty) or 1.0
        out.append((-ty / m, tx / m, L[i] / tot))
    return out


def leaf(cx, cy, rx, ry, deg=0.0, n=24):
    """Lens shape, pointed both ends -- ear, petal, leaf, seed, wing."""
    cl = [(cx - rx + 2 * rx * i / n, cy) for i in range(n + 1)]
    p = band(cl, lambda t: ry * math.sin(math.pi * t) ** 0.72)
    return rot(p, cx, cy, deg)



REGISTRY = {}


def register(name, fn, tags="", note="", source="", notes=None):
    REGISTRY[name] = {"fn": fn, "tags": set(tags.split()), "note": note,
                      "source": source, "notes": list(notes or [])}
    return fn


def find(query):
    """Elements matching any word in `query`, best match first."""
    words = set(str(query).lower().split())
    hits = []
    for name, e in REGISTRY.items():
        score = len(words & e["tags"])
        if any(w in name for w in words):
            score += 2
        if score:
            hits.append((score, name, e))
    return [(n, e) for _, n, e in sorted(hits, key=lambda h: -h[0])]


def feedback(name, said):
    """Record what the user said about an element, on the element.

    The library is only worth having if judgment accumulates in it. A note
    here outlives the session that earned it.
    """
    if name in REGISTRY:
        REGISTRY[name]["notes"].append(said)
        return True
    return False


# --------------------------------------------------------------- botanical
def leaf_simple(cx, cy, rx, ry, deg=0.0):
    """Lens, pointed both ends. rx is half-LENGTH, ry half-THICKNESS.

    Swapping those two turns an ear into a propeller; it did once, on the
    coloring-book bunny. The argument order is the trap, not the shape.
    """
    return leaf(cx, cy, rx, ry, deg)


def leaf_veined(cx, cy, rx, ry, deg=0.0):
    """Outline plus a midrib and four vein pairs. Returns [outline, *veins]."""
    out = leaf(cx, cy, rx, ry, deg)
    mid = rot([(cx - rx, cy), (cx + rx, cy)], cx, cy, deg)
    veins = [mid]
    for t in (-0.45, -0.15, 0.15, 0.45):
        bx = cx + rx * t
        h = ry * math.sin(math.pi * (t + 1) / 2) ** 0.72 * 0.8
        for s in (-1, 1):
            veins.append(rot([(bx, cy), (bx + rx * 0.22, cy + s * h)],
                               cx, cy, deg))
    return [out] + veins


def petal(cx, cy, rx, ry, deg=0.0):
    return leaf(cx, cy, rx, ry, deg)


# ------------------------------------------------------------------ celestial
def star_sharp(cx, cy, r, points=5, rot_deg=-90.0):
    return star(cx, cy, r, 0.42, points, rot_deg)


def star_soft(cx, cy, r, points=5, rot_deg=-90.0):
    """Rounded points -- starfish, sparkle, a star that is not spiky."""
    return crom(star(cx, cy, r, 0.46, points, rot_deg)[:-1], n=14)


def sparkle(cx, cy, r):
    """Four-armed twinkle: two crossed needles plus two short diagonals."""
    out = []
    for deg, k in ((0, 1.0), (90, 1.0), (45, 0.6), (-45, 0.6)):
        a = math.radians(deg)
        out.append([(cx - math.cos(a) * r * k, cy - math.sin(a) * r * k),
                    (cx + math.cos(a) * r * k, cy + math.sin(a) * r * k)])
    return out


def crescent(cx, cy, r, bite=0.82, offset=0.5, n=160):
    """Moon, as ONE closed polygon -- the true boolean difference of two disks.

    The first version returned [outer, inner] and left the caller to clip. Drawn
    straight, that reads as two overlapping circles, which is exactly what the
    contact sheet showed. An element that only looks right if you remember a
    caveat is a bad element, so the subtraction happens here.
    """
    R = float(r)
    r2 = R * bite
    d = R * offset                      # inner disk center, offset along +x
    if d >= R + r2 or d + r2 <= R:      # no bite, or bite swallowed: plain disk
        return ell(cx, cy, R)
    # angle from each center to the two intersection points
    ca = (d * d + R * R - r2 * r2) / (2 * d * R)
    cb = (d * d + r2 * r2 - R * R) / (2 * d * r2)
    ca = max(-1.0, min(1.0, ca))
    cb = max(-1.0, min(1.0, cb))
    a = math.acos(ca)                   # half-angle at the outer center
    b = math.acos(cb)                   # half-angle at the inner center
    pts = []
    # outer circle: the major arc AWAY from the bite, a .. 2pi-a
    for i in range(n + 1):
        t = a + (2 * math.pi - 2 * a) * i / n
        pts.append((cx + R * math.cos(t), cy + R * math.sin(t)))
    # inner circle: back along the arc that lies inside the outer disk
    for i in range(n + 1):
        t = math.pi + b - (2 * b) * i / n
        pts.append((cx + d + r2 * math.cos(t), cy + r2 * math.sin(t)))
    pts.append(pts[0])
    return pts


# ------------------------------------------------------------------- organic
def blob(cx, cy, r, lumps=9, amp=0.075, phase=0.0):
    """Gentle closed near-circle: a cloud puff, a stone, a head, a bush."""
    return lumpy(cx, cy, r, n=lumps, amp=amp, phase=phase)


def squircle(cx, cy, side, corner):
    """Rounded square, the iOS/app-icon silhouette."""
    h = side / 2.0
    return rrect(cx - h, cy - h, cx + h, cy + h, corner)


# ---------------------------------------------------------------- creatures
def devil_head(cx, cy, r=1.0):
    """A small horned face. Returns [jaw, horn, horn, eye, eye, grin].

    Lives in rm_sig because it is the daemon's identity, registered here
    because it is a plain reusable shape. `r` is roughly half the jaw width.
    """
    from paperdaemon.pipeline.draw import signature as rm_sig
    return rm_sig.devil_head(cx, cy, r)


register("devil-head", devil_head, tags="devil demon face horns icon daemon",
         note="six polylines; r ~ half the jaw width. Horns sweep from the "
              "CROWN and taper -- the first version put triangles on the sides "
              "and it read unmistakably as a cat.",
         source="draw/signature.py",
         notes=["A little devil head icon was asked for next to the "
                "daemon's signature.",
                "v1 read as a cat: side-mounted triangular horns are ears, and "
                "smiling arc eyes finished the job. Angled slash eyes and a "
                "narrow wedge jaw fixed it."])


# -------------------------------------------------------------------- marks
def arrow(x0, y0, x1, y1, head=34.0, spread=28.0):
    """Straight shaft plus an open V head. Returns [shaft, head]."""
    a = math.atan2(y1 - y0, x1 - x0)
    s = math.radians(spread)
    return [[(x0, y0), (x1, y1)],
            [(x1 - head * math.cos(a - s), y1 - head * math.sin(a - s)),
             (x1, y1),
             (x1 - head * math.cos(a + s), y1 - head * math.sin(a + s))]]


def tick(cx, cy, s=30.0):
    return [(cx - s, cy), (cx - s * 0.25, cy + s * 0.75), (cx + s, cy - s * 0.8)]


def cross(cx, cy, s=30.0):
    return [[(cx - s, cy - s), (cx + s, cy + s)],
            [(cx - s, cy + s), (cx + s, cy - s)]]


def bracket(x, y0, y1, depth=26.0):
    """Square bracket down a margin -- ties a note to a block of lines."""
    return [(x + depth, y0), (x, y0), (x, y1), (x + depth, y1)]


def underline(x0, x1, y, sag=6.0):
    """A slightly sagging rule; dead-straight reads as machine-drawn."""
    return [(x0 + (x1 - x0) * i / 24.0,
             y + sag * math.sin(math.pi * i / 24.0)) for i in range(25)]


# --------------------------------------------------------------------- frames
# The page border used across the coloring pages. Exactly the kind of thing
# this library is for: simple, structural, wanted again and again.
#
# THREE variants on purpose. A solved element is a starting point, not a rule --
# reaching for the same border every time is how a notebook starts looking
# machine-made. Pick to suit the page, or ask.
def frame_double(x0=-700, y0=150, x1=700, y1=2010, r=70, inset=36):
    """Rounded outer rule with a lighter inner rule. The coloring-page default."""
    return [rrect(x0, y0, x1, y1, r),
            rrect(x0 + inset, y0 + inset, x1 - inset, y1 - inset,
                    max(8, r - 22))]


def frame_single(x0=-700, y0=150, x1=700, y1=2010, r=70):
    """Just the one rule. Quieter; right when the page is already busy."""
    return [rrect(x0, y0, x1, y1, r)]


def frame_corners(x0=-700, y0=150, x1=700, y1=2010, arm=180, r=60):
    """Four corner brackets instead of a closed box -- open, modern, and it
    does not fence in artwork that wants to break the edge."""
    out = []
    for sx, cx in ((1, x0), (-1, x1)):
        for sy, cy in ((1, y0), (-1, y1)):
            out.append([(cx + sx * r, cy + sy * (r + arm)),
                        (cx + sx * r, cy + sy * r),
                        (cx + sx * (r + arm), cy + sy * r)])
    return out


def rule(x0, x1, y):
    """A plain horizontal rule -- separates an answer from what is above it."""
    return [(x0, y), (x1, y)]


for _n, _f, _t, _note in [
    ("leaf-simple", leaf_simple, "leaf plant foliage petal lens",
     "rx is half-LENGTH, ry half-THICKNESS -- swapping them is the classic bug"),
    ("leaf-veined", leaf_veined, "leaf plant foliage vein detail",
     "returns [outline, midrib, *veins]; draw veins finer than the outline"),
    ("petal", petal, "petal flower bloom", "same lens as the leaf, different name"),
    ("star-sharp", star_sharp, "star spiky night sky rating", "classic 5-point"),
    ("star-soft", star_soft, "star starfish sparkle soft rounded",
     "rounded points; reads friendlier and is right for a starfish"),
    ("sparkle", sparkle, "sparkle twinkle shine magic star",
     "returns a LIST of strokes, not one polygon"),
    ("crescent", crescent, "moon crescent night",
     "one closed polygon; the disk subtraction is done for you"),
    ("blob", blob, "cloud stone rock bush head lump organic",
     "the workhorse organic silhouette"),
    ("heart", heart, "heart love valentine", ""),
    ("squircle", squircle, "icon badge app rounded square tile",
     "app-icon silhouette; corner about 0.28 of the side looks right"),
    ("arrow", arrow, "arrow pointer direction callout",
     "returns [shaft, head]; head is an open V, not a filled triangle"),
    ("tick", tick, "tick check correct yes done", ""),
    ("cross", cross, "cross wrong no incorrect delete", "returns two strokes"),
    ("bracket", bracket, "bracket margin annotate group span", ""),
    ("underline", underline, "underline rule emphasis",
     "sags slightly on purpose -- a straight rule looks machine-drawn"),
    ("frame-double", frame_double, "frame border page rule box outline",
     "outer + lighter inner rule; the coloring-page default"),
    ("frame-single", frame_single, "frame border page rule box outline",
     "one rule only; quieter on an already-busy page"),
    ("frame-corners", frame_corners, "frame border page corner bracket open",
     "four corner brackets; lets artwork break the edge"),
    ("rule", rule, "rule line separator divider",
     "plain horizontal rule, e.g. between a question and its answer"),
]:
    register(_n, _f, _t, _note, source="draw/shapes.py")




# ---------------------------------------------------------------- the icon set
# 126 ICONS WERE SITTING UNREACHABLE. rm_icons.py holds Lucide v1.46 flattened to one path per
# icon -- cake, bird, apple, balloon, bell, bike, book, camera... -- but it was built for the
# CHART renderer (the paths are in the unit box a Vega custom symbol is drawn in) and nothing
# outside rm_chart/rm_glyphs could see it. Meanwhile `element()` searched this file's 20 shapes,
# so the model asking for a cake got "no element 'cake'" while the cake sat in the next module.
#
# The bridge already existed too: parse_path (below) turns those path strings into
# flattened points, arcs and beziers included. So this is a lookup, not a drawing job.
#
# The model's reach for emoji is not blunted: the icon / ASCII library should have all standard
# emoji to resolve to. EMOJI maps onto the same set -- the icon
# is what an emoji MEANS, drawn in the tablet's own line vocabulary.
EMOJI = {
    # --- faces and people: every smiling/neutral face is one icon; the tablet draws line art,
    # not expressions, and a "smile" that means "happy" is truer than a wrong specific face.
    "\U0001F600": "smile", "\U0001F603": "smile", "\U0001F604": "smile", "\U0001F601": "smile",
    "\U0001F642": "smile", "\U0001F60A": "smile", "\U0001F60D": "smile", "\U0001F929": "smile",
    "\U0001F60E": "smile", "\U0001F917": "smile", "\U0001F643": "smile", "\U0001F609": "smile",
    "\u263A": "smile", "\U0001F60B": "smile", "\U0001F61B": "smile", "\U0001F92A": "smile",
    "\U0001F44B": "smile", "\U0001F44D": "smile", "\U0001F44C": "smile", "\U0001F44F": "smile",
    "\U0001F47B": "ghost", "\U0001F47D": "ghost", "\U0001F480": "ghost",
    "\U0001F476": "baby", "\U0001F6BC": "baby",
    "\U0001F464": "user", "\U0001F9D1": "user", "\U0001F468": "user", "\U0001F469": "user",
    "\U0001F465": "users", "\U0001F46A": "users", "\U0001F46B": "users", "\U0001F46C": "users",
    "\U0001F3C3": "run", "\U0001F6B6": "walk", "\U0001F3CB": "dumbbell", "\U0001F4AA": "dumbbell",
    "\U0001F393": "graduation", "\U0001F3EB": "school",
    "\U0001F451": "crown", "\U0001F454": "shirt", "\U0001F455": "shirt", "\U0001F45A": "shirt",
    # --- hearts and affection
    "\u2764": "heart", "\U0001F495": "heart", "\U0001F496": "heart", "\U0001F497": "heart",
    "\U0001F498": "heart", "\U0001F499": "heart", "\U0001F49A": "heart", "\U0001F49B": "heart",
    "\U0001F49C": "heart", "\U0001F49D": "heart", "\U0001F49E": "heart", "\U0001F9E1": "heart",
    "\U0001F5A4": "heart", "\U0001F90D": "heart", "\U0001F90E": "heart", "\U0001F494": "heart",
    "\U0001F48B": "heart", "\U0001F60D": "smile",
    # --- marks, status, attention
    "\u2713": "check", "\u2714": "check", "\u2705": "check", "\u2611": "check",
    "\u274C": "cross", "\u2716": "cross", "\u2717": "cross", "\u274E": "cross", "\u2718": "cross",
    "\u26A0": "alert", "\U0001F6A8": "alert", "\u203C": "alert", "\u2757": "alert", "\u2755": "alert",
    "\u2139": "info", "\u2753": "info", "\u2754": "info", "\u2049": "info",
    "\u2B50": "star", "\U0001F31F": "star", "\u2605": "star", "\u2606": "star", "\U0001F4AB": "star",
    "\u2728": "sparkle", "\U0001F389": "party", "\U0001F38A": "party",
    "\U0001F3AF": "target", "\U0001F3C6": "trophy", "\U0001F947": "trophy", "\U0001F396": "trophy",
    "\U0001F4CC": "pin", "\U0001F4CD": "pin", "\U0001F6A9": "flag", "\U0001F3C1": "flag",
    "\u2B06": "up", "\u2B07": "down", "\u2191": "up", "\u2193": "down",
    "\u25B6": "play", "\u23F8": "pause", "\u23F5": "play",
    # --- weather and sky: the deepest part of the icon set
    "\u2600": "sun", "\U0001F31E": "sun", "\u2601": "cloud", "\U0001F325": "cloud",
    "\U0001F326": "sun_ring", "\U0001F327": "rain", "\U0001F4A7": "drop", "\u2614": "umbrella",
    "\u2602": "umbrella", "\U0001F328": "snow", "\u2744": "snow", "\u2603": "snowman",
    "\u26C4": "snowman", "\U0001F329": "storm", "\u26C8": "storm", "\u26A1": "bolt",
    "\U0001F32A": "tornado", "\U0001F32B": "fog", "\U0001F32C": "wind", "\U0001F4A8": "wind",
    "\U0001F308": "rainbow", "\U0001F305": "sunrise", "\U0001F304": "sunrise",
    "\U0001F307": "sunset", "\U0001F311": "moon", "\U0001F312": "moon", "\U0001F313": "moon",
    "\U0001F314": "moon", "\U0001F315": "moon", "\U0001F319": "moon", "\U0001F31B": "moon",
    "\U0001F30A": "waves", "\U0001F321": "thermo", "\U0001F4A6": "shower", "\U0001F6BF": "shower",
    # --- nature
    "\U0001F333": "tree", "\U0001F332": "tree", "\U0001F334": "tree", "\U0001F335": "tree",
    "\U0001F331": "leaf", "\U0001F343": "leaf", "\U0001F342": "leaf", "\U0001F340": "leaf",
    "\U0001F338": "flower", "\U0001F339": "flower", "\U0001F33A": "flower", "\U0001F33B": "flower",
    "\U0001F337": "flower", "\U0001F3F5": "flower", "\U0001F3D4": "mountain", "\u26F0": "mountain",
    "\U0001F30D": "globe", "\U0001F30E": "globe", "\U0001F30F": "globe", "\U0001F5FA": "map",
    "\U0001F383": "pumpkin", "\u267B": "recycle",
    # --- animals
    "\U0001F408": "cat", "\U0001F431": "cat", "\U0001F415": "dog", "\U0001F436": "dog",
    "\U0001F429": "dog", "\U0001F41F": "fish", "\U0001F420": "fish", "\U0001F41A": "fish",
    "\U0001F426": "bird", "\U0001F425": "bird", "\U0001F424": "bird", "\U0001F985": "bird",
    "\U0001F423": "egg", "\U0001F95A": "egg", "\U0001F373": "egg",
    # --- food and drink
    "\U0001F34E": "apple", "\U0001F34F": "apple", "\U0001F382": "cake", "\U0001F370": "cake",
    "\U0001F36C": "candy", "\U0001F36D": "candy", "\U0001F36B": "candy",
    "\u2615": "coffee", "\U0001F375": "coffee", "\U0001F35F": "utensils", "\U0001F37D": "utensils",
    "\U0001F374": "utensils", "\U0001F355": "pizza", "\U0001F356": "utensils",
    "\U0001F377": "wine", "\U0001F378": "wine", "\U0001F379": "wine", "\U0001F37A": "wine",
    "\U0001F37B": "wine", "\U0001F942": "wine",
    # --- objects, home, work
    "\U0001F3E0": "home", "\U0001F3E1": "home", "\U0001F3D8": "home",
    "\U0001F4DA": "book", "\U0001F4D6": "book", "\U0001F4D5": "book", "\U0001F4D7": "book",
    "\U0001F4D8": "book", "\U0001F4D9": "book", "\U0001F4C4": "file", "\U0001F4DD": "file",
    "\U0001F4C1": "folder", "\U0001F4C2": "folder", "\U0001F4BC": "briefcase",
    "\u270F": "pencil", "\u270E": "pencil", "\U0001F58A": "pencil", "\U0001F58C": "brush",
    "\U0001F3A8": "brush", "\u2702": "scissors", "\U0001F528": "hammer", "\U0001F527": "wrench",
    "\U0001F511": "key", "\U0001F510": "lock", "\U0001F512": "lock", "\U0001F513": "lock",
    "\U0001F4E7": "mail", "\u2709": "mail", "\U0001F4E9": "mail", "\U0001F4EB": "mail",
    "\U0001F50D": "search", "\U0001F50E": "search", "\u2699": "wrench",
    "\U0001F5D1": "trash", "\U0001F4CE": "part", "\U0001F381": "gift", "\U0001F388": "balloon",
    "\U0001F56F": "candle", "\U0001F4A1": "lightbulb", "\U0001F525": "bolt",
    "\U0001F4B0": "coin", "\U0001F4B5": "wallet", "\U0001F45B": "wallet", "\U0001F45C": "wallet",
    "\U0001F6D2": "cart", "\U0001F3AB": "ticket", "\U0001F3B2": "dice", "\U0001F9E9": "puzzle",
    "\U0001F4E6": "package", "\U0001F5A8": "printer", "\U0001F9F3": "briefcase",
    "\u26FA": "tent", "\u2693": "anchor", "\U0001F9ED": "compass", "\U0001F9F2": "target",
    # --- time and measurement
    "\u23F0": "clock", "\u231A": "clock", "\U0001F550": "clock", "\U0001F551": "clock",
    "\U0001F552": "clock", "\U0001F553": "clock", "\u23F1": "clock", "\u23F3": "clock",
    "\U0001F4C5": "calendar", "\U0001F5D3": "calendar", "\U0001F4C6": "calendar",
    "\U0001F4CA": "chart", "\U0001F4C8": "chart", "\U0001F4C9": "chart", "\U0001F5C2": "folder",
    # --- tech
    "\U0001F4BB": "laptop", "\U0001F5A5": "laptop", "\U0001F4F1": "phone", "\u260E": "phone",
    "\U0001F4DE": "phone", "\U0001F4FA": "tv", "\U0001F4F7": "camera", "\U0001F4F8": "camera",
    "\U0001F3A5": "camera", "\U0001F3A7": "headphones", "\U0001F3A4": "mic", "\U0001F50A": "speaker",
    "\U0001F508": "speaker", "\U0001F509": "speaker", "\U0001F3B5": "music", "\U0001F3B6": "music",
    "\U0001F3AE": "gamepad", "\U0001F579": "gamepad", "\U0001F5A7": "server", "\U0001F4BE": "server",
    "\U0001F6DC": "wifi", "\U0001F50B": "battery", "\U0001F5A9": "cpu",
    # --- transport
    "\U0001F697": "car", "\U0001F698": "car", "\U0001F695": "car", "\U0001F693": "car",
    "\U0001F6B2": "bike", "\u2708": "plane", "\U0001F6E9": "plane", "\U0001F680": "rocket",
    "\U0001F682": "train", "\U0001F686": "train", "\U0001F687": "train", "\U0001F69A": "truck",
    "\U0001F69B": "truck", "\U0001F6A2": "anchor",
    # --- health
    "\U0001FA7A": "stethoscope", "\U0001F489": "pill", "\U0001F48A": "pill", "\U0001F3E5": "stethoscope",
    "\U0001F634": "sleep", "\U0001F4A4": "sleep", "\U0001F6CF": "sleep",
    "\U0001F514": "bell", "\U0001F515": "bell", "\U0001F6CE": "bell",
}

# Emoji rarely arrive bare. A heart is usually U+2764 U+FE0F, a thumbs-up may carry a skin tone,
# and a family is several codepoints joined by ZERO WIDTH JOINERs. Strip the modifiers and take
# the first real codepoint, or every one of these lookups misses and the caller falls back to "-".
_VARIATION = "\ufe0e\ufe0f"
_SKIN = "".join(chr(c) for c in range(0x1F3FB, 0x1F400))
_ZWJ = "\u200d"


def resolve_emoji(ch):
    """An emoji (however it is composed) -> the icon name that means the same, or None."""
    if not ch:
        return None
    if ch in EMOJI:                       # exact match first: cheap and covers the common case
        return EMOJI[ch]
    base = ch.split(_ZWJ)[0]
    base = "".join(c for c in base if c not in _VARIATION and c not in _SKIN)
    if base in EMOJI:
        return EMOJI[base]
    for c in base:                        # a sequence whose first character carries the meaning
        if c in EMOJI:
            return EMOJI[c]
    return None


def _icon_paths(name, cx, cy, r):
    """One rm_icons entry -> [[(x, y), ...], ...] in page coordinates, centered on (cx, cy).

    The stored path lives in a unit box centered on the origin, so the whole mapping is a scale
    by `r` and a translate -- the same contract `element()` already has with its own shapes.
    """
    d = icon_path(name)
    if d is None:
        return None
    # parse_path's `scale` sets how finely curves are FLATTENED, not how big the result is: the
    # output is identical at scale 1 and scale 40, always about 1.667 units across. Passing `r`
    # to it therefore drew every icon at one and a half PIXELS -- a dot. The size has to be
    # applied here. `r` is the half-extent, so the icon comes out 2r wide.
    HALF = 0.8333                       # the stored box runs about -0.833..0.833
    k = float(r) / HALF
    out = []
    for pts, closed in parse_path(d, scale=max(1.0, float(r))):
        if len(pts) < 2:
            continue
        path = [(cx + float(x) * k, cy + float(y) * k) for x, y in pts]
        if closed and path[0] != path[-1]:
            path.append(path[0])
        out.append(path)
    return out or None


def icon_names():
    """Every name element() can resolve, this file's shapes and the icon set together."""
    try:
        from paperdaemon.pipeline.charts import icons as rm_icons
        extra = sorted(rm_icons.ICONS)
    except Exception:
        extra = []
    return sorted(set(list(REGISTRY) + extra + list(EXTRA_ICONS)))




# Added after the table above rather than inside it: ZWJ sequences and the rest of the face range.
# A family must not resolve by its first person, and a sequence like "man + laptop" means the
# laptop, not the man. The set has ONE face (smile) plus a ghost, so a cheerful face resolves and
# a grieving or furious one deliberately does NOT -- drawing a smile for a sob is worse than
# drawing nothing, and the caller can then fall back honestly instead of lying in ink.
EMOJI.update({
    "\U0001F468\u200d\U0001F469\u200d\U0001F466": "users",
    "\U0001F468\u200d\U0001F469\u200d\U0001F467": "users",
    "\U0001F469\u200d\U0001F469\u200d\U0001F466": "users",
    "\U0001F46A": "users", "\U0001F491": "users", "\U0001F46D": "users",
    "\U0001F468\u200d\U0001F4BB": "laptop", "\U0001F469\u200d\U0001F4BB": "laptop",
    "\U0001F468\u200d\U0001F373": "utensils", "\U0001F469\u200d\U0001F373": "utensils",
    "\U0001F468\u200d\U0001F3EB": "school", "\U0001F469\u200d\U0001F3EB": "school",
    "\U0001F602": "smile", "\U0001F923": "smile", "\U0001F605": "smile", "\U0001F606": "smile",
    "\U0001F607": "smile", "\U0001F608": "ghost", "\U0001F60C": "smile", "\U0001F60F": "smile",
    "\U0001F618": "heart", "\U0001F617": "heart", "\U0001F619": "heart", "\U0001F61A": "heart",
    "\U0001F61C": "smile", "\U0001F61D": "smile", "\U0001F92D": "smile", "\U0001F92B": "smile",
    "\U0001F970": "heart", "\U0001F973": "party", "\U0001F978": "smile",
    "\U0001F638": "cat", "\U0001F639": "cat", "\U0001F63A": "cat", "\U0001F63B": "cat",
    "\U0001F63C": "cat", "\U0001F640": "cat", "\U0001F63D": "cat",
})


# ---------------------------------------------------------------- the icons Lucide's set lacked
# THE TEN EMOJI A MODEL REACHES FOR MOST HAD NOTHING BEHIND THEM. rm_icons holds 126 Lucide
# outlines and no flame, no snowflake, no thumb and no face except a smile -- so a fire resolved
# to the LIGHTNING BOLT and a snowflake to a snow CLOUD. Both drew something confident and wrong,
# which is worse than drawing nothing: the reader believes it.
#
# These are drawn on Lucide's own 24-unit grid and mapped through the same (v - 12) * 0.0694
# transform, so they scale, stroke and sit on the baseline exactly like the generated set. They
# live here and not in rm_icons.py because that file is generated and says so.
EXTRA_ICONS = {
    'angry': (
        'M -0.6944 0.0000 A 0.6944 0.6944 0 1 0 0.6944 0.0000 A 0.6944 0.6944 0 1 0 -0.6944 '
        '0.0000 Z M -0.2778 0.2778 C -0.2083 0.1805 -0.1111 0.1389 0.0000 0.1389 C 0.1111 0.1389 '
        '0.2083 0.1805 0.2778 0.2778 M -0.3125 -0.2778 L -0.1389 -0.1944 M 0.3125 -0.2778 L '
        '0.1389 -0.1944 M -0.2083 -0.0694 L -0.2055 -0.0694 M 0.2083 -0.0694 L 0.2111 -0.0694'
    ),
    'eye': (
        'M -0.6944 0.0000 C -0.4861 -0.3194 -0.2500 -0.4791 0.0000 -0.4791 C 0.2500 -0.4791 '
        '0.4861 -0.3194 0.6944 0.0000 C 0.4861 0.3194 0.2500 0.4791 0.0000 0.4791 C -0.2500 '
        '0.4791 -0.4861 0.3194 -0.6944 0.0000 Z M -0.2083 0.0000 A 0.2083 0.2083 0 1 0 0.2083 '
        '0.0000 A 0.2083 0.2083 0 1 0 -0.2083 0.0000 Z'
    ),
    'flame': (
        'M -0.2430 0.1736 A 0.1736 0.1736 0 0 0 -0.0694 0.0000 C -0.0694 -0.0958 -0.1042 -0.1389 '
        '-0.1389 -0.2083 C -0.2132 -0.3569 -0.1542 -0.4896 0.0000 -0.6250 C 0.0347 -0.4514 0.1389 '
        '-0.2847 0.2778 -0.1736 C 0.4166 -0.0625 0.4861 0.0694 0.4861 0.2083 A 0.4861 0.4861 0 1 '
        '1 -0.4861 0.2083 C -0.4861 0.1285 -0.4562 0.0493 -0.4166 0.0000 A 0.1736 0.1736 0 0 0 '
        '-0.2430 0.1736 Z'
    ),
    'frown': (
        'M -0.6944 0.0000 A 0.6944 0.6944 0 1 0 0.6944 0.0000 A 0.6944 0.6944 0 1 0 -0.6944 '
        '0.0000 Z M -0.2778 0.2778 C -0.2083 0.1805 -0.1111 0.1389 0.0000 0.1389 C 0.1111 0.1389 '
        '0.2083 0.1805 0.2778 0.2778 M -0.2083 -0.2083 L -0.2055 -0.2083 M 0.2083 -0.2083 L '
        '0.2111 -0.2083'
    ),
    'hand': (
        'M 0.4166 -0.0694 L 0.4166 -0.3819 A 0.1042 0.1042 0 0 0 0.2083 -0.3819 L 0.2083 -0.4861 '
        'A 0.1042 0.1042 0 0 0 0.0000 -0.4861 L 0.0000 -0.4166 A 0.1042 0.1042 0 0 0 -0.2083 '
        '-0.4166 L -0.2083 0.0347 L -0.3194 -0.0972 A 0.1111 0.1111 0 0 0 -0.4861 0.0556 L '
        '-0.2500 0.4583 A 0.3819 0.3819 0 0 0 0.0833 0.6528 A 0.3472 0.3472 0 0 0 0.4305 0.3055 L '
        '0.4305 -0.0694 Z'
    ),
    'laugh': (
        'M -0.6944 0.0000 A 0.6944 0.6944 0 1 0 0.6944 0.0000 A 0.6944 0.6944 0 1 0 -0.6944 '
        '0.0000 Z M -0.4166 0.0694 L 0.4166 0.0694 A 0.4166 0.4166 0 0 1 -0.4166 0.0694 Z M '
        '-0.2639 -0.2500 C -0.2153 -0.3055 -0.1389 -0.3055 -0.0903 -0.2500 M 0.0903 -0.2500 C '
        '0.1389 -0.3055 0.2153 -0.3055 0.2639 -0.2500'
    ),
    'meh': (
        'M -0.6944 0.0000 A 0.6944 0.6944 0 1 0 0.6944 0.0000 A 0.6944 0.6944 0 1 0 -0.6944 '
        '0.0000 Z M -0.2778 0.2430 L 0.2778 0.2430 M -0.2083 -0.2083 L -0.2055 -0.2083 M 0.2083 '
        '-0.2083 L 0.2111 -0.2083'
    ),
    'snowflake': (
        'M 0.0000 -0.6944 L 0.0000 0.6944 M -0.6014 -0.3472 L 0.6014 0.3472 M 0.6014 -0.3472 L '
        '-0.6014 0.3472 M 0.0000 -0.4444 L -0.1667 -0.5833 M 0.0000 -0.4444 L 0.1667 -0.5833 M '
        '0.0000 0.4444 L -0.1667 0.5833 M 0.0000 0.4444 L 0.1667 0.5833 M -0.3847 -0.2222 L '
        '-0.4444 -0.4305 M -0.3847 -0.2222 L -0.5972 -0.1805 M 0.3847 0.2222 L 0.4444 0.4305 M '
        '0.3847 0.2222 L 0.5972 0.1805 M 0.3847 -0.2222 L 0.4444 -0.4305 M 0.3847 -0.2222 L '
        '0.5972 -0.1805 M -0.3847 0.2222 L -0.4444 0.4305 M -0.3847 0.2222 L -0.5972 0.1805'
    ),
    'thumbs-down': (
        'M -0.3472 0.1389 L -0.3472 -0.6250 A 0.0694 0.0694 0 0 0 -0.4166 -0.6944 L -0.5555 '
        '-0.6944 A 0.1389 0.1389 0 0 0 -0.6944 -0.5555 L -0.6944 0.0000 A 0.1389 0.1389 0 0 0 '
        '-0.5555 0.1389 Z M -0.3472 0.1389 L -0.0694 0.6944 A 0.2083 0.2083 0 0 0 0.1389 0.4514 L '
        '0.0694 0.1736 L 0.4861 0.1736 A 0.1528 0.1528 0 0 0 0.6319 -0.0139 L 0.5000 -0.5347 A '
        '0.1667 0.1667 0 0 0 0.3403 -0.6597 L -0.2083 -0.6597 A 0.1389 0.1389 0 0 0 -0.3472 '
        '-0.5208 Z'
    ),
    'thumbs-up': (
        'M -0.3472 -0.1389 L -0.3472 0.6250 A 0.0694 0.0694 0 0 1 -0.4166 0.6944 L -0.5555 0.6944 '
        'A 0.1389 0.1389 0 0 1 -0.6944 0.5555 L -0.6944 0.0000 A 0.1389 0.1389 0 0 1 -0.5555 '
        '-0.1389 Z M -0.3472 -0.1389 L -0.0694 -0.6944 A 0.2083 0.2083 0 0 1 0.1389 -0.4514 L '
        '0.0694 -0.1736 L 0.4861 -0.1736 A 0.1528 0.1528 0 0 1 0.6319 0.0139 L 0.5000 0.5347 A '
        '0.1667 0.1667 0 0 1 0.3403 0.6597 L -0.2083 0.6597 A 0.1389 0.1389 0 0 1 -0.3472 0.5208 '
        'Z'
    ),
}


def icon_path(name):
    """The path data for an icon name, from either set."""
    if name in EXTRA_ICONS:
        return EXTRA_ICONS[name]
    try:
        from paperdaemon.pipeline.charts import icons as rm_icons
        return rm_icons.ICONS.get(name)
    except Exception:
        return None


# THIRTY FACES ALL RESOLVED TO "smile" -- including the crying one. That is not a near miss, it
# is the opposite of what was written, and it went onto the page in the user's handwriting. A thumbs-up
# drew a smile and a fire drew a lightning bolt. With the icons above behind them, these now say
# what they mean; the negative faces had no entry at all before, so they drew a dash.
EMOJI.update({
    # the four that were confidently wrong
    "🔥": "flame", "❄": "snowflake", "❅": "snowflake", "❆": "snowflake",
    "👍": "thumbs-up", "👎": "thumbs-down",
    # hands
    "👋": "hand", "👏": "hand", "✋": "hand", "🖐": "hand",
    "🤚": "hand", "✊": "hand", "🙌": "hand", "🙏": "hand",
    "👌": "check", "🤝": "hand",
    # eyes
    "👀": "eye", "👁": "eye", "👅": "smile",
    # laughing, as distinct from merely smiling
    "😂": "laugh", "🤣": "laugh", "😆": "laugh", "😄": "laugh",
    "😃": "laugh", "😅": "laugh", "😁": "laugh",
    # sad
    "😢": "frown", "😭": "frown", "😞": "frown", "😔": "frown",
    "😟": "frown", "🙁": "frown", "☹": "frown", "😕": "frown",
    "😥": "frown", "😫": "frown", "😰": "frown", "😓": "frown",
    # angry
    "😠": "angry", "😡": "angry", "🤬": "angry", "😤": "angry",
    "👿": "angry", "😬": "angry",
    # flat
    "😐": "meh", "😑": "meh", "😶": "meh", "🤨": "meh",
    "🙄": "meh", "😒": "meh", "🤔": "meh", "😳": "meh",
    "😮": "meh", "😯": "meh", "😱": "frown", "😨": "frown",
})


# ---------------------------------------------------------------- SVG paths

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_TOK = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|" + _NUM)


def _arc(p0, rx, ry, phi, large, sweep, p1, n):
    """Points along an SVG arc (endpoint parameterization), excluding p0."""
    x0, y0 = p0
    x1, y1 = p1
    if rx == 0 or ry == 0 or (x0, y0) == (x1, y1):
        return [p1]
    rx, ry = abs(rx), abs(ry)
    ph = math.radians(phi)
    cp, sp = math.cos(ph), math.sin(ph)
    dx, dy = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1p = cp * dx + sp * dy
    y1p = -sp * dx + cp * dy
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x0 + x1) / 2.0
    cy = sp * cxp + cp * cyp + (y0 + y1) / 2.0

    def ang(ux, uy, vx, vy):
        d = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return d
    th1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    out = []
    for i in range(1, n + 1):
        t = th1 + dth * i / n
        xx, yy = rx * math.cos(t), ry * math.sin(t)
        out.append((cp * xx - sp * yy + cx, sp * xx + cp * yy + cy))
    out[-1] = p1
    return out


def _bezier(pts, n):
    out = []
    for i in range(1, n + 1):
        t = i / float(n)
        q = list(pts)
        while len(q) > 1:
            q = [((1 - t) * q[j][0] + t * q[j + 1][0], (1 - t) * q[j][1] + t * q[j + 1][1])
                 for j in range(len(q) - 1)]
        out.append(q[0])
    return out


def parse_path(d, scale=1.0):
    """SVG path data -> [(points, closed), ...] with curves flattened (segments sized by page px).

    `scale` IS NOT A SIZE. It only says how finely curves are flattened -- how many segments an
    arc or a bezier is worth at the size this path will be drawn. The coordinates come back in
    the path's own units either way: parse_path(ICONS['cake'], scale=1) and scale=40 return
    IDENTICAL points. Passing a radius here and expecting the output to be that big draws every
    icon as a 1.6-pixel dot. Scale the points yourself afterwards.
    """
    toks = _TOK.findall(d)
    i, cmd = 0, None
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    last_c = None
    subs, pts = [], []

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def seg_n(a, b):
        return max(3, min(28, int(math.hypot(b[0] - a[0], b[1] - a[1]) * scale / 4.0) + 3))

    def flush(closed):
        nonlocal pts
        if len(pts) >= 2:
            subs.append((pts, closed))
        pts = []
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if pts:
                    pts.append(start)
                flush(True)
                cur = start
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            x, y = num(), num()
            if rel:
                x, y = cur[0] + x, cur[1] + y
            flush(False)
            cur = start = (x, y)
            pts = [cur]
            cmd = "l" if rel else "L"
        elif c == "L":
            x, y = num(), num()
            if rel:
                x, y = cur[0] + x, cur[1] + y
            cur = (x, y)
            pts.append(cur)
        elif c == "H":
            x = num()
            cur = ((cur[0] + x) if rel else x, cur[1])
            pts.append(cur)
        elif c == "V":
            y = num()
            cur = (cur[0], (cur[1] + y) if rel else y)
            pts.append(cur)
        elif c in ("C", "S"):
            if c == "C":
                c1 = (num(), num())
                c2 = (num(), num())
            else:
                c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
                c2 = (num(), num())
            p = (num(), num())
            if rel:
                if c == "C":
                    c1 = (cur[0] + c1[0], cur[1] + c1[1])
                c2 = (cur[0] + c2[0], cur[1] + c2[1])
                p = (cur[0] + p[0], cur[1] + p[1])
            pts.extend(_bezier([cur, c1, c2, p], seg_n(cur, p)))
            last_c = c2
            cur = p
            continue
        elif c in ("Q", "T"):
            if c == "Q":
                c1 = (num(), num())
            else:
                c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
            p = (num(), num())
            if rel:
                if c == "Q":
                    c1 = (cur[0] + c1[0], cur[1] + c1[1])
                p = (cur[0] + p[0], cur[1] + p[1])
            pts.extend(_bezier([cur, c1, p], seg_n(cur, p)))
            last_c = c1
            cur = p
            continue
        elif c == "A":
            rx, ry, phi, large, sweep = num(), num(), num(), int(num()), int(num())
            p = (num(), num())
            if rel:
                p = (cur[0] + p[0], cur[1] + p[1])
            pts.extend(_arc(cur, rx, ry, phi, large, sweep, p, seg_n(cur, p) + 4))
            cur = p
        else:
            i += 1
        last_c = None if c not in ("C", "S", "Q", "T") else last_c
    flush(False)
    return subs
