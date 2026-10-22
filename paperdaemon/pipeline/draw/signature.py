r"""The daemon's signature: a devil head and "Daemon", written with a broad nib.

Used by the daemon when it writes on a page itself -- a failure note, an
acknowledgment -- so it is never mistaken for the assistant's answer or the user's writing.

Two pieces, deliberately different in kind:

* `devil_head()` is a LIBRARY element: five simple polylines, no cleverness,
  the sort of thing rm_elements exists to hold. It is a STAMP, so it is never
  sheared or slanted.

* the word is TRACED from a reference signature, not constructed.
  Three hand-built cursive versions were attempted and all three read "Daemom"
  or "DormOm" -- six connected lowercase arches are not separable at the size
  this gets written, and no amount of adjusting arch counts, widths or tails
  fixed it. Tracing a real signature did, first try.

  The trace is CENTER-LINE (threshold -> Zhang-Suen thinning -> path tracing
  -> simplify -> Chaikin), not edge-detected: the reference glyphs are solid
  black, so XDoG would have produced hollow doubled outlines of every stroke.
  The geometry lives in `rm_sig_daemon.json`.

Drawn with the CALLIGRAPHY pen (tool 21, thickness_scale 1.0 -- what the device
itself uses) and a real broad-nib width model: the nib is held at NIB_ANGLE and
the stroke width is the projection of its edge across the direction of travel,
so it is widest square to the edge and a hairline along it.

Authored in PEN SPACE: baseline y=0, x-height y=1, y UP, x advancing right.
`place()` scales and flips into page coordinates.
"""
import io
import math
import os
import sys
from paperdaemon.pipeline import draw as A
from paperdaemon import paths

def devil_head(cx=0.0, cy=0.0, r=1.0):
    """Five polylines in pen space, centered on (cx, cy), radius r.

    Second pass. Version one read as a CAT: triangular horns pinned to the
    sides of a round face are ears, and smiling arc eyes finished the job.
    Horns now sweep up and outward from the CROWN and taper to a point, the
    jaw is a narrow wedge rather than a circle, and the eyes are angled
    slashes.
    """
    def P(x, y):
        return (cx + x * r, cy + y * r)

    # face: broad brow, straight cheeks, pointed chin
    face = [P(-0.88, 0.52), P(-0.96, 0.86), P(-0.62, 1.02), P(0.00, 1.10),
            P(0.62, 1.02), P(0.96, 0.86), P(0.88, 0.52),
            P(0.74, -0.10), P(0.40, -0.78), P(0.00, -1.16),
            P(-0.40, -0.78), P(-0.74, -0.10), P(-0.88, 0.52)]
    horns = []
    for sx in (-1, 1):
        base_in, base_out = P(sx * 0.30, 1.00), P(sx * 0.78, 0.86)
        horns.append(A.bez(base_out, P(sx * 1.28, 1.42), P(sx * 1.16, 2.02),
                           P(sx * 0.86, 2.16), n=18)
                     + A.bez(P(sx * 0.94, 1.72), P(sx * 0.70, 1.36),
                             base_in, base_in, n=18))
    eyes = [[P(-0.62, 0.62), P(-0.20, 0.34)], [P(0.62, 0.62), P(0.20, 0.34)]]
    grin = A.bez(P(-0.46, -0.18), P(-0.26, -0.56), P(0.26, -0.56),
                 P(0.46, -0.18), n=26)
    return [face] + horns + eyes + [grin]


# Forward slant, as a shear, for a more italic hand.
# A shear is the right tool because it leans the whole hand consistently --
# the letters and the swash tilt together, which is what makes a signature look
# written rather than assembled. The devil head is NOT sheared -- pass slant=0
# for anything that is a stamp rather than handwriting.
SLANT = 0.30


def place(polys, x, y, height, flip=True, slant=SLANT):
    """Pen space -> page coordinates. `height` is the x-height in page units."""
    s = float(height)
    out = []
    for p in polys:
        out.append([(x + (px + slant * py) * s,
                     y - py * s if flip else y + py * s)
                    for px, py in p])
    return out


