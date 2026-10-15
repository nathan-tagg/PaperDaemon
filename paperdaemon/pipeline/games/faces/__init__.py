r"""Faces for game characters: bold, icon-like SVG avatars, one per emotion.

A character's face is built from PARTS named in its roster profile (`look`), so a hundred
characters stay one consistent family and an emotion always reads the same way:

    look = {"badge": "#F3D9B1", "head": "round", "skin": "#E1AE86", "eyes": "dark",
            "brows": {"color": "#4A2F22", "weight": 7},
            "body":  {"part": "tshirt", "color": "#6BA368"},
            "hair":  [{"part": "side_tufts", "color": "#5B3A29"}, {"part": "cap", "color": "#C0392B"}],
            "face":  [{"part": "stubble"}, {"part": "round_nose"}]}

    svg = face_svg(look, "angry")          # a 200 x 200 viewBox, transparent outside the badge

The emotion is carried by eyes, brows and mouth, plus ONE extra per emotion that reads even when
the face is small: a tear (sad), a vein (angry), a sweat drop (worried), a sigh (relieved), thought
dots (thinking), shock lines (surprised), a sparkle (smug), a question mark (confused), blush (happy).
Neutral, jealous and determined have none: jealous is its half-lidded side-eye, uneven brows and
crooked mouth (a green cast over the whole face did not read well, so there is none), determined
its narrowed eyes, low brows and confident grin.

Heads place the features: each head type returns the anchors (eye centers, brow line, mouth,
nose, cheeks, temple, ears, chin) that the emotion parts are drawn at, so a new head needs only
its outline and its anchors.

THE KIT GROWS BY REGISTRY. A new head, hair or hat, face part, body, eye style or mouth style is a
function registered from a part module (people.py, creatures.py, imported at the end of this file) --
species, robots and the rest live there, and the if-chains below stay as they were:

    @register(HEADS, "elephant")
    def _elephant(skin, look): ...        # -> (svg, outline path, anchors, edge color)

A head's anchors may also carry "eyes_style" / "mouth_style" (a key of EYES / MOUTHS: LED eyes, a
beak), "neck": False (no human neck under it), and "no_brows": True.

MARKS are the SUBTLE frames: a glint on a lens, a bead of sweat, a twitch, a brow that lifts, a
glance away, a flicker of something not human. None is an emotion; each sits on whatever face is
showing (face_svg(look, emotion, marks=("glint",))), small enough that only a player watching that
character closely learns what it means. A character's tells name them (rm_characters).

Some parts make a face HARD TO READ, for characters who give little away: a full_beard hides most
of the mouth (it shows through a small opening), sunglasses hide the eyes (the brows stay free
above the frames), and a fixed_grin keeps smiling whatever is felt (strained over a bad feeling).
Brows, and each emotion's extra, are still drawn on top, so all twelve emotions still differ.
"""

INK = "#2B2E33"
EMOTIONS = ("neutral", "happy", "sad", "angry", "jealous", "worried", "relieved", "thinking",
            "surprised", "smug", "determined", "confused", "curious", "hopeful", "embarrassed",
            "disappointed", "skeptical", "tired")
# Mixed expressions reuse each species' own feature vocabulary, not human mouths pasted on beaks
# or robots. Existing twelve frames are unchanged. These quieter feelings have no cartoon symbol.
#                     eyes        brows       mouth       extra marks
MIXED_EXPRESSIONS = {
    "curious":      ("thinking", "happy",    "neutral",  ()),
    "hopeful":      ("worried",  "happy",    "happy",    ()),
    "embarrassed":  ("neutral",  "worried",  "relieved", ("glance", "flush")),
    "disappointed": ("relieved", "sad",      "sad",      ()),
    "skeptical":    ("jealous",  "confused", "neutral",  ()),
    "tired":        ("relieved", "neutral",  "surprised",()),
}
MARKS = ("glint", "bead", "twitch", "brow_up", "knit", "narrow", "glance", "blink", "flush", "pale",
         "press", "smirk", "jaw", "nostrils", "ear_flick", "glitch", "led", "static", "twinkle")

HEADS, HAIR_BACK, HAIR_FRONT, FACE_PARTS, BODIES, EYES, MOUTHS = {}, {}, {}, {}, {}, {}, {}
FACE_UNDER = set()          # registered face parts drawn under the eyes (a mask, a muzzle, a tattoo)

# THE TABLET'S GAMUT. Its color screen shows a skin darker than about this as solid black, face and
# features gone (and light line art on a dark skin looks poor). So a dark skin is DRAWN lifted to the
# lightness the tablet can render, its hue kept and its color a touch richer: plainly dark-skinned
# still, with the ordinary ink features, and a face on the tablet. Only skin tones -- the
# warm browns -- are lifted: near-black with no color in it (a black cat, a crow) is black on purpose,
# and a strong color (a red cabinet, a magenta octopus) is a color, not a skin in the dark.
SKIN_FLOOR = 0.43                   # relative luminance
SKIN_KEEP_BELOW_SAT = 0.18          # HLS saturation: this gray is black on purpose
SKIN_KEEP_FROM_SAT = 0.6            # ... and this vivid is a color
SKIN_HUES = (0.0, 60.0 / 360)       # the warm browns and tans of skin and fur


def lum(hexcolor):
    """0 (black) .. 1 (white): a color's lightness as the eye sees it."""
    h = str(hexcolor or "").lstrip("#")
    if len(h) != 6:
        return 1.0
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def tablet_skin(hexcolor):
    """The skin as the face is drawn: lifted into what the tablet can show (SKIN_FLOOR), or as it is."""
    import colorsys
    if lum(hexcolor) >= SKIN_FLOOR:
        return hexcolor
    h = hexcolor.lstrip("#")
    hh, ll, ss = colorsys.rgb_to_hls(*(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)))
    if ss < SKIN_KEEP_BELOW_SAT or ss >= SKIN_KEEP_FROM_SAT or not SKIN_HUES[0] <= hh <= SKIN_HUES[1]:
        return hexcolor
    ss = min(1.0, ss * 1.1)

    def at(l):
        return "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in colorsys.hls_to_rgb(hh, l, ss))
    lo, hi = ll, 0.95
    for _ in range(24):
        mid = (lo + hi) / 2.0
        if lum(at(mid)) < SKIN_FLOOR:
            lo = mid
        else:
            hi = mid
    return at(hi)


def dark_face(look):
    """Black fur (a crow, a black cat): ink would vanish on it, so the fine marks are drawn light."""
    return lum(look.get("skin", "#E1AE86")) < 0.35


def register(table, name, under=False):
    """Add a part to one of the kit's tables: @register(HEADS, "elephant")."""
    def deco(fn):
        table[name] = fn
        if under:
            FACE_UNDER.add(name)
        return fn
    return deco


def _p(d, fill="none", stroke=INK, width=5, extra=""):
    s = ' stroke="%s" stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"' % (stroke, width) \
        if stroke else ""
    return '<path d="%s" fill="%s"%s%s/>' % (d, fill, s, extra)


def _c(x, y, r, fill, stroke=INK, width=4, extra=""):
    s = ' stroke="%s" stroke-width="%s"' % (stroke, width) if stroke else ""
    return '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"%s%s/>' % (x, y, r, fill, s, extra)


