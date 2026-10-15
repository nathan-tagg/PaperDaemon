r"""Single-stroke (monoline) vector font for reMarkable pages.

rm_art.py gives paths and fills but no lettering, and a page of sketch captions
is mostly lettering. Glyphs are defined on a unit grid -- baseline y=0, cap
height y=1, y UP -- and emitted into a Drawing with y flipped, since reMarkable
pages run y downward.

Round letters are built from real arcs rather than hand-typed polylines: at a
90px title cap height a 6-segment "O" shows its corners, an arc does not.

A small per-glyph baseline wobble and rotation is applied by default. Without it
the lettering reads as plotter output next to hand-drawn sketches; the amount is
deliberately under a pixel or two at caption sizes.
"""
import math, random, unicodedata
from rmscene.scene_items import Pen, PenColor

XH = 0.60          # x-height
DESC = -0.28       # descender depth


def _arc(cx, cy, rx, ry, a0, a1, n=None):
    """Unit-space arc, degrees, standard math orientation (y up, CCW)."""
    if n is None:
        n = max(6, int(abs(a1 - a0) / 11) + 2)
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def _cat(*chunks):
    out = []
    for c in chunks:
        if out and c and abs(out[-1][0] - c[0][0]) < 1e-9 \
                and abs(out[-1][1] - c[0][1]) < 1e-9:
            out.extend(c[1:])
        else:
            out.extend(c)
    return out


def _dot(x, y=0.0):
    return [(x, y), (x, y + 0.05)]


# S and s share a construction: two arcs, one over the other, meeting at the center.
def _ess(cx, cy, rx, ry):
    # The terminals used to stop at -10 and -160, which left both ends looking lopped off rather
    # than curled. Carrying each arc round another 25 degrees finishes the stroke.
    #
    # The arcs used to meet at 250 / 110 degrees -- a point LEFT of center, joined by a vertical
    # chord, which put a kink in the spine. They meet at the center now, where both tangents are
    # horizontal, so the spine is one continuous curve.
    top = _arc(cx, cy + ry, rx, ry, -35, 270)
    bot = _arc(cx, cy - ry, rx, ry, 90, -185)
    return _cat(top, bot)


def _rot180(strokes, cx, cy):
    """A glyph turned through half a turn about (cx, cy).

    A 9 is a 6 upside down. Drawing it separately is how the two ended up in different style
    languages -- the 9 had a straight tail and three corners while the 6 was all arcs.
    """
    return [[(2 * cx - x, 2 * cy - y) for x, y in poly] for poly in strokes]


# A BOOKEND is a short line across the end of a stroke -- the tick at the top-left of a 7, the
# bar where the two bowls of a 3 meet. One length, so every one of them matches.
TICK = 0.14