# An optional traced signature (a list of polylines in pen space) from the content folder; without it
# the word is lettered in the tablet's own stroke font.
DAEMON_TRACE = paths.content_path("signature", "rm_sig_daemon.json")
_TRACED = [None]


def _lettered_word(word="Daemon", track=0.08):
    """The word in the stroke lettering of rm_text, in pen space (baseline y=0, cap height y=1, y UP)."""
    from paperdaemon.pipeline.draw import lettering as T
    out, x = [], 0.0
    for ch in word:
        adv, polys = T.G[ch]
        out += [[(x + px, py) for px, py in poly] for poly in polys]
        x += adv + track
    return out


def daemon_traced():
    """The signature, center-line traced from a reference image.

    Three hand-built cursive versions read "Daemom" / "DormOm" no matter what
    was done to the letterforms -- six connected lowercase arches are simply
    not separable at the size this gets written. The honest answer was to
    trace a real signature image rather than keep inventing letters.

    Center-line, not edge-detected: the glyphs are solid black, so XDoG would
    have produced OUTLINES -- a doubled hollow version of every stroke. The
    chain is threshold -> Zhang-Suen thinning -> path tracing -> simplify ->
    Chaikin, which yields single strokes down the middle of the ink.

    Pen space, same convention as everything else: baseline y=0, y UP.
    """
    if _TRACED[0] is None:
        if os.path.isfile(DAEMON_TRACE):
            import json
            with io.open(DAEMON_TRACE, encoding="utf-8") as f:
                _TRACED[0] = [[(float(x), float(y)) for x, y in p] for p in json.load(f)]
        else:
            _TRACED[0] = _lettered_word()
    return _TRACED[0]


# A broad nib is held at a fixed angle and the stroke width is the projection
# of the nib edge across the direction of travel: widest when you move square
# to the edge, hairline when you move along it. 40 degrees is the standard
# italic hold -- it puts the fat strokes on the down-right diagonal and the
# hairlines on the up-right, which is what makes calligraphy look written
# rather than merely thick.
NIB_ANGLE = 40.0
NIB_THIN = 0.16          # hairline, as a fraction of the full nib width


def nib_profile(pts, full, angle_deg=NIB_ANGLE):
    """Per-point widths for a broad nib, from the LOCAL direction of travel.

    Drawing.stroke takes a callable of t in [0,1], so the direction-derived
    widths are precomputed here and looked up by index.
    """
    a = math.radians(angle_deg)
    ws = []
    n = len(pts)
    for i in range(n):
        j0, j1 = max(0, i - 1), min(n - 1, i + 1)
        dx = pts[j1][0] - pts[j0][0]
        dy = pts[j1][1] - pts[j0][1]
        if dx == 0 and dy == 0:
            ws.append(full * NIB_THIN)
            continue
        th = math.atan2(dy, dx)
        w = abs(math.sin(th - a))
        ws.append(full * (NIB_THIN + (1.0 - NIB_THIN) * w))
    if n > 1:                       # ease the very ends, as a nib lifts
        ws[0] = ws[0] * 0.75
        ws[-1] = ws[-1] * 0.75
    return lambda t, _w=ws: _w[int(round(t * (len(_w) - 1)))]


def draw_signature(d, x, y, height=34.0, dash=True, nib=None):
    """Stroke the signature into a Drawing with the CALLIGRAPHY pen.

    The calligraphy pen is used with accurate pen angles, so the word is
    written with a real nib model rather than a swelling profile: tool 21,
    thickness_scale 1.0 (what the device itself uses), and per-point widths
    from the angle between travel and the nib edge.
    """
    from rmscene.scene_items import Pen
    full = height * 0.34
    for k, poly in enumerate(signature(x, y, height=height, dash=dash)):
        if k == 0 and dash:
            d.stroke(poly, width=max(3, int(full * 0.55)), tool=Pen.CALIGRAPHY)
        else:
            d.stroke(poly, width=nib_profile(poly, full, nib or NIB_ANGLE),
                     tool=Pen.CALIGRAPHY)
    return y