def _e(x, y, rx, ry, fill, stroke=INK, width=4, extra=""):
    s = ' stroke="%s" stroke-width="%s"' % (stroke, width) if stroke else ""
    return '<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s"%s%s/>' % (x, y, rx, ry, fill, s, extra)


def _shade(hexcolor, f):
    """A color darkened (f < 1) or lightened (f > 1)."""
    h = hexcolor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if f < 1:
        r, g, b = (int(v * f) for v in (r, g, b))
    else:
        r, g, b = (int(v + (255 - v) * (f - 1)) for v in (r, g, b))
    return "#%02X%02X%02X" % (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


# ---------------------------------------------------------------- heads: outline + anchors
def head(kind, skin, look=None):
    """-> (svg of ears + head, the head's outline path for tints, anchors)."""
    if kind in HEADS:
        return HEADS[kind](skin, look or {})
    edge = _shade(skin, 0.62)
    if kind == "round":                       # a broad, round face
        d = "M 40 116 Q 40 56 100 56 Q 160 56 160 116 Q 160 176 100 178 Q 40 176 40 116 Z"
        ears = _e(41, 122, 10, 14, skin, INK, 4) + _e(159, 122, 10, 14, skin, INK, 4)
        a = dict(lx=78, rx=122, ey=120, by=104, mx=100, my=156, nx=100, ny=138,
                 cheeks=((66, 144), (134, 144)), temple=(150, 90), top=56, ears=(41, 159, 122), chin=178)
    elif kind == "strong":                    # a squarer jaw
        d = ("M 48 104 Q 48 46 100 46 Q 152 46 152 104 L 150 140 Q 146 168 118 177 "
             "Q 100 181 82 177 Q 54 168 50 140 Z")
        ears = _e(47, 114, 8, 12, skin, INK, 4) + _e(153, 114, 8, 12, skin, INK, 4)
        a = dict(lx=80, rx=120, ey=108, by=90, mx=100, my=150, nx=100, ny=128,
                 cheeks=((70, 134), (130, 134)), temple=(146, 82), top=46, ears=(47, 153, 114), chin=180)
    elif kind == "oval":
        d = "M 46 110 Q 46 46 100 46 Q 154 46 154 110 Q 154 174 100 176 Q 46 174 46 110 Z"
        ears = _e(47, 114, 8, 12, skin, INK, 4) + _e(153, 114, 8, 12, skin, INK, 4)
        a = dict(lx=80, rx=120, ey=108, by=84, mx=100, my=150, nx=100, ny=128,
                 cheeks=((70, 132), (130, 132)), temple=(146, 80), top=46, ears=(47, 153, 114), chin=176)
    elif kind == "raccoon":                   # cheek fluff, wide ears; features sit in the mask
        d = ("M 42 122 Q 30 102 48 80 Q 70 54 100 52 Q 130 54 152 80 Q 170 102 158 122 "
             "L 172 134 Q 152 148 142 158 Q 122 178 100 178 Q 78 178 58 158 Q 48 148 28 134 Z")
        ears = (_p("M 50 80 Q 36 38 58 32 Q 78 36 88 60 Z", skin, INK, 4)
                + _p("M 56 70 Q 50 46 60 44 Q 70 48 78 60 Z", "#3B3D42", None)
                + _p("M 150 80 Q 164 38 142 32 Q 122 36 112 60 Z", skin, INK, 4)
                + _p("M 144 70 Q 150 46 140 44 Q 130 48 122 60 Z", "#3B3D42", None))
        a = dict(lx=76, rx=124, ey=110, by=86, mx=100, my=152, nx=100, ny=134,
                 cheeks=((60, 140), (140, 140)), temple=(152, 88), top=52, ears=(42, 158, 122), chin=178,
                 lid="#2B2D31")                 # the eyes sit in the black mask

    else:
        raise ValueError("no head %r" % kind)
    return ears + _p(d, skin, INK, 5), d, a, edge


# ---------------------------------------------------------------- parts
def _body(part, color, a):
    """Shoulders under the head; clipped to the badge by the caller."""
    kind = part.get("part")
    if kind in BODIES:
        return BODIES[kind](part, color, a)
    col = part.get("color", "#8A8D93")
    base = _p("M 16 204 Q 22 168 68 160 L 132 160 Q 178 168 184 204 Z", col, INK, 5)
    if kind == "tshirt":
        out = base + _p("M 78 161 Q 100 180 122 161", "none", INK, 4)
        if part.get("mark") == "house":        # a little board-game house on the chest
            out += _p("M 122 196 L 122 184 L 131 176 L 140 184 L 140 196 Z", _shade(col, 0.6), INK, 2.5)
        return out
    if kind == "gi":
        belt = part.get("trim", "#2B2E33")
        return (base + _p("M 78 161 L 100 196 L 122 161", "none", INK, 4)
                + _p("M 86 161 L 100 184 L 114 161", "none", _shade(col, 0.8), 3)
                + _p("M 60 196 L 140 196", "none", belt, 7))
    if kind == "cardigan":
        blouse = part.get("trim", "#F4F1EA")
        return (base + _p("M 84 160 L 100 178 L 116 160 Z", blouse, INK, 3)
                + _p("M 100 178 L 100 204", "none", INK, 3)
                + _c(92, 190, 2.5, _shade(col, 0.6), None) + _c(92, 200, 2.5, _shade(col, 0.6), None))
    if kind == "neckerchief":
        return (_p("M 30 204 Q 40 172 72 164 L 128 164 Q 160 172 170 204 Z", part.get("fur", "#8F9297"), INK, 5)
                + _p("M 64 164 Q 100 176 136 164 L 100 196 Z", col, INK, 4)
                + _c(100, 168, 5, _shade(col, 0.75), INK, 3))
    if kind == "slicker":                      # a fisherman's oilskin: collar turned up, snaps down the front
        dark = _shade(col, 0.8)
        return (base + _p("M 100 176 L 100 204", "none", INK, 3.5)
                + _c(111, 186, 3, dark, INK, 2) + _c(111, 198, 3, dark, INK, 2)
                + _p("M 60 166 L 72 146 L 100 170 L 128 146 L 140 166 L 118 184 L 100 172 L 82 184 Z", dark, INK, 4))
    if kind == "suit":                         # a salesman's jacket: wide lapels, white shirt, a loud tie
        lapel = _shade(col, 0.82)
        return (base + _p("M 80 160 L 100 204 L 120 160 Z", "#FFFFFF", INK, 3.5)
                + _p("M 93 163 L 107 163 L 104 173 L 111 197 L 100 207 L 89 197 L 96 173 Z",
                     part.get("tie", "#C0392B"), INK, 3)
                + _p("M 80 160 L 62 172 L 72 179 L 64 187 L 97 207 Z", lapel, INK, 3.5)
                + _p("M 120 160 L 138 172 L 128 179 L 136 187 L 103 207 Z", lapel, INK, 3.5)
                + _p("M 144 184 L 160 184 L 156 176 L 150 182 L 146 176 Z", "#FFFFFF", INK, 2.5))
    if kind == "hoodie":                       # the hood's drawstrings hanging down the front
        cord = part.get("cord", "#F4F4F4")
        return (base + _p("M 70 162 Q 100 182 130 162", "none", _shade(col, 0.72), 5)
                + _p("M 90 172 Q 87 186 90 198 M 110 172 Q 113 186 110 198", "none", cord, 3.5)
                + _c(90, 199, 3, cord, INK, 2) + _c(110, 199, 3, cord, INK, 2))
    return base


def _brooch(x, y):
    """A tiny queen's crown pin."""
    return (_p("M %d %d L %d %d L %d %d L %d %d L %d %d L %d %d L %d %d Z"
               % (x - 9, y + 5, x - 10, y - 5, x - 4, y, x, y - 8, x + 4, y, x + 10, y - 5, x + 9, y + 5),
               "#E2B73C", INK, 2.5))


def _hair_back(part, a):
    kind, col = part.get("part"), part.get("color", "#3A2A20")
    if kind in HAIR_BACK:
        return HAIR_BACK[kind](part, a)
    if kind == "braid":                       # over the left shoulder, drawn behind the head
        return "".join(_e(x, y, 8, 10, col, INK, 3) for x, y in ((50, 150), (45, 166), (42, 182), (40, 197)))
    if kind == "headband_tails":
        band = part.get("band", "#C0392B")
        return (_p("M 150 88 Q 174 76 190 86 Q 180 92 176 98 Q 166 90 152 96 Z", band, INK, 3.5)
                + _p("M 150 94 Q 170 100 184 116 Q 172 116 166 122 Q 160 108 148 102 Z", band, INK, 3.5))
    if kind == "hood":                         # a hood pulled up: its back, behind the head and shoulders
        return _p("M 22 204 Q 12 120 36 76 Q 60 24 100 22 Q 140 24 164 76 Q 188 120 178 204 Z", col, INK, 5)
    return ""


def _hair_front(part, a):
    kind, col = part.get("part"), part.get("color", "#3A2A20")
    if kind in HAIR_FRONT:
        return HAIR_FRONT[kind](part, a)
    if kind == "cap":                          # a ball cap, brim forward, sitting above the brows
        dark = _shade(col, 0.72)
        return (_p("M 40 88 Q 38 30 100 28 Q 162 30 160 88 Q 130 76 100 76 Q 70 76 40 88 Z", col, INK, 5)
                + _p("M 100 28 L 100 76", "none", dark, 3)
                + _c(100, 30, 4.5, dark, INK, 2.5)
                + _p("M 30 90 Q 100 70 170 90 Q 172 98 162 100 Q 100 84 38 100 Q 28 98 30 90 Z", dark, INK, 4.5)
                + _c(78, 54, 8, "#FFFFFF", INK, 3))
    if kind == "side_tufts":
        return (_p("M 42 104 Q 38 116 46 124 Q 48 112 54 106 Z", col, INK, 3)
                + _p("M 158 104 Q 162 116 154 124 Q 152 112 146 106 Z", col, INK, 3))
    if kind == "pulled_back":                 # hair swept back from the forehead
        return _p("M 48 100 Q 44 44 100 42 Q 156 44 152 100 Q 146 70 126 62 Q 100 56 74 62 Q 54 70 48 100 Z",
                  col, INK, 5)
    if kind == "headband":
        band = part.get("band", "#C0392B")
        return (_p("M 47 80 Q 100 64 153 80 L 153 92 Q 100 76 47 92 Z", band, INK, 4)
                + _c(153, 88, 6, _shade(band, 0.8), INK, 3))
    if kind == "bun":                          # silver hair, a bun on top, a side part
        return (_c(100, 36, 19, col, INK, 4)
                + _p("M 88 30 Q 100 22 112 32", "none", _shade(col, 0.72), 3)
                + _p("M 46 108 Q 40 48 100 46 Q 160 48 154 108 Q 150 78 122 70 Q 100 64 80 70 Q 54 78 46 108 Z",
                     col, INK, 5)
                + _p("M 116 50 Q 106 62 100 70", "none", _shade(col, 0.72), 3))
    if kind == "beanie":                       # a knit watch cap, cuff folded up, pulled low
        L, R, _ = a["ears"]
        t, cb = a["top"], a["by"] - 7          # the cuff's lower edge sits just above the brows
        ct = cb - 19
        rib = _shade(col, 0.62)

        def edge(y0, x):                       # the cuff's curved edges (a symmetric quadratic)
            s = (x - (L - 3)) / float(R - L + 6)
            return y0 - 40 * s * (1 - s)
        ribs = "".join(_p("M %d %.1f L %d %.1f" % (x, edge(ct, x) + 3, x, edge(cb, x) - 3), "none", rib, 2.5)
                       for x in range(L + 7, R - 3, 11))
        return (_p("M %d %d Q %d %d 100 %d Q %d %d %d %d Z" % (L - 1, ct + 2, L - 1, t - 26, t - 26, R + 1, t - 26, R + 1, ct + 2),
                   col, INK, 5)
                + _p("M 100 %d L 100 %d" % (t - 24, ct - 8), "none", rib, 2.5)
                + _p("M %d %d Q 100 %d %d %d L %d %d Q 100 %d %d %d Z" % (L - 3, ct, ct - 20, R + 3, ct, R + 3, cb, cb - 20, L - 3, cb),
                     _shade(col, 0.88), INK, 4.5)
                + ribs)
    if kind == "side_part":                    # slicked hair, a hard side part, a comb's shine
        return (_p("M 46 104 Q 40 44 98 38 Q 156 38 156 102 Q 150 72 130 64 Q 104 58 80 66 Q 70 58 74 50 "
                   "Q 58 60 54 76 Q 48 88 46 104 Z", col, INK, 5)
                + _p("M 92 48 Q 116 42 138 56", "none", _shade(col, 1.55), 3.5)
                + _p("M 74 50 Q 70 58 80 66", "none", _shade(col, 0.6), 3))
    if kind == "hood":                         # the hood's rim framing the face
        return _p("M 26 178 Q 16 58 100 24 Q 184 58 174 178 L 158 178 Q 166 66 100 40 Q 34 66 42 178 Z",
                  col, INK, 5) + _p("M 42 178 Q 34 66 100 40 Q 166 66 158 178", "none", _shade(col, 0.66), 4)
    if kind == "fringe":                       # a side-swept wisp of bangs, kept clear of the brows
        return _p("M 48 100 Q 44 50 100 44 Q 144 46 154 66 Q 130 56 106 58 Q 82 60 64 72 Q 54 82 48 100 Z", col, INK, 4)
    return ""


def _face_part(part, a, skin):
    kind = part.get("part")
    if kind in FACE_PARTS:
        return FACE_PARTS[kind](part, a, skin)
    if kind == "stubble":
        # A FIVE O'CLOCK SHADOW ON THIS HEAD'S JAW: a band from the ears round the chin, up to just
        # under the mouth, cut to the head's own outline -- one fixed band drawn for a broad round
        # face stuck out past the jaw of every narrower head
        L, R, ye = a["ears"]
        chin, my = a["chin"], a["my"]
        band = _p("M %d %d Q %d %d 100 %d Q %d %d %d %d Q %d %d 100 %d Q %d %d %d %d Z" % (
            L - 6, ye + 6, L - 2, chin + 6, chin + 8, R + 2, chin + 6, R + 6, ye + 6,
            R - 20, my + 2, my + 5, L + 20, my + 2, L - 6, ye + 6), part.get("color", "#6E5A4C"), None,
            extra=' opacity="0.28"')
        if not a.get("head_d"):
            return band
        return ('<clipPath id="stubble-jaw"><path d="%s"/></clipPath><g clip-path="url(#stubble-jaw)">%s</g>'
                % (a["head_d"], band))
    if kind == "round_nose":
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d" % (a["nx"] - 9, a["ny"] - 7, a["nx"] - 12, a["ny"] + 6,
                  a["nx"], a["ny"] + 7, a["nx"] + 12, a["ny"] + 6, a["nx"] + 9, a["ny"] - 7),
                  _shade(skin, 0.86), INK, 4)
    if kind == "small_nose":
        return _p("M %d %d Q %d %d %d %d" % (a["nx"] - 1, a["ny"] - 14, a["nx"] - 7, a["ny"] + 1,
                                             a["nx"] + 3, a["ny"] + 3), "none", INK, 4)
    if kind == "bandage":                      # a strip across the right cheek
        x, y = a["cheeks"][1]
        return ('<g transform="rotate(-24 %d %d)">' % (x + 2, y - 4)
                + '<rect x="%d" y="%d" width="30" height="13" rx="3" fill="#F3E3C3" stroke="%s" stroke-width="3"/>'
                % (x - 13, y - 10, INK)
                + _p("M %d %d L %d %d M %d %d L %d %d" % (x - 2, y - 7, x - 2, y + 0, x + 6, y - 7, x + 6, y + 0),
                     "none", "#C9B48E", 2.5) + "</g>")
    if kind == "wrinkles":
        c = _shade(skin, 0.72)
        lx, rx, ey = a["lx"], a["rx"], a["ey"]
        return (_p("M 76 66 Q 100 60 124 66 M 82 74 Q 100 69 118 74", "none", c, 2.5)
                + _p("M %d %d L %d %d M %d %d L %d %d" % (lx - 22, ey - 4, lx - 28, ey - 7, lx - 22, ey + 3, lx - 28, ey + 5),
                     "none", c, 2.5)
                + _p("M %d %d L %d %d M %d %d L %d %d" % (rx + 22, ey - 4, rx + 28, ey - 7, rx + 22, ey + 3, rx + 28, ey + 5),
                     "none", c, 2.5)
                + _p("M 84 134 Q 78 144 82 152 M 116 134 Q 122 144 118 152", "none", c, 2.5))
    if kind == "earrings":
        # at the head's own ears: a["earrings"], which face_svg fills in (the first heads keep the
        # places they were drawn at; a mouse's came out on its cheeks)
        (x1, y1), (x2, y2) = a.get("earrings") or ((47, 128), (153, 128))
        return _c(x1, y1, 5, "#FBFBF7", "#8A8D93", 2.5) + _c(x2, y2, 5, "#FBFBF7", "#8A8D93", 2.5)
    if kind == "raccoon_mask":
        return _p("M 40 106 Q 56 88 100 100 Q 144 88 160 106 Q 156 128 132 126 Q 112 122 100 112 "
                  "Q 88 122 68 126 Q 44 128 40 106 Z", "#2B2D31", INK, 3)
    if kind == "raccoon_brows":                # the pale patches over the mask
        return ""
    if kind == "muzzle":
        return _e(100, 146, 32, 23, "#ECECEC", INK, 3.5)
    if kind == "raccoon_nose":
        return _p("M 90 128 Q 100 124 110 128 Q 108 138 100 140 Q 92 138 90 128 Z", "#1E1F22", INK, 2.5) \
            + _c(96, 129, 2, "#FFFFFF", None)
    if kind == "whiskers":
        return _p("M 70 146 L 44 140 M 70 152 L 46 156 M 130 146 L 156 140 M 130 152 L 154 156",
                  "none", "#6E7177", 2.5)
    return ""