# glyph -> (advance width, [polyline, ...])
G = {
    " ": (0.30, []),
    "A": (0.62, [[(0, 0), (0.31, 1.0), (0.62, 0)], [(0.115, 0.37), (0.505, 0.37)]]),
    "B": (0.62, [[(0, 0), (0, 1.0)],
                 _cat([(0, 1.0), (0.40, 1.0)], _arc(0.40, 0.77, 0.20, 0.23, 90, -90), [(0, 0.54)]),
                 _cat([(0, 0.54), (0.42, 0.54)], _arc(0.42, 0.27, 0.22, 0.27, 90, -90), [(0, 0)])]),
    "C": (0.64, [_arc(0.33, 0.5, 0.33, 0.5, 52, 308)]),
    "D": (0.64, [_cat([(0, 0), (0, 1.0), (0.26, 1.0)],
                      _arc(0.26, 0.5, 0.36, 0.5, 90, -90), [(0, 0)])]),
    "E": (0.60, [[(0.58, 1.0), (0, 1.0), (0, 0), (0.58, 0)], [(0, 0.52), (0.46, 0.52)]]),
    "F": (0.58, [[(0.58, 1.0), (0, 1.0), (0, 0)], [(0, 0.54), (0.44, 0.54)]]),
    "G": (0.66, [_cat(_arc(0.33, 0.5, 0.33, 0.5, 38, 330),
                      [(0.617, 0.46), (0.34, 0.46)])]),
    "H": (0.62, [[(0, 0), (0, 1.0)], [(0.62, 0), (0.62, 1.0)], [(0, 0.5), (0.62, 0.5)]]),
    "I": (0.28, [[(0.14, 0), (0.14, 1.0)],
                 [(0.14 - TICK / 2, 1.0), (0.14 + TICK / 2, 1.0)],
                 [(0.14 - TICK / 2, 0), (0.14 + TICK / 2, 0)]]),
    "J": (0.52, [_cat([(0.46, 1.0)], _arc(0.23, 0.24, 0.23, 0.24, 0, -180))]),
    "K": (0.62, [[(0, 0), (0, 1.0)], [(0.60, 1.0), (0.05, 0.42)], [(0.21, 0.59), (0.62, 0)]]),
    "L": (0.56, [[(0, 1.0), (0, 0), (0.56, 0)]]),
    "M": (0.76, [[(0, 0), (0, 1.0), (0.38, 0.28), (0.76, 1.0), (0.76, 0)]]),
    "N": (0.64, [[(0, 0), (0, 1.0), (0.64, 0), (0.64, 1.0)]]),
    "O": (0.68, [_arc(0.34, 0.5, 0.34, 0.5, 0, 360)]),
    "P": (0.60, [_cat([(0, 0), (0, 1.0), (0.38, 1.0)],
                      _arc(0.38, 0.76, 0.21, 0.24, 90, -90), [(0, 0.52)])]),
    "Q": (0.68, [_arc(0.34, 0.5, 0.34, 0.5, 0, 360), [(0.44, 0.20), (0.70, -0.10)]]),
    "R": (0.62, [_cat([(0, 0), (0, 1.0), (0.38, 1.0)],
                      _arc(0.38, 0.76, 0.21, 0.24, 90, -90), [(0, 0.52)]),
                 [(0.30, 0.52), (0.62, 0)]]),
    "S": (0.60, [_ess(0.30, 0.5, 0.28, 0.25)]),
    "T": (0.60, [[(0, 1.0), (0.60, 1.0)], [(0.30, 1.0), (0.30, 0)]]),
    "U": (0.62, [_cat([(0, 1.0)], _arc(0.31, 0.30, 0.31, 0.30, 180, 360), [(0.62, 1.0)])]),
    "V": (0.62, [[(0, 1.0), (0.31, 0), (0.62, 1.0)]]),
    "W": (0.82, [[(0, 1.0), (0.19, 0), (0.41, 0.70), (0.63, 0), (0.82, 1.0)]]),
    "X": (0.62, [[(0, 1.0), (0.62, 0)], [(0, 0), (0.62, 1.0)]]),
    "Y": (0.62, [[(0, 1.0), (0.31, 0.46), (0.62, 1.0)], [(0.31, 0.46), (0.31, 0)]]),
    "Z": (0.60, [[(0, 1.0), (0.60, 1.0), (0, 0), (0.60, 0)]]),

    "0": (0.60, [_arc(0.30, 0.5, 0.30, 0.5, 0, 360)]),
    "1": (0.44, [[(0.08, 0.80), (0.30, 1.0), (0.30, 0)],
                 [(0.30 - TICK * 0.8, 0), (0.30 + TICK * 0.8, 0)]]),
    "2": (0.58, [_cat(_arc(0.30, 0.76, 0.27, 0.24, 172, -38), [(0.02, 0), (0.58, 0)])]),
    # the two bowls run in to the waist almost level (their ends at -75 / 75 degrees) and meet
    # against a short UPRIGHT there -- a bookend, not a crossbar
    "3": (0.58, [_cat(_arc(0.28, 0.755, 0.25, 0.245, 168, -75),
                      _arc(0.28, 0.255, 0.28, 0.255, 75, -168)),
                 [(0.35, 0.51 - TICK / 2), (0.35, 0.51 + TICK / 2)]]),
    "4": (0.62, [[(0.46, 0), (0.46, 1.0), (0.0, 0.30), (0.62, 0.30)]]),
    "5": (0.58, [_cat([(0.54, 1.0 - TICK), (0.54, 1.0), (0.09, 1.0), (0.05, 0.58)],
                      _arc(0.29, 0.30, 0.29, 0.30, 82, -148))]),
    "6": (0.60, [_cat(_arc(0.30, 0.70, 0.30, 0.30, 62, 180),
                      _arc(0.30, 0.27, 0.30, 0.27, 180, -180))]),
    "7": (0.58, [[(0.02, 1.0 - TICK), (0.02, 1.0), (0.58, 1.0), (0.20, 0)],
                 [(0.15, 0.50), (0.39, 0.50)]]),
    "8": (0.58, [_arc(0.29, 0.755, 0.25, 0.245, 0, 360),
                 _arc(0.29, 0.255, 0.29, 0.255, 0, 360)]),
    "9": (0.60, []),        # filled in below: the 6, turned through half a turn
    # A circle with a stem tangent to it left a notch at the top right and a stem whose top
    # floated free; a half-height stem read as an o with a tick. This is one stroke: up the
    # stem, round a small shoulder, across the top, down and round the bowl, back into the stem.
    "a": (0.58, [_cat([(0.56, 0), (0.56, 0.48)],
                      _arc(0.44, 0.48, 0.12, 0.12, 0, 90),
                      [(0.28, 0.60)],
                      _arc(0.28, 0.30, 0.28, 0.30, 90, 360))]),
    "b": (0.60, [[(0, 1.0), (0, 0)], _arc(0.30, 0.30, 0.30, 0.30, 0, 360)]),
    "c": (0.56, [_arc(0.29, 0.30, 0.29, 0.30, 48, 312)]),
    "d": (0.60, [[(0.60, 1.0), (0.60, 0)], _arc(0.30, 0.30, 0.30, 0.30, 0, 360)]),
    "e": (0.58, [_cat([(0.02, 0.36)], _arc(0.29, 0.30, 0.28, 0.30, 8, 318))]),
    "f": (0.48, [_cat([(0.48, 0.88), (0.40, 1.0), (0.26, 1.0)],
                      _arc(0.26, 0.86, 0.08, 0.14, 90, 180), [(0.18, 0)]),
                 [(0.0, 0.60), (0.44, 0.60)]]),
    "g": (0.60, [_arc(0.29, 0.30, 0.29, 0.30, 0, 360),
                 [(0.58, 0.60), (0.58, -0.14), (0.42, -0.28), (0.16, -0.26), (0.02, -0.17)]]),
    "h": (0.58, [[(0, 1.0), (0, 0)],
                 [(0, 0.36), (0.11, 0.55), (0.32, 0.60), (0.50, 0.50), (0.56, 0.32), (0.56, 0)]]),
    "i": (0.28, [[(0.14, 0.60), (0.14, 0)], _dot(0.14, 0.84)]),
    "j": (0.36, [[(0.28, 0.60), (0.28, -0.14), (0.15, -0.27), (0.0, -0.23)], _dot(0.28, 0.84)]),
    "k": (0.56, [[(0, 1.0), (0, 0)], [(0.52, 0.60), (0.04, 0.22)], [(0.19, 0.35), (0.55, 0)]]),
    "l": (0.26, [[(0.12, 1.0), (0.12, 0)]]),
    "m": (0.88, [[(0, 0.60), (0, 0)],
                 [(0, 0.38), (0.10, 0.55), (0.28, 0.60), (0.40, 0.50), (0.43, 0.34), (0.43, 0)]],
          ),
    "n": (0.58, [[(0, 0.60), (0, 0)],
                 [(0, 0.38), (0.11, 0.55), (0.32, 0.60), (0.50, 0.50), (0.56, 0.32), (0.56, 0)]]),
    "o": (0.60, [_arc(0.30, 0.30, 0.30, 0.30, 0, 360)]),
    "p": (0.60, [[(0, 0.60), (0, -0.28)], _arc(0.30, 0.30, 0.30, 0.30, 0, 360)]),
    "q": (0.60, [_arc(0.29, 0.30, 0.29, 0.30, 0, 360), [(0.58, 0.60), (0.58, -0.28)]]),
    "r": (0.46, [[(0, 0.60), (0, 0)], [(0, 0.36), (0.12, 0.54), (0.31, 0.60), (0.45, 0.57)]]),
    "s": (0.52, [_ess(0.26, 0.30, 0.24, 0.155)]),
    "t": (0.44, [[(0.17, 0.88), (0.17, 0.13), (0.29, 0.01), (0.43, 0.05)],
                 [(0.0, 0.60), (0.40, 0.60)]]),
    "u": (0.58, [_cat([(0, 0.60)], _arc(0.28, 0.21, 0.28, 0.21, 180, 360), [(0.56, 0.60)]),
                 [(0.56, 0.34), (0.56, 0)]]),
    "v": (0.56, [[(0, 0.60), (0.28, 0), (0.56, 0.60)]]),
    "w": (0.76, [[(0, 0.60), (0.17, 0), (0.38, 0.42), (0.59, 0), (0.76, 0.60)]]),
    "x": (0.54, [[(0, 0.60), (0.54, 0)], [(0, 0), (0.54, 0.60)]]),
    "y": (0.56, [[(0, 0.60), (0.29, 0.02)], [(0.56, 0.60), (0.13, -0.28)]]),
    "z": (0.54, [[(0, 0.60), (0.54, 0.60), (0, 0), (0.54, 0)]]),

    ".": (0.26, [_dot(0.11)]),
    ",": (0.26, [[(0.13, 0.07), (0.05, -0.15)]]),
    ":": (0.26, [_dot(0.11), _dot(0.11, 0.36)]),
    ";": (0.26, [_dot(0.11, 0.36), [(0.13, 0.07), (0.05, -0.15)]]),
    "!": (0.28, [[(0.13, 1.0), (0.13, 0.24)], _dot(0.13)]),
    "?": (0.54, [_cat(_arc(0.27, 0.79, 0.24, 0.21, 188, -42), [(0.27, 0.44), (0.27, 0.26)]),
                 _dot(0.27)]),
    "'": (0.22, [[(0.11, 1.0), (0.08, 0.78)]]),
    '"': (0.38, [[(0.11, 1.0), (0.08, 0.78)], [(0.29, 1.0), (0.26, 0.78)]]),
    "-": (0.46, [[(0.05, 0.36), (0.41, 0.36)]]),
    "~": (0.58, [[(0.02, 0.33), (0.15, 0.45), (0.30, 0.34), (0.45, 0.23), (0.58, 0.34)]]),
    "/": (0.48, [[(0.0, -0.04), (0.48, 1.0)]]),
    "(": (0.32, [_arc(0.36, 0.44, 0.32, 0.62, 132, 228)]),
    ")": (0.32, [_arc(-0.04, 0.44, 0.32, 0.62, 48, -48)]),
    "+": (0.56, [[(0.06, 0.36), (0.50, 0.36)], [(0.28, 0.14), (0.28, 0.58)]]),
    ">": (0.52, [[(0.08, 0.62), (0.46, 0.34), (0.08, 0.06)]]),
    "<": (0.52, [[(0.44, 0.62), (0.06, 0.34), (0.44, 0.06)]]),
    "*": (0.48, [[(0.24, 0.86), (0.24, 0.44)], [(0.06, 0.78), (0.42, 0.52)],
                 [(0.42, 0.78), (0.06, 0.52)]]),
    "#": (0.66, [[(0.16, 0.0), (0.24, 0.72)], [(0.40, 0.0), (0.48, 0.72)],
                 [(0.04, 0.24), (0.58, 0.24)], [(0.07, 0.48), (0.61, 0.48)]]),
    "=": (0.56, [[(0.06, 0.46), (0.50, 0.46)], [(0.06, 0.26), (0.50, 0.26)]]),
}

