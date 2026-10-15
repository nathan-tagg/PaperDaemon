r"""People parts for the face kit (games/faces): heads, hair, hats and face parts for a cast of people.

    heads       long, heart, jowly, child
    hair        bald, buzz, afro, curly, long_straight, bob, ponytail, messy_bun, spiky, comb_over, swoop,
                big_curls, big_wig, fade, gray_crop            (HAIR_FRONT, plus HAIR_BACK where hair falls)
    hats        wizard_hat, hard_hat, boonie_hat, captain_hat, fedora, witch_hat_small      (HAIR_FRONT)
    face        mustache, goatee, short_beard, sideburns, small_glasses, monocle, eyepatch, scar, freckles,
                gold_tooth, lipstick, lashes, bags, broken_nose, bell_pin

Every part fits itself to the head's anchors (ears, top, brow line, eyes, nose, mouth, chin), so any hair or
hat sits on any head. Hats stop above the brows; the brows are drawn last anyway.

A face part does not know the emotion, and the core draws face parts BEFORE the mouth. The parts that must
follow the feeling -- a mustache lying over the mouth and lifting with a smile, lipstick on whatever shape
the mouth takes, a gold tooth that shows in an open mouth, a close beard whose opening fits the mouth,
lashes on whatever shape the eyes take -- hook a LAYER onto the mouth or the eyes instead: the part sets the
anchors' mouth_style / eyes_style to "folk_mouth" / "folk_eyes" (keeping any style the head already had,
a child's small mouth or a beak), and that style draws the mouth or eyes and then each layer, knowing the
emotion. (With a fixed_grin the core draws its grin in place of any mouth style, so mouth layers are lost.)
"""
import math
import re
from paperdaemon.pipeline.games import faces as F
from paperdaemon.pipeline.games.faces import INK, _c, _e, _p, _shade, register
from paperdaemon.pipeline.games.faces import INK, _c, _p, _shade, register
from paperdaemon.pipeline.games.faces import INK, _p, _shade, register
import zlib
from paperdaemon.pipeline.games.faces import BODIES, INK, _c, _e, _p, _shade, _star, register

SKIN = "#E1AE86"


# ---------------------------------------------------------------- layers on the eyes and the mouth
def _layer(a, slot, order, fn):
    """Hook fn(emotion, svg so far, marks, base) -> svg onto the eyes or the mouth ("eyes" / "mouth"),
    where base is the eyes or mouth as drawn; lower order first. A layer that goes under prepends, one
    that goes over appends. Returns "" so a part can hand back its result directly."""
    style = slot + "_style"
    if a.get(style) != "folk_" + slot:
        a["folk_prev_" + slot] = a.get(style)
        a[style] = "folk_" + slot
    a.setdefault("folk_layers_" + slot, []).append((order, fn))
    return ""


def _run_layers(a, slot, e, base, marks):
    svg = base
    for _, fn in sorted(a.get("folk_layers_" + slot, []), key=lambda t: t[0]):
        svg = fn(e, svg, marks, base)
    return svg


@register(F.EYES, "folk_eyes")
def _eyes_layers(e, a, light, marks):
    prev = F.EYES.get(a.get("folk_prev_eyes"))
    return _run_layers(a, "eyes", e, prev(e, a, light, marks) if prev else F._eyes(e, a, light, marks), marks)


@register(F.MOUTHS, "folk_mouth")
def _mouth_layers(e, a, fill, marks):
    prev = F.MOUTHS.get(a.get("folk_prev_mouth"))
    return _run_layers(a, "mouth", e, prev(e, a, fill, marks) if prev else F._mouth(e, a, fill, marks), marks)


@register(F.EYES, "folk_big")
def _big_eyes(e, a, light, marks):
    """A child's eyes: the usual eyes, drawn bigger about each eye's own center."""
    s, y = a.get("eye_scale", 1.25), a["ey"]
    a2 = dict(a, lx=100 + (a["lx"] - 100) / s, rx=100 + (a["rx"] - 100) / s)
    return ('<g transform="translate(100 %s) scale(%s) translate(-100 -%s)">' % (y, s, y)
            + F._eyes(e, a2, light, marks) + "</g>")


@register(F.MOUTHS, "folk_small")
def _small_mouth(e, a, fill, marks):
    """A child's mouth: the usual mouth, a little smaller."""
    x, y, s = a["mx"], a["my"], a.get("mouth_scale", 0.84)
    return ('<g transform="translate(%s %s) scale(%s) translate(-%s -%s)">' % (x, y, s, x, y)
            + F._mouth(e, a, fill, marks) + "</g>")


# ---------------------------------------------------------------- heads
def _head(d, ears, skin, a, extra=""):
    return ears + _p(d, skin, INK, 5) + extra, d, a, _shade(skin, 0.62)


def _ears(L, R, y, rx=8, ry=12, skin=SKIN):
    return _e(L, y, rx, ry, skin, INK, 4) + _e(R, y, rx, ry, skin, INK, 4)


@register(F.HEADS, "long")
def _long(skin, look):
    """A long, narrow face: a high forehead, a long jaw."""
    d = "M 54 104 Q 54 38 100 38 Q 146 38 146 104 L 145 142 Q 141 180 100 184 Q 59 180 55 142 Z"
    a = dict(lx=81, rx=119, ey=108, by=90, mx=100, my=158, nx=100, ny=134,
             cheeks=((71, 138), (129, 138)), temple=(140, 80), top=38, ears=(53, 147, 114), chin=184,
             jaw="M 54 110 L 55 142 Q 59 180 100 184 Q 141 180 145 142 L 146 110")
    return _head(d, _ears(53, 147, 114, skin=skin), skin, a)


@register(F.HEADS, "heart")
def _heart(skin, look):
    """Wide at the cheekbones, tapering to a pointed chin."""
    d = ("M 42 102 Q 42 44 100 44 Q 158 44 158 102 Q 158 130 140 152 Q 122 172 100 180 "
         "Q 78 172 60 152 Q 42 130 42 102 Z")
    a = dict(lx=78, rx=122, ey=108, by=90, mx=100, my=150, nx=100, ny=129,
             cheeks=((64, 130), (136, 130)), temple=(148, 80), top=44, ears=(43, 157, 110), chin=180,
             jaw="M 42 104 Q 42 130 60 152 Q 78 172 100 180 Q 122 172 140 152 Q 158 130 158 104")
    return _head(d, _ears(43, 157, 110, skin=skin), skin, a)


@register(F.HEADS, "jowly")
def _jowly(skin, look):
    """Older and heavier: the jaw widens into jowls, a fold under the chin."""
    d = ("M 48 104 Q 48 48 100 48 Q 152 48 152 104 L 153 128 Q 164 158 148 174 Q 128 186 100 186 "
         "Q 72 186 52 174 Q 36 158 47 128 Z")
    crease = _shade(skin, 0.7)
    folds = (_p("M 70 142 Q 62 156 68 170 M 130 142 Q 138 156 132 170", "none", crease, 3)
             + _p("M 84 180 Q 100 185 116 180", "none", crease, 3))
    a = dict(lx=80, rx=120, ey=108, by=90, mx=100, my=154, nx=100, ny=131,
             cheeks=((68, 134), (132, 134)), temple=(146, 82), top=48, ears=(47, 153, 112), chin=186,
             jaw="M 48 106 L 47 128 Q 36 158 52 174 Q 72 186 100 186 Q 128 186 148 174 Q 164 158 153 128 L 152 106")
    return _head(d, _ears(47, 153, 112, skin=skin), skin, a, folds)


@register(F.HEADS, "child")
def _child(skin, look):
    """A child: a round face, the features low on it, big eyes, a small mouth."""
    d = "M 44 120 Q 44 60 100 60 Q 156 60 156 120 Q 156 174 100 176 Q 44 174 44 120 Z"
    a = dict(lx=79, rx=121, ey=124, by=105, mx=100, my=156, nx=100, ny=141,
             cheeks=((64, 146), (136, 146)), temple=(148, 94), top=60, ears=(45, 155, 126), chin=176,
             jaw="M 44 122 Q 44 174 100 176 Q 156 174 156 122",
             eyes_style="folk_big", mouth_style="folk_small", eye_scale=1.25)
    return _head(d, _ears(45, 155, 126, 9, 12, skin), skin, a)


# ---------------------------------------------------------------- hair helpers
def _geo(a):
    L, R, ye = a["ears"]
    return L, R, ye, a["top"], a["by"]


def _dome(a, o=2, y0=None):
    """The crown of the head, o px outside its outline: an open path from the left side over the top."""
    L, R, ye, T, B = _geo(a)
    sl, sr = L - 1 - o, R + 1 + o
    y0 = ye - 6 if y0 is None else y0
    return sl, sr, y0, "M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f" % (
        sl, y0, sl, T - o, T - o, sr, T - o, sr, y0)


def _hairline(sl, sr, y0, hl, inset=6, move=False):
    """From the right temple along the hairline to the left temple: continues a _dome path, or with
    move=True starts a path of its own."""
    return " %s %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f" % (
        "M" if move else "L", sr - inset, y0, sr - inset, hl, hl, sl + inset, hl, sl + inset, y0)


def _qpts(p0, p1, p2, n):
    """n + 1 points along a quadratic curve."""
    out = []
    for i in range(n + 1):
        t = i / float(n)
        out.append(((1 - t) ** 2 * p0[0] + 2 * t * (1 - t) * p1[0] + t * t * p2[0],
                    (1 - t) ** 2 * p0[1] + 2 * t * (1 - t) * p1[1] + t * t * p2[1]))
    return out


def _ring(cx, cy, rx, ry, n, t0=0.0, t1=360.0):
    """Points on an ellipse, clockwise on screen from angle t0 (0 = right, 90 = down)."""
    full = abs(t1 - t0) >= 360
    return [(cx + rx * math.cos(math.radians(t0 + (t1 - t0) * i / n)),
             cy + ry * math.sin(math.radians(t0 + (t1 - t0) * i / n))) for i in range(n if full else n + 1)]


def _bumps(pts, r=None, close=True, start=True):
    """Curls: a circular arc bulging outward between each pair of points (points run clockwise)."""
    d = ("M %.1f %.1f" % pts[0]) if start else ""
    seq = list(pts[1:]) + ([pts[0]] if close else [])
    prev = pts[0]
    for x, y in seq:
        rr = r or 0.62 * math.hypot(x - prev[0], y - prev[1])
        d += " A %.1f %.1f 0 0 1 %.1f %.1f" % (rr, rr, x, y)
        prev = (x, y)
    return d + (" Z" if close else "")


def _hairline_pts(sl, sr, y0, hl, n, inset=6):
    """Points along the hairline, right temple to left temple."""
    return (_qpts((sr - inset, y0), (sr - inset, hl), (100, hl), n // 2)
            + _qpts((100, hl), (sl + inset, hl), (sl + inset, y0), n // 2)[1:])


def _swirls(pts, col, w=2.5):
    """Little C-shaped curl marks."""
    return _p(" ".join("M %.1f %.1f q -5 -1 -5 4 q 1 5 6 4" % (x, y) for x, y in pts), "none", col, w)


def _shine(col):
    """A highlight that shows on dark hair and on light hair."""
    h = col.lstrip("#")
    lum = 0.3 * int(h[0:2], 16) + 0.59 * int(h[2:4], 16) + 0.11 * int(h[4:6], 16)
    return _shade(col, 1.6) if lum < 150 else _shade(col, 0.74)


# ---------------------------------------------------------------- hair: short
@register(F.HAIR_FRONT, "bald")
def _bald(part, a):
    """A bare crown with a shine; a color draws the fringe of hair left above the ears."""
    L, R, ye, T, B = _geo(a)
    out = (_p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (L + 20, T + 18, L + 25, T + 8, L + 42, T + 6),
              "none", "#FFFFFF", 4.5, ' opacity="0.6"')
           + _c(L + 16, T + 27, 2.4, "#FFFFFF", None, extra=' opacity="0.6"'))
    if part.get("color"):                    # tufts above the ears, curling out past the head's sides
        col = part["color"]
        for s, x in ((1, L), (-1, R)):
            pts = [(x + 12 * s, ye - 30), (x + 2 * s, ye - 26), (x - 3 * s, ye - 14), (x - 2 * s, ye - 2)]
            if s < 0:
                pts = pts[::-1]
            tuft = _bumps(pts, close=False)
            out += _p(tuft + " L %.1f %.1f L %.1f %.1f Z" % ((x + 7 * s, ye - 6, x + 14 * s, ye - 28) if s > 0 else
                                                              (x + 14 * s, ye - 28, x + 7 * s, ye - 6)), col, INK, 3)
    return out


def _short(part, a, default, o, hl_up, edge_w, zig=False):
    """Hair cropped close: the crown down to a rounded hairline, a texture of short strokes."""
    col = part.get("color", default)
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, outer = _dome(a, o)
    hl = B - hl_up
    if zig:                                  # a cropped, uneven hairline
        pts = _hairline_pts(sl, sr, y0, hl, 12, 5)
        inner = " L %.1f %.1f" % pts[0] + "".join(
            " L %.1f %.1f L %.1f %.1f" % ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + 3.5, q[0], q[1])
            for p, q in zip(pts, pts[1:])) + " Z"
    else:
        inner = _hairline(sl, sr, y0, hl, 5) + " Z"
    ticks = " ".join("M %.1f %.1f l %.1f -4" % (x, y, 2 if x > 100 else -2)
                     for x, y in ((70, T + 14), (86, T + 8), (100, T + 12), (114, T + 8), (130, T + 14),
                                  (78, T + 24), (122, T + 24)))
    return _p(outer + inner, col, INK, edge_w) + _p(ticks, "none", _shine(col), 2.2)


@register(F.HAIR_FRONT, "buzz")
def _buzz(part, a):
    """Clipped to the scalp: the head keeps its own outline, the hairline is a soft, dotted edge."""
    col = part.get("color", "#3A2A20")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, outer = _dome(a, 0)
    hl = B - 12
    dots = "".join(_p(_dome(a, -k, y0=B - 10 - k)[3], "none", _shine(col), 2.2,
                      ' stroke-dasharray="0.1 7" stroke-dashoffset="%d"' % (k % 5)) for k in (7, 15, 23))
    return (_p(outer + _hairline(sl, sr, y0, hl, 5) + " Z", col, None, extra=' opacity="0.78"')
            + _p(_hairline(sl, sr, y0, hl, 5, move=True), "none", _shade(col, 0.8), 3,
                 ' stroke-dasharray="2 3.2"')
            + dots + _p(outer, "none", INK, 5))


@register(F.HAIR_FRONT, "gray_crop")
def _gray_crop(part, a):
    return _short(part, a, "#B9B9BE", 3, 14, 4.5, zig=True)


@register(F.HAIR_FRONT, "fade")
def _fade(part, a):
    """Faded sides, a sharp line-up, a little length on top."""
    col = part.get("color", "#1E1B1A")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, outer = _dome(a, 1)
    hl = B - 13
    gid = "folk-fade-" + col.lstrip("#")      # full on top, fading down the sides
    grad = ('<defs><linearGradient id="%s" gradientUnits="userSpaceOnUse" x1="0" y1="%.1f" x2="0" y2="%.1f">'
            '<stop offset="0" stop-color="%s"/><stop offset="0.3" stop-color="%s"/>'
            '<stop offset="1" stop-color="%s" stop-opacity="0.18"/></linearGradient></defs>' % (gid, T, y0, col, col, col))
    return (grad + _p(outer + _hairline(sl, sr, y0, hl, 5) + " Z", "url(#%s)" % gid, None)
            + _p(_hairline(sl, sr, y0, hl, 5, move=True), "none", col, 2.5, ' opacity="0.8"')
            + _p(outer, "none", INK, 5))


# ---------------------------------------------------------------- hair: curls
@register(F.HAIR_BACK, "afro")
def _afro_back(part, a):
    col = part.get("color", "#1E1B1A")
    L, R, ye, T, B = _geo(a)
    s = part.get("size", 1.0)
    top, bot = T - 22 * s, ye + 6
    out = _p(_bumps(_ring(100, (top + bot) / 2, (R - L) / 2 + 16 * s, (bot - top) / 2, 15, 180, 540)), col, INK, 5)
    if part.get("temples"):                  # gray at the temples, where the afro shows beside the face
        for s2, x in ((1, L), (-1, R)):
            out += _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
                x + 2 * s2, ye - 34, x - 16 * s2, ye - 26, x - 14 * s2, ye + 2, x - 4 * s2, ye - 8, x + 2 * s2, ye - 34),
                part["temples"], None)
    return out