def _glasses(a):
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    fr = "#34363C"
    return (_c(lx, y, 17, "#FFFFFF", fr, 4, ' fill-opacity="0.18"')
            + _c(rx, y, 17, "#FFFFFF", fr, 4, ' fill-opacity="0.18"')
            + _p("M %d %d Q 100 %d %d %d" % (lx + 17, y - 2, y - 8, rx - 17, y - 2), "none", fr, 4)
            + _p("M %d %d L 48 %d M %d %d L 152 %d" % (lx - 17, y - 3, y - 6, rx + 17, y - 3, y - 6), "none", fr, 3.5))


# ---------------------------------------------------------------- parts that hide the feeling
# Drawn over the emotion's own features, so the face stays hard to read. Brows still go on top of
# everything, and every emotion keeps its extra, so each of the twelve still differs.
def _sunglasses(a, part):
    """Dark lenses over the eyes, the brows free above the frames."""
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    L, R, _ = a["ears"]
    lens, fr = part.get("color", "#1C1E22"), part.get("frame", "#141518")
    out = ""
    for x in (lx, rx):
        out += (_p("M %d %d L %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 19, y - 13, x + 19, y - 13, x + 20, y + 11,
                   x, y + 14, x - 20, y + 11, x - 19, y - 13), lens, fr, 4)
                + _p("M %d %d L %d %d" % (x - 12, y + 5, x - 4, y - 7), "none", "#FFFFFF", 3, ' opacity="0.5"'))
    return (out + _p("M %d %d Q 100 %d %d %d" % (lx + 19, y - 8, y - 14, rx - 19, y - 8), "none", fr, 4.5)
            + _p("M %d %d L %d %d M %d %d L %d %d" % (lx - 19, y - 10, L + 1, y - 12, rx + 19, y - 10, R - 1, y - 12),
                 "none", fr, 4))