# 'm' needs a third stem; patch it in rather than fighting the literal above.
G["m"] = (0.88, [[(0, 0.60), (0, 0)],
                 [(0, 0.38), (0.10, 0.55), (0.27, 0.60), (0.39, 0.50), (0.42, 0.34), (0.42, 0)],
                 [(0.42, 0.38), (0.52, 0.55), (0.69, 0.60), (0.81, 0.50), (0.85, 0.34),
                  (0.85, 0)]])

# the degree sign (weather screens: "72°"): a small ring at cap height, added for the
# decomposer's UI mode. Advance 0.42 cap.
G["°"] = (0.42, [_arc(0.21, 0.86, 0.11, 0.11, 0, 360, 20)])

# A 9 is a 6 turned over. Derived rather than drawn, so the two can never drift apart again.
G["9"] = (G["6"][0], _rot180(G["6"][1], 0.30, 0.50))
# The two characters the charts reach for that ASCII does not have: the middle dot that separates
# a value from its share ("42  \u00b7  30%"), and the minus sign d3 formats negatives with. Missing
# glyphs fall back to another face and stand out at once; these keep the page in one hand.
G["\u00b7"] = (0.26, [_dot(0.11, 0.36)])
G["\u2212"] = G["-"]
# BOXES: a to-do list is written "\u2610 Pack a box", and the font dropped the box and left a space in
# front of every item. A cap-high square, empty, ticked or crossed. (A tick
# or cross on its own is an emoji and drawn from the icon library; in a box it is this glyph, which
# is why emoji_icon() gives way to the font.)
_BOX = [[(0.06, 0.0), (0.84, 0.0), (0.84, 0.78), (0.06, 0.78), (0.06, 0.0)]]
G["\u2610"] = (1.0, _BOX)                                                        # ballot box
G["\u25a1"] = G["\u2610"]                                                        # white square
G["\u2611"] = (1.0, _BOX + [[(0.20, 0.40), (0.38, 0.17), (0.72, 0.66)]])        # box, ticked
G["\u2612"] = (1.0, _BOX + [[(0.22, 0.16), (0.68, 0.62)], [(0.22, 0.62), (0.68, 0.16)]])