def signature(x, y, height=34.0, dash=True):
    """The whole mark: an em dash, the traced signature, then the devil head.

    `x, y` is the LEFT end of the dash, sitting on the baseline `y`.
    The traced mark carries its own flourish, so there is no separate swash.
    """
    out = []
    cur = x
    if dash:
        out.append([(cur, y - height * 0.42), (cur + height * 0.9, y - height * 0.42)])
        cur += height * 1.15
    word = daemon_traced()
    # NO SHEAR. It is already handwriting; shearing it again just leans a
    # signature that was never upright to begin with.
    out += [[(cur + px * height, y - py * height) for px, py in p] for p in word]
    cur += max(px for p in word for px, _ in p) * height
    # THE ICON IS NOT ITALIC -- a stamp, not handwriting. It stands clear of the name: its own left edge (a horn's
    # tip, the widest it gets) a third of the height past the signature's last stroke.
    head = devil_head(0.0, 0.0, 1.0)
    k = height * 0.62
    cur += height * 0.35 - min(px for p in head for px, _ in p) * k
    out += place(head, cur, y - height * 0.55, k, slant=0.0)
    return out


def signature_width(height=34.0, dash=True):
    """How wide the whole mark is, written at `height`: the room a line must leave for it."""
    xs = [px for p in signature(0.0, 0.0, height=height, dash=dash) for px, _ in p]
    return max(xs) - min(0.0, min(xs))


# ------------------------------------------------------------------ placement
# The daemon signs in the GUTTER, not in the page: below all drawn content,
# below the "safe zone" of the page -- or at the VERY bottom of the page.
#
# That is what makes an unattended write defensible. A note in the margin is a
# stamp on an envelope; the same note dropped next to the user's handwriting is
# the daemon editing their notebook. The band below SAFE_BOTTOM holds nothing the
# user ever put there, so nothing of theirs can be pushed around or overlapped.
# ON THE PAGE'S OWN FRAME (tablets.TABLETS): the numbers below are a Paper Pro page's (1620 x 2160); a page of
# another tablet keeps the same distances from its own bottom and left edge (_gutter).
PAGE_BOTTOM = 2160.0
SAFE_BOTTOM = 2060.0
FOOTER_Y = 2112.0             # baseline: below the safe zone, above the edge
FOOTER_MAX = 2136.0           # never closer than this to the paper edge
FOOTER_X = -690.0


def _gutter(frame):
    """(baseline, lowest baseline, left x) of the footer on a page of this frame: the Paper Pro's distances from the
    bottom and the left edge."""
    w, h = (float(v) for v in (frame or (1620.0, PAGE_BOTTOM)))
    return h - (PAGE_BOTTOM - FOOTER_Y), h - (PAGE_BOTTOM - FOOTER_MAX), -w / 2.0 + (810.0 + FOOTER_X)


def footer_baseline(content_bottom=None, gap=26.0, frame=None):
    """Where the footer sits, given the lowest thing already on the page.

    Normally just FOOTER_Y. If a drawing runs past the safe zone into the
    gutter, the footer steps down to clear it, and stops at FOOTER_MAX rather
    than walking off the paper.
    """
    y, low, _x = _gutter(frame)
    if content_bottom is not None and content_bottom + gap > y:
        y = content_bottom + gap
    return min(y, low)


def draw_footer(d, message, content_bottom=None, height=26.0, x=None,
                width=8, frame=None):
    """Stamp one line plus the signature into the gutter of a Drawing.

    Follows the house convention: rm_text draws into a Drawing, so this does
    too. Returns the baseline used, so the caller can record what it wrote.
    """
    from paperdaemon.pipeline.draw import lettering as T
    y = footer_baseline(content_bottom, frame=frame)
    cur = x if x is not None else _gutter(frame)[2]
    if message:
        cur += T.text(d, message, x, y, size=height, width=width)
        cur += height * 0.9
    # The signature is drawn SMALLER than the message. The traced mark is ~2.6
    # pen units tall, so at the message's own height its D loop stands three
    # times the cap height of the text and collides with whatever is above --
    # and two stacked notes overlap each other. 0.55 keeps the whole mark
    # inside the gutter band.
    draw_signature(d, cur, y, height=height * 0.55)
    return y