def _beard(e, a, part):
    """A full beard over the jaw and chin, a mustache over the mouth. The mouth shows only through a
    small opening, which widens when the mouth opens; the mustache lifts with a smile and droops
    with a frown."""
    col = part.get("color", "#9E9891")
    L, R, ye = a["ears"]
    x, my, ny, chin = a["mx"], a["my"], a["ny"], a["chin"]
    hx, hy = {"surprised": (9, 9), "angry": (13, 7), "happy": (14, 6.5)}.get(e, (10, 4.5))
    lift = {"happy": 5, "smug": 3, "relieved": 3, "sad": -4, "worried": -3}.get(e, 0)
    cy = my + 3
    outer = ("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d "
             "L %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Z" % (
                 L + 3, ye - 14, L - 7, ye + 22, L + 7, ye + 48, x - 40, chin + 20, x, chin + 22,
                 x + 40, chin + 20, R - 7, ye + 48, R + 7, ye + 22, R - 3, ye - 14,
                 R - 9, ye - 12, R - 8, ye + 16, x + 30, my - 10, x + 14, ny + 10, x, ny + 8,
                 x - 14, ny + 10, x - 30, my - 10, L + 8, ye + 16, L + 9, ye - 12))
    hole = "M %.1f %.1f A %.1f %.1f 0 1 0 %.1f %.1f A %.1f %.1f 0 1 0 %.1f %.1f Z" % (
        x - hx, cy, hx, hy, x + hx, cy, hx, hy, x - hx, cy)
    tips = my + 5 - lift
    stache = ("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d "
              "Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Z" % (
                  x, ny + 7, x + 14, ny + 2, x + 26, my - 8, x + 34, my - 2, x + 30, tips,
                  x + 22, my - 1, x + 12, my - 2, x + 4, my - 3, x, my - 6,
                  x - 4, my - 3, x - 12, my - 2, x - 22, my - 1, x - 30, tips,
                  x - 34, my - 2, x - 26, my - 8, x - 14, ny + 2, x, ny + 7))
    strand = _shade(col, 0.72)
    return (_p(outer + " " + hole, col, INK, 4.5, ' fill-rule="evenodd"')
            + _p("M %d %d q 4 6 0 12 M %d %d q -4 6 0 12 M %d %d q 3 6 0 11 M %d %d q -3 6 0 11 M %d %d q 0 6 0 10" % (
                x - 26, chin - 2, x + 26, chin - 2, x - 42, ye + 36, x + 42, ye + 36, x, chin + 6), "none", strand, 2.5)
            + _p(stache, _shade(col, 0.86), INK, 4))