_FALLBACK = "-"

# HOW FAR THE TALLEST GLYPH REACHES ABOVE THE BASELINE, in cap heights. It is NOT 1.0: `$`, `|`,
# `{}`, `[]` and the backtick overshoot the cap line, `$` by a tenth. Anything that places a first
# baseline at "band top + cap height" therefore hangs those glyphs above the band and into
# whatever the band was avoiding. Measured from the table rather than written down, so adding a
# taller glyph cannot silently invalidate it.
# It is a FUNCTION, not a constant, for two reasons that both bit: glyphs are still being added
# to G further down this file (`$`, the tallest of them, is defined ~250 lines below here, so a
# constant computed at this point reads 1.0 and is wrong), and rm_serif.install() REPLACES the
# glyph table at runtime with a different face that has its own ascent.
# The accented letters (accents.py) are measured only where they are used: an accented capital's mark stands above
# the cap line, and counting it here would set every line of every page lower.
TALL = set()


def ascent(s=None):
    """How far the tallest glyph reaches above the baseline, in cap heights, for the face
    currently installed: 1.10 for rm_text's own face (`$` is the tallest thing in it), and higher only when `s`
    (the line being placed) has an accented capital in it."""
    tops = [gy for ch, (_adv, polys) in G.items() if ch not in TALL for poly in polys for _gx, gy in poly]
    if s:
        tops += [gy for ch in set(str(s)) if ch in TALL for poly in G[ch][1] for _gx, gy in poly]
    return max(tops, default=1.0)