@register(F.HAIR_FRONT, "afro")
def _afro(part, a):
    """A rounded afro (part["size"] scales it; part["temples"] colors the temples, e.g. gray)."""
    col = part.get("color", "#1E1B1A")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, outer = _dome(a, 6)
    pts = _hairline_pts(sl, sr, y0, B - 14, 10, 7)
    out = _p(outer + " L %.1f %.1f" % pts[0] + _bumps(pts, close=False, start=False) + " Z", col, None)
    out += _p(_bumps(pts, close=False), "none", INK, 4)
    return out + _swirls([(78, T + 6), (102, T + 2), (124, T + 8), (66, T + 22), (136, T + 22)], _shine(col))


@register(F.HAIR_BACK, "curly")
def _curly_back(part, a):
    L, R, ye, T, B = _geo(a)
    top, bot = T - 10, ye + 26
    return _p(_bumps(_ring(100, (top + bot) / 2, (R - L) / 2 + 10, (bot - top) / 2, 16, 180, 540)),
              part.get("color", "#2E2019"), INK, 4.5)


@register(F.HAIR_FRONT, "curly")
def _curly(part, a):
    """A cap of tight curls, curled at the hairline too; part["streak"] adds a streak of another color."""
    col = part.get("color", "#2E2019")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, _ = _dome(a, 4)
    top = _qpts((sl, y0), (sl, T - 8), (100, T - 8), 5) + _qpts((100, T - 8), (sr, T - 8), (sr, y0), 5)[1:]
    line = _hairline_pts(sl, sr, y0, B - 14, 10, 6)
    out = _p(_bumps(top, close=False) + " L %.1f %.1f" % line[0] + _bumps(line, close=False, start=False) + " Z",
             col, INK, 4.5)
    if part.get("streak"):
        out += _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (96, T - 2, sl + 14, T + 4, sl + 8, B - 8), "none",
                  part["streak"], 7)
    return out + _swirls([(80, T + 8), (104, T + 4), (126, T + 10), (68, T + 24), (138, T + 26)], _shine(col))


# ---------------------------------------------------------------- hair: long, bobbed, tied up
@register(F.HAIR_BACK, "long_straight")
def _long_back(part, a):
    col = part.get("color", "#3A2A20")
    L, R, ye, T, B = _geo(a)
    sl, sr = L - 5, R + 5
    out = _p("M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f L %.1f 204 L %.1f 204 Z" % (
        sl, ye, sl - 2, T - 6, T - 6, sr + 2, T - 6, sr, ye, sr + 8, sl - 8), col, INK, 5)
    if part.get("streak"):
        out += _p("M %.1f %.1f L %.1f 204" % (sr - 3, ye - 10, sr + 2), "none", part["streak"], 7)
    return out


@register(F.HAIR_FRONT, "long_straight")
def _long_straight(part, a):
    """Long hair parted in the middle, falling past the ears; part["streak"] colors a streak on one side."""
    col = part.get("color", "#3A2A20")
    L, R, ye, T, B = _geo(a)
    sl, sr, T2 = L - 4, R + 4, T - 4
    out = ""
    for s, x in ((1, sl), (-1, sr)):
        out += _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f L %.1f %.1f L %.1f %.1f L %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
            100 - 2 * s, T2, x, T2, x, ye + 4, x, ye + 34, x + 13 * s, ye + 34, x + 13 * s, B,
            x + 16 * s, T + 10, 100 - 2 * s, T + 6), col, INK, 4.5)
    if part.get("streak"):                   # down the face side of the right-hand curtain
        out += _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f L %.1f %.1f" % (
            106, T + 1, sr - 13, T + 8, sr - 9, B + 2, sr - 9, ye + 30), "none", part["streak"], 7)
    return out + _p("M 100 %.1f L 100 %.1f" % (T2 + 2, T + 6), "none", _shade(col, 0.7), 2.5)


@register(F.HAIR_BACK, "bob")
def _bob_back(part, a):
    L, R, ye, T, B = _geo(a)
    sl, sr = L - 6, R + 6
    return _p("M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f Q 100 %.1f %.1f %.1f Z" % (
        sl, ye + 32, sl - 8, T - 8, T - 8, sr + 8, T - 8, sr, ye + 32, ye + 40, sl, ye + 32),
        part.get("color", "#1E1B1A"), INK, 5)


@register(F.HAIR_FRONT, "bob")
def _bob(part, a):
    """A chin-length bob with blunt bangs, kept above the brows."""
    col = part.get("color", "#1E1B1A")
    L, R, ye, T, B = _geo(a)
    sl, sr, bang = L - 5, R + 5, B - 16
    d = ("M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f L %.1f %.1f L %.1f %.1f Q %.1f %.1f %.1f %.1f "
         "Q 100 %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f L %.1f %.1f Z") % (
        sl, ye + 32, sl - 6, T - 6, T - 6, sr + 6, T - 6, sr, ye + 32, sr - 11, ye + 32,
        sr - 11, bang + 14, sr - 12, bang, sr - 24, bang, bang + 3, sl + 24, bang, sl + 12, bang, sl + 11, bang + 14,
        sl + 11, ye + 32)
    return (_p(d, col, INK, 4.5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f" % (sl + 22, T + 6, T - 1, sr - 22, T + 6), "none", _shine(col), 3))


@register(F.HAIR_BACK, "ponytail")
def _ponytail_back(part, a):
    col = part.get("color", "#1E1B1A")
    L, R, ye, T, B = _geo(a)
    return _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
        R - 14, T + 10, R + 20, T + 4, R + 22, T + 36, R + 24, ye + 30, R + 10, ye + 62,
        R + 12, ye + 28, R + 2, ye - 4, R - 6, T + 30, R - 14, T + 10), col, INK, 4.5)


@register(F.HAIR_FRONT, "ponytail")
def _ponytail(part, a):
    """Pulled back tight into a ponytail (the tail hangs behind, on the right); part["tie"] colors the tie."""
    col = part.get("color", "#1E1B1A")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, outer = _dome(a, 2)
    return (_p(outer + _hairline(sl, sr, y0, B - 14, 6) + " Z", col, INK, 4.5)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (
                84, B - 16, 96, T + 8, R - 12, T + 14, 70, B - 10, 84, T + 18, R - 12, T + 22), "none", _shine(col), 2.5)
            + _e(R - 7, T + 17, 5, 7, part.get("tie", "#C0392B"), INK, 3))


def _pencil(x, y, length):
    """A yellow pencil lying along +x from (x, y), point first; drawn in the caller's rotated frame."""
    return ('<rect x="%.1f" y="%.1f" width="%.1f" height="8" rx="1.5" fill="#F2C230" stroke="%s" stroke-width="2.5"/>'
            % (x - length, y - 4, length, INK)
            + _p("M %.1f %.1f L %.1f %.1f L %.1f %.1f Z" % (x, y - 4, x + 9, y, x, y + 4), "#F1D9B5", INK, 2.5)
            + _c(x + 7, y, 1.6, INK, None))


@register(F.HAIR_FRONT, "messy_bun")
def _messy_bun(part, a):
    """A bun piled on top, loose strands at the temples; part["pencil"]: true sticks a pencil through it."""
    col = part.get("color", "#6B3A24")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, outer = _dome(a, 2)
    x, y = 104, T - 12
    rot = '<g transform="rotate(-28 %.1f %.1f)">' % (x, y)
    out = ""
    if part.get("pencil"):                   # the pencil's far end, behind the bun
        out += rot + _pencil(x + 26, y, 58) + '<rect x="%.1f" y="%.1f" width="8" height="8" rx="1.5" ' \
            'fill="#E88A9A" stroke="%s" stroke-width="2.5"/>' % (x - 40, y - 4, INK) + "</g>"
    out += _p(_bumps(_ring(x, y, 21, 16, 7, 150, 510)), col, INK, 4)
    out += _p("M %.1f %.1f q -9 -7 -2 -14 M %.1f %.1f q 12 -2 9 -14 M %.1f %.1f q -5 7 5 12" % (
        x - 4, y - 14, x + 14, y - 7, x - 12, y + 2), "none", _shade(col, 0.66), 2.5)
    if part.get("pencil"):                   # its point comes out in front: it goes through the bun
        out += rot + _pencil(x + 26, y, 22) + "</g>"
    out += _p(outer + _hairline(sl, sr, y0, B - 14, 6) + " Z", col, INK, 4.5)
    out += _p("M %.1f %.1f q -6 8 -2 18 M %.1f %.1f q 6 8 2 18" % (sl + 8, B - 12, sr - 8, B - 12), "none", col, 3)
    return out + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (78, B - 16, 92, T + 6, 104, T + 2), "none", _shine(col), 2.5)


# ---------------------------------------------------------------- hair: styled
@register(F.HAIR_FRONT, "spiky")
def _spiky(part, a):
    """Anime spikes all over the crown, spiky bangs; part["tip"] colors the tips (red, blond...)."""
    col, tip = part.get("color", "#1E1B1A"), part.get("tip")
    L, R, ye, T, B = _geo(a)
    cx, cy = 100.0, ye - 8.0
    rx, ry = (R - L) / 2.0 + 2, cy - T + 2

    def at(deg, grow=0.0):
        t = math.radians(deg)
        return cx + (rx + grow) * math.cos(t), cy + (ry + grow) * math.sin(t)
    spikes = []                              # (left base, tip, right base), clockwise over the crown
    for deg, length in ((194, 17), (216, 23), (238, 27), (260, 29), (282, 29), (304, 26), (326, 22), (347, 16)):
        spikes.append((at(deg - 11), at(deg + 7, length), at(deg + 11)))
    hl = B - 20
    bangs = []                               # bangs hanging onto the forehead, tips kept above the brows
    for bx in (132, 114, 96, 78):
        bangs.append(((bx + 9, hl), (bx - 2, B - 9), (bx - 8, hl)))
    d = "M %.1f %.1f" % at(180)
    for l, t, r in spikes:
        d += " L %.1f %.1f L %.1f %.1f L %.1f %.1f" % (l + t + r)
    d += " L %.1f %.1f L %.1f %.1f" % (at(0) + (R - 6, hl))
    for l, t, r in bangs:
        d += " L %.1f %.1f L %.1f %.1f L %.1f %.1f" % (l + t + r)
    d += " L %.1f %.1f Z" % (L + 6, hl)
    out = _p(d, col, INK, 4.5)
    if tip:
        tri = ""
        for (l, t, r), k in [(s, 0.42) for s in spikes] + [(b, 0.4) for b in bangs]:
            tri += "M %.1f %.1f L %.1f %.1f L %.1f %.1f Z " % (
                l[0] + (t[0] - l[0]) * k, l[1] + (t[1] - l[1]) * k, t[0], t[1],
                r[0] + (t[0] - r[0]) * k, r[1] + (t[1] - r[1]) * k)
        out += _p(tri, tip, None) + _p(d, "none", INK, 4.5)
    return out + _p("M %.1f %.1f L %.1f %.1f M %.1f %.1f L %.1f %.1f" % (
        84, T + 6, 94, T - 4, 112, T + 8, 124, T - 2), "none", _shine(col), 2.5)