def _grin(e, a, fill):
    """A grin that stays whatever is felt: wide and toothy, strained flat over a bad feeling, dropped
    open in surprise."""
    x, y = a["mx"], a["my"]

    def at(y0, yc, half, dx):                  # a symmetric quadratic edge's height, dx from the middle
        s = (dx + half) / (2.0 * half)
        return y0 + 2 * (yc - y0) * s * (1 - s)
    if e == "surprised":                       # the jaw drops; the smile stays
        return (_p("M %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 22, y - 7, x, y + 40, x + 22, y - 7, x, y + 1, x - 22, y - 7),
                   fill, INK, 4.5)
                + _p("M %d %d Q %d %d %d %d L %d %d Q %d %d %d %d Z" % (x - 19, y - 5, x, y + 1, x + 19, y - 5,
                     x + 17, y + 1, x, y + 7, x - 17, y + 1), "#FFFFFF", None))
    strained = e in ("sad", "angry", "worried", "jealous", "confused")
    w, up, low, mid = (26, 3, 10, 5) if strained else (23, 8, 16, 8)   # half width, corner lift, depth, bite
    top_c, bot_c = y + 2, 2 * (y + low) - (y - up)
    bite0, bite_c = y - up + 2, 2 * (y + mid) - (y - up + 2)
    out = (_p("M %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - w, y - up, x, top_c, x + w, y - up, x, bot_c, x - w, y - up),
              "#FFFFFF", INK, 4.5)
           + _p("M %d %d Q %d %d %d %d" % (x - w + 3, bite0, x, bite_c, x + w - 3, bite0), "none", INK, 2.5))
    for dx in ((-15, -5, 5, 15) if strained else (-10, 0, 10)):   # clenched teeth show both rows
        y2 = at(y - up, bot_c, w, dx) - 2 if strained else at(bite0, bite_c, w - 3, dx) - 1
        out += _p("M %d %.1f L %d %.1f" % (x + dx, at(y - up, top_c, w, dx) + 2, x + dx, y2), "none", INK, 2)
    return out


# ---------------------------------------------------------------- emotion parts
def _eyes(e, a, light, marks=()):
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    stroke = "#F4F4F4" if light else INK
    pupil = "#1C1D20"
    gx = -4 if "glance" in marks else 0        # a glance away: the pupils slide toward the left
    if "blink" in marks:                       # caught mid-blink, whatever is felt
        return "".join(_p("M %d %d Q %d %d %d %d" % (x - 10, y + 1, x, y + 5, x + 10, y + 1), "none", stroke, 5)
                       for x in (lx, rx))

    def dot(x, dy=0):
        x += gx
        if light:
            return _e(x, y + dy, 9, 10, "#FFFFFF", None) + _c(x, y + dy + 1, 5.5, pupil, None) + _c(x + 2.5, y + dy - 2.5, 2, "#FFFFFF", None)
        return _e(x, y + dy, 7, 9, pupil, None) + _c(x + 2.5, y + dy - 3, 2.5, "#FFFFFF", None)

    def wide(x, px=0, py=0, pr=4.5, rx_=10, ry_=11):
        px += gx
        return (_e(x, y, rx_, ry_, "#FFFFFF", INK if not light else None, 3)
                + _c(x + px, y + py, pr, pupil, None) + _c(x + px + 1.8, y + py - 1.8, 1.4, "#FFFFFF", None))

    def arc(x, up=True):
        d = ("M %d %d Q %d %d %d %d" % (x - 10, y + 3, x, y - 9, x + 10, y + 3) if up
             else "M %d %d Q %d %d %d %d" % (x - 10, y - 2, x, y + 8, x + 10, y - 2))
        return _p(d, "none", stroke, 6)

    if e == "neutral":
        return dot(lx) + dot(rx)
    if e == "happy":
        return arc(lx) + arc(rx)
    if e == "sad":
        lid = "#FFFFFF" if light else INK
        return (dot(lx, 2) + dot(rx, 2)
                + _p("M %d %d L %d %d" % (lx + 9, y - 9, lx - 10, y - 3), "none", lid, 3.5)
                + _p("M %d %d L %d %d" % (rx - 9, y - 9, rx + 10, y - 3), "none", lid, 3.5))
    if e == "angry":
        fill = "#FFFFFF" if light else pupil
        out = (_p("M %d %d L %d %d Q %d %d %d %d Z" % (lx - 11, y - 6, lx + 10, y + 1, lx + 2, y + 12, lx - 9, y + 5), fill, None)
               + _p("M %d %d L %d %d Q %d %d %d %d Z" % (rx + 11, y - 6, rx - 10, y + 1, rx - 2, y + 12, rx + 9, y + 5), fill, None))
        if light:
            out += _c(lx, y + 4, 4, pupil, None) + _c(rx, y + 4, 4, pupil, None)
        return out
    if e == "jealous":                         # half-lidded side-eye
        def side(x):
            return (_p("M %d %d L %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 10, y - 1, x + 10, y - 4, x + 9, y + 9,
                       x, y + 9, x - 9, y + 8, x - 10, y - 1), "#FFFFFF", INK if not light else None, 3)
                    + _c(x + 5, y + 3, 4.5, pupil, None)
                    + _p("M %d %d L %d %d" % (x - 12, y - 1, x + 12, y - 5), "none", stroke, 4))
        return side(lx) + side(rx)
    if e == "worried":
        return wide(lx, 0, 1, 4) + wide(rx, 0, 1, 4)
    if e == "relieved":
        return arc(lx, False) + arc(rx, False)
    if e == "thinking":
        return wide(lx, 4, -4, 4.5) + wide(rx, 4, -4, 4.5)
    if e == "surprised":
        return wide(lx, 0, 0, 3.5, 12, 12) + wide(rx, 0, 0, 3.5, 12, 12)
    if e == "smug":
        fill = "#FFFFFF" if light else pupil
        out = ""
        for x in (lx, rx):
            out += _p("M %d %d Q %d %d %d %d Z" % (x - 9, y, x, y + 12, x + 9, y), fill, None)
            if light:
                out += _c(x, y + 4, 3.5, pupil, None)
            out += _p("M %d %d L %d %d" % (x - 11, y - 1, x + 11, y + 1), "none", stroke, 4.5)
        return out
    if e == "determined":
        # NARROWED AND FOCUSED: the upper lids come down over the top of the eye (a["lid"], the skin,
        # covers it) along a firm line that dips a touch toward the nose, and a catch-light stays.
        # Two earlier designs did not read: clenched teeth under a scowl looked furious, and wide eyes
        # under a raised lid over a wobbly half-smile looked nervous.
        lid = a.get("lid", "#E1AE86")
        out = ""
        for x, s in ((lx, 1), (rx, -1)):
            x += gx
            if light:
                out += _e(x, y + 1, 9, 9, "#FFFFFF", None) + _c(x, y + 3, 5, pupil, None)
            else:
                out += _e(x, y + 1, 7, 9, pupil, None)
            yo, yi = y - 2, y                  # the lid's outer end, and its inner end a touch lower
            x_o, x_i = (x - 11, x + 11) if s > 0 else (x + 11, x - 11)
            out += _p("M %d %d L %d %d L %d %d L %d %d Z" % (x_o, y - 13, x_i, y - 13, x_i, yi, x_o, yo), lid, None)
            out += _p("M %d %d L %d %d" % (x_o, yo, x_i, yi), "none", INK, 4.5)
            out += _c(x + 2.5, y + 3, 2.2, "#FFFFFF", None)
        return out
    if e == "confused":
        small = (_e(rx, y + 1, 8, 4, "#FFFFFF", None) + _c(rx, y + 1, 3.5, pupil, None)) if light else \
            _p("M %d %d L %d %d" % (rx - 8, y + 1, rx + 8, y + 1), "none", INK, 5)
        return wide(lx, -2, 0, 4, 11, 12) + small
    return dot(lx) + dot(rx)