def descent():
    """How far the deepest glyph reaches BELOW the baseline, in cap heights. 0.28 -- `p`, `q`,
    `y`, `g`. A block measured to its last BASELINE forgets these and hangs them out of the
    band; that is the same mistake as forgetting the ascent, at the other end."""
    return -min((gy for _adv, polys in G.values() for poly in polys for _gx, gy in poly),
                default=0.0)


# ---------------------------------------------------------------- emoji in a line of text
# THE FONT HAS 98 GLYPHS AND SUBSTITUTES "-" FOR EVERYTHING ELSE, SILENTLY. So every emoji the
# model wrote came out as a dash, and so did every accented letter. The model's reach for emoji
# is not blunted.
#
# An emoji is not a letter and there is no letterform for it. What it HAS is a meaning, and the
# icon library is that meaning drawn in the tablet's own line vocabulary -- so it is resolved to
# an icon and drawn inline at cap height. The advance is a square em, decided in ONE place below
# so that measure(), wrap() and text() cannot disagree about where the next word starts; when they
# disagree, lines overrun the column and wrapping silently breaks.
EMOJI_EM = 1.0                     # an emoji occupies a square of the cap height

# THE UNIT OF LETTERING IS A CLUSTER, NOT A CHARACTER. A heart arrives as U+2764 U+FE0F: step
# through that one character at a time and the heart resolves, then its variation selector falls
# through to the font and draws a stray "-" beside it. Skin tones, keycaps and ZWJ-joined
# sequences do the same. So the modifiers are absorbed into the thing they modify, once, here --
# and measure(), wrap() and text() all walk the string through this function so they cannot
# disagree about how many units a line holds.
_ZWJ = "‍"
_MODIFIERS = ("︎️"                                        # variation selectors
              + "".join(chr(c) for c in range(0x1F3FB, 0x1F400))   # skin tones
              + "⃣"                                           # keycap
              + "".join(chr(c) for c in range(0x0300, 0x0370)))    # combining accents


def clusters(s):
    """A string -> its drawing units: a letter is one, an emoji with its modifiers is one."""
    out, i, n = [], 0, len(s)
    while i < n:
        j = i + 1
        while j < n:
            c = s[j]
            if c in _MODIFIERS:
                j += 1
            elif c == _ZWJ and j + 1 < n:
                j += 2
            elif j == i + 1 and 0x1F1E6 <= ord(s[i]) <= 0x1F1FF and 0x1F1E6 <= ord(c) <= 0x1F1FF:
                j += 1                                  # a flag is two regional indicators
            else:
                break
        out.append(s[i:j])
        i = j
    return out


# AND THE FONT SUBSTITUTES "-" FOR EVERY CHARACTER IT DOES NOT HAVE, SILENTLY: 98 glyphs, ASCII
# plus a degree sign, a middle dot and a minus. So "café" came out "caf-" and a curly
# apostrophe cut "don't" in half -- on the page, in the user's handwriting, looking like a mistake
# they made. An accent is not a different letter to this font; fold it to the letter underneath and
# the word reads correctly, which is the entire point of writing it down.
_FOLD = {"‘": "'", "’": "'", "“": '"', "”": '"', "«": '"',
         "»": '"', "′": "'", "″": '"', "–": "-", "—": "--",
         "…": "...", " ": " ", "•": "·", "×": "x", "÷": "/",
         "→": "->", "←": "<-", "≤": "<=", "≥": ">=", "≠": "!=",
         "½": "1/2", "¼": "1/4", "⅓": "1/3", "€": "EUR", "£": "GBP",
         "	": "    "}