@register(F.HAIR_FRONT, "comb_over")
def _comb_over(part, a):
    """A few long strands combed up from a low part, over a bald crown; the rest above the ears."""
    col = part.get("color", "#E6E3DC")
    L, R, ye, T, B = _geo(a)
    out = _bald({"color": col}, a)
    edge = _shade(col, 0.62)
    for k in range(3):                       # thin, spaced, tapering: strands, not a band
        d = "M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f" % (
            L + 8, B - 4 - 9 * k, 70 - 4 * k, T + 2 + 7 * k, 100, T + 1 + 8 * k, 126, T + 1 + 8 * k, R - 14 + 3 * k,
            T + 20 + 9 * k)
        out += _p(d, "none", edge, 5) + _p(d, "none", col, 2.4)
    return out


@register(F.HAIR_FRONT, "swoop")
def _swoop(part, a):
    """A swoop: short sides, a tall wave on top swept over to one side."""
    col = part.get("color", "#D8B45A")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, outer = _dome(a, 0)
    wave = ("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f "
            "Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z") % (
        sl + 4, T + 30, sl - 2, T - 4, 72, T - 13, 106, T - 24, 142, T - 12, 164, T - 1, sr - 2, T + 28,
        sr - 10, T + 14, 136, T + 10, 114, T + 8, 102, B - 18, 86, B - 26, 72, B - 20, 56, B - 16, sl + 4, T + 30)
    return (_p(outer + _hairline(sl, sr, y0, B - 12, 5) + " Z", col, None, extra=' opacity="0.45"')
            + _p(wave, col, INK, 4.5)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (
                74, T - 2, 104, T - 14, 136, T - 2, 88, T + 12, 112, T + 2, 132, T + 10), "none", _shine(col), 2.5))


@register(F.HAIR_BACK, "big_curls")
def _big_curls_back(part, a):
    L, R, ye, T, B = _geo(a)
    top, bot = T - 18, ye + 52
    col = part.get("color", "#8E3B1F")
    return (_p(_bumps(_ring(100, (top + bot) / 2, (R - L) / 2 + 28, (bot - top) / 2, 17, 180, 540)), col, INK, 5)
            + _swirls([(40, ye - 10), (160, ye - 10), (36, ye + 26), (166, ye + 26)], _shade(col, 0.7)))


@register(F.HAIR_FRONT, "big_curls")
def _big_curls(part, a):
    """Voluminous curls to the shoulders, curled bangs swept to one side."""
    col = part.get("color", "#8E3B1F")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, outer = _dome(a, 8)
    pts = _hairline_pts(sl, sr, y0, B - 16, 10, 5)
    return (_p(outer + " L %.1f %.1f" % pts[0] + _bumps(pts, close=False, start=False) + " Z", col, None)
            + _p(_bumps(pts, close=False), "none", INK, 4)
            + _swirls([(76, T + 4), (100, T), (124, T + 4), (62, T + 20), (140, T + 22), (90, T + 18)], _shine(col)))


@register(F.HAIR_BACK, "big_wig")
def _big_wig_back(part, a):
    L, R, ye, T, B = _geo(a)
    top, bot = T - 40, ye + 78
    col = part.get("color", "#F3EEDC")
    return (_p(_bumps(_ring(100, (top + bot) / 2, (R - L) / 2 + 42, (bot - top) / 2, 18, 180, 540)), col, INK, 5)
            + _swirls([(34, ye - 20), (166, ye - 20), (30, ye + 18), (170, ye + 18), (40, T), (160, T)],
                      _shade(col, 0.78), 3))


@register(F.HAIR_FRONT, "big_wig")
def _big_wig(part, a):
    """A huge platinum drag wig: a bouffant crown, a great swoop of bangs, a rhinestone clip."""
    col = part.get("color", "#F3EEDC")
    L, R, ye, T, B = _geo(a)
    sl, sr, y0, _ = _dome(a, 4)
    bang = ("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f "
            "Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z") % (
        sl + 2, ye - 2, sl - 8, T - 16, 96, T - 20, 158, T - 20, sr + 6, T + 32, sr + 4, ye - 4, sr - 5, ye + 8,
        sr - 12, T + 30, 134, T + 22, 112, T + 16, 98, B - 20, 72, B - 18, sl + 2, ye - 2)
    curl = _shade(col, 0.78)
    return (_p(bang, col, INK, 4.5)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (
                70, T + 2, 104, T - 14, 146, T + 8, 80, T + 16, 110, T + 4, 136, T + 18), "none", curl, 3)
            + F._star(sr - 14, T + 24, 7, "#BFE6F5", INK, 1.8))


# ---------------------------------------------------------------- hats: brims stop above the brows
def _star5(x, y, r, fill, stroke=INK, width=1.6):
    pts = []
    for i in range(10):
        rr, t = (r if i % 2 == 0 else r * 0.45), math.radians(-90 + 36 * i)
        pts.append("%.1f %.1f" % (x + rr * math.cos(t), y + rr * math.sin(t)))
    return _p("M " + " L ".join(pts) + " Z", fill, stroke, width)


@register(F.HAIR_FRONT, "wizard_hat")
def _wizard_hat(part, a):
    """A tall wizard's hat, crooked at the top, its tip bent over to the right at (130, 11); stars on it,
    one of them exactly where the "twinkle" mark draws (twinkle_x/_y, else 132, max(12, top - 14)), so a
    twinkle makes that star glimmer."""
    col = part.get("color", "#2F3F8F")
    L, R, ye, T, B = _geo(a)
    yb = B - 14
    tx, ty = 132, 12                          # the tip, whatever the head
    kx, ky = 88, T - 10                       # where the cone bends over toward the tip
    crown = ("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f "
             "Q %.1f %.1f %.1f %.1f Z") % (
        L + 2, yb - 2, L + 6, T + 2, kx, ky, 104, ky - 4, tx, ty,
        144, 22, R - 1, T + 10, R + 1, T + 26, R - 3, yb - 2)
    band = "M %.1f %.1f Q 100 %.1f %.1f %.1f L %.1f %.1f Q 100 %.1f %.1f %.1f Z" % (
        L + 3, yb - 3, yb - 17, R - 3, yb - 3, R - 3, yb - 12, yb - 26, L + 3, yb - 12)
    brim = ("M %.1f %.1f Q 100 %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q 100 %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z") % (
        L - 14, yb, yb - 20, R + 14, yb, R + 18, yb + 7, R + 2, yb + 8, yb - 6, L - 2, yb + 8, L - 18, yb + 7, L - 14, yb)
    gold = part.get("stars", "#F2C94C")
    sx, sy = a.get("twinkle_x", 132), a.get("twinkle_y", max(12, T - 14))
    return (_p(crown, col, INK, 5)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (kx + 4, ky + 3, 110, ky + 2, 124, ky + 10), "none", _shade(col, 0.6), 2.5)
            + _p(band, _shade(col, 1.45), INK, 3.5)
            + _p(brim, _shade(col, 0.86), INK, 4.5)
            + _star5(L + 24, yb - 28, 6, gold) + _star5(104, yb - 40, 4.5, gold) + _star5(R - 22, yb - 24, 3.5, gold)
            + _c(L + 40, yb - 44, 1.8, gold, None) + _c(118, yb - 30, 1.6, gold, None)
            + F._star(sx, sy, 5.5, gold, INK, 1.4))


@register(F.HAIR_FRONT, "hard_hat")
def _hard_hat(part, a):
    """A construction / oil-rig hard hat: a ridged shell and a short brim all round."""
    col = part.get("color", "#F08A24")
    L, R, ye, T, B = _geo(a)
    yb = B - 14
    return (_p("M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f Z" % (
                L - 5, yb, L - 6, T - 14, T - 16, R + 6, T - 14, R + 5, yb), col, INK, 5)
            + _p("M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f" % (91, yb - 3, 91, T - 10, T - 16, 109, T - 10, 109, yb - 3),
                 _shade(col, 0.86), INK, 3)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (
                L + 14, yb - 4, L + 18, T + 2, 80, T - 10, R - 14, yb - 4, R - 18, T + 2, 120, T - 10), "none", _shade(col, 0.72), 3)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (L + 8, T + 14, L + 14, T - 2, 74, T - 8), "none", "#FFFFFF", 3.5,
                 ' opacity="0.5"')
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f L %.1f %.1f Q 100 %.1f %.1f %.1f Z" % (
                L - 12, yb - 3, yb - 14, R + 12, yb - 3, R + 12, yb + 5, yb - 6, L - 12, yb + 5), _shade(col, 0.84), INK, 4.5))


@register(F.HAIR_FRONT, "boonie_hat")
def _boonie_hat(part, a):
    """A soldier's floppy bush hat: a soft crown, a band, a wide brim drooping at the sides."""
    col = part.get("color", "#6B7B3A")
    L, R, ye, T, B = _geo(a)
    yb = B - 12
    brim = ("M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f "
            "Q 100 %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z") % (
        L - 22, yb + 12, L - 18, yb - 8, yb - 10, R + 18, yb - 8, R + 22, yb + 12, R + 8, yb + 16, R - 6, yb + 2,
        yb - 4, L + 6, yb + 2, L - 8, yb + 16, L - 22, yb + 12)
    return (_p("M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f Z" % (
                L + 4, yb - 4, L + 2, T - 14, T - 16, R - 2, T - 14, R - 4, yb - 4), col, INK, 5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f L %.1f %.1f Q 100 %.1f %.1f %.1f Z" % (
                L + 5, yb - 6, yb - 16, R - 5, yb - 6, R - 4, yb - 14, yb - 24, L + 4, yb - 14), _shade(col, 0.72), INK, 3.5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f" % (L + 10, T - 2, T - 12, R - 10, T - 2), "none", _shade(col, 0.8), 2.5)
            + _p(brim, _shade(col, 0.9), INK, 4.5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f" % (L - 12, yb + 6, yb - 12, R + 12, yb + 6), "none", _shade(col, 0.66),
                 1.8, ' stroke-dasharray="3 3"'))


@register(F.HAIR_FRONT, "captain_hat")
def _captain_hat(part, a):
    """A ship captain's peaked cap: a wide top (white, or navy), a band with gold cord, a black visor,
    a gold anchor badge."""
    col = part.get("color", "#F4F4F0")
    L, R, ye, T, B = _geo(a)
    yb = B - 12
    h = col.lstrip("#")
    dark = 0.3 * int(h[0:2], 16) + 0.59 * int(h[2:4], 16) + 0.11 * int(h[4:6], 16) < 110
    band = "#1C1E22" if dark else part.get("band", "#1F2F55")
    gold = "#E2B73C"
    x, y = 100, yb - 30
    return (_p("M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f Z" % (
                L - 4, yb - 12, L - 12, T - 8, T - 12, R + 12, T - 8, R + 4, yb - 12), col, INK, 4.5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f L %.1f %.1f Q 100 %.1f %.1f %.1f Z" % (
                L + 2, yb - 12, yb - 24, R - 2, yb - 12, R - 2, yb - 2, yb - 14, L + 2, yb - 2), band, INK, 3.5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f" % (L + 6, yb - 8, yb - 20, R - 6, yb - 8), "none", gold, 2.5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q 100 %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
                L + 6, yb - 4, yb - 14, R - 6, yb - 4, R - 2, yb + 6, R - 16, yb + 6, yb - 2, L + 16, yb + 6,
                L + 2, yb + 6, L + 6, yb - 4), "#1C1E22", INK, 3.5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f" % (L + 20, yb - 3, yb - 8, 90, yb - 7), "none", "#FFFFFF", 2.5,
                 ' opacity="0.45"')
            + _e(x, y, 8, 9, band, gold, 2.5)
            + _p("M %d %d L %d %d M %d %d L %d %d M %d %d Q %d %d %d %d Q %d %d %d %d" % (
                x, y - 5, x, y + 5, x - 3.5, y - 2, x + 3.5, y - 2, x - 5, y + 1, x - 4, y + 6, x, y + 6, x + 4, y + 6,
                x + 5, y + 1), "none", gold, 2)
            + _c(x, y - 6, 1.6, "none", gold, 1.5))


@register(F.HAIR_FRONT, "fedora")
def _fedora(part, a):
    """A fedora: a pinched crown, a dark band, a snap brim."""
    col = part.get("color", "#6E6253")
    L, R, ye, T, B = _geo(a)
    yb = B - 14
    return (_p("M %.1f %.1f Q %.1f %.1f 82 %.1f Q 100 %.1f 118 %.1f Q %.1f %.1f %.1f %.1f Z" % (
                L + 8, yb - 6, L + 6, T - 12, T - 14, T - 4, T - 14, R - 6, T - 12, R - 8, yb - 6), col, INK, 5)
            + _p("M 92 %.1f Q 100 %.1f 108 %.1f" % (T - 6, T + 6, T - 6), "none", _shade(col, 0.7), 2.5)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f L %.1f %.1f Q 100 %.1f %.1f %.1f Z" % (
                L + 8, yb - 7, yb - 19, R - 8, yb - 7, R - 8, yb - 16, yb - 28, L + 8, yb - 16), _shade(col, 0.5), INK, 3)
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q 100 %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
                L - 18, yb, yb - 20, R + 18, yb, R + 18, yb + 8, R + 4, yb + 6, yb - 8, L - 4, yb + 6, L - 18, yb + 8,
                L - 18, yb), _shade(col, 0.88), INK, 4.5))


@register(F.HAIR_FRONT, "witch_hat_small")
def _witch_hat_small(part, a):
    """A small witch's hat worn tilted on the crown, fascinator-size, its tip bent."""
    col, band = part.get("color", "#2A2533"), part.get("band", "#6C4F9E")
    L, R, ye, T, B = _geo(a)
    return ('<g transform="translate(%.1f %.1f) rotate(16) scale(0.95)">' % (112, T + 6)
            + _e(0, 0, 25, 6, _shade(col, 1.25), INK, 3.5)
            + _p("M -14 -2 Q -9 -22 -3 -33 Q 2 -41 13 -43 Q 6 -36 5 -28 Q 8 -14 14 -2 Z", col, INK, 3.5)
            + _p("M -13 -6 Q 0 -2 13 -6 L 11.5 -12 Q 0 -9 -11.5 -12 Z", band, INK, 2.5)
            + _p("M -6 -16 Q -3 -26 1 -33", "none", _shade(col, 2.2), 2, ' opacity="0.6"')
            + "</g>")