def _brows(e, a, color, w, marks=()):
    lx, rx, b = a["lx"], a["rx"], a["by"]

    def q(x1, y1, cx, cy, x2, y2):
        return _p("M %d %d Q %d %d %d %d" % (x1, y1, cx, cy, x2, y2), "none", color, w)

    def pair(l, r):
        l, r = list(l), list(r)
        if "knit" in marks:                    # the inner ends drawn down and together
            l[4], l[5], r[0], r[1] = l[4] - 2, l[5] + 4, r[0] + 2, r[1] + 4
        if "brow_up" in marks:                 # one brow lifts a touch
            r = [v - 6 if i % 2 else v for i, v in enumerate(r)]
        return q(*l) + q(*r)

    L = {
        "neutral":    ((lx - 12, b + 1, lx, b - 3, lx + 12, b + 1), (rx - 12, b + 1, rx, b - 3, rx + 12, b + 1)),
        "happy":      ((lx - 12, b - 1, lx, b - 10, lx + 12, b - 1), (rx - 12, b - 1, rx, b - 10, rx + 12, b - 1)),
        "sad":        ((lx - 13, b + 5, lx, b + 1, lx + 12, b - 7), (rx - 12, b - 7, rx, b + 1, rx + 13, b + 5)),
        "angry":      ((lx - 13, b - 6, lx, b - 1, lx + 12, b + 7), (rx - 12, b + 7, rx, b - 1, rx + 13, b - 6)),
        "jealous":    ((lx - 12, b + 3, lx, b + 3, lx + 12, b + 6), (rx - 12, b - 2, rx, b - 10, rx + 12, b - 7)),
        "worried":    ((lx - 13, b + 2, lx + 2, b - 3, lx + 12, b - 10), (rx - 12, b - 10, rx - 2, b - 3, rx + 13, b + 2)),
        "relieved":   ((lx - 12, b, lx, b - 7, lx + 12, b - 3), (rx - 12, b - 3, rx, b - 7, rx + 12, b)),
        "thinking":   ((lx - 12, b + 3, lx, b + 2, lx + 12, b + 3), (rx - 12, b - 4, rx, b - 16, rx + 12, b - 8)),
        "surprised":  ((lx - 12, b - 10, lx, b - 20, lx + 12, b - 10), (rx - 12, b - 10, rx, b - 20, rx + 12, b - 10)),
        "smug":       ((lx - 12, b + 3, lx, b + 2, lx + 12, b + 2), (rx - 12, b - 5, rx, b - 14, rx + 12, b - 6)),
        "determined": ((lx - 13, b - 1, lx, b + 1, lx + 12, b + 5), (rx - 12, b + 5, rx, b + 1, rx + 13, b - 1)),
        "confused":   ((lx - 12, b - 6, lx, b - 16, lx + 12, b - 6), (rx - 12, b + 5, rx, b + 3, rx + 12, b - 1)),
    }[e]
    return pair(*L)


def _mouth(e, a, fill, marks=()):
    x, y = a["mx"], a["my"]
    if e == "neutral" and "press" in marks:    # lips pressed thin
        return _p("M %d %d L %d %d" % (x - 9, y, x + 9, y), "none", INK, 7)
    if e in ("neutral", "thinking") and "smirk" in marks:   # one corner lifts
        return _p("M %d %d L %d %d Q %d %d %d %d" % (x - 12, y, x + 5, y, x + 10, y, x + 14, y - 5), "none", INK, 5.5)
    if e == "neutral":
        return _p("M %d %d L %d %d" % (x - 12, y, x + 12, y), "none", INK, 5.5)
    if e == "happy":
        return (_p("M %d %d Q %d %d %d %d Z" % (x - 22, y - 7, x, y + 28, x + 22, y - 7), fill, INK, 4.5)
                + _p("M %d %d Q %d %d %d %d L %d %d Q %d %d %d %d Z" % (x - 18, y - 5, x, y + 1, x + 18, y - 5,
                     x + 16, y, x, y + 6, x - 16, y), "#FFFFFF", None)
                + _e(x, y + 11, 8, 4.5, "#E27A7A", None))
    if e == "sad":
        return _p("M %d %d Q %d %d %d %d" % (x - 16, y + 8, x, y - 7, x + 16, y + 8), "none", INK, 5.5)
    if e == "angry":                           # shouting: an open frown, top teeth showing
        return (_p("M %d %d L %d %d Q %d %d %d %d L %d %d Q %d %d %d %d Z" % (x - 20, y + 11, x - 14, y - 4,
                   x, y - 9, x + 14, y - 4, x + 20, y + 11, x, y + 5, x - 20, y + 11), fill, INK, 4.5)
                + _p("M %d %d Q %d %d %d %d L %d %d Q %d %d %d %d Z" % (x - 13, y - 3, x, y - 8, x + 13, y - 3,
                     x + 14, y + 1, x, y - 3, x - 14, y + 1), "#FFFFFF", None))
    if e == "jealous":
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d" % (x - 12, y + 4, x - 3, y - 3, x + 5, y + 2,
                                                            x + 10, y + 5, x + 15, y), "none", INK, 5)
    if e == "worried":
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d" % (x - 18, y + 3, x - 12, y - 5, x - 6, y + 2,
                  x, y + 9, x + 6, y + 2, x + 12, y - 5, x + 18, y + 3), "none", INK, 4.5)
    if e == "relieved":
        return _p("M %d %d Q %d %d %d %d" % (x - 16, y - 3, x, y + 10, x + 16, y - 3), "none", INK, 5.5)
    if e == "thinking":
        return _p("M %d %d Q %d %d %d %d" % (x - 3, y + 3, x + 6, y - 1, x + 15, y + 1), "none", INK, 5)
    if e == "surprised":
        return _e(x, y + 3, 9, 12, fill, INK, 4.5)
    if e == "smug":
        return _p("M %d %d Q %d %d %d %d" % (x - 15, y + 3, x + 2, y + 8, x + 18, y - 7), "none", INK, 5.5)
    if e == "determined":                      # a confident grin: flat top, teeth, corners up ("let's do this")
        return (_p("M %d %d L %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 16, y - 3, x + 16, y - 3, x + 15, y + 9,
                                                                      x, y + 10, x - 15, y + 9, x - 16, y - 3), "#FFFFFF", INK, 4.5)
                + _p("M %d %d L %d %d" % (x - 15, y + 2, x + 15, y + 2), "none", INK, 2))
    if e == "confused":
        return _p("M %d %d L %d %d" % (x - 12, y + 5, x + 12, y - 3), "none", INK, 5.5)
    return ""