def fold(ch):
    """A character the font cannot draw -> the closest it can, or "" when there is none."""
    if ch in G:
        return ch
    if ch in _FOLD:
        return _FOLD[ch]
    return "".join(c for c in unicodedata.normalize("NFKD", ch) if c in G)


def emoji_icon(ch):
    """The icon name for this character, or None if it is a letter (or an emoji we cannot draw)."""
    if ch and ch.rstrip("︎️") in G:
        return None                  # the font's own glyph wins: "☑" is a ticked BOX, not a tick
    try:
        from paperdaemon.pipeline.draw import shapes as _E
        return _E.resolve_emoji(ch)
    except Exception:
        return None


def _emoji_paths(name, cx, cy, r):
    try:
        from paperdaemon.pipeline.draw import shapes as _E
        return _E._icon_paths(name, cx, cy, r)
    except Exception:
        return None


def advance(u, size, track):
    """The x advance of ONE drawing unit: a cluster from clusters(), or a single character."""
    if emoji_icon(u):
        return EMOJI_EM * size + track * size
    return sum(G[c][0] * size + track * size for c in _drawable(u))


def _drawable(u):
    """The cluster as characters the font actually holds -- folded, unknowns dropped."""
    return "".join(fold(c) for c in u)


def measure(s, size=34, track=0.13):
    return sum(advance(u, size, track) for u in clusters(s))


def text(d, s, x, y, size=34, width=17, tool=Pen.FINELINER_2,
         color=PenColor.BLACK, track=0.13, wobble=0.022, seed=None, angle=0.0, slant=0.0):
    """Draw `s` with its baseline at y and left edge at x (reMarkable coords).

    size is the cap height in px. Returns the x advance. `slant` leans each glyph right by that
    fraction of its height -- italics (0.2): the model's *steps forward* in a role-play turn, whose
    asterisks came off and left the action running into the speech.
    Advances are unchanged, so measure() and wrapping are too.

    `angle` rotates the WHOLE RUN clockwise about (x, y) -- the baseline start.
    That is separate from the per-glyph wobble, which stays tiny and random so
    the lettering does not read as plotter output. Use it for a margin note down
    the side of a page, a label along a diagonal, or a caption on a rotated
    figure. Rotation happens after layout, so `measure()` is unchanged and
    wrapping still works.
    """
    import zlib                    # a stable seed: the same words letter the same way in every run (hash() is salted)
    rnd = random.Random(seed if seed is not None else (zlib.crc32(s.encode("utf-8")) & 0xffff))
    ra = math.radians(angle)
    rc, rs = math.cos(ra), math.sin(ra)
    cx = x
    for unit in clusters(s):
        icon = emoji_icon(unit)
        if icon:
            # centered on its own square: half an em along, and lifted so the square sits on the
            # baseline rather than hanging from it
            r = EMOJI_EM * size * 0.5
            paths = _emoji_paths(icon, cx + r, y - r * 0.92, r * 0.92)
            for pth in (paths or ()):
                d.stroke([(px, py) for px, py in pth], max(4, int(width * 0.8)),
                         tool=tool, color=color)
            cx += EMOJI_EM * size + track * size
            continue
        # a cluster can fold to more than one glyph -- an em dash draws as two
        for ch in _drawable(unit):
            aw, polys = G[ch]
            if polys:
                dy = rnd.uniform(-wobble, wobble) * size
                th = math.radians(rnd.uniform(-1.4, 1.4))
                ct, st = math.cos(th), math.sin(th)
                w = int(round(width * rnd.uniform(0.92, 1.08)))
                for poly in polys:
                    pts = []
                    for gx, gy in poly:
                        px, py = (gx + slant * gy) * size, -gy * size      # flip: page y runs down
                        rx = px * ct - py * st
                        ry = px * st + py * ct
                        # run-local, then rotate the run about its own origin
                        lx, ly = (cx - x) + rx, ry + dy
                        if angle:
                            lx, ly = lx * rc - ly * rs, lx * rs + ly * rc
                        pts.append((x + lx, y + ly))
                    d.stroke(pts, max(4, w), tool=tool, color=color)
            cx += aw * size + track * size
    return cx - x


def center(d, s, cx, y, size=34, **kw):
    track = kw.get("track", 0.13)
    return text(d, s, cx - measure(s, size, track) / 2, y, size, **kw)