# ---------------------------------------------------------------- reading the mouth and eyes as drawn
# The layers read the mouth and eyes that were actually drawn (the core's, or a head's own style):
# the corners, the top of the mouth's middle, its teeth and open cavity, the eyes' outer corners. So
# they follow the core when its shapes change, instead of keeping a table of them.
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_NARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "T": 2, "C": 6, "S": 4, "A": 7}


def _path_pts(d):
    """Points along an SVG path: lines and curves sampled, an arc by its end point."""
    toks = re.findall(r"[A-Za-z]|" + _NUM, d)
    pts, cmd, i = [], "M", 0
    cur = start = (0.0, 0.0)

    def line(p, q, n=4):
        return [(p[0] + (q[0] - p[0]) * k / float(n), p[1] + (q[1] - p[1]) * k / float(n)) for k in range(1, n + 1)]
    while i < len(toks):
        if toks[i].isalpha():
            cmd, i = toks[i], i + 1
            if cmd in "Zz":
                pts += line(cur, start)
                cur = start
                continue
        n = _NARGS.get(cmd.upper())
        if n is None or i + n > len(toks):
            break
        v = [float(t) for t in toks[i:i + n]]
        i += n
        ox, oy = cur if cmd.islower() else (0.0, 0.0)
        C = cmd.upper()
        p = ((v[0] + ox, cur[1]) if C == "H" else (cur[0], v[0] + oy) if C == "V" else (v[-2] + ox, v[-1] + oy))
        ts = [k / 8.0 for k in range(1, 9)]
        if C in ("Q", "S"):
            c = (v[0] + ox, v[1] + oy)
            seg = [tuple((1 - t) ** 2 * cur[j] + 2 * t * (1 - t) * c[j] + t * t * p[j] for j in (0, 1)) for t in ts]
        elif C == "C":
            c1, c2 = (v[0] + ox, v[1] + oy), (v[2] + ox, v[3] + oy)
            seg = [tuple((1 - t) ** 3 * cur[j] + 3 * t * (1 - t) ** 2 * c1[j] + 3 * t * t * (1 - t) * c2[j] + t ** 3 * p[j]
                         for j in (0, 1)) for t in ts]
        elif C == "M":
            seg, start = [p], p
            cmd = "l" if cmd == "m" else "L"
        else:
            seg = line(cur, p)
        pts += seg
        cur = p
    return pts


def _affine(tf, m):
    """Compose an SVG transform list (translate, scale, rotate) onto the matrix m = (a, b, c, d, e, f)."""
    for name, args in re.findall(r"(translate|scale|rotate)\s*\(([^)]*)\)", tf or ""):
        v = [float(x) for x in re.findall(_NUM, args)] or [0.0]
        if name == "translate":
            n = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            n = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        else:
            r = math.radians(v[0])
            cs, sn = math.cos(r), math.sin(r)
            cx, cy = (v[1], v[2]) if len(v) > 2 else (0.0, 0.0)
            n = (cs, sn, -sn, cs, cx - cs * cx + sn * cy, cy - sn * cx - cs * cy)
        a, b, c, d, e, f = m
        m = (a * n[0] + c * n[1], b * n[0] + d * n[1], a * n[2] + c * n[3], b * n[2] + d * n[3],
             a * n[4] + c * n[5] + e, b * n[4] + d * n[5] + f)
    return m


def _shapes(svg):
    """Each drawn element of an SVG fragment: its points (transforms applied), fill, stroke, stroke width."""
    out, stack, m = [], [], (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for close, tag, attrs, selfclose in re.findall(r"<(/?)(g|path|ellipse|circle|rect)\b([^>]*?)(/?)>", svg):
        at = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        if tag == "g":
            if close:
                m = stack.pop() if stack else m
            elif not selfclose:
                stack.append(m)
                m = _affine(at.get("transform"), m)
            continue
        if close:
            continue
        mm = _affine(at.get("transform"), m)

        def num(k, dflt=0.0):
            return float(at.get(k, dflt))
        if tag == "path":
            pts = _path_pts(at.get("d", ""))
        elif tag == "rect":
            x, y, w, h = num("x"), num("y"), num("width"), num("height")
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        else:
            rx, ry = num("rx", at.get("r", 0)), num("ry", at.get("r", 0))
            pts = [(num("cx") + rx * math.cos(k * math.pi / 8), num("cy") + ry * math.sin(k * math.pi / 8)) for k in range(16)]
        out.append(dict(pts=[(mm[0] * x + mm[2] * y + mm[4], mm[1] * x + mm[3] * y + mm[5]) for x, y in pts],
                        fill=at.get("fill", "#000000").upper(), stroke=at.get("stroke", "none").upper(),
                        width=float(at.get("stroke-width", 0) or 0) * math.sqrt(abs(mm[0] * mm[3] - mm[1] * mm[2]))))
    return out


def _span_at(pts, x):
    """Where a closed outline crosses the vertical line at x: (top, bottom), or None."""
    ys = [y0 + (y1 - y0) * (x - x0) / (x1 - x0) for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])
          if (x0 - x) * (x1 - x) <= 0 and x0 != x1]
    return (min(ys), max(ys)) if ys else None


def _mouth_geo(base, a):
    """The mouth as drawn: its left and right corners, the top of its middle (stroke included), its box,
    its teeth, its open cavity."""
    x, y = a["mx"], a["my"]
    sh = [s for s in _shapes(base) if s["pts"]]
    pts = [p for s in sh for p in s["pts"]] or [(x - 12.0, float(y)), (x + 12.0, float(y))]
    w = max([s["width"] for s in sh] + [0.0]) / 2.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mid = [p[1] for p in pts if abs(p[0] - x) <= 10] or ys
    return dict(left=min(pts), right=max(pts), top=min(mid) - w,
                box=(min(xs) - w, min(ys) - w, max(xs) + w, max(ys) + w),
                teeth=[s for s in sh if s["fill"] == "#FFFFFF"],
                cavity=[s for s in sh if s["fill"] not in ("NONE", "#FFFFFF") and s["stroke"] == INK and s["width"] >= 3.5])


# ---------------------------------------------------------------- facial hair
def _stache_path(style, g, a):
    """(outline, strands) of a mustache resting on the mouth g: the tips ride the mouth's corners (up
    with a smile, down with a frown), the lower edge sits on the top of the mouth's middle."""
    x, my, ny = a["mx"], a["my"], a["ny"]
    (lx_, ly), (rx_, ry) = g["left"], g["right"]
    t = min(ny + 9, my - 12)                             # just under the nose
    bc = max(g["top"] - 0.5, t + 6)
    wl, wr = max(x - lx_ + 4, 25), max(rx_ - x + 4, 25)
    ly, ry = max(ly - 1, t + 4), max(ry - 1, t + 4)
    if style == "walrus":                                # heavy and drooping: it hides the upper lip
        t, bc = t - 2, max(g["top"] + 4, t + 9)
        wl, wr = max(wl, 29), max(wr, 29)
        ly, ry = max(ly + 7, bc + 3), max(ry + 7, bc + 3)
        return ("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f "
                "Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z") % (
            x - 16, t, x, t - 5, x + 16, t, x + wr, t + 6, x + wr, ry, x + 12, bc + 3, x, bc + 2,
            x - 12, bc + 3, x - wl, ly, x - wl, t + 6, x - 16, t), (
            "M %.1f %.1f l 1 6 M %.1f %.1f l 0 7 M %.1f %.1f l -1 6 M %.1f %.1f l 2 5 M %.1f %.1f l -2 5" % (
                x - 9, bc - 6, x, bc - 7, x + 9, bc - 6, x - 19, ry - 9, x + 19, ry - 9))
    if style == "pencil":                                # a thin line along the upper lip, parted in the middle
        y = bc - 1
        el, er = min(max(ly - 4, y - 6), y + 3), min(max(ry - 4, y - 6), y + 3)
        return "M %.1f %.1f Q %.1f %.1f %.1f %.1f M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (
            x - 2.5, y, x - 11, y - 2.5, x - 18, el, x + 2.5, y, x + 11, y - 2.5, x + 18, er), ""
    if style == "handlebar":                             # a full middle, long arms curled up at the ends
        return ("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f "
                "Q %.1f %.1f %.1f %.1f Z") % (
            x, t + 1, x + 12, t - 2, x + 20, t + 3, x + 16, bc + 1, x, bc - 1,
            x - 16, bc + 1, x - 20, t + 3, x - 12, t - 2, x, t + 1), (
            "M %.1f %.1f Q %.1f %.1f %.1f %.1f q 6 -1 3 -7 M %.1f %.1f Q %.1f %.1f %.1f %.1f q -6 -1 -3 -7" % (
                x + 17, t + 5, x + 31, ry + 2, x + 34, ry - 9, x - 17, t + 5, x - 31, ly + 2, x - 34, ly - 9))
    # chevron: a thick brush over the lip, parted at the middle, its hair combed down and out
    h = bc - t
    return ("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f L %.1f %.1f "
            "L %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z") % (
        x - 15, t, x, t - 3, x + 15, t, x + wr - 2, t + 1, x + wr, ry, x + 12, bc + 1, x + 3, bc, x, bc - 2.5,
        x - 3, bc, x - 12, bc + 1, x - wl, ly, x - wl + 2, t + 1, x - 15, t), (
        " ".join("M %.1f %.1f l %.1f %.1f" % (x + s * dx, t + 2.5, s * 2.5, max(h - 5, 2))
                 for s in (-1, 1) for dx in (5, 12)))


@register(F.FACE_PARTS, "mustache")
def _mustache(part, a, skin):
    """A mustache over the mouth: it lifts with a smile, droops with a frown, rides up off an open
    mouth. part["style"]: chevron (default) | handlebar | pencil | walrus; part["color"]."""
    style, col = part.get("style", "chevron"), part.get("color", "#4A3326")

    def draw(e, svg, marks, base):
        body, strands = _stache_path(style, _mouth_geo(base, a), a)
        if style == "pencil":
            return svg + _p(body, "none", INK, 6) + _p(body, "none", col, 3)
        out = svg + _p(body, col, INK, 4)
        if style == "handlebar":
            out += _p(strands, "none", INK, 7.5) + _p(strands, "none", col, 3.5) + _p(body, col, INK, 4)
        elif strands:
            out += _p(strands, "none", _shade(col, 0.72), 2)
        return out
    return _layer(a, "mouth", 40, draw)


def _jaw(a):
    """The head's lower outline, ear to ear through the chin: the head's own when it gives one ("jaw"),
    else a curve a few pixels outside a rounded jaw."""
    if a.get("jaw"):
        return a["jaw"]
    L, R, ye = a["ears"]
    c = a["chin"] + 3
    return "M %.1f %.1f Q %.1f %.1f 100 %.1f Q %.1f %.1f %.1f %.1f" % (L - 2, ye, L - 2, c, c, R + 2, c, R + 2, ye)


def _mouth_hole(g):
    """An oval opening a little larger than the mouth's box."""
    x0, y0, x1, y1 = g["box"]
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hx, hy = (x1 - x0) / 2.0 * 1.12 + 5, (y1 - y0) / 2.0 * 1.12 + 5
    return "M %.1f %.1f A %.1f %.1f 0 1 0 %.1f %.1f A %.1f %.1f 0 1 0 %.1f %.1f Z" % (
        cx - hx, cy, hx, hy, cx + hx, cy, hx, hy, cx - hx, cy)


@register(F.FACE_PARTS, "short_beard")
def _short_beard(part, a, skin):
    """A close beard along the jaw and over the lip; it opens around the mouth, whatever the mouth does."""
    col = part.get("color", "#3A2A20")
    L, R, ye = a["ears"]
    x, ny, my = a["mx"], a["ny"], a["my"]
    jaw = _jaw(a)
    xl, yl = [float(v) for v in jaw.split()[1:3]]
    xr, yr = [float(v) for v in jaw.split()[-2:]]
    t = min(ny + 8, my - 13)
    inner = (" L %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f "
             "Q %.1f %.1f %.1f %.1f Z") % (
        xr - 10, yr + 2, xr - 12, my - 8, x + 22, t + 4, x + 10, t - 2, x, t,
        x - 10, t - 2, x - 22, t + 4, xl + 12, my - 8, xl + 10, yl + 2)

    def draw(e, svg, marks, base):
        return (_p(jaw + inner + " " + _mouth_hole(_mouth_geo(base, a)), col, None, ' fill-rule="evenodd"')
                + _p(jaw, "none", INK, 4.5)
                + _p("M %.1f %.1f q 2 5 0 9 M %.1f %.1f q -2 5 0 9 M %.1f %.1f q 0 5 0 8" % (
                    x - 24, my + 12, x + 24, my + 12, x, a["chin"] - 6), "none", _shine(col), 2.2, ' opacity="0.7"')
                + svg)
    return _layer(a, "mouth", 20, draw)


@register(F.FACE_PARTS, "goatee")
def _goatee(part, a, skin):
    """A tuft on the chin, under the lower lip (the mouth draws over it when it opens wide)."""
    col = part.get("color", "#3A2A20")
    x, my, chin = a["mx"], a["my"], a["chin"]
    top = my + 12
    return (_p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
                x - 12, top, x, top - 3, x + 12, top, x + 11, chin, x + 2, chin + 7, x - 1, chin + 3, x - 5, chin + 5,
                x - 11, chin, x - 12, top), col, INK, 3.5)
            + _p("M %.1f %.1f q 1 5 0 9 M %.1f %.1f q -1 5 0 9" % (x - 4, top + 3, x + 4, top + 3), "none", _shine(col), 2))