def _extra(e, a, head_d):
    tx, ty = a["temple"]
    if e == "happy":
        return "".join(_e(cx, cy, 10, 5.5, "#E8828A", None, extra=' opacity="0.6"') for cx, cy in a["cheeks"])
    if e == "sad":
        x, y = a["lx"] - 7, a["ey"] + 12
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x, y, x + 7, y + 12, x, y + 17, x - 7, y + 12, x, y),
                  "#5DA9E9", "#2F6FA8", 2.5)
    if e == "angry":
        x, y = tx + 2, ty - 8
        return _p("M %d %d Q %d %d %d %d M %d %d Q %d %d %d %d M %d %d Q %d %d %d %d M %d %d Q %d %d %d %d"
                  % (x - 10, y - 3, x - 3, y - 3, x - 3, y - 10, x + 3, y - 10, x + 3, y - 3, x + 10, y - 3,
                     x + 10, y + 3, x + 3, y + 3, x + 3, y + 10, x - 3, y + 10, x - 3, y + 3, x - 10, y + 3),
                  "none", "#D0433A", 4.5)
    # JEALOUS HAS NO EXTRA: a green cast over the whole face does not read
    if e == "worried":
        x, y = tx + 6, ty - 4
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x, y - 12, x + 9, y + 4, x, y + 8, x - 9, y + 4, x, y - 12),
                  "#9ED3F5", "#3F86C2", 2.5)
    if e == "relieved":                        # a sigh: a puff of breath leaving the corner of the mouth
        x, y = a["mx"] + 22, a["my"] - 4
        return (_p("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Z" % (
                    x, y + 4, x + 2, y - 6, x + 12, y - 5, x + 20, y - 10, x + 28, y - 2, x + 34, y + 6, x + 24, y + 12,
                    x + 12, y + 14, x, y + 4), "#EEF1F4", "#8A9097", 3)
                + _p("M %d %d L %d %d M %d %d L %d %d" % (x + 36, y - 6, x + 44, y - 10, x + 38, y + 10, x + 46, y + 12),
                     "none", "#8A9097", 3))
    if e == "thinking":
        return (_c(tx - 2, ty - 18, 4, "#FFFFFF", INK, 3) + _c(tx + 8, ty - 32, 5.5, "#FFFFFF", INK, 3)
                + _c(tx + 18, ty - 50, 7.5, "#FFFFFF", INK, 3))
    if e == "surprised":
        return _p("M 148 40 L 158 28 M 160 50 L 174 44 M 138 32 L 140 18", "none", INK, 4.5)
    if e == "smug":
        x, y = 42, 48
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Z" % (
            x, y - 13, x + 2, y - 2, x + 13, y, x + 2, y + 2, x, y + 13, x - 2, y + 2, x - 13, y, x - 2, y - 2,
            x, y - 13), "#F2C94C", INK, 2.5)
    # DETERMINED HAS NO EXTRA: the narrowed eyes, low brows and confident grin carry it. Steam from the
    # nose read as bubbles, a flame at the temple read as sweat, and a bigger blaze still did not work.
    if e == "confused":
        return (_p("M 150 30 Q 150 18 162 18 Q 174 18 174 30 Q 174 38 164 42 L 164 50", "none", INK, 6)
                + _c(164, 60, 4, INK, None))
    return ""


def _star(x, y, r, fill, stroke=INK, width=1.8):
    """A small four-point sparkle."""
    k = r * 0.28
    return _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (
        x, y - r, x + k, y - k, x + r, y, x + k, y + k, x, y + r, x - k, y + k, x - r, y, x - k, y - k, x, y - r),
        fill, stroke, width)


def _marks(marks, a, look, head_d):
    """The subtle frames that sit over a face (MARKS). The ones that change a feature -- glance,
    blink, brow_up, knit, press, smirk -- are drawn by the feature itself."""
    out = ""
    lx, rx, ey = a["lx"], a["rx"], a["ey"]
    tx, ty = a["temple"]
    L, R, ye = a["ears"]
    lensed = any(p.get("part") in ("glasses", "sunglasses", "small_glasses", "monocle", "beak_glasses")
                 for p in look.get("face") or [])
    # the fine marks are drawn in ink; on a dark face (black fur, dark skin) ink vanishes, so light instead
    dark = dark_face(look)
    ink = "#D9DDE3" if dark else INK
    for m in marks:
        if m == "glint":                       # light catching a lens, or the eye itself
            out += _star(rx + 7, ey - 7, 7 if lensed else 5, "#FFFFFF", INK, 1.5)
        elif m == "bead":                      # one small bead of sweat
            x, y = tx - 6, ty + 10
            out += _p("M %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x, y - 6, x + 4, y + 2, x, y + 4, x - 4, y + 2, x, y - 6),
                      "#BFE3F7", "#3F86C2", 1.8)
        elif m == "twitch":                    # the corner of one eye jumps
            x = lx - 17
            out += _p("M %d %d Q %d %d %d %d M %d %d Q %d %d %d %d" % (x, ey - 7, x - 4, ey - 3, x, ey + 1,
                                                                        x - 5, ey - 9, x - 10, ey - 3, x - 5, ey + 3),
                      "none", ink, 1.8)
        elif m == "narrow":                    # the upper lids drop a little
            lid = a.get("lid", look.get("skin", "#E1AE86"))
            for x in (lx, rx):
                out += _p("M %d %d L %d %d L %d %d Q %d %d %d %d Z" % (x - 12, ey - 13, x + 12, ey - 13, x + 12, ey - 3,
                                                                    x, ey - 6, x - 12, ey - 3), lid, None)
                out += _p("M %d %d Q %d %d %d %d" % (x - 11, ey - 3, x, ey - 6, x + 11, ey - 3), "none", INK, 3)
        elif m == "flush":                     # color rising in the cheeks
            out += "".join(_e(cx, cy, 11, 6, "#E8828A", None, extra=' opacity="0.3"') for cx, cy in a["cheeks"])
        elif m == "pale":                      # the color draining out
            out += _p(head_d, "#9FB4C4", None, extra=' opacity="0.14"')
        elif m == "jaw":                       # a clenched jaw, the muscle standing out
            cy = a["my"] - 6
            out += _p("M %d %d Q %d %d %d %d M %d %d Q %d %d %d %d" % (L + 14, cy - 6, L + 10, cy, L + 14, cy + 6,
                                                                        R - 14, cy - 6, R - 10, cy, R - 14, cy + 6),
                      "none", ink if dark else _shade(look.get("skin", "#E1AE86"), 0.6), 2.5)
        elif m == "nostrils":                  # flaring
            nx, ny = a["nx"], a["ny"]
            out += _p("M %d %d Q %d %d %d %d M %d %d Q %d %d %d %d" % (nx - 10, ny + 1, nx - 14, ny + 5, nx - 11, ny + 9,
                                                                        nx + 10, ny + 1, nx + 14, ny + 5, nx + 11, ny + 9),
                      "none", ink, 2)
        elif m == "ear_flick":                 # one ear twitches
            x, y = R + 6, ye - 22
            out += _p("M %d %d Q %d %d %d %d M %d %d Q %d %d %d %d" % (x, y - 8, x + 5, y - 2, x, y + 4,
                                                                        x + 6, y - 11, x + 12, y - 3, x + 6, y + 5),
                      "none", INK, 1.8)
        elif m == "glitch":                    # for an instant, something that is not a person
            for i, (y, dx) in enumerate(((ey - 16, 7), (ey + 22, -6), (a["my"] + 10, 5))):
                out += '<rect x="%d" y="%d" width="%d" height="4" fill="%s" opacity="0.55"/>' % (
                    L - 4 + dx, y, R - L + 8, "#39D98A" if i != 1 else "#6E7CF2")
            out += _e(rx, ey, 3, 8, "#39D98A", INK, 1.5)
        elif m == "led":                       # an indicator light changes color
            out += "".join(_c(x, ey, 13, "#F5A623", None, extra=' opacity="0.45"') for x in (lx, rx))
        elif m == "static":                    # a flicker of interference
            out += "".join('<rect x="%d" y="%d" width="%d" height="2" fill="%s" opacity="0.35"/>' % (L, y, R - L, ink)
                           for y in range(int(a["top"]) + 14, int(a["chin"]) - 6, 23))
        elif m == "twinkle":                   # a glimmer over the head (a hat's star, a halo's edge)
            out += _star(a.get("twinkle_x", 132), a.get("twinkle_y", max(12, a["top"] - 14)), 7, "#FFE08A", INK, 1.5)
    return out