def right(d, s, rx, y, size=34, **kw):
    track = kw.get("track", 0.13)
    return text(d, s, rx - measure(s, size, track), y, size, **kw)


def wrap(s, size, maxw, track=0.13):
    """Greedy word wrap to a pixel width. Returns a list of lines."""
    lines, cur = [], ""
    for word in s.split():
        trial = (cur + " " + word) if cur else word
        if cur and measure(trial, size, track) > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def flow(d, text, bands, x, maxw, size=28, leading=1.78, **kw):
    """Write `text` through a LIST OF FREE BANDS, continuing in the next one when a band fills.

    This is what makes a reply go *around* a picture instead of starting below everything. The
    bands come from rm_layout.plan_space, which has already taken out the erasures and reserved
    the image boxes -- so a band is somewhere it is genuinely safe to write.

    -> {"written": <lines drawn>, "left": <text that did not fit any band>}. Text that does not
    fit is RETURNED, never dropped: it belongs on the next page.
    """
    words = text
    drawn = 0
    for b in sorted(bands, key=lambda q: q["y"]):
        if not words:
            break
        # a band too short for one whole line is not a place to write: split_to_fit never
        # returns nothing (by design -- it must not truncate), so the skip belongs here
        first = (wrap(words, size, maxw, kw.get("track", 0.13)) or [""])[0]
        if b["height"] < size * (ascent(first) + descent()):
            continue
        head, words = split_to_fit(words, b["height"], size, maxw, leading, kw.get("track", 0.13))
        if not head:
            continue
        # the first baseline sits a full ASCENT below the band's top edge, not a cap height:
        # the difference is where `$` and `|` used to hang out of the band
        paragraph(d, head, x, b["y"] + size * ascent(first), maxw, size=size, leading=leading, **kw)
        drawn += len(wrap(head, size, maxw, kw.get("track", 0.13)))
    return {"written": drawn, "left": words}


def block_height(s, size=28, maxw=1152.0, leading=1.78, track=0.13):
    """How tall a `paragraph` of this text will be, in page px. Measured, not estimated.

    This exists because nothing could answer "will my answer fit?", so the reply was written
    blind and came out short every time, choked off as if a small amount of space had been
    planned for it. Nothing was planning any space at all.
    """
    # TRUE INK EXTENT, not cap-top to last baseline. This returned `+ size`, i.e. it measured
    # down to the final BASELINE and stopped -- so the descenders of the last line, and the
    # overshoot of a `$` on the first, fell outside whatever box this height was used to fit.
    # split_to_fit() then put one line too many into a band and it hung into the next thing.
    lines = wrap(s, size, maxw, track)
    return 0.0 if not lines else (len(lines) - 1) * size * leading + size * (ascent(lines[0]) + descent())


def split_to_fit(s, height, size=28, maxw=1152.0, leading=1.78, track=0.13):
    """-> (what fits in `height`, what is left over). Never truncates: the remainder is meant to
    be written on the next page, which is what the model is told to do. A word longer
    than the column still goes out on the first line rather than being dropped."""
    lines = wrap(s, size, maxw, track)
    if not lines:
        return "", ""
    # ONE EXTENT MODEL, shared with block_height(). This carried its own copy that measured a
    # line as `size` tall -- the cap height -- so it fitted a line whose ascender and descenders
    # did not actually fit, and the last line of a band hung into whatever the band was avoiding.
    # A block of n lines is (n-1) leadings plus one line's true ink extent.
    ink = size * (ascent(lines[0]) + descent())
    if height < ink:
        # NOT EVEN ONE LINE FITS. This used to hand back one anyway, which is not "not
        # truncating" -- it is writing a line into a space that cannot hold it, i.e. onto
        # whatever is underneath. Returning it all as the remainder loses nothing: the caller's
        # contract is already that the remainder goes on the next page.
        return "", s
    room = max(1, int((height - ink) / (size * leading)) + 1)
    return " ".join(lines[:room]), " ".join(lines[room:])


def paragraph(d, s, x, y, maxw, size=28, leading=1.78, **kw):
    """Word-wrapped block. Returns the baseline y after the last line."""
    track = kw.get("track", 0.13)
    for i, line in enumerate(wrap(s, size, maxw, track)):
        text(d, line, x, y + i * size * leading, size, **kw)
    return y + (len(wrap(s, size, maxw, track)) - 1) * size * leading