@register(F.FACE_PARTS, "sideburns")
def _sideburns(part, a, skin):
    col = part.get("color", "#3A2A20")
    L, R, ye = a["ears"]
    out = ""
    for s, x in ((1, L + 3), (-1, R - 3)):
        out += _p("M %.1f %.1f L %.1f %.1f L %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
            x, ye - 26, x + 9 * s, ye - 24, x + 8 * s, ye + 16, x + 3 * s, ye + 21, x, ye + 14), col, INK, 3)
    return out


# ---------------------------------------------------------------- eyewear
@register(F.FACE_PARTS, "small_glasses")
def _small_glasses(part, a, skin):
    """Small round wire frames."""
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    L, R, _ = a["ears"]
    fr = part.get("color", "#34363C")
    r = 14 * a.get("eye_scale", 1) ** 0.7
    return (_c(lx, y, r, "#FFFFFF", fr, 2.8, ' fill-opacity="0.15"') + _c(rx, y, r, "#FFFFFF", fr, 2.8, ' fill-opacity="0.15"')
            + _p("M %.1f %.1f Q 100 %.1f %.1f %.1f" % (lx + r, y - 1, y - 7, rx - r, y - 1), "none", fr, 2.8)
            + _p("M %.1f %.1f L %.1f %.1f M %.1f %.1f L %.1f %.1f" % (lx - r, y - 2, L + 2, y - 5, rx + r, y - 2, R - 2, y - 5),
                 "none", fr, 2.5))


@register(F.FACE_PARTS, "monocle")
def _monocle(part, a, skin):
    """A monocle over the right eye, on a fine gold chain."""
    rx, y = a["rx"], a["ey"]
    R, ye = a["ears"][1], a["ears"][2]
    gold = part.get("color", "#C9A03A")
    return (_c(rx, y, 15, "#FFFFFF", gold, 3.5, ' fill-opacity="0.2"')
            + _c(rx, y, 15, "none", INK, 1.2, ' opacity="0.6"')
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (rx + 10, y + 11, R + 2, ye + 12, R - 6, ye + 48), "none", gold, 2.2,
                 ' stroke-dasharray="0.1 4"'))


@register(F.FACE_PARTS, "eyepatch")
def _eyepatch(part, a, skin):
    """A patch over the left eye (the viewer's left), its strap across the forehead."""
    lx, y = a["lx"], a["ey"]
    L, R, _ = a["ears"]
    col = part.get("color", "#1E1F22")
    return (_p("M %.1f %.1f L %.1f %.1f M %.1f %.1f L %.1f %.1f" % (lx + 12, y - 11, R - 1, a["by"] - 24, lx - 15, y - 5, L + 1, y - 8),
               "none", col, 3.5)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
                lx - 15, y - 10, lx, y - 15, lx + 15, y - 10, lx + 17, y + 8, lx, y + 14, lx - 17, y + 8, lx - 15, y - 10),
                col, INK, 3)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (lx - 8, y - 7, lx - 2, y - 10, lx + 6, y - 9), "none", "#FFFFFF", 2,
                 ' opacity="0.3"'))


# ---------------------------------------------------------------- marks on the skin (drawn under the eyes)
@register(F.FACE_PARTS, "scar", under=True)
def _scar(part, a, skin):
    """An old scar across the right brow and down the cheek."""
    rx, ey, by = a["rx"], a["ey"], a["by"]
    x0, y0, x1, y1 = rx + 4, by - 13, rx + 15, ey + 24
    ticks = "".join("M %.1f %.1f l 7 -3 " % (x0 + (x1 - x0) * k - 3.5, y0 + (y1 - y0) * k + 1.5) for k in (0.2, 0.5, 0.8))
    col = part.get("color", "#D77A72")
    return (_p("M %.1f %.1f L %.1f %.1f" % (x0, y0, x1, y1), "none", col, 5)
            + _p(ticks, "none", _shade(col, 0.62), 2.2))


@register(F.FACE_PARTS, "freckles", under=True)
def _freckles(part, a, skin):
    col = part.get("color", _shade(skin, 0.66))
    nx, ny = a["nx"], a["ny"]
    pts = [(nx - 7, ny - 8), (nx + 7, ny - 8), (nx, ny - 12)]
    for (cx, cy), s in zip(a["cheeks"], (1, -1)):
        pts += [(cx - 7 * s, cy - 8), (cx + 1 * s, cy - 11), (cx + 7 * s, cy - 6), (cx - 2 * s, cy - 3), (cx + 5 * s, cy + 1)]
    return "".join(_c(x, y, 1.9, col, None) for x, y in pts)


@register(F.FACE_PARTS, "bags", under=True)
def _bags(part, a, skin):
    """Tired bags under the eyes."""
    c = _shade(skin, 0.7)
    k = a.get("eye_scale", 1)
    out = ""
    for x in (a["lx"], a["rx"]):
        y = a["ey"] + 10 * k
        out += (_p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - 11, y, x, y + 7, x + 11, y), "none", c, 2.6)
                + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - 7, y + 5, x, y + 10, x + 7, y + 5), "none", c, 2, ' opacity="0.6"'))
    return out


# ---------------------------------------------------------------- the rest
@register(F.FACE_PARTS, "broken_nose")
def _broken_nose(part, a, skin):
    """A boxer's nose: the bridge knocked crooked, the tip flattened and pushed aside (use it in place of a nose)."""
    nx, ny = a["nx"], a["ny"]
    return (_p("M %.1f %.1f L %.1f %.1f L %.1f %.1f" % (nx - 1, ny - 24, nx + 5, ny - 15, nx - 3, ny - 6), "none", INK, 3.5)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
                nx - 12, ny - 1, nx - 14, ny + 8, nx - 3, ny + 8, nx + 9, ny + 9, nx + 7, ny - 1, nx - 2, ny - 7, nx - 12, ny - 1),
                _shade(skin, 0.86), INK, 3.5)
            + _p("M %.1f %.1f q 2 3 5 2" % (nx - 8, ny + 3), "none", _shade(skin, 0.6), 2))


@register(F.FACE_PARTS, "lashes", under=True)       # under=True: it must hook the eyes before they are drawn
def _lashes(part, a, skin):
    """Long lashes flicking out from the outer top corner of each eye, on whatever shape the eyes take."""
    col = part.get("color", INK)

    def draw(e, svg, marks, base):
        pts = [p for s in _shapes(base) for p in s["pts"]]
        k = a.get("eye_scale", 1)
        d = ""
        for x, s in ((a["lx"], -1), (a["rx"], 1)):
            own = [p for p in pts if (p[0] < 100) == (x < 100)] or [(x + 7 * s, a["ey"] - 6)]
            cx, cy = max(own, key=lambda p: s * (p[0] - x) - 0.6 * (p[1] - a["ey"]))
            d += "M %.1f %.1f L %.1f %.1f M %.1f %.1f L %.1f %.1f " % (
                cx - s, cy - 1, cx + 7 * s * k, cy - 4 * k, cx - 3 * s, cy - 3, cx + 2 * s * k, cy - 10 * k)
        return svg + _p(d, "none", col, 2.8)
    return _layer(a, "eyes", 10, draw)


def _restroke(svg, color, grow):
    """Copies of the mouth's outlines (strokes 4 px or wider), recolored and thickened: a rim to lay under it."""
    m = re.match(r"(<g [^>]*>)(.*)(</g>)$", svg, re.S)
    if m:
        return m.group(1) + _restroke(m.group(2), color, grow) + m.group(3)
    out = []
    for el in re.findall(r"<(?:path|ellipse|circle|rect)\b[^>]*/>", svg):
        w = re.search(r'stroke-width="([\d.]+)"', el)
        if not w or float(w.group(1)) < 4 or 'stroke="%s"' % INK not in el:
            continue
        el = el.replace('stroke="%s"' % INK, 'stroke="%s"' % color)
        el = re.sub(r'stroke-width="[\d.]+"', 'stroke-width="%.1f"' % (float(w.group(1)) + grow), el)
        out.append(re.sub(r'fill="[^"]*"', 'fill="%s"' % color, el, count=1))
    return "".join(out)


@register(F.FACE_PARTS, "lipstick")
def _lipstick(part, a, skin):
    """Lipstick on whatever shape the mouth takes: a colored lip, outlined, under the mouth's own lines.
    part["color"]."""
    lip = part.get("color", "#C8323C")

    def draw(e, svg, marks, base):
        return _restroke(base, INK, 10) + _restroke(base, lip, 6.5) + svg
    return _layer(a, "mouth", 10, draw)


@register(F.FACE_PARTS, "gold_tooth")
def _gold_tooth(part, a, skin):
    """A gold tooth: among the teeth when they show, hanging in an open mouth, and a glint at the corner
    of a closed one."""
    gold = part.get("color", "#E8B730")

    def tooth(x, y, w, h):
        return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="1" fill="%s" stroke="%s" stroke-width="1.4"/>'
                % (x, y, w, h, gold, INK) + F._star(x + w, y + 0.5, 3.5, "#FFF6C8", None))

    def draw(e, svg, marks, base):
        g = _mouth_geo(base, a)
        for s in g["teeth"]:                  # the teeth show: one of them, right of center, is gold
            xs = [p[0] for p in s["pts"]]
            x0, x1 = min(xs), max(xs)
            xc = x0 + 0.68 * (x1 - x0)
            span = _span_at(s["pts"], xc)
            if span and span[1] - span[0] >= 3:
                w = max(4.0, min(7.0, 0.17 * (x1 - x0)))
                return svg + tooth(xc - w / 2, span[0] + 0.5, w, span[1] - span[0] - 1)
        for s in g["cavity"]:                 # open, no teeth drawn: it hangs from the top
            xs = [p[0] for p in s["pts"]]
            xc = (min(xs) + max(xs)) / 2.0 + 3
            span = _span_at(s["pts"], xc)
            if span and span[1] - span[0] >= 10:
                return svg + tooth(xc - 2.5, span[0] + s["width"] / 2, 5, 5)
        cx, cy = g["right"]                   # closed: a glint at the corner
        return svg + _c(cx + 1, cy + 1, 2.6, gold, INK, 1.3) + F._star(cx + 5, cy - 4, 4.5, "#FFE9A0", INK, 1.1)
    return _layer(a, "mouth", 30, draw)


@register(F.FACE_PARTS, "bell_pin")
def _bell_pin(part, a, skin):
    """A tiny brass bell pinned at the collar."""
    x, y = 130, min(a["chin"] + 4, 186)
    brass = part.get("color", "#C9A03A")
    return (_c(x, y - 7.5, 1.7, "none", _shade(brass, 0.7), 1.4)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
                x - 6, y + 3.5, x - 4.5, y + 1, x - 4.5, y - 1.5, x - 4.5, y - 6, x, y - 6, x + 4.5, y - 6,
                x + 4.5, y - 1.5, x + 4.5, y + 1, x + 6, y + 3.5), brass, INK, 1.8)
            + _c(x, y + 4.8, 1.6, _shade(brass, 0.55), INK, 1)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - 2.5, y - 1, x - 2.5, y - 3.5, x - 0.5, y - 4.5), "none", "#FFF2C0", 1.4))


# ==================================================================================================
# Finer features for the face kit (games/faces), for a face the stock parts could not do justice: a slim,
# delicate face with long hair and almond eyes. Same line weights and flat color as the rest of the kit;
# nothing tinted over the whole face.
#
#     head   fine           a slim face with a delicate, softly pointed chin and a longer nose line
#     hair   pony_tail      (HAIR_BACK) the kit's ponytail, hanging behind the head on the right
#            curtain_bangs  (HAIR_FRONT) a middle part, heavy curtain bangs falling to the brows and
#                           sweeping aside, flowing into long strands that frame the face to the jaw
#     eyes   soft           large almond eyes with light irises (anchors["iris"]), a calm upper lid,
#                           fine lashes; the lids come down with the feeling; the closed-eye feelings
#                           are the kit's own
#     face   straight_nose  a thin straight nose with a small rounded tip
#            soft_lips      small full lips at rest (a bowed upper lip, a fuller lower one, the lips
#                           just apart); every other mouth is the kit's own shape
#
# Earlier tries that did not read well: a helmet-like crown with a shine like a headband, spiky bangs and
# dark slabs down the sides, cat-eye wings, thick brows and a blush on the tip of the nose; the stock kit
# alone read as nobody in particular.
# ==================================================================================================

def _fine(skin, look):
    """A slim face, longer below the eyes, tapering to a delicate, softly pointed chin."""
    d = ("M 51 104 Q 51 40 100 40 Q 149 40 149 104 Q 149 140 134 160 Q 118 179 100 182 "
         "Q 82 179 66 160 Q 51 140 51 104 Z")
    a = dict(lx=80, rx=120, ey=110, by=93, mx=100, my=160, nx=100, ny=137,
             cheeks=((68, 139), (132, 139)), temple=(142, 82), top=40, ears=(50, 150, 116), chin=182,
             jaw="M 51 106 Q 51 140 66 160 Q 82 179 100 182 Q 118 179 134 160 Q 149 140 149 106",
             neck_w=19)                          # a slender neck
    return _head(d, _ears(50, 150, 116, skin=skin), skin, a)


# ---------------------------------------------------------------- hair
@register(F.HAIR_BACK, "pony_tail")
def _pony_tail(part, a):
    """A slim ponytail hanging behind the head, to the right: only what is past the head shows."""
    col = part.get("color", "#3B2A22")
    L, R, ye, T, B = _geo(a)
    return _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
        R - 10, T + 16, R + 14, T + 20, R + 15, T + 48, R + 18, ye + 30, R + 10, ye + 62,
        R + 5, ye + 26, R + 1, T + 52, R - 4, T + 34, R - 10, T + 16), col, INK, 4)