# ---------------------------------------------------------------- a whole face
def face_svg(look, emotion, size=200, marks=()):
    """The character's face for one emotion, as a standalone SVG string (200 x 200 viewBox)."""
    if look.get('cast_id') and look.get('art_direction'):
        from paperdaemon.pipeline.games import cast as rm_cast
        authored_face = rm_cast.hook("face_svg")          # a pack's own faces for its characters
        if authored_face is not None:
            return authored_face(look, emotion, size, marks)
    if emotion not in EMOTIONS:
        raise ValueError("no emotion %r; have %s" % (emotion, ", ".join(EMOTIONS)))
    bad = [m for m in marks if m not in MARKS]
    if bad:
        raise ValueError("no mark %r; have %s" % (bad[0], ", ".join(MARKS)))
    if look.get("portrait_set"):
        from paperdaemon.pipeline.games.faces.portraits import face_svg as drawn_portrait
        return drawn_portrait(look, emotion, size, marks)
    eye_e, brow_e, mouth_e, extra_marks = MIXED_EXPRESSIONS.get(emotion, (emotion, emotion, emotion, ()))
    # a look may carry HABITS: marks it always shows (a set jaw, a squint, a half-smile) -- one face
    # among several a character can wear (rm_characters: alters)
    habits = tuple(m for m in look.get("marks") or () if m in MARKS)
    marks = tuple(dict.fromkeys(tuple(marks) + extra_marks + habits))
    skin = tablet_skin(look.get("skin", "#E1AE86"))      # a dark skin, lifted into what the tablet shows
    look = dict(look, skin=skin)
    # a head may draw what it holds by the feeling and the marks (a vending machine's stock)
    head_svg, head_d, a, _edge = head(look.get("head", "oval"), skin, dict(look, _emotion=emotion, _marks=marks))
    a = dict(a, **(look.get("anchors") or {}))
    a["head_d"] = head_d                        # parts cut to the head's own outline (stubble)
    a.setdefault("lid", skin)                   # what covers an eye when a lid comes down (determined, narrow)
    if "earrings" not in a:
        L_, R_, ye_ = a["ears"]
        a["earrings"] = (((47, 128), (153, 128)) if look.get("head", "oval") in ("round", "strong", "oval", "raccoon")
                         else ((L_ + 6, ye_ + 12), (R_ - 6, ye_ + 12)))
    light = look.get("eyes") == "light"
    brow = look.get("brows") or {}
    body = look.get("body") or {}
    hair = look.get("hair") or []
    face = look.get("face") or []
    kinds = [p.get("part") for p in face]
    beard = [p for p in face if p.get("part") == "full_beard"]
    parts_before_eyes = [p for p in face if p.get("part") in ("raccoon_mask", "muzzle", "stubble", "wrinkles", "bandage")
                         or p.get("part") in FACE_UNDER]
    # a nose sits on top of a mustache, so under a beard it is drawn after it
    noses = [p for p in face if beard and p.get("part") in ("round_nose", "small_nose", "raccoon_nose")]
    parts_after = [p for p in face if p not in parts_before_eyes and p not in noses
                   and p.get("part") not in ("brooch", "glasses", "sunglasses", "full_beard", "fixed_grin")]
    badge = look.get("badge", "#E4E4E7")
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="%d" height="%d">' % (size, size),
           '<defs><clipPath id="badge"><circle cx="100" cy="100" r="97"/></clipPath></defs>',
           _c(100, 100, 97, badge, None),
           '<g clip-path="url(#badge)">']
    out += [_hair_back(h, a) for h in hair]
    out.append(_body(dict(body, fur=skin), body.get("color"), a) if body else "")
    if any(p.get("part") == "brooch" for p in face):
        out.append(_brooch(126, 186))
    nw = float(a.get("neck_w", 28))             # a head may have a slimmer neck (anchors["neck_w"])
    out.append('<rect x="%.1f" y="150" width="%.1f" height="22" fill="%s" stroke="%s" stroke-width="4"/>'
               % (100 - nw / 2, nw, skin, INK) if look.get("head") != "raccoon" and a.get("neck", True) else "")
    out.append(head_svg)
    out += [_face_part(p, a, skin) for p in parts_before_eyes]
    eyes = EYES.get(a.get("eyes_style"))
    out.append(eyes(eye_e, a, light, marks) if eyes else _eyes(eye_e, a, light, marks))
    out += [_face_part(p, a, skin) for p in parts_after]
    if "glasses" in kinds:
        out.append(_glasses(a))
    out += [_sunglasses(a, p) for p in face if p.get("part") == "sunglasses"]
    fill = look.get("mouth_fill", "#7A2E35")
    mouth = MOUTHS.get(a.get("mouth_style"))
    out.append(_grin(mouth_e, a, fill) if "fixed_grin" in kinds else
               mouth(mouth_e, a, fill, marks) if mouth else _mouth(mouth_e, a, fill, marks))
    out += [_beard(mouth_e, a, p) for p in beard]
    out += [_face_part(p, a, skin) for p in noses]
    out += [_hair_front(h, a) for h in hair]
    # BROWS LAST: they carry half of every emotion, so nothing -- a cap's brim, a headband, bangs --
    # may cover them; floating over the hair is the cartoon convention anyway
    if not a.get("no_brows"):
        out.append(_brows(brow_e, a, brow.get("color", INK), brow.get("weight", 6), marks))
    out.append(_marks([m for m in marks if m not in ("glance", "blink", "brow_up", "knit", "press", "smirk")
                       and m not in (a.get("own_marks") or ())],
                      a, look, head_d))
    out.append("</g>")
    out.append(_c(100, 100, 97, "none", INK, 3))
    out.append(_extra(emotion, a, head_d))
    out.append("</svg>")
    return "".join(x for x in out if x)


# ---------------------------------------------------------------- the part modules
# The part modules register their parts (people, animals, machines) on import, after the kit above exists.
from paperdaemon.pipeline.games.faces import creatures, people  # noqa: E402,F401