# ---------------------------------------------------------------------------
# Completing ASCII 32..126.
#
# Thirteen printable characters were missing, and the fallback glyph is "-", so
# they rendered SILENTLY WRONG rather than visibly wrong: "$5" came out as "-5".
# A font that quietly substitutes is worse than one that is obviously
# incomplete, so the gap is closed here.
#
# Same unit grid as the rest: baseline y=0, cap height y=1, y UP, x from 0 to
# the advance width.
# ---------------------------------------------------------------------------
def _rounds(cx, cy, rx, ry, a0, a1, n=16):
    return _arc(cx, cy, rx, ry, a0, a1, n)


# "$" is an S with a bar through it, so BUILD it from the S that already
# exists rather than hand-rolling a second S badly -- the first attempt at a
# freehand one came out looking like a "b".
_S_W, _S_POLYS = G["S"]
G["$"] = (_S_W, [[(pxy[0], pxy[1]) for pxy in poly] for poly in _S_POLYS] +
          [[(_S_W * 0.5, -0.12), (_S_W * 0.5, 1.10)]])
G["%"] = (0.78, [_rounds(0.17, 0.79, 0.15, 0.17, 0, 360, 18),
                 _rounds(0.61, 0.21, 0.15, 0.17, 0, 360, 18),
                 [(0.06, 0.02), (0.72, 0.98)]])
# One flowing stroke: up from the lower right through the crossing, round the
# small top loop, back down through the crossing into the bottom bowl, out to
# the upper right. Written as an explicit path because an ampersand is the one
# glyph that does not decompose into arcs cleanly.
G["&"] = (0.76, [[(0.74, 0.20), (0.62, 0.34), (0.50, 0.47), (0.40, 0.58),
                  (0.33, 0.67), (0.30, 0.76), (0.33, 0.85), (0.41, 0.90),
                  (0.50, 0.87), (0.53, 0.79), (0.51, 0.70), (0.44, 0.61),
                  (0.34, 0.51), (0.24, 0.41), (0.16, 0.31), (0.13, 0.20),
                  (0.17, 0.10), (0.27, 0.05), (0.39, 0.07), (0.50, 0.15),
                  (0.60, 0.27), (0.69, 0.39), (0.76, 0.47)]])
G["@"] = (0.86, [_cat(_rounds(0.43, 0.42, 0.18, 0.18, 0, 360, 20),
                      [(0.61, 0.42), (0.61, 0.24)],
                      _rounds(0.43, 0.42, 0.40, 0.44, -30, 300, 34))])
G["["] = (0.34, [[(0.28, 1.02), (0.08, 1.02), (0.08, -0.16), (0.28, -0.16)]])
G["]"] = (0.34, [[(0.06, 1.02), (0.26, 1.02), (0.26, -0.16), (0.06, -0.16)]])
G["{"] = (0.40, [[(0.34, 1.02), (0.22, 0.98), (0.22, 0.52), (0.06, 0.43),
                  (0.22, 0.34), (0.22, -0.12), (0.34, -0.16)]])
G["}"] = (0.40, [[(0.06, 1.02), (0.18, 0.98), (0.18, 0.52), (0.34, 0.43),
                  (0.18, 0.34), (0.18, -0.12), (0.06, -0.16)]])
G["\\"] = (0.50, [[(0.06, 1.00), (0.44, -0.10)]])
G["^"] = (0.56, [[(0.08, 0.62), (0.28, 0.96), (0.48, 0.62)]])
G["_"] = (0.56, [[(0.02, -0.16), (0.54, -0.16)]])
G["`"] = (0.30, [[(0.06, 1.02), (0.24, 0.82)]])
G["|"] = (0.26, [[(0.13, 1.06), (0.13, -0.18)]])


# THE FONT. rm_serif replaces the glyph table above with a serif-like set and sets the space to
# match its word gap; it installs itself on import. Done here so that importing rm_text is enough --
# the model writes a fresh script for every job and none of them should have to know.
#
# Guarded twice over. The import is circular by design (rm_serif needs the helpers above), so
# importing rm_serif FIRST hands this a half-built module, which is harmless because rm_serif
# installs itself when it finishes. And a font that fails to load must never stop text being drawn.
try:
    from paperdaemon.pipeline.draw import serif as _rm_serif
except Exception as _e:                    # pragma: no cover
    import sys as _sys
    print("rm_text: keeping the built-in glyphs (%s)" % _e, file=_sys.stderr)

# THE EXTENDED LATIN LETTERS, built from whichever face is installed (so after rm_serif)
try:
    from paperdaemon.pipeline.draw import accents as _accents
    _accents.install()
except Exception as _e:                    # pragma: no cover
    import sys as _sys
    print("rm_text: no accented letters (%s)" % _e, file=_sys.stderr)