@register(F.HAIR_FRONT, "curtain_bangs")
def _curtain_bangs(part, a):
    """Heavy bangs over the forehead, parted just at the middle and falling to the brows, longer toward
    the temples, running on into long strands that frame the face to the cheekbones and below, over
    the ears; the rest is drawn back (pony_tail)."""
    col = part.get("color", "#3B2A22")
    L, R, ye, T, B = _geo(a)
    lx, rx, my = a["lx"], a["rx"], a["my"]
    out = ""
    for s in (-1, 1):
        edge = L if s < 0 else R
        eye = lx if s < 0 else rx
        X = lambda dx: 100 + s * dx
        e = abs(eye - 100)
        # one piece a side: from the part over the crown and down past the ear to the strand's end, back up
        # the strand's inner edge to the temple, then the bangs' lower edge: just above the brow, rising
        # a little to the part, where a narrow line of skin shows
        d = ("M %.1f %.1f Q %.1f %.1f %.1f %.1f "
             "Q %.1f %.1f %.1f %.1f "
             "Q %.1f %.1f %.1f %.1f "
             "Q %.1f %.1f %.1f %.1f "
             "Q %.1f %.1f %.1f %.1f "
             "Q %.1f %.1f %.1f %.1f Z") % (
            X(0.5), T - 3, X(46), T - 6, edge - s * 4, ye - 6,
            edge - s * 4, ye + 24, edge + s * 7, my + 6,
            edge + s * 13, ye + 26, edge + s * 12, B + 12,
            X(e + 12), B + 1, X(e + 2), B - 5,
            X(e - 12), B - 8, X(8), B - 11,
            X(2), B - 20, X(0.5), T + 8)
        out += _p(d, col, INK, 3.5)
    # one soft shine on the crown
    shine = _shade(col, 1.5) if F.lum(col) < 0.3 else _shade(col, 0.8)
    out += _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (L + 18, T + 16, L + 30, T + 3, 88, T + 1), "none", shine, 2.4,
              ' opacity="0.6"')
    return out


# ---------------------------------------------------------------- eyes
SOFT = {                  # feeling: (how far the upper lid comes down 0..1, iris dx, dy, lid tilt toward the nose)
    "neutral": (0.1, 0, 0.5, 0), "worried": (0.02, 0, -0.5, -3), "thinking": (0.1, 3, -2.5, 0),
    "surprised": (0.0, 0, 0, 0), "sad": (0.34, 0, 1.5, -4), "angry": (0.46, 0, 1, 5),
    "jealous": (0.5, 4, 1, 0), "smug": (0.5, 0, 1, 0), "determined": (0.38, 0, 1, 3),
    "confused": (0.12, -2, 0, 0)}


@register(F.EYES, "soft")
def _soft_eyes(e, a, light, marks):
    """Large almond eyes with light irises and a calm upper lid; closed-eye feelings are the kit's."""
    if e in ("happy", "relieved") or "blink" in marks:
        return F._eyes(e, a, light, marks)
    iris = a.get("iris", "#8C9460")
    lid_col = a.get("lid", "#F3D5C4")
    gx = -3 if "glance" in marks else 0
    out = ""
    for x, s, key in ((a["lx"], -1, "L"), (a["rx"], 1, "R")):
        y = a["ey"]
        f, dx, dy, tilt = SOFT.get(e, SOFT["neutral"])
        if e == "confused" and s > 0:
            f = 0.5
        w, up, lo = 14.0, 16.0, 11.0
        xi, xo = x - s * w, x + s * w           # the inner and outer corners
        shape = "M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (xi, y + 1, x - s * 1, y - up, xo, y - 1,
                                                                            x + s * 1, y + lo, xi, y + 1)
        r = 6.0 if e == "surprised" else 6.9
        ix, iy = x + dx + gx, y + dy
        cid = "soft-%s" % key
        out += '<clipPath id="%s"><path d="%s"/></clipPath>' % (cid, shape)
        out += _p(shape, "#FFFFFF", None)
        out += ('<g clip-path="url(#%s)">' % cid
                + _c(ix, iy, r, iris, _shade(iris, 0.55), 1.2)
                + _c(ix, iy, r * 0.44, "#1C1D20", None)
                + _c(ix + 2.1, iy - 2.1, 1.8, "#FFFFFF", None))
        top = y - up * 0.5
        yl = top + f * (up * 0.5 + lo * 0.7)
        yi, yo = yl + tilt * 0.5, yl - tilt * 0.5
        if f > 0:                               # the upper lid, down to where the feeling puts it
            out += _p("M %.1f %.1f L %.1f %.1f L %.1f %.1f L %.1f %.1f Z" % (xi - 2, y - up - 2, xo + 2, y - up - 2,
                                                                             xo + 2, yo, xi - 2, yi), lid_col, None)
        out += "</g>"
        # the lid line: along the lid where it has come down, else the eye's own upper edge; two fine
        # lashes at the outer corner; a soft lower lid
        if f > 0:
            out += _p("M %.1f %.1f L %.1f %.1f" % (xi, yi, xo, yo), "none", INK, 2.6)
        out += _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (xi, y + 1, x - s * 1, y - up, xo, y - 1), "none", INK, 2.4)
        out += _p("M %.1f %.1f l %.1f %.1f M %.1f %.1f l %.1f %.1f" % (xo - s * 1, y - 3, s * 4, -3, xo - s * 4, y - 6, s * 3, -4),
                  "none", INK, 1.8)
        out += _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (xi + s * 3, y + 3, x + s * 2, y + lo + 0.5, xo - s * 1, y + 1),
                  "none", _shade(lid_col, 0.7), 1.3)
    return out


# ---------------------------------------------------------------- the raincoat
SHOULDERS = "M 16 204 Q 22 168 68 160 L 132 160 Q 178 168 184 204 Z"


@register(F.BODIES, "raincoat")
def _raincoat(part, color, a):
    """A clear yellow raincoat over a dark top: the top shows through the plastic, the coat is open at
    the throat with a wide collar, and a shine runs down each side."""
    coat = part.get("color", "#F2C94C")
    under = part.get("under", "#1D1E24")
    edge = _shade(coat, 0.7)
    out = _p(SHOULDERS, under, INK, 5)
    out += _p("M 88 160 Q 100 176 112 160", "none", _shade(under, 1.6), 2.5)          # the top's neckline
    for s in (-1, 1):
        X = lambda dx: 100 + s * dx
        # the coat's front panel, open at the middle, over the shoulder to the edge of the picture
        panel = ("M %.1f 204 L %.1f 176 Q %.1f 166 %.1f 162 L %.1f 160 Q %.1f 168 %.1f 204 Z"
                 % (X(10), X(14), X(18), X(30), X(34), X(78), X(86)))
        out += _p(panel, coat, edge, 2.5, ' fill-opacity="0.82"')
        # the wide collar, folded back
        out += _p("M %.1f %.1f L %.1f %.1f L %.1f %.1f L %.1f %.1f Z" % (X(12), 162, X(36), 156, X(44), 176, X(20), 184),
                  coat, edge, 2.5, ' fill-opacity="0.9"')
        # the plastic's shine: long streaks down the panel, a glint on the collar
        out += _p("M %.1f 170 Q %.1f 186 %.1f 204" % (X(54), X(58), X(60)), "none", "#FFFFFF", 3.2, ' opacity="0.75"')
        out += _p("M %.1f 172 Q %.1f 188 %.1f 204" % (X(70), X(74), X(77)), "none", "#FFFFFF", 2, ' opacity="0.6"')
        out += _p("M %.1f 164 L %.1f 174" % (X(28), X(36)), "none", "#FFFFFF", 2, ' opacity="0.7"')
    return out + "".join(_c(92, y, 2.2, _shade(coat, 0.85), edge, 1.2) for y in (190, 200))


# ---------------------------------------------------------------- nose and lips
@register(F.FACE_PARTS, "straight_nose")
def _straight_nose(part, a, skin):
    """A thin straight nose line down from between the eyes, and a small rounded tip."""
    nx, ny = a["nx"], a["ny"]
    shade = _shade(skin, 0.72)
    return (_p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (nx - 3, ny - 15, nx - 5, ny - 8, nx - 4, ny - 3), "none", shade, 2)
            + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f" % (nx - 6, ny - 1, nx - 5, ny + 4, nx, ny + 4,
                                                                             nx + 5, ny + 4, nx + 6, ny - 1), "none", INK, 2.2))


@register(F.FACE_PARTS, "soft_lips")
def _soft_lips(part, a, skin):
    """Small full lips at rest; every other mouth is the kit's own shape, untouched."""
    lip = part.get("color", "#D0858C")

    def draw(e, svg, marks, base):
        if e != "neutral" or ({"press", "smirk"} & set(marks)):
            return svg
        x, y = a["mx"], a["my"]
        edge = _shade(lip, 0.8)
        upper = ("M %.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
            x - 11, y, x - 7, y - 4.5, x - 3, y - 5, x, y - 2.5, x + 3, y - 5, x + 7, y - 4.5, x + 11, y, x, y + 1, x - 11, y))
        lower = "M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (x - 10, y + 1, x, y + 10, x + 10, y + 1,
                                                                            x, y + 2.5, x - 10, y + 1)
        return (_p(upper, lip, edge, 1.2) + _p(lower, lip, edge, 1.2)
                + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - 10.5, y + 0.8, x, y + 2.4, x + 10.5, y + 0.8), "none", INK, 1.8)
                + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - 3, y + 5, x, y + 6, x + 3, y + 5), "none", _shade(lip, 1.3), 1.4))
    return _layer(a, "mouth", 10, draw)


# ==================================================================================================
# Habits for the face kit (games/faces): what one face can wear that another face of the same person does
# not -- dimples, a furrow, a winged liner.
#
#     face  dimples   two small creases beside the corners of the mouth
#           furrow    two short upright creases between the brows (a frown that has set in)
#           liner     a winged line at the outer corner of each eye
#
# A character with alters (rm_characters) wears some of these only while one of them is out, beside the
# habits a look can carry as standing marks (look["marks"]: a squint, a set jaw, a half-smile).
# ==================================================================================================

def _dimples(part, a, skin):
    col = part.get("color", _shade(skin, 0.62))
    x, y = a["mx"], a["my"]
    return (_p("M %d %d q -4 4 0 9" % (x - 25, y - 7), "none", col, 2.6)
            + _p("M %d %d q 4 4 0 9" % (x + 25, y - 7), "none", col, 2.6))


@register(F.FACE_PARTS, "furrow")
def _furrow(part, a, skin):
    col = part.get("color", _shade(skin, 0.6))
    x, b = a["nx"], a["by"]
    return (_p("M %d %d q -2 6 0 11" % (x - 4, b + 3), "none", col, 2.4)
            + _p("M %d %d q 2 6 0 11" % (x + 4, b + 3), "none", col, 2.4))


@register(F.FACE_PARTS, "liner")
def _liner(part, a, skin):
    col = part.get("color", INK)
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    return (_p("M %d %d L %d %d" % (lx - 10, y - 2, lx - 19, y - 8), "none", col, 3.2)
            + _p("M %d %d L %d %d" % (rx + 10, y - 2, rx + 19, y - 8), "none", col, 3.2))


# ==================================================================================================
# Clothes for the face kit: bodies, the shoulders drawn under the head (and clipped to the badge by
# the caller), like the kit's tshirt, suit and hoodie.
#
#     look["body"] = {"part": "blazer", "color": "#2D3A55", "pin": "flag"}
#
# Every body takes "color" (the garment; the band on dog_collar; fur ignores it). The other keys:
#   robe            trim (the bands down the front)       a wizard's robe, stars on the shoulders
#   judge_robe      trim (the jabot)                      black, a white lace jabot
#   army_jacket     -                                     olive M-65: collar, epaulets, flapped pockets
#   coveralls       trim (the stitched name), patch       work coveralls: a zip, a name patch
#   flannel         trim (the plaid's thin line)          a plaid shirt, collar and buttons
#   apron           trim (the blouse)                     a diner apron over a blouse, a pencil in the pocket
#   windbreaker     trim (the chest stripe)               a zip-up with a stripe across the chest
#   blazer          trim (the shirt), pin                 pin "flag": a flag pin, "badge": a gold badge
#   quarter_zip     trim (the shirt)                      a quilted vest zipped over a shirt
#   sweater_vest    trim (the shirt), tie                 a V-neck vest; a tie when "tie" is a color
#   trench          -                                     a detective's trench coat, collar turned up
#   denim_jacket    trim (the stitching)                  pointed pocket flaps, copper buttons
#   leather_jacket  -                                     a biker jacket: wide lapels, a slanted zip
#   sequins         trim (the lapels), tie (a bow tie)    a sparkling stage jacket
#   tracksuit       trim (the stripes)                    a zip-up track jacket, striped sleeves
#   turtleneck      -                                     a rolled collar
#   scrubs          -                                     a V-neck (the skin shows), pens in the pocket
#   lab_coat        trim (the shirt), tie                 a white coat, a name badge, pens
#   waistcoat       trim (the shirt), tie (a cravat)      buttons and a gold watch chain
#   lace_collar     trim (the lace)                       a round lace collar over a dress (or feathers)
#   fur             trim (a paler chest)                  bare shoulders in the look's skin (part["fur"])
#   chassis         trim (the status light)               a robot's plated shoulders
#   high_collar     trim (the lining)                     a black coat whose collar stands up past the jaw
#   dog_collar      trim (the tag)                        bare fur shoulders, a collar, a round tag
# A tie given as true (not a color) is drawn in the garment's usual tie color.
#
# The caller passes the look's skin as part["fur"]; fur, dog_collar and the scrubs' V-neck use it.
#
# Most of a body hides under the chin: what shows is the crescent between the jaw and the badge's rim
# (y 176..197 in the middle, from y 160 at the sides), so every garment says what it is there.
# ==================================================================================================

SH = "M 16 204 Q 22 168 68 160 L 132 160 Q 178 168 184 204 Z"      # the kit's shoulders
FUR = "M 30 204 Q 40 172 72 164 L 128 164 Q 160 172 170 204 Z"     # an animal's (the neckerchief's)
GOLD, SILVER = "#E2B73C", "#C9CDD3"


def _box(x0, y0, x1, y1, r):
    return ("M %.1f %.1f H %.1f A %.1f %.1f 0 0 1 %.1f %.1f V %.1f A %.1f %.1f 0 0 1 %.1f %.1f H %.1f "
            "A %.1f %.1f 0 0 1 %.1f %.1f V %.1f A %.1f %.1f 0 0 1 %.1f %.1f Z" % (
                x0 + r, y0, x1 - r, r, r, x1, y0 + r, y1 - r, r, r, x1 - r, y1, x0 + r, r, r, x0, y1 - r,
                y0 + r, r, r, x0 + r, y0))


def _clip(d, inner):
    """inner, clipped to the path d. The id comes from the path, so equal ids always mean equal clips."""
    cid = "rmfw%08x" % zlib.crc32(d.encode())
    return ('<defs><clipPath id="%s"><path d="%s"/></clipPath></defs><g clip-path="url(#%s)">%s</g>'
            % (cid, d, cid, inner))


def _mirror(d_fn):
    """A left-side piece and its mirror image: d_fn(sign) draws it with x = 100 + sign * dx."""
    return d_fn(-1) + d_fn(1)


def _dark(col):
    h = col.lstrip("#")
    return (0.299 * int(h[0:2], 16) + 0.587 * int(h[2:4], 16) + 0.114 * int(h[4:6], 16)) < 90


def _col(part, color, default):
    return part.get("color") or color or default


def _opt(part, key, default):
    """The color a part gives under key; the default when it gives none (or true, for "tie": true)."""
    v = part.get(key)
    return v if isinstance(v, str) and v else default


def _zip(y0, y1):
    """A zip down the middle, its pull near the top."""
    d = "M 100 %d L 100 %d" % (y0, y1)
    return (_p(d, "none", INK, 3.5) + _p(d, "none", SILVER, 1.6, ' stroke-dasharray="1.6 1.6"')
            + _p(_box(97, y0 + 6, 103, y0 + 15, 1.5), SILVER, INK, 2))


def _collar_points(col, y_tip=184, width=3.5):
    """A shirt collar's two points, turned down either side of the neck."""
    return _mirror(lambda s: _p("M %d 160 L %d %d L %d 170 Z" % (100 + s * 26, 100 + s * 14, y_tip, 100 + s * 1),
                                col, INK, width))


# ---------------------------------------------------------------- robes
@register(BODIES, "robe")
def _robe(part, color, a):
    col = _col(part, color, "#5B3F8C")
    trim = _opt(part, "trim", GOLD)
    out = _p(SH, col, INK, 5) + _p("M 72 160 L 128 160 L 100 198 Z", _shade(col, 0.6), INK, 3.5)
    out += _mirror(lambda s: _p("M %d 160 L 100 198 L %d 205 L %d 166 Z" % (100 + s * 28, 100 + s * 8, 100 + s * 36),
                                trim, INK, 3))
    return out + _star(54, 180, 6.5, trim, INK, 1.6) + _star(146, 180, 6.5, trim, INK, 1.6)


@register(BODIES, "judge_robe")
def _judge_robe(part, color, a):
    col = _col(part, color, "#1E2024")
    lace = _opt(part, "trim", "#FBFAF6")
    pleat = _shade(col, 1.4) if _dark(col) else _shade(col, 0.7)
    out = _p(SH, col, INK, 5)
    out += _p("M 44 204 Q 46 184 58 172 M 156 204 Q 154 184 142 172 M 30 204 Q 34 186 44 176 M 170 204 Q 166 186 156 176",
              "none", pleat, 2.5)

    def tier(y, w, h, n=4):                    # one ruffled tier: a flared tab, its hem scalloped
        x1, x0 = 100 + w + 3, 100 - w - 3
        step = (x1 - x0) / float(n)
        hem = "".join("Q %.1f %.1f %.1f %.1f " % (x1 - step * (i + .5), y + h + 5, x1 - step * (i + 1), y + h)
                      for i in range(n))
        return _p("M %.1f %.1f L %.1f %.1f L %.1f %.1f %sZ" % (100 - w, y, 100 + w, y, x1, y + h, hem), lace, INK, 2.5)
    return out + tier(164, 12, 14) + tier(176, 17, 15, 5)


# ---------------------------------------------------------------- jackets and coats
@register(BODIES, "army_jacket")
def _army_jacket(part, color, a):
    col = _col(part, color, "#5E6B3F")
    dark = _shade(col, 0.78)
    out = _p(SH, col, INK, 5)
    out += _mirror(lambda s: _p("M %d 164 L %d 170 L %d 180 L %d 173 Z" % (100 + s * 34, 100 + s * 36, 100 + s * 64,
                                                                           100 + s * 63), dark, INK, 3)
                   + _c(100 + s * 38, 168, 2.4, dark, INK, 1.5))                 # epaulets
    out += _collar_points(dark, 186)
    out += _p("M 97 172 L 103 172 L 103 206 L 97 206 Z", dark, INK, 2.5)       # the snap placket
    out += _c(100, 188, 1.8, INK, None)
    out += _mirror(lambda s: _p("M %d 177 L %d 177 L %d 185 L %d 189 L %d 185 Z" % (100 + s * 16, 100 + s * 40,
                                100 + s * 40, 100 + s * 28, 100 + s * 16), dark, INK, 3)
                   + _c(100 + s * 28, 184, 2, INK, None))                      # flapped chest pockets
    return out


@register(BODIES, "coveralls")
def _coveralls(part, color, a):
    col = _col(part, color, "#3B5B82")
    dark = _shade(col, 0.8)
    out = _p(SH, col, INK, 5) + _collar_points(dark, 184) + _zip(170, 206)
    out += _e(125, 183, 12, 7, _opt(part, "patch", "#FFFFFF"), INK, 2.5)
    out += _p("M 117 184 Q 119 179 121 184 Q 123 188 125 183 Q 127 179 129 184 L 133 182", "none",
              _opt(part, "trim", "#C0392B"), 1.8)
    out += _p("M 60 178 L 80 178", "none", dark, 2.5) + _p("M 64 176 L 64 170", "none", "#F2C94C", 3)   # a pencil
    return out


@register(BODIES, "flannel")
def _flannel(part, color, a):
    col = _col(part, color, "#B23A2E")
    dark, thin = _shade(col, 0.55), part.get("trim") or _shade(col, 1.55)
    plaid = "".join('<rect x="%d" y="150" width="11" height="60" fill="%s" opacity="0.5"/>' % (x, dark)
                    for x in range(20, 190, 28))
    plaid += "".join('<rect x="0" y="%d" width="200" height="9" fill="%s" opacity="0.5"/>' % (y, dark) for y in (168, 190))
    plaid += _p(" ".join("M %d 150 L %d 210" % (x + 17, x + 17) for x in range(20, 190, 28))
                + " M 0 181 L 200 181 M 0 203 L 200 203", "none", thin, 1.6, ' opacity="0.8"')
    out = _p(SH, col, None) + _clip(SH, plaid) + _p(SH, "none", INK, 5)
    out += _collar_points(col, 184) + _p("M 100 172 L 100 206", "none", INK, 2.5)
    return out + _c(104, 182, 2.4, "#F4F1EA", INK, 1.5) + _c(104, 192, 2.4, "#F4F1EA", INK, 1.5)


@register(BODIES, "apron")
def _apron(part, color, a):
    apron = _col(part, color, "#F2EEE4")
    blouse = _opt(part, "trim", "#C75B6E")
    out = _p(SH, blouse, INK, 5)
    out += _mirror(lambda s: _p("M %d 181 L %d 181 L %d 161 L %d 162 Z" % (100 + s * 27, 100 + s * 21, 100 + s * 36,
                                                                           100 + s * 42), apron, INK, 2.5))
    out += _p(_box(72, 177, 128, 214, 6), apron, INK, 3.5)
    out += _p("M 110 180 L 110 190", "none", "#F2C94C", 3.5) + _p("M 108.5 180 L 110 176 L 111.5 180 Z", "#3B3D42", None)
    out += _p(_box(90, 187, 116, 204, 3), _shade(apron, 0.92), INK, 2.5)       # the pocket, a pencil in it
    return out


@register(BODIES, "windbreaker")
def _windbreaker(part, color, a):
    col = _col(part, color, "#2C6FB7")
    stripe = _opt(part, "trim", "#F4F4F4")
    band = '<rect x="0" y="178" width="200" height="9" fill="%s"/>' % stripe
    band += _p("M 0 178 L 200 178 M 0 187 L 200 187", "none", INK, 2.5)
    out = _p(SH, col, None) + _clip(SH, band) + _p(SH, "none", INK, 5)
    out += _p("M 30 196 Q 36 182 48 176 M 170 196 Q 164 182 152 176", "none", "#FFFFFF", 2.5, ' opacity="0.35"')
    return out + _zip(172, 206)


def _lapels(col, shirt):
    """A shirt's open V between notched lapels."""
    return (_p("M 82 160 L 100 200 L 118 160 Z", shirt, INK, 3.5)
            + _mirror(lambda s: _p("M %d 160 L %d 170 L %d 176 L %d 184 L %d 206 L 100 200 Z" % (
                100 + s * 18, 100 + s * 34, 100 + s * 26, 100 + s * 32, 100 + s * 2), _shade(col, 0.82), INK, 3.5)))


def _flag_pin(x, y):
    return (_p(_box(x - 6, y - 4, x + 6, y + 4, 0.5), "#FFFFFF", INK, 1.4)
            + _p("M %.1f %.1f H %.1f M %.1f %.1f H %.1f" % (x - 5.3, y - 1.4, x + 5.3, x - 5.3, y + 1.6, x + 5.3), "none",
                 "#C0392B", 1.3)
            + _p(_box(x - 6, y - 4, x - 1, y, 0.3), "#2C4A8C", None)
            + _p(_box(x - 6, y - 4, x + 6, y + 4, 0.5), "none", INK, 1.4))


def _badge_pin(x, y):
    return (_p("M %d %d L %d %d L %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 6, y - 6, x + 6, y - 6, x + 6, y + 1,
               x + 6, y + 6, x, y + 8, x - 6, y + 6, x - 6, y + 1), GOLD, INK, 1.8)
            + _star(x, y + 0.5, 3.4, _shade(GOLD, 0.7), None))


@register(BODIES, "blazer")
def _blazer(part, color, a):
    col = _col(part, color, "#2D3A55")
    out = _p(SH, col, INK, 5) + _lapels(col, _opt(part, "trim", "#FFFFFF"))
    out += _p("M 134 185 L 146 183", "none", _shade(col, 0.7), 2.5)              # a breast pocket's welt
    pin = part.get("pin")
    if pin == "flag":
        out += _flag_pin(121, 183)
    elif pin == "badge":
        out += _badge_pin(121, 182)
    return out


@register(BODIES, "quarter_zip")
def _quarter_zip(part, color, a):
    vest = _col(part, color, "#2F3642")
    shirt = _opt(part, "trim", "#AFC8E6")
    d = "M 36 204 Q 40 174 70 161 L 130 161 Q 160 174 164 204 Z"
    out = _p(SH, shirt, INK, 5)
    quilt = _p("M 20 180 Q 100 192 180 180 M 20 196 Q 100 208 180 196", "none", _shade(vest, 0.62), 2.5)
    out += _p(d, vest, None) + _clip(d, quilt) + _p(d, "none", INK, 4.5)
    out += _zip(176, 206) + _collar_points(shirt, 181, 3)
    return out + _p(_box(116, 178, 128, 183, 1), "#E8ECF0", INK, 1.5)             # a small logo patch


@register(BODIES, "sweater_vest")
def _sweater_vest(part, color, a):
    vest = _col(part, color, "#B5895A")
    shirt = _opt(part, "trim", "#F4F2EC")
    out = _p(SH, shirt, INK, 5)
    if part.get("tie"):
        tie = _opt(part, "tie", "#8E2B2B")
        out += (_p("M 94 164 L 106 164 L 104 174 L 96 174 Z", tie, INK, 2.5)
                + _p("M 96 174 L 104 174 L 108 200 L 100 208 L 92 200 Z", tie, INK, 2.5))
    d = "M 38 204 Q 44 174 70 163 L 84 163 L 100 194 L 116 163 L 130 163 Q 156 174 162 204 Z"
    diamonds = "".join(_p("M %d %d l 7 9 l -7 9 l -7 -9 Z" % (x, y), _shade(vest, 0.82), None)
                       for x, y in ((60, 172), (140, 172), (74, 188), (126, 188), (46, 190), (154, 190)))
    diamonds += _p("M 40 172 L 80 208 M 80 172 L 40 208 M 120 172 L 160 208 M 160 172 L 120 208", "none",
                   _shade(vest, 1.3), 1.4, ' opacity="0.8"')
    out += _p(d, vest, None) + _clip(d, diamonds) + _p(d, "none", INK, 4.5)
    return out + _p("M 83 164 L 100 197 L 117 164", "none", _shade(vest, 0.72), 4.5) + _collar_points(shirt, 174, 3)


@register(BODIES, "trench")
def _trench(part, color, a):
    col = _col(part, color, "#B89B6A")
    dark = _shade(col, 0.8)
    out = _p(SH, col, INK, 5)
    # the collar turned up: its points stand either side of the jaw, behind the head
    out += _mirror(lambda s: _p("M %d 166 L %d 116 L %d 122 L %d 158 L %d 182 Z" % (100 + s * 28, 100 + s * 50,
                                100 + s * 62, 100 + s * 64, 100 + s * 46), dark, INK, 4))
    out += _mirror(lambda s: _p("M %d 166 L %d 176 L %d 181 L %d 188 L %d 206 L 100 198 Z" % (
        100 + s * 26, 100 + s * 40, 100 + s * 32, 100 + s * 38, 100 + s * 4), _shade(col, 0.9), INK, 3.5))
    return out


@register(BODIES, "denim_jacket")
def _denim_jacket(part, color, a):
    col = _col(part, color, "#4A74A8")
    thread = _opt(part, "trim", "#E3A857")
    dark = _shade(col, 0.8)
    copper = "#C27C3A"
    out = _p(SH, col, INK, 5)
    out += _p("M 24 186 Q 40 176 58 176 M 176 186 Q 160 176 142 176", "none", thread, 1.8, ' stroke-dasharray="3 2"')
    out += _collar_points(dark, 186) + _p("M 100 172 L 100 206", "none", INK, 3)
    out += _mirror(lambda s: _p("M %d 178 L %d 178 L %d 185 L %d 191 L %d 185 Z" % (100 + s * 15, 100 + s * 39,
                                100 + s * 39, 100 + s * 27, 100 + s * 15), dark, INK, 3)
                   + _p("M %d 181 L %d 181 L %d 186" % (100 + s * 18, 100 + s * 36, 100 + s * 36), "none", thread, 1.4,
                        ' stroke-dasharray="2 1.6"')
                   + _c(100 + s * 27, 186, 2.3, copper, INK, 1.3))
    return out + _c(104, 184, 2.4, copper, INK, 1.3) + _c(104, 193, 2.4, copper, INK, 1.3)


@register(BODIES, "leather_jacket")
def _leather_jacket(part, color, a):
    col = _col(part, color, "#27272B")
    lapel = _shade(col, 1.3) if _dark(col) else _shade(col, 0.8)
    out = _p(SH, col, INK, 5)
    out += _p("M 30 194 Q 36 178 52 170 M 170 194 Q 164 178 148 170", "none", "#FFFFFF", 3, ' opacity="0.28"')
    out += _p("M 76 160 L 54 172 L 66 180 L 58 190 L 94 206 L 102 196 Z", lapel, INK, 3.5)
    out += _p("M 124 160 L 148 170 L 136 179 L 146 188 L 108 206 L 102 196 Z", lapel, INK, 3.5)
    out += _p("M 120 166 L 104 206", "none", INK, 3.5) + _p("M 120 166 L 104 206", "none", SILVER, 1.6,
                                                            ' stroke-dasharray="1.6 1.6"')
    return out + _c(62, 177, 2.2, SILVER, INK, 1.2) + _c(141, 175, 2.2, SILVER, INK, 1.2) + _c(66, 188, 2.2, SILVER, INK, 1.2)


@register(BODIES, "sequins")
def _sequins(part, color, a):
    col = _col(part, color, "#8E3FB8")
    lapel = part.get("trim") or _shade(col, 0.55)
    hi, lo = _shade(col, 1.45), _shade(col, 0.78)
    dots = ""
    for j, y in enumerate(range(160, 208, 7)):
        for i, x in enumerate(range(14 + (j % 2) * 4, 190, 8)):
            dots += _c(x, y, 2.6, hi if (i + j) % 3 == 0 else lo if (i + j) % 3 == 1 else col, None)
    out = _p(SH, col, None) + _clip(SH, dots) + _p(SH, "none", INK, 5)
    out += _p("M 88 160 Q 84 180 100 198 Q 116 180 112 160 Z", "#1E1F24", INK, 3)
    out += _mirror(lambda s: _p("M %d 160 Q %d 184 %d 206 L 100 198 Q %d 180 %d 160 Z" % (
        100 + s * 20, 100 + s * 36, 100 + s * 2, 100 + s * 14, 100 + s * 12), lapel, INK, 3.5))
    if part.get("tie"):                         # a bow tie
        t = _opt(part, "tie", "#1E1F24")
        out += (_p("M 100 180 L 90 175 L 90 187 Z M 100 180 L 110 175 L 110 187 Z", t, INK, 2.2) + _c(100, 180, 2.6, t, INK, 1.8))
    return out + _star(50, 180, 6, "#FFFFFF", INK, 1.3) + _star(136, 185, 5, "#FFFFFF", INK, 1.2) + _star(132, 170, 3.5, "#FFFFFF", None)


@register(BODIES, "tracksuit")
def _tracksuit(part, color, a):
    col = _col(part, color, "#1F4E8C")
    stripe = _opt(part, "trim", "#F4F4F4")
    out = _p(SH, col, INK, 5)
    out += _mirror(lambda s: _p("M %d 165 Q %d 172 %d 204 M %d 170 Q %d 178 %d 204" % (
        100 + s * 34, 100 + s * 73, 100 + s * 77, 100 + s * 36, 100 + s * 66, 100 + s * 69), "none", stripe, 4))
    out += _p("M 72 164 Q 100 180 128 164", "none", stripe, 3)
    return out + _zip(176, 206)


@register(BODIES, "turtleneck")
def _turtleneck(part, color, a):
    col = _col(part, color, "#1E1F24")
    roll = _shade(col, 1.3) if _dark(col) else _shade(col, 0.88)
    out = _p(SH, col, INK, 5)
    out += _p("M 68 164 Q 100 178 132 164 L 134 180 Q 100 196 66 180 Z", roll, INK, 4)
    ribs = ""
    for x in range(76, 126, 8):                 # the ribbing, between the roll's curved edges
        t, u = (x - 68) / 64.0, (134 - x) / 68.0
        ribs += "M %d %.1f L %d %.1f " % (x, 164 + 28 * t * (1 - t) + 3, x, 180 + 32 * u * (1 - u) - 3)
    return out + _p(ribs.strip(), "none", _shade(roll, 0.8), 2)


@register(BODIES, "scrubs")
def _scrubs(part, color, a):
    col = _col(part, color, "#4FA3A5")
    out = _p(SH, col, INK, 5)
    out += _p("M 82 160 L 100 192 L 118 160 Z", part.get("fur", "#E1AE86"), INK, 3)
    out += _p("M 80 160 L 100 196 L 120 160", "none", _shade(col, 0.75), 4.5)
    out += (_p("M 121 168 L 121 184", "none", INK, 5.5) + _p("M 121 168 L 121 184", "none", "#2B6CB0", 3)
            + _p("M 128 170 L 128 184", "none", INK, 5.5) + _p("M 128 170 L 128 184", "none", "#E0533A", 3))
    return out + _p(_box(114, 180, 136, 198, 2.5), col, INK, 2.5)


@register(BODIES, "lab_coat")
def _lab_coat(part, color, a):
    col = _col(part, color, "#F6F7F8")
    shirt = _opt(part, "trim", "#9DB6D0")
    out = _p(SH, col, INK, 5)
    out += _p("M 82 160 L 100 200 L 118 160 Z", shirt, INK, 3.5)
    if part.get("tie"):
        out += _p("M 96 170 L 104 170 L 106 196 L 100 202 L 94 196 Z", _opt(part, "tie", "#2C4A8C"), INK, 2.2)
    out += _mirror(lambda s: _p("M %d 160 L %d 172 L %d 178 L %d 186 L %d 206 L 100 200 Z" % (
        100 + s * 18, 100 + s * 36, 100 + s * 28, 100 + s * 34, 100 + s * 3), _shade(col, 0.93), INK, 3.5))
    out += _p(_box(114, 182, 128, 192, 1.5), "#FFFFFF", INK, 1.8) + _p("M 115 185 H 127", "none", "#2F6FA8", 2.5)
    out += _p("M 58 175 L 58 186 M 64 174 L 64 186", "none", "#2B2E33", 3)      # pens in the breast pocket
    return out + _p(_box(50, 183, 74, 204, 2), col, INK, 2.5)


@register(BODIES, "waistcoat")
def _waistcoat(part, color, a):
    vest = _col(part, color, "#7A2E35")
    shirt = _opt(part, "trim", "#F4F2EC")
    out = _p(SH, shirt, INK, 5) + _collar_points(shirt, 176, 3)
    if part.get("tie"):                         # a cravat
        out += _p("M 92 166 Q 100 162 108 166 L 104 184 Q 100 188 96 184 Z", _opt(part, "tie", "#F4F2EC"), INK, 2.2)
    d = "M 40 204 Q 46 176 70 163 L 86 163 L 100 184 L 114 163 L 130 163 Q 154 176 160 204 Z"
    out += _p(d, vest, INK, 4.5)
    out += _p("M 120 186 L 134 184", "none", _shade(vest, 0.6), 2.5)
    out += _p("M 102 190 Q 112 200 124 186", "none", GOLD, 2.2, ' stroke-dasharray="2.4 1.6"')
    return out + _c(100, 189, 2.6, GOLD, INK, 1.5) + _c(100, 195, 2.6, GOLD, INK, 1.5) + _c(124, 186, 1.8, GOLD, INK, 1)


def _scallops(cx, cy, rx, ry, n=11, bump=4.5):
    """The lower half of an ellipse, scalloped outward, left to right."""
    pts = [(cx + rx * math.cos(math.pi - math.pi * i / n), cy + ry * math.sin(math.pi - math.pi * i / n))
           for i in range(n + 1)]
    out = "M %.1f %.1f " % pts[0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        nx, ny = mx - cx, (my - cy) * (rx / float(ry)) ** 2
        k = bump / max(1e-6, (nx * nx + ny * ny) ** 0.5)
        out += "Q %.1f %.1f %.1f %.1f " % (mx + nx * k * 2, my + ny * k * 2, x1, y1)
    return out


@register(BODIES, "lace_collar")
def _lace_collar(part, color, a):
    col = _col(part, color, "#2B2B30")
    lace = _opt(part, "trim", "#FBFAF5")
    out = _p(SH, col, INK, 5)
    d = _scallops(100, 160, 60, 32) + "Q 100 174 40 160 Z"
    out += _p(d, lace, INK, 3)
    holes = "".join(_c(100 + 48 * math.cos(t), 160 + 22 * math.sin(t), 2, _shade(lace, 0.78), None)
                    for t in [math.pi * (i + .5) / 9 for i in range(9)])
    return out + holes + _p(_scallops(100, 160, 38, 16, 7, 3) + "Q 100 170 62 160", "none", _shade(lace, 0.78), 1.6)


# ---------------------------------------------------------------- fur and machines
@register(BODIES, "fur")
def _fur(part, color, a):
    fur = part.get("fur") or _col(part, color, "#8F9297")
    out = _p(FUR, fur, INK, 5)
    if part.get("trim"):                        # a paler chest
        out += _p("M 74 166 Q 100 214 126 166 Q 100 176 74 166 Z", part["trim"], None)
    tuft = _shade(fur, 0.7)
    return out + _p("M 44 190 q 4 -8 10 -9 M 50 196 q 4 -7 9 -8 M 156 190 q -4 -8 -10 -9 M 150 196 q -4 -7 -9 -8 "
                    "M 94 196 q 6 -5 12 0", "none", tuft, 2.5)


@register(BODIES, "chassis")
def _chassis(part, color, a):
    col = _col(part, color, "#8C939B")
    light = _opt(part, "trim", "#8FF3FF")
    dark, hi = _shade(col, 0.72), _shade(col, 1.18)
    out = _p(SH, col, INK, 5)
    out += _p("M 62 168 L 138 168 L 130 206 L 70 206 Z", hi, INK, 3.5)
    out += "".join(_c(x, y, 2.2, dark, INK, 1.2) for x, y in ((69, 175), (131, 175), (77, 189), (123, 189)))
    out += _p("M 88 194 L 112 194", "none", dark, 2.5)                           # a vent slot
    out += _p("M 100 185 m -7 0 a 7 7 0 1 0 14 0 a 7 7 0 1 0 -14 0", "none", light, 9, ' opacity="0.3"')
    out += _c(100, 185, 5, light, INK, 2.5)
    out += _mirror(lambda s: _p("M %d 204 Q %d 172 %d 164 Q %d 161 %d 172 Q %d 178 %d 204 Z" % (
        100 + s * 86, 100 + s * 84, 100 + s * 54, 100 + s * 38, 100 + s * 30, 100 + s * 50, 100 + s * 56), dark, INK, 4)
                   + _c(100 + s * 58, 176, 2.2, col, INK, 1.2) + _c(100 + s * 70, 188, 2.2, col, INK, 1.2))
    return out


@register(BODIES, "high_collar")
def _high_collar(part, color, a):
    col = _col(part, color, "#17181C")
    lining = _opt(part, "trim", "#8E1B2B")
    out = _p(SH, col, INK, 5)
    out += _mirror(lambda s: _p("M %d 170 L %d 92 L %d 150 L %d 184 Z" % (100 + s * 24, 100 + s * 72, 100 + s * 80,
                                100 + s * 60), col, INK, 4)
                   + _p("M %d 168 L %d 102 L %d 150 L %d 176 Z" % (100 + s * 30, 100 + s * 68, 100 + s * 72, 100 + s * 56),
                        lining, None))
    out += _p("M 100 176 L 100 206", "none", _shade(col, 1.5), 2.5)
    return out + "".join(_p("M %d %d L %d %d" % (90, y, 110, y), "none", SILVER, 3) + _c(90, y, 2.4, SILVER, INK, 1.2)
                         + _c(110, y, 2.4, SILVER, INK, 1.2) for y in (184, 194))


@register(BODIES, "dog_collar")
def _dog_collar(part, color, a):
    fur = part.get("fur") or "#B08A5A"
    band = _col(part, color, "#C0392B")
    tag = _opt(part, "trim", GOLD)
    out = _p(FUR, fur, INK, 5)
    out += _p("M 64 164 Q 100 188 136 164 L 136 174 Q 100 198 64 174 Z", band, INK, 3.5)
    out += "".join(_c(x, y, 1.8, SILVER, None) for x, y in ((76, 176), (88, 181), (112, 181), (124, 176)))
    return out + _c(100, 186, 2.8, "none", INK, 2) + _c(100, 192, 6.5, tag, INK, 2.5) + _c(100, 192, 2.5, _shade(tag, 0.75), None)
