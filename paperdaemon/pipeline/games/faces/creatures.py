r"""Animal heads for the face kit (games/faces): elephant, mouse, fox, bear, owl, crow, tortoise, seal,
rabbit, cat, basset, goat, octopus.

Each head draws its whole species -- ears, muzzle, nose, whiskers, spots, trunk, arms -- so a look
needs only {"head": "fox", "skin": "#E07A2E"}; the kit's shared eyes, brows, mouths and extras carry
the twelve emotions on top, exactly as on a person. Fur color is look["skin"]; the accent colors
below have defaults and may be set in the look:

    elephant  inner (inner ear)                 owl       disc (facial disc), beak, tufts (False: none)
    mouse     inner, nose                       crow      beak, sheen
    fox       accent (cheeks, muzzle), inner    tortoise  beak
    bear      muzzle, inner                     seal      spots, pads (whisker pads)
    rabbit    inner, nose, accent (cheeks)      cat       inner, nose, whiskers
    basset    accent (blaze, muzzle), ears      goat      horns, beard, inner
    octopus   suckers

Dark fur wants "eyes": "light" and light brows in the look (as the raccoon's mask does): a black
crow or cat with dark eyes has none.

Anchor conventions (the kit reads these; see faces.head):
- lx/rx/ey, by, mx/my, cheeks, temple, top, chin: as on a person. The temple sits on the upper right
  of the head's outline, where a vein, a sweat drop or a flame reads.
- nx/ny is where the nostrils mark flares: the nose, the trunk's tip, a beak's base.
- ears (L, R, y) is the head's width at the ears, placed so that ear_flick (drawn at R + 6, y - 22)
  lands beside the right ear and jaw (L + 14, R - 14 at my - 6) on the cheeks.
- "neck": False on every head; "lid" (narrow's lid color) where the eyes sit on a patch that is not
  fur; "mouth_style": "beak" on the birds and the tortoise; "eyes_style": "big_round" (the seal's and
  the owl's big eyes, a["eye_scale"]) or "goat" (wide and short: horizontal pupils) -- both are the
  kit's own eyes, scaled, so every emotion keeps its shape; "lens_r" sizes beak_glasses to the eyes.

The beak (MOUTHS "beak") is two mandibles; the emotion opens the lower one (happy, angry, surprised,
a nervous gap when worried), tilts the whole beak (smug, thinking, jealous, confused), and creases
its corners up or down. Its shape comes from the anchors: beak_top (where it meets the face), my (the
gape), beak_tip (the upper mandible's tip), beak_w (half its width at the gape), beak_low (the lower
mandible's length), beak_fill / beak_under / beak_crease (colors).
"""
from paperdaemon.pipeline.games.faces import (INK, EYES, FACE_PARTS, HEADS, MOUTHS, _c, _e, _eyes, _p, _shade, register)
import math
from paperdaemon.pipeline.games.faces import EYES, HEADS, INK, MOUTHS, _c, _e, _p, _shade, register

# ---------------------------------------------------------------- helpers
def _mix(c1, c2, t):
    """c1 blended toward c2 by t (0..1)."""
    a = [int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02X%02X%02X" % tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _lum(c):
    h = c.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def _mirror(d, cx=100):
    """A path (absolute M L Q C H V Z only) mirrored left to right about x = cx."""
    out, cmd, k = [], None, 0
    for t in d.replace(",", " ").split():
        if t.isalpha():
            cmd, k = t, 0
            out.append(t)
            continue
        v = float(t)
        if cmd in "MLQCST" and k % 2 == 0 or cmd == "H":
            v = 2 * cx - v
        k += 1
        out.append("%g" % v)
    return " ".join(out)


def _pair(d, fill, stroke=INK, width=4, extra=""):
    """A left-side part and its mirror image."""
    return _p(d, fill, stroke, width, extra) + _p(_mirror(d), fill, stroke, width, extra)


def _whisker_ink(skin):
    return "#E9E9E6" if _lum(skin) < 0.35 else "#6E7177"


def _anchors(**kw):
    kw.setdefault("neck", False)
    return kw


PINK = "#EFA3AE"


# ---------------------------------------------------------------- heads
@register(HEADS, "elephant")
def _elephant(skin, look):
    """Big ears, a trunk that curls up to the right; the mouth sits under the trunk's base."""
    inner = look.get("inner") or _mix(skin, "#E79AA6", 0.45)
    fold = _shade(skin, 0.7)
    ear = "M 62 64 C 38 38 10 46 10 88 C 10 128 32 152 64 142 Z"
    ear_in = "M 58 74 C 40 58 22 66 22 90 C 22 120 38 136 60 130 Z"
    face = "M 100 40 C 132 40 152 62 152 102 C 152 144 136 176 100 178 C 64 176 48 144 48 102 C 48 62 68 40 100 40 Z"
    # down from between the eyes, then out to the right under the right eye, the tip turned up. It runs
    # the same way round as the face, so a tint over face + trunk (the pale mark) leaves no hole.
    trunk = ("M 111 84 L 112 112 Q 112 126 120 127 Q 132 128 142 122 Q 146 117 151 120 Q 157 126 150 132 "
             "Q 136 142 114 142 Q 88 142 88 112 L 89 84 Z")
    trunk_edge = ("M 92 82 Q 88 90 88 100 L 88 112 Q 88 142 114 142 Q 136 142 150 132 Q 157 126 151 120 "
                  "Q 146 117 142 122 Q 132 128 120 127 Q 112 126 112 112 L 112 100 Q 112 90 108 82")
    folds = ("M 90 98 Q 100 102 110 98 M 90 106 Q 100 110 110 106 M 120 129 Q 123 135 121 141 "
             "M 131 128 Q 135 133 133 139")
    svg = (_pair(ear, skin, INK, 4) + _pair(ear_in, inner, None)
           + _p(face, skin, INK, 5)
           + _p(trunk, skin, None) + _p(trunk_edge, "none", INK, 4.5) + _p(folds, "none", fold, 2.5))
    a = _anchors(lx=72, rx=128, ey=104, by=84, mx=100, my=159, nx=148, ny=121,
                 cheeks=((66, 150), (136, 154)), temple=(150, 80), top=40, ears=(46, 154, 63), chin=178)
    return svg, face + " " + trunk, a, _shade(skin, 0.62)


@register(HEADS, "mouse")
def _mouse(skin, look):
    """Big round ears, a pointed snout with a pink nose, whiskers."""
    inner = look.get("inner") or PINK
    nose = look.get("nose") or "#E57D8E"
    face = "M 100 60 C 138 60 158 86 156 118 C 154 150 128 174 100 176 C 72 174 46 150 44 118 C 42 86 62 60 100 60 Z"
    svg = (_c(50, 58, 29, skin, INK, 4) + _c(150, 58, 29, skin, INK, 4)
           + _c(52, 61, 18, inner, None) + _c(148, 61, 18, inner, None)
           + _p(face, skin, INK, 5)
           + _pair("M 70 142 L 38 134 M 70 148 L 40 152", "none", _whisker_ink(skin), 2.5)
           + _e(100, 137, 8.5, 6.5, nose, INK, 3) + _c(97, 134.5, 2, "#FFFFFF", None))
    a = _anchors(lx=78, rx=122, ey=112, by=94, mx=100, my=160, nx=100, ny=136,
                 cheeks=((66, 142), (134, 142)), temple=(148, 90), top=60, ears=(46, 154, 78), chin=176,
                 twinkle_x=100, twinkle_y=38)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "fox")
def _fox(skin, look):
    """Pointed ears, cheek ruffs; white cheeks and muzzle under a black nose."""
    white = look.get("accent") or "#FBF7F0"
    inner = look.get("inner") or white
    tip = _shade(skin, 0.45)
    ear = "M 50 90 L 40 30 Q 41 22 49 26 L 94 58 Z"
    ear_in = "M 56 82 L 47 43 L 82 62 Z"
    ear_tip = "M 40 30 Q 41 22 49 26 L 61 35 L 42 41 Z"
    face = ("M 52 86 Q 66 56 100 56 Q 134 56 148 86 Q 158 106 176 128 Q 160 138 146 148 Q 126 174 100 176 "
            "Q 74 174 54 148 Q 40 138 24 128 Q 42 106 52 86 Z")
    muzzle = ("M 24 128 Q 44 116 62 124 Q 78 132 90 124 Q 96 120 100 120 Q 104 120 110 124 Q 122 132 138 124 "
              "Q 156 116 176 128 Q 160 138 146 148 Q 126 174 100 176 Q 74 174 54 148 Q 40 138 24 128 Z")
    svg = (_pair(ear, skin, INK, 4) + _pair(ear_in, inner, None) + _pair(ear_tip, tip, None)
           + _pair("M 40 30 Q 41 22 49 26 L 94 58", "none", INK, 4)
           + _p(face, skin, INK, 5) + _p(muzzle, white, None) + _p(face, "none", INK, 5)
           + _p("M 90 130 Q 100 125 110 130 Q 108 140 100 142 Q 92 140 90 130 Z", "#1E1F22", INK, 2.5)
           + _c(96, 130, 2, "#FFFFFF", None))
    a = _anchors(lx=76, rx=124, ey=104, by=86, mx=100, my=157, nx=100, ny=134,
                 cheeks=((60, 138), (140, 138)), temple=(148, 84), top=56, ears=(44, 156, 73), chin=176,
                 twinkle_x=100, twinkle_y=38)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "bear")
def _bear(skin, look):
    """Round ears, a big round head, a pale muzzle under a dark nose."""
    muzzle = look.get("muzzle") or _mix(skin, "#F4E2C6", 0.6)
    inner = look.get("inner") or _mix(skin, "#F4E2C6", 0.35)
    face = "M 100 46 C 140 46 164 72 164 110 C 164 150 138 176 100 176 C 62 176 36 150 36 110 C 36 72 60 46 100 46 Z"
    svg = (_c(54, 54, 21, skin, INK, 4) + _c(146, 54, 21, skin, INK, 4)
           + _c(55, 56, 11, inner, None) + _c(145, 56, 11, inner, None)
           + _p(face, skin, INK, 5)
           + _e(100, 146, 32, 26, muzzle, INK, 3.5)
           + _p("M 88 129 Q 100 123 112 129 Q 110 139 100 141 Q 90 139 88 129 Z", "#1E1F22", INK, 2.5)
           + _c(95, 129, 2.2, "#FFFFFF", None))
    a = _anchors(lx=74, rx=126, ey=104, by=86, mx=100, my=157, nx=100, ny=133,
                 cheeks=((56, 136), (144, 136)), temple=(152, 84), top=46, ears=(40, 160, 69), chin=176,
                 twinkle_x=100, twinkle_y=30)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "owl")
def _owl(skin, look):
    """Feather tufts, a heart-shaped facial disc, big eyes, a hooked beak."""
    disc = look.get("disc") or "#F6EEDF"
    rim = _shade(skin, 0.8)
    tuft = "M 44 84 Q 34 60 34 30 Q 42 38 48 46 Q 46 34 50 22 Q 58 34 60 46 Q 64 38 70 32 Q 72 50 78 62 Z"
    face = "M 100 42 C 146 42 170 74 170 114 C 170 154 140 180 100 180 C 60 180 30 154 30 114 C 30 74 54 42 100 42 Z"
    dsc = "M 100 72 C 82 58 50 58 42 88 C 34 120 58 154 100 170 C 142 154 166 120 158 88 C 150 58 118 58 100 72 Z"
    svg = ((_pair(tuft, skin, INK, 4) + _pair("M 46 70 Q 42 56 42 44 M 56 64 Q 54 52 54 40", "none", rim, 2.5)
            if look.get("tufts", True) else "")
           + _p(face, skin, INK, 5)
           + _p("M 84 52 L 88 57 L 92 52 M 108 52 L 112 57 L 116 52 M 96 60 L 100 65 L 104 60", "none", rim, 2.5)
           + _p(dsc, disc, rim, 3.5))
    a = _anchors(lx=74, rx=126, ey=104, by=80, mx=100, my=124, nx=100, ny=112,
                 cheeks=((58, 134), (142, 134)), temple=(154, 82), top=42, ears=(40, 160, 80), chin=180,
                 twinkle_x=100, twinkle_y=28,
                 eyes_style="big_round", eye_scale=1.3, lid=disc, lens_r=19,
                 mouth_style="beak", beak_top=110, beak_tip=136, beak_w=11, beak_low=9,
                 beak_fill=look.get("beak") or "#E6B95B")
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "crow")
def _crow(skin, look):
    """Glossy black feathers, a spiky crest, a long gray beak."""
    sheen = look.get("sheen") or _mix(skin, "#7B8CB4", 0.55)
    crest = "M 86 48 L 80 26 L 94 40 L 100 16 L 106 40 L 120 28 L 114 50 Z"
    face = "M 100 40 C 142 40 162 72 162 110 C 162 150 136 176 100 178 C 64 176 38 150 38 110 C 38 72 58 40 100 40 Z"
    beak = look.get("beak") or "#6A717D"
    svg = (_p(crest, skin, INK, 4) + _p(face, skin, INK, 5)
           + _p("M 60 80 Q 72 58 98 52", "none", sheen, 5, ' opacity="0.8"')
           + _p("M 146 128 Q 152 114 150 100", "none", sheen, 4, ' opacity="0.6"'))
    a = _anchors(lx=74, rx=126, ey=102, by=84, mx=100, my=128, nx=100, ny=114,
                 cheeks=((60, 136), (140, 136)), temple=(150, 82), top=40, ears=(40, 160, 100), chin=178,
                 mouth_style="beak", beak_top=108, beak_tip=156, beak_w=15, beak_low=18,
                 beak_fill=beak, beak_under=_shade(beak, 0.8), beak_crease="#A9B2C2", lens_r=15)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "tortoise")
def _tortoise(skin, look):
    """A domed, wrinkly head on a creased neck; no ears; a wide horny beak."""
    fold = _shade(skin, 0.7)
    horn = look.get("beak") or _mix(skin, "#D9CB9C", 0.55)
    neck = "M 74 140 L 72 180 L 128 180 L 126 140 Z"          # tucked into the collar: no line along the bottom
    face = "M 100 40 C 140 40 160 68 160 102 C 160 138 140 164 100 166 C 60 164 40 138 40 102 C 40 68 60 40 100 40 Z"
    scales = ("M 90 50 L 100 45 L 110 50 L 108 59 L 92 59 Z "
              "M 74 58 L 86 52 L 90 61 L 82 68 L 71 65 Z M 126 58 L 114 52 L 110 61 L 118 68 L 129 65 Z")
    wrinkles = ("M 62 114 Q 74 120 86 114 M 114 114 Q 126 120 138 114 "
                "M 52 96 L 46 94 M 52 102 L 46 104 M 148 96 L 154 94 M 148 102 L 154 104 "
                "M 56 132 Q 62 146 72 152 M 144 132 Q 138 146 128 152")
    svg = (_p(neck, skin, None) + _p("M 74 140 L 72 180 M 126 140 L 128 180", "none", INK, 4)
           + _p("M 74 158 Q 100 164 126 158 M 73 170 Q 100 176 127 170", "none", fold, 2.5)
           + _p(face, skin, INK, 5) + _p(scales, _shade(skin, 0.93), fold, 2.5) + _p(wrinkles, "none", fold, 2.5)
           + _e(94, 120, 2.2, 1.6, INK, None) + _e(106, 120, 2.2, 1.6, INK, None))
    a = _anchors(lx=74, rx=126, ey=98, by=80, mx=100, my=140, nx=100, ny=119,
                 cheeks=((60, 128), (140, 128)), temple=(150, 78), top=40, ears=(42, 158, 96), chin=166,
                 mouth_style="beak", beak_top=131, beak_tip=148, beak_w=24, beak_low=10,
                 beak_fill=skin, beak_under=horn, beak_blend=True, beak_hook=0.12)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "seal")
def _seal(skin, look):
    """A round spotted head, big dark eyes, puffy whisker pads."""
    spot = look.get("spots") or _shade(skin, 0.7)
    pad = look.get("pads") or _mix(skin, "#FFFFFF", 0.35)
    face = "M 100 42 C 142 42 164 72 164 110 C 164 150 138 176 100 176 C 62 176 36 150 36 110 C 36 72 58 42 100 42 Z"
    spots = "".join(_c(x, y, r, spot, None) for x, y, r in (
        (62, 66, 5), (80, 53, 3.5), (122, 54, 4), (140, 66, 3), (48, 98, 3.5), (154, 104, 4),
        (50, 130, 3.5), (152, 138, 3), (104, 60, 2.5), (68, 160, 3), (134, 160, 3.5)))
    dots = "".join(_c(x, y, 1.4, INK, None) for x, y in ((80, 131), (86, 137), (80, 140), (120, 131), (114, 137), (120, 140)))
    svg = (_p(face, skin, INK, 5) + spots
           + _pair("M 74 128 L 40 120 M 74 134 L 40 136 M 76 140 L 44 150", "none", _whisker_ink(skin), 2.5)
           + _e(88, 134, 15, 12, pad, INK, 3.5) + _e(112, 134, 15, 12, pad, INK, 3.5) + dots
           + _p("M 91 117 Q 100 112 109 117 Q 107 125 100 127 Q 93 125 91 117 Z", "#1E1F22", INK, 2.5)
           + _c(96, 117, 1.8, "#FFFFFF", None)
           + _e(42, 100, 2.2, 3, INK, None) + _e(158, 100, 2.2, 3, INK, None))
    a = _anchors(lx=74, rx=126, ey=100, by=74, mx=100, my=159, nx=100, ny=120,
                 cheeks=((56, 128), (144, 128)), temple=(152, 80), top=42, ears=(40, 160, 100), chin=176,
                 eyes_style="big_round", eye_scale=1.4)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "rabbit")
def _rabbit(skin, look):
    """Long upright ears, a pink twitchy nose, white cheeks."""
    inner = look.get("inner") or PINK
    nose = look.get("nose") or "#E57D8E"
    white = look.get("accent") or _mix(skin, "#FFFFFF", 0.6)
    ear = "M 64 78 C 50 52 52 14 70 10 C 88 8 92 44 88 78 Z"
    ear_in = "M 68 72 C 60 50 61 22 71 19 C 81 18 84 46 81 72 Z"
    face = "M 100 64 C 138 64 158 90 158 122 C 158 156 134 178 100 178 C 66 178 42 156 42 122 C 42 90 62 64 100 64 Z"
    svg = (_pair(ear, skin, INK, 4) + _pair(ear_in, inner, None)
           + _p(face, skin, INK, 5)
           + _e(84, 146, 17, 12, white, None) + _e(116, 146, 17, 12, white, None)
           + _pair("M 70 142 L 42 134 M 70 148 L 44 152", "none", _whisker_ink(skin), 2.5)
           + _p("M 100 142 L 100 148", "none", INK, 3)
           + _p("M 92 133 Q 100 128 108 133 Q 106 140 100 142 Q 94 140 92 133 Z", nose, INK, 3)
           + _c(97, 133, 1.8, "#FFFFFF", None))
    a = _anchors(lx=78, rx=122, ey=114, by=96, mx=100, my=161, nx=100, ny=136,
                 cheeks=((64, 146), (136, 146)), temple=(146, 94), top=64, ears=(62, 138, 59), chin=178,
                 twinkle_x=100, twinkle_y=40)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "cat")
def _cat(skin, look):
    """Triangle ears, cheek ruffs, a small pink nose, whiskers."""
    inner = look.get("inner") or PINK
    nose = look.get("nose") or "#E88A9A"
    ear = "M 46 94 L 38 33 Q 39 26 46 29 L 96 58 Z"
    ear_in = "M 52 86 L 46 44 L 82 63 Z"
    face = ("M 48 88 Q 66 56 100 56 Q 134 56 152 88 Q 164 108 162 126 L 176 136 Q 160 146 150 152 "
            "Q 130 176 100 176 Q 70 176 50 152 Q 40 146 24 136 L 38 126 Q 36 108 48 88 Z")
    svg = (_pair(ear, skin, INK, 4) + _pair(ear_in, inner, None)
           + _p(face, skin, INK, 5)
           + _pair("M 70 136 L 30 128 M 70 142 L 30 144 M 72 148 L 36 158", "none",
                   look.get("whiskers") or _whisker_ink(skin), 2.5)
           + _p("M 92 128 L 108 128 Q 108 132 100 138 Q 92 132 92 128 Z", nose, INK, 3))
    a = _anchors(lx=76, rx=124, ey=104, by=86, mx=100, my=154, nx=100, ny=131,
                 cheeks=((62, 134), (138, 134)), temple=(150, 84), top=56, ears=(42, 158, 77), chin=176,
                 twinkle_x=100, twinkle_y=38)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "basset")
def _basset(skin, look):
    """Long droopy ears, a white blaze and muzzle, heavy jowls, red drooping lower lids: sad at rest."""
    white = look.get("accent") or "#FBF8F2"
    ear_col = look.get("ears") or _shade(skin, 0.68)
    fold = _shade(skin, 0.72)
    ear = "M 60 60 C 34 62 26 98 30 136 C 32 160 40 176 56 174 C 70 172 74 158 72 140 C 70 116 72 88 76 66 Z"
    face = ("M 100 44 C 132 44 148 64 148 96 C 148 128 146 150 136 166 C 126 180 112 184 100 184 "
            "C 88 184 74 180 64 166 C 54 150 52 128 52 96 C 52 64 68 44 100 44 Z")
    blaze = ("M 64 166 C 74 180 88 184 100 184 C 112 184 126 180 136 166 C 142 150 140 126 120 116 "
             "C 108 110 106 80 104 52 Q 100 49 96 52 C 94 80 92 110 80 116 C 60 126 58 150 64 166 Z")
    svg = (_pair(ear, ear_col, INK, 4)
           + _p(face, skin, INK, 5) + _p(blaze, white, None) + _p(face, "none", INK, 5)
           + _p("M 82 66 Q 91 61 100 66 Q 109 61 118 66 M 86 74 Q 100 69 114 74", "none", fold, 2.5)
           + _pair("M 66 114 Q 78 126 90 114 Q 78 120 66 114 Z", "#D98C8C", INK, 2.5)
           + _pair("M 90 138 Q 72 146 72 168 Q 72 176 80 178", "none", INK, 3.5)
           + _p("M 86 126 Q 100 118 114 126 Q 114 136 100 140 Q 86 136 86 126 Z", "#1E1F22", INK, 2.5)
           + _c(94, 126, 2.2, "#FFFFFF", None))
    a = _anchors(lx=78, rx=122, ey=104, by=88, mx=100, my=162, nx=100, ny=130,
                 cheeks=((64, 146), (136, 146)), temple=(142, 80), top=44, ears=(52, 148, 100), chin=184)
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "goat")
def _goat(skin, look):
    """Small curved horns, ears out to the sides, a long face, a chin beard."""
    horn = look.get("horns") or "#C9BC9C"
    beard = look.get("beard") or _shade(skin, 0.86)
    inner = look.get("inner") or PINK
    horn_d = "M 80 58 C 74 44 70 30 58 22 C 76 22 92 36 94 54 Z"
    ear = "M 56 90 C 40 82 20 86 10 98 C 22 108 44 106 58 100 Z"
    ear_in = "M 52 93 C 40 88 26 92 19 98 C 28 103 42 102 52 98 Z"
    face = ("M 100 44 C 134 44 150 66 150 94 C 150 122 140 142 132 158 C 124 172 114 178 100 178 "
            "C 86 178 76 172 68 158 C 60 142 50 122 50 94 C 50 66 66 44 100 44 Z")
    svg = (_pair(horn_d, horn, INK, 4) + _pair("M 72 42 L 81 38 M 66 32 L 74 29", "none", _shade(horn, 0.7), 2.5)
           + _pair(ear, skin, INK, 4) + _pair(ear_in, inner, None)
           + _p(face, skin, INK, 5)
           + _pair("M 90 142 Q 92 136 97 137", "none", INK, 3)
           + _p("M 87 170 C 89 180 95 188 100 193 C 105 188 111 180 113 170 Z", beard, INK, 4)
           + _p("M 96 176 L 97 186 M 104 176 L 103 186", "none", _shade(beard, 0.8), 2.5))
    a = _anchors(lx=76, rx=124, ey=100, by=82, mx=100, my=158, nx=100, ny=138,
                 cheeks=((66, 128), (134, 128)), temple=(146, 78), top=44, ears=(50, 150, 108), chin=178,
                 twinkle_x=100, twinkle_y=26, eyes_style="goat")
    return svg, face, a, _shade(skin, 0.62)


@register(HEADS, "octopus")
def _octopus(skin, look):
    """A mantle head, the face at its base, arms curling out below in place of shoulders."""
    sucker = look.get("suckers") or _mix(skin, "#FFFFFF", 0.62)
    spot = _mix(skin, "#FFFFFF", 0.22)
    # the two outer arms curl up inside the badge; the four in front run down out of it, as shoulders do
    arms = ("M 64 140 C 48 152 36 158 30 147 C 27 139 34 131 40 137",
            "M 76 146 C 66 166 58 180 60 204",
            "M 92 150 C 90 170 86 186 80 206",
            "M 108 150 C 110 170 114 186 120 206",
            "M 124 146 C 134 166 142 180 140 204",
            "M 136 140 C 152 152 164 158 170 147 C 173 139 166 131 160 137")
    tubes = "".join(_p(d, "none", INK, 24) for d in arms) + "".join(_p(d, "none", skin, 16) for d in arms)
    suckers = "".join(_c(x, y, r, sucker, _shade(skin, 0.62), 1.5) for x, y, r in (
        (42, 153, 3), (32, 146, 2.5), (158, 153, 3), (168, 146, 2.5), (62, 182, 3), (61, 194, 2.5),
        (138, 182, 3), (139, 194, 2.5), (86, 184, 3), (83, 196, 2.5), (114, 184, 3), (117, 196, 2.5)))
    face = ("M 100 16 C 150 16 172 56 168 96 C 166 124 150 142 128 150 C 116 154 84 154 72 150 "
            "C 50 142 34 124 32 96 C 28 56 50 16 100 16 Z")
    svg = (tubes + suckers + _p(face, skin, INK, 5)
           + "".join(_c(x, y, r, spot, None) for x, y, r in ((70, 44, 6), (124, 36, 4), (142, 64, 5), (58, 74, 3.5), (100, 28, 3))))
    a = _anchors(lx=72, rx=128, ey=106, by=86, mx=100, my=134, nx=100, ny=122,
                 cheeks=((58, 126), (142, 126)), temple=(152, 78), top=16, ears=(36, 164, 100), chin=152,
                 twinkle_x=136, twinkle_y=26)
    return svg, face, a, _shade(skin, 0.62)


# ---------------------------------------------------------------- eyes
def _scaled_eyes(e, a, light, marks, sx, sy):
    """The kit's own eyes for every emotion, scaled about their centers (the centers stay put)."""
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    cx = (lx + rx) / 2.0
    inner = dict(a, lx=cx + (lx - cx) / sx, rx=cx + (rx - cx) / sx)
    return '<g transform="translate(%.1f %.1f) scale(%.2f %.2f) translate(%.1f %.1f)">%s</g>' % (
        cx, y, sx, sy, -cx, -y, _eyes(e, inner, light, marks))


@register(EYES, "big_round")
def _big_round(e, a, light, marks=()):
    """Big eyes (a seal's, an owl's): the kit's eyes drawn a["eye_scale"] times larger."""
    s = a.get("eye_scale", 1.35)
    return _scaled_eyes(e, a, light, marks, s, s)


@register(EYES, "goat")
def _goat_eyes(e, a, light, marks=()):
    """A goat's eyes: the kit's eyes drawn wide and short, so the pupils lie horizontal."""
    return _scaled_eyes(e, a, light, marks, 1.3, 0.72)


# ---------------------------------------------------------------- the beak
# emotion: (lower mandible drops by, tilt in degrees, left corner dy, right corner dy, crease)
_BEAK = {
    "neutral":    (0, 0, 0, 0, None),
    "happy":      (12, 0, -4, -4, "up"),
    "sad":        (0, 0, 4, 4, "down"),
    "angry":      (12, 0, 3, 3, "down"),
    "jealous":    (0, -9, 3, 0, "down_l"),
    "worried":    (6, 0, 3, 3, "down"),
    "relieved":   (0, 0, -2, -2, "up"),
    "thinking":   (0, 8, 0, -2, None),
    "surprised":  (18, 0, 0, 0, None),
    "smug":       (0, 11, 1, -4, "up_r"),
    "determined": (4, 0, -3, -3, "up"),          # a confident grin, just parted (the kit's own determined mouth)
    "confused":   (0, -13, -2, 3, None),
}


@register(MOUTHS, "beak")
def _beak(e, a, fill, marks=()):
    """A beak for a mouth: upper and lower mandibles meeting at the gape (anchor my)."""
    o, tilt, dl, dr, crease = _BEAK.get(e, _BEAK["neutral"])
    if e == "neutral" and "press" in marks:
        crease = "flat"
    if e in ("neutral", "thinking") and "smirk" in marks:
        tilt, dr, crease = 6, -4, "up_r"
    x, g = a["mx"], a["my"]
    top = a.get("beak_top", g - 12)
    tip = a.get("beak_tip", g + 10)
    w = a.get("beak_w", 12)
    low = a.get("beak_low", 10)
    col = a.get("beak_fill", "#E6B95B")
    under = a.get("beak_under", _shade(col, 0.82))
    ink = a.get("beak_crease", INK)
    xl, yl, xr, yr = x - w, g + dl, x + w, g + dr
    blend = a.get("beak_blend")
    k = a.get("beak_hook", 0.5)                 # how the gape runs to the tip: 0.5 a straight V, less a flat edge and a hook
    # open, the upper mandible tips up (its hook no longer hides the mouth) and the lower one drops by o
    tu = g + (tip - g) * 0.35 + 1 if o else tip
    bot = tu + o + low * 0.7 if o else g + low  # the lower mandible's point

    def through(y_mid):                         # the control point that carries a corner-to-corner curve through y_mid
        return 2 * y_mid - (yl + yr) / 2.0
    out = [_p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (xl + 2, yl, x, through(bot), xr - 2, yr), under,
              _shade(under, 0.62) if blend else INK, 2.5 if blend else 3.5)]
    if o:                                       # the mouth inside
        out.append(_p("M %.1f %.1f Q %.1f %.1f %.1f %.1f Z" % (xl + 2, yl, x, through(tu + o), xr - 2, yr), fill, INK, 3))
        if e == "happy":
            out.append(_e(x, tu + o * 0.62, w * 0.42, o * 0.26, "#E27A7A", None))
    upper = "M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f" % (
        xl, yl, xl + w * 0.1, top, x, top, xr - w * 0.1, top, xr, yr)
    gape = "Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x + w * 0.3, yr + (tu - yr) * k, x, tu,
                                                          x - w * 0.3, yl + (tu - yl) * k, xl, yl)
    if blend:                                   # a beak that is the face's own edge (a tortoise): no outline on top
        out.append(_p(upper + " " + gape + " Z", col, None))
        out.append(_p("M %.1f %.1f %s" % (xr, yr, gape), "none", INK, 4))
    else:
        out.append(_p(upper + " " + gape + " Z", col, INK, 3.5))
        out.append(_p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - w * 0.35, top + 4, x, top + 1, x + w * 0.35, top + 4),
                      "none", "#FFFFFF", 2.5, ' opacity="0.45"'))
    c = []
    if crease in ("up", "up_r"):
        c += [(xr, yr, 1, -1)] + ([(xl, yl, -1, -1)] if crease == "up" else [])
    if crease in ("down", "down_l"):
        c += [(xl, yl, -1, 1)] + ([(xr, yr, 1, 1)] if crease == "down" else [])
    for cx, cy, sx, sy in c:
        out.append(_p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (cx + sx * 2, cy, cx + sx * 8, cy, cx + sx * 11, cy + sy * 7),
                      "none", ink, 3.5))
    if crease == "flat":
        out.append(_p("M %.1f %.1f L %.1f %.1f M %.1f %.1f L %.1f %.1f" % (xl - 2, yl, xl - 10, yl + 2, xr + 2, yr, xr + 10, yr + 2),
                      "none", ink, 3.5))
    body = "".join(out)
    return ('<g transform="rotate(%d %.1f %.1f)">%s</g>' % (tilt, x, top, body)) if tilt else body


# ---------------------------------------------------------------- face parts
@register(FACE_PARTS, "beak_glasses")
def _beak_glasses(part, a, skin):
    """Small round spectacles on a beak: the bridge rides the top of the beak, the arms run back."""
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    r = part.get("r") or a.get("lens_r", 16)
    fr = part.get("color", "#8C6A2E")
    L, R, _ = a["ears"]
    cx = (lx + rx) / 2.0
    if a.get("beak_top", 999) - y <= r:         # a bird's beak starts between the eyes: the bridge rides it
        bridge = "M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (lx + r * 0.9, y + r * 0.35, cx, a["beak_top"] - 1, rx - r * 0.9, y + r * 0.35)
    else:                                       # no beak up there: an ordinary bridge between the lenses
        bridge = "M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (lx + r, y - 2, cx, y - 8, rx - r, y - 2)
    return (_c(lx, y, r, "#FFFFFF", fr, 3.5, ' fill-opacity="0.18"') + _c(rx, y, r, "#FFFFFF", fr, 3.5, ' fill-opacity="0.18"')
            + _p(bridge, "none", fr, 3.5)
            + _p("M %.1f %.1f L %d %.1f M %.1f %.1f L %d %.1f" % (lx - r, y - 2, L + 2, y - 6, rx + r, y - 2, R - 2, y - 6),
                 "none", fr, 3))


# ==================================================================================================
# Machines for the face kit: robot heads, and the eye and mouth styles that let an emotion read on
# a visor, a screen or a painted face.
#
#     look = {"badge": "#CFD8DC", "head": "robot_box", "skin": "#E2A82B", "glow": "#8FF3FF",
#             "body": {"part": "chassis"}}
#
# Heads (skin is the paint, the porcelain or the cabinet; the look keys each one reads are listed):
#   robot_box   a boxy industrial welding robot: glowing eyes and LED brows behind a welding visor on
#               hinge knobs, a mouth lit behind a grille, bolts, a stubby antenna.
#               glow: the lit color; screen: the welding glass
#   robot_dome  an android nanny: a porcelain dome, painted doll eyes with lashes, a small painted mouth,
#               a bun-like knob on top, ear discs; the kit's own brows, so give it thin ones.
#               accent: knob ring, ear discs, neck joint; iris; paint: the lips. The lashes are painted
#               on, so the lashes face part would draw a second set.
#   robot_vac   a robot vacuum seen from just above the front: a disc, a bumper with a dark sensor window
#               where the eyes glow, a small LED mouth, a status light on top, side brushes.
#               glow; screen: the sensor window; bumper
#   vending     a vending machine: a dot-matrix display carries the face, a product window, a coin slot,
#               a pickup flap. glow: the display's dots; screen: the display
#
# EYES styles (signature (emotion, anchors, light, marks)):
#   glow     lit shapes on dark glass: bars, lid cuts, arcs, rings with a pupil; LED brows when the head
#            sets anchors["led_brows"]
#   painted  a doll's painted eyes: big glossy irises (anchors["iris"]), a lid line, painted lashes
#   pixel    a dot-matrix face on a display grid: eyes, and pixel brows over them
# MOUTHS styles (signature (emotion, anchors, fill, marks)):
#   grille   a lit mouth behind the slats of a grille (anchors["grille"] = its box)
#   glow     a small lit mouth (anchors["mouth_scale"])
#   painted  a small painted doll's mouth (anchors["paint"])
#   pixel    a dot-matrix mouth on the same grid as the pixel eyes
#
# The styles read their colors and geometry from the anchors, so a look can retune them through
# look["anchors"] (e.g. {"eye_w": 20}) and any other head can use them.
#
# Marks on machines: led turns every lit part amber (a painted iris too, and the vacuum's status light);
# static puts broken scan lines on the glass (the display's are drawn by the pixel mouth, the last thing
# drawn on it); glitch tears the lit features sideways, over the kit's own bars; twitch flickers in the
# glow color, since ink would vanish on dark glass; glance, blink, brow_up, knit, press and smirk move
# the lit features the way they move a face's. Everything else is the kit's.
# ==================================================================================================

AMBER = "#FFB23F"          # the "led" mark: every lit part flicks amber
GLITCH = ("#FF4FD8", "#3FE0FF")


# ---------------------------------------------------------------- geometry helpers
def _rr(x0, y0, x1, y1, r):
    """A rounded rectangle's path."""
    return ("M %.1f %.1f H %.1f A %.1f %.1f 0 0 1 %.1f %.1f V %.1f A %.1f %.1f 0 0 1 %.1f %.1f H %.1f "
            "A %.1f %.1f 0 0 1 %.1f %.1f V %.1f A %.1f %.1f 0 0 1 %.1f %.1f Z" % (
                x0 + r, y0, x1 - r, r, r, x1, y0 + r, y1 - r, r, r, x1 - r, y1, x0 + r, r, r, x0, y1 - r,
                y0 + r, r, r, x0 + r, y0))


def _rr_pts(cx, cy, w, h, r, n=5):
    """Points around a rounded rectangle, clockwise on screen."""
    r = min(r, w / 2.0, h / 2.0)
    pts = []
    for ox, oy, a0 in ((cx - w / 2 + r, cy - h / 2 + r, 180), (cx + w / 2 - r, cy - h / 2 + r, 270),
                       (cx + w / 2 - r, cy + h / 2 - r, 0), (cx - w / 2 + r, cy + h / 2 - r, 90)):
        for i in range(n + 1):
            t = math.radians(a0 + 90.0 * i / n)
            pts.append((ox + r * math.cos(t), oy + r * math.sin(t)))
    return pts


def _ell_pts(cx, cy, rx, ry, n=40):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _cut(pts, A, B, C):
    """The part of a convex polygon where A*x + B*y + C <= 0."""
    out, n = [], len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        fp, fq = A * p[0] + B * p[1] + C, A * q[0] + B * q[1] + C
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _below(pts, p, q):
    """Keep what lies below the line through p and q (screen y grows downward)."""
    (x1, y1), (x2, y2) = sorted((p, q))
    k = (y2 - y1) / float(x2 - x1)
    return _cut(pts, k, -1.0, y1 - k * x1)


def _above(pts, p, q):
    (x1, y1), (x2, y2) = sorted((p, q))
    k = (y2 - y1) / float(x2 - x1)
    return _cut(pts, -k, 1.0, k * x1 - y1)


def _poly(pts):
    return ("M " + " L ".join("%.1f %.1f" % p for p in pts) + " Z") if len(pts) > 2 else ""


def _line_y(p, q, x):
    (x1, y1), (x2, y2) = p, q
    return y1 + (y2 - y1) * (x - x1) / float(x2 - x1)


# ---------------------------------------------------------------- light
def _lit(a, marks):
    return AMBER if "led" in marks else a.get("glow", "#8FF3FF")


def _halo(d, col, w):
    return _p(d, "none", col, w, ' opacity="0.32"')


def _lit_fill(d, col):
    return (_halo(d, col, 6) + _p(d, col, None)) if d else ""


def _lit_line(d, col, w=5.0):
    return _halo(d, col, w + 6) + _p(d, "none", col, w)


def _twitch(a, col):
    """The kit's twitch, in light: ink would vanish on dark glass."""
    x, y = a["lx"] - 17, a["ey"]
    return _p("M %d %d Q %d %d %d %d M %d %d Q %d %d %d %d" % (x, y - 7, x - 4, y - 3, x, y + 1,
                                                                x - 5, y - 9, x - 10, y - 3, x - 5, y + 3),
              "none", col, 2)


def _static(a):
    """Broken scan lines and specks across the glass (the static mark on a screen)."""
    box = a.get("screen_box")
    if not box:
        return ""
    x0, y0, x1, y1 = box
    rows = (((.02, .31), (.39, .56), (.64, .97)), ((.05, .19), (.27, .71), (.79, .95)),
            ((0, .43), (.51, .6), (.68, 1)), ((.1, .36), (.46, .86)), ((0, .22), (.3, .5), (.58, .93)))
    w, h = x1 - x0, y1 - y0
    out = ""
    for i, segs in enumerate(rows):
        y = y0 + h * (i + .7) / (len(rows) + .4)
        d = " ".join("M %.1f %.1f L %.1f %.1f" % (x0 + w * s, y, x0 + w * e, y) for s, e in segs)
        out += _p(d, "none", "#FFFFFF", 1.6, ' opacity="0.55"')
    specks = ((.12, .24), (.3, .6), (.57, .12), (.72, .44), (.88, .78), (.45, .9), (.2, .83), (.93, .3))
    out += "".join('<rect x="%.1f" y="%.1f" width="3" height="2" fill="#FFFFFF" opacity="0.7"/>'
                   % (x0 + w * u - 1.5, y0 + h * v - 1) for u, v in specks)
    return out


# ---------------------------------------------------------------- EYES: glow
# LED brows: (outer, inner) rise of the left brow's ends (negative is up); a second pair is the right
# brow when the two differ (the right's are given outer, inner too).
LED_BROWS = {
    "neutral": ((0, 0),), "happy": ((-3, -3),), "sad": ((4, -5),), "angry": ((-4, 5),),
    "jealous": ((3, 4), (-7, -2)), "worried": ((2, -7),), "relieved": ((-1, -3),),
    "thinking": ((2, 2), (-8, -4)), "surprised": ((-7, -7),), "smug": ((2, 2), (-6, -5)),
    "determined": ((0, 1),), "confused": ((-7, -7), (-1, 5)),        # determined: level, focused -- never angry
}


def _led_brows(e, a, col, marks):
    lx, rx, b = a["lx"], a["rx"], a["by"]
    hl = a.get("brow_half", 9)
    spec = LED_BROWS[e]
    left, right = spec[0], spec[-1]
    d = ""
    for x, side, (o, i) in ((lx, -1, left), (rx, 1, right)):
        if "brow_up" in marks and side == 1:
            o, i = o - 5, i - 5
        knit = 2 if "knit" in marks else 0      # the inner ends drawn down and together
        if knit:
            i += 3
        d += "M %.1f %.1f L %.1f %.1f " % (x + side * hl, b + o, x - side * (hl + knit), b + i)
    return _lit_line(d.strip(), col, 4.5)


def _glow_eye(e, x, y, w, h, side, col, marks, gx):
    """One lit eye; side is -1 for the left eye, +1 for the right (inner = toward the middle)."""
    def blob(t_out=0.0, t_in=0.0, b=0.0, dx=0.0, dy=0.0, sw=1.0, sh=1.0, lr=None):
        W, H = w * sw, h * sh
        cx, cy = x + gx + dx, y + dy
        pts = _rr_pts(cx, cy, W, H, min(W, H) * 0.34)
        xo, xi, top = cx + side * W / 2, cx - side * W / 2, cy - H / 2
        if lr:                                   # a lid given left / right, not outer / inner
            pts = _below(pts, (cx - W / 2, top + lr[0] * H), (cx + W / 2, top + lr[1] * H))
        elif t_out or t_in:
            pts = _below(pts, (xo, top + t_out * H), (xi, top + t_in * H))
        if b:
            bot = cy + H / 2 - b * H
            pts = _above(pts, (cx - W, bot), (cx + W, bot))
        return _lit_fill(_poly(pts), col)

    def ring(r, px=0.0, py=0.0, pr=3.5, dx=0.0):
        cx = x + gx + dx
        out = _halo("M %.1f %.1f A %.1f %.1f 0 1 0 %.1f %.1f A %.1f %.1f 0 1 0 %.1f %.1f Z"
                    % (cx - r, y, r, r, cx + r, y, r, r, cx - r, y), col, 10)
        out += _c(cx, y, r, "none", col, 4)
        return out + (_c(cx + px, y + py, pr, col, None) if pr else "")

    def arc(up=True):
        cx = x + gx
        d = ("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (cx - w / 2, y + 4, cx, y - h * 0.72, cx + w / 2, y + 4) if up
             else "M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (cx - w / 2, y - 3, cx, y + h * 0.62, cx + w / 2, y - 3))
        return _lit_line(d, col, 5.5)

    knit = 0.16 if "knit" in marks else 0.0
    up = -3 if ("brow_up" in marks and side == 1) else 0
    if e == "neutral":
        return blob(t_in=knit, dy=up)
    if e == "happy":
        return arc(True)
    if e == "sad":
        return blob(t_out=0.44, t_in=0.06, dy=2 + up, sh=0.92)
    if e == "angry":
        return blob(t_in=0.52, dy=up)
    if e == "jealous":                          # half-lidded, both glancing the same way
        return blob(lr=(0.44, 0.56), dx=3, dy=1 + up)
    if e == "worried":
        return ring(min(w, h) * 0.46, 0, 2, 3.5)
    if e == "relieved":
        return arc(False)
    if e == "thinking":
        return ring(min(w, h) * 0.46, 3.2, -3.2, 3.6)
    if e == "surprised":
        return ring(min(w, h) * 0.6, 0, 0, 2.6)
    if e == "smug":
        return blob(lr=(0.46, 0.56), dy=2 + up)
    if e == "determined":                       # narrowed and focused, the lids dipping a touch to the middle
        return blob(t_out=0.36, t_in=0.46 + knit, dy=1 + up, sh=0.95)
    if e == "confused":
        return ring(min(w, h) * 0.5, -1, 0, 3.8) if side < 0 else blob(lr=(0.62, 0.62), b=0.1, dy=up)
    return blob()


@register(EYES, "glow")
def _eyes_glow(e, a, light, marks=()):
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    w, h = a.get("eye_w", 18), a.get("eye_h", 22)
    col = _lit(a, marks)
    gx = -4 if "glance" in marks else 0
    out = _led_brows(e, a, col, marks) if a.get("led_brows") else ""
    if "blink" in marks:                         # caught mid-blink: two thin lit lines
        out += "".join(_lit_line("M %.1f %.1f L %.1f %.1f" % (x - w / 2 + 2, y + 3, x + w / 2 - 2, y + 3), col, 4)
                       for x in (lx, rx))
    else:
        eyes = _glow_eye(e, lx, y, w, h, -1, col, marks, gx) + _glow_eye(e, rx, y, w, h, 1, col, marks, gx)
        if "glitch" in marks:                    # the picture tears: a displaced ghost of each eye
            out += ('<g transform="translate(-4 1)" opacity="0.6">%s</g>'
                    % (_glow_eye(e, lx, y, w, h, -1, GLITCH[0], (), gx) + _glow_eye(e, rx, y, w, h, 1, GLITCH[0], (), gx)))
            out += ('<g transform="translate(4 -1)" opacity="0.6">%s</g>'
                    % (_glow_eye(e, lx, y, w, h, -1, GLITCH[1], (), gx) + _glow_eye(e, rx, y, w, h, 1, GLITCH[1], (), gx)))
        out += eyes
    if "twitch" in marks:
        out += _twitch(a, col)
    if "led" in marks and a.get("status"):      # a status light elsewhere on the head flicks amber too
        sx, sy = a["status"]
        out += _halo("M %.1f %.1f h 12" % (sx - 6, sy), AMBER, 8) + _e(sx, sy, 6, 2.2, AMBER, None)
    if "static" in marks:
        out += _static(a)
    return out


# ---------------------------------------------------------------- MOUTHS: lit shapes, grille
def _lit_mouth(e, x, y, s, col, marks):
    """A lit mouth's shape at scale s (1.0 fits a 52 x 20 grille)."""
    def L(fmt, *xy):                            # xy: alternating x, y offsets in the unit frame
        return fmt % tuple((x if i % 2 == 0 else y) + s * v for i, v in enumerate(xy))
    w = max(3.0, 5.8 * s ** 0.5)
    if e == "neutral" and "press" in marks:
        return _lit_line(L("M %.1f %.1f L %.1f %.1f", -8, 0, 8, 0), col, w * 1.4)
    if e in ("neutral", "thinking") and "smirk" in marks:
        return _lit_line(L("M %.1f %.1f L %.1f %.1f Q %.1f %.1f %.1f %.1f", -13, 1, 5, 1, 10, 1, 14, -5), col, w)
    if e == "neutral":
        return _lit_line(L("M %.1f %.1f L %.1f %.1f", -13, 0, 13, 0), col, w)
    if e == "happy":
        return _lit_fill(L("M %.1f %.1f Q %.1f %.1f %.1f %.1f Z", -17, -5, 0, 17, 17, -5), col)
    if e == "sad":
        return _lit_line(L("M %.1f %.1f Q %.1f %.1f %.1f %.1f", -14, 6, 0, -11, 14, 6), col, w)
    if e == "angry":                            # a snarl of jagged light
        return _lit_line(L("M %.1f %.1f L %.1f %.1f L %.1f %.1f L %.1f %.1f L %.1f %.1f L %.1f %.1f L %.1f %.1f",
                           -17, 4, -11, -4, -5, 4, 0, -4, 5, 4, 11, -4, 17, 4), col, w * 0.9)
    if e == "jealous":
        return _lit_line(L("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f", -13, 3, -5, -4, 2, 1, 9, 5, 15, -1),
                         col, w)
    if e == "worried":
        return _lit_line(L("M %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f",
                           -16, 2, -11, -6, -5, 1, 0, 7, 5, 1, 11, -6, 16, 2), col, w * 0.9)
    if e == "relieved":
        return _lit_line(L("M %.1f %.1f Q %.1f %.1f %.1f %.1f", -13, -2, 0, 10, 13, -2), col, w)
    if e == "thinking":
        return _lit_line(L("M %.1f %.1f Q %.1f %.1f %.1f %.1f", -2, 2, 7, -1, 15, 0), col, w)
    if e == "surprised":
        cx, cy, rx_, ry_ = x, y, 7.5 * s, 7.5 * s
        return (_halo("M %.1f %.1f A %.1f %.1f 0 1 0 %.1f %.1f A %.1f %.1f 0 1 0 %.1f %.1f Z"
                      % (cx - rx_, cy, rx_, ry_, cx + rx_, cy, rx_, ry_, cx - rx_, cy), col, w + 6)
                + _e(cx, cy, rx_, ry_, "none", col, w * 0.9))
    if e == "smug":
        return _lit_line(L("M %.1f %.1f Q %.1f %.1f %.1f %.1f", -14, 2, 2, 9, 16, -7), col, w)
    if e == "determined":                       # a confident grin: corners up, a line of teeth (never a grimace)
        return (_lit_line(L("M %.1f %.1f L %.1f %.1f Q %.1f %.1f %.1f %.1f Q %.1f %.1f %.1f %.1f Z", -15, -3, 15, -3, 14, 8, 0, 9,
                            -14, 8, -15, -3), col, w)
                + _lit_line(L("M %.1f %.1f L %.1f %.1f", -12, 2, 12, 2), col, w * 0.55))
    if e == "confused":
        return _lit_line(L("M %.1f %.1f L %.1f %.1f", -13, 5, 13, -3), col, w)
    return ""


@register(MOUTHS, "grille")
def _mouth_grille(e, a, fill, marks=()):
    """A mouth lit behind the slats of a grille (anchors["grille"] = x0, y0, x1, y1 of the box)."""
    x0, y0, x1, y1 = a.get("grille") or (a["mx"] - 26, a["my"] - 10, a["mx"] + 26, a["my"] + 10)
    col = _lit(a, marks)
    out = "" if a.get("grille") else _p(_rr(x0, y0, x1, y1, 5), "#22262A", None)   # a head with a grille draws its box
    out += _lit_mouth(e, a["mx"] - (4 if "glitch" in marks else 0), a["my"], a.get("mouth_scale", 1.0), col, marks)
    bar, step = a.get("grille_bar", "#3A3F45"), 6.5
    n = int((x1 - x0 - 8) // step)
    xs = [x0 + (x1 - x0) / 2.0 + step * (i - n / 2.0) for i in range(n + 1)]
    out += _p(" ".join("M %.1f %.1f L %.1f %.1f" % (x, y0 + 1, x, y1 - 1) for x in xs), "none", bar, 1.6,
              ' opacity="0.9"')
    return out + _p(_rr(x0, y0, x1, y1, 5), "none", INK, 3.5)


@register(MOUTHS, "glow")
def _mouth_glow(e, a, fill, marks=()):
    col = _lit(a, marks)
    return _lit_mouth(e, a["mx"] - (3 if "glitch" in marks else 0), a["my"], a.get("mouth_scale", 0.6), col, marks)


# ---------------------------------------------------------------- EYES / MOUTHS: painted
def _lashes(p, side, dy=-1):
    """Three painted lashes flicking out from the lid's outer end p (dy=-1 up, +1 down)."""
    x, y = p
    s = side
    return _p("M %.1f %.1f L %.1f %.1f M %.1f %.1f L %.1f %.1f M %.1f %.1f L %.1f %.1f" % (
        x, y, x + s * 7, y + dy * 3, x - s * 2.5, y + dy * 2.5, x + s * 3, y + dy * 8.5,
        x - s * 6.5, y + dy * 4, x - s * 3.5, y + dy * 10), "none", INK, 2.6)


def _painted_eye(e, x, y, side, iris, gx, marks):
    lit = "led" in marks
    wide = e in ("worried", "thinking", "surprised") or (e == "confused" and side < 0)
    if e in ("happy", "relieved"):
        up = e == "happy"
        d = ("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - 10, y + 3, x, y - 11, x + 10, y + 3) if up
             else "M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - 10, y - 2, x, y + 9, x + 10, y - 2))
        end = (x + side * 10, y + (3 if up else -2))
        return _p(d, "none", INK, 4.5) + _lashes(end, side, -1 if up else 1)
    rx_, ry_ = (9.0, 11.5)
    cx, cy = x + gx, y
    lid = None                                  # (left y, right y) of the upper lid line
    bottom = None
    if e == "sad":
        lid, cy = ((y - 2, y - 9) if side < 0 else (y - 9, y - 2)), y + 1
    elif e == "angry":
        lid = (y - 10, y - 2) if side < 0 else (y - 2, y - 10)
    elif e == "jealous":
        lid, cx = (y - 1, y - 5), cx + 3
    elif e == "smug":
        lid, cy = (y - 1, y + 1), y + 2
    elif e == "determined":                     # narrowed, the lids dipping a touch toward the nose
        lid, bottom = ((y - 3, y) if side < 0 else (y, y - 3)), y + 8
    elif e == "confused" and side > 0:
        lid, bottom = (y, y), y + 6
    if wide:                                    # the white shows: wide eyes, a smaller iris
        big = 1.2 if e == "surprised" else 1.0
        sx, sy = 10 * big, 12 * big
        ir = 4.4 if e == "surprised" else 5.4
        px, py = {"thinking": (3.5, -3.5), "worried": (0, 1.5)}.get(e, (0, 0))
        px += gx
        out = _e(x, y, sx, sy, "#FFFFFF", INK, 3)
        out += _c(x + px, y + py, ir, AMBER if lit else iris, None) + _c(x + px, y + py, ir * 0.5, _shade(iris, 0.45), None)
        out += _c(x + px + 1.6, y + py - 1.8, 1.5, "#FFFFFF", None)
        top = (x + side * sx * 0.72, y - sy * 0.69)
        return out + _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (x - sx * 0.98, y - 2, x, y - sy * 1.28, x + sx * 0.98, y - 2),
                        "none", INK, 3.5) + _lashes(top, side)
    pts = _ell_pts(cx, cy, rx_, ry_)
    pupil = _ell_pts(cx, cy + 1, 4.2, 5.2, 24)
    if lid:
        pts = _below(pts, (cx - 12, lid[0]), (cx + 12, lid[1]))
        pupil = _below(pupil, (cx - 12, lid[0]), (cx + 12, lid[1]))
    if bottom:
        pts = _above(pts, (cx - 12, bottom), (cx + 12, bottom))
        pupil = _above(pupil, (cx - 12, bottom), (cx + 12, bottom))
    col = AMBER if lit else iris
    out = (_halo(_poly(pts), AMBER, 6) if lit else "") + _p(_poly(pts), col, INK, 2.5)
    if len(pupil) > 2:
        out += _p(_poly(pupil), _shade(col, 0.45), None)
    for hx, hy, hr in ((cx + 3, cy - 4, 3.0), (cx - 3, cy + 4.5, 1.4)):
        if not lid or hy - hr > _line_y((cx - 12, lid[0]), (cx + 12, lid[1]), hx):
            if not bottom or hy + hr < bottom:
                out += _c(hx, hy, hr, "#FFFFFF", None)
    if lid:
        l, r = (cx - 12, lid[0]), (cx + 12, lid[1])
        cut = [p for p in pts if abs(p[1] - _line_y(l, r, p[0])) < 0.01]    # the lid line's two ends
        a0, a1 = (min(cut), max(cut)) if len(cut) >= 2 else (l, r)
        ext = 2.5
        k = (r[1] - l[1]) / 24.0
        a0, a1 = (a0[0] - ext, a0[1] - ext * k), (a1[0] + ext, a1[1] + ext * k)
        out += _p("M %.1f %.1f L %.1f %.1f" % (a0 + a1), "none", INK, 3.5)
        out += _lashes(a0 if side < 0 else a1, side)
    else:
        out += _p("M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (cx - rx_ - 1.5, cy - 2, cx, cy - ry_ * 1.42, cx + rx_ + 1.5, cy - 2),
                  "none", INK, 3.5)
        out += _lashes((cx + side * (rx_ * 0.72), cy - ry_ * 0.7), side)
    if bottom:
        out += _p("M %.1f %.1f L %.1f %.1f" % (cx - 9, bottom, cx + 9, bottom), "none", INK, 3)
    return out


@register(EYES, "painted")
def _eyes_painted(e, a, light, marks=()):
    lx, rx, y = a["lx"], a["rx"], a["ey"]
    iris = a.get("iris", "#34466E")
    gx = -3 if "glance" in marks else 0
    if "blink" in marks:                         # lids down, lashes fluttering
        return "".join(_p("M %d %d Q %d %d %d %d" % (x - 10, y + 1, x, y + 7, x + 10, y + 1), "none", INK, 4.5)
                       + _lashes((x + s * 10, y + 1), s, 1) for x, s in ((lx, -1), (rx, 1)))
    out = _painted_eye(e, lx, y, -1, iris, gx, marks) + _painted_eye(e, rx, y, 1, iris, gx, marks)
    if "glitch" in marks:                        # a hairline crack of light through the paint
        out += _p("M %d %d L %d %d L %d %d L %d %d" % (rx + 4, y - 16, rx - 2, y - 6, rx + 5, y + 2, rx - 1, y + 14),
                  "none", "#39D98A", 2)
    return out


@register(MOUTHS, "painted")
def _mouth_painted(e, a, fill, marks=()):
    """A small painted doll's mouth: a rosebud at rest."""
    x, y = a["mx"], a["my"]
    paint = a.get("paint", "#C84B64")
    lip, inside = _shade(paint, 0.72), _shade(paint, 0.5)
    if e == "neutral" and "press" in marks:
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 7, y, x, y - 2, x + 7, y, x, y + 2, x - 7, y), paint, INK, 2.5)
    if e in ("neutral", "thinking") and "smirk" in marks:
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 7, y + 1, x - 2, y - 2, x + 2, y - 1,
                  x + 6, y - 4, x + 10, y - 4, x + 2, y + 5, x - 7, y + 1), paint, INK, 2.5)
    if e == "neutral":                          # a closed rosebud
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 8, y, x - 4, y - 5, x, y - 2,
                  x + 4, y - 5, x + 8, y, x, y + 6, x - 8, y), paint, INK, 2.5)
    if e == "happy":
        return (_p("M %d %d Q %d %d %d %d Z" % (x - 12, y - 3, x, y + 16, x + 12, y - 3), inside, INK, 3)
                + _e(x, y + 4, 5, 2.6, paint, None))
    if e == "sad":
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 9, y + 5, x, y - 6, x + 9, y + 5, x, y + 1, x - 9, y + 5),
                  paint, INK, 2.5)
    if e == "angry":
        return _p("M %d %d L %d %d Q %d %d %d %d L %d %d Q %d %d %d %d Z" % (x - 10, y + 6, x - 7, y - 2, x, y - 6,
                  x + 7, y - 2, x + 10, y + 6, x, y + 3, x - 10, y + 6), inside, INK, 3)
    if e == "jealous":
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 6, y + 2, x - 1, y - 2, x + 3, y,
                  x + 7, y - 1, x + 10, y + 2, x + 2, y + 6, x - 6, y + 2), paint, INK, 2.5)
    if e == "worried":
        return _p("M %d %d Q %d %d %d %d Q %d %d %d %d Q %d %d %d %d" % (x - 10, y + 2, x - 6, y - 3, x - 3, y + 1,
                  x, y + 5, x + 3, y + 1, x + 6, y - 3, x + 10, y + 2), "none", lip, 3.5)
    if e == "relieved":
        return _p("M %d %d Q %d %d %d %d" % (x - 9, y - 1, x, y + 6, x + 9, y - 1), "none", lip, 3.5)
    if e == "thinking":
        return _e(x + 5, y + 1, 4, 3, paint, INK, 2.2)
    if e == "surprised":
        return _e(x, y + 2, 5, 7, inside, INK, 3)
    if e == "smug":
        return _p("M %d %d Q %d %d %d %d" % (x - 9, y + 1, x + 1, y + 5, x + 11, y - 4), "none", lip, 3.5)
    if e == "determined":                       # a small confident grin, teeth showing
        return (_p("M %d %d L %d %d Q %d %d %d %d Q %d %d %d %d Z" % (x - 10, y - 2, x + 10, y - 2, x + 9, y + 5, x, y + 6,
                                                                      x - 9, y + 5, x - 10, y - 2), "#FFFFFF", INK, 2.5)
                + _p("M %d %d L %d %d" % (x - 9, y + 1, x + 9, y + 1), "none", INK, 1.5))
    if e == "confused":
        return _p("M %d %d L %d %d" % (x - 8, y + 3, x + 8, y - 2), "none", lip, 3.5)
    return ""


# ---------------------------------------------------------------- EYES / MOUTHS: pixel (dot matrix)
# Grids are drawn for the LEFT eye ('#' lit); the right eye is the mirror image.
PX_EYES = {
    "neutral":    (".###.", "#####", "#####", "#####", ".###."),
    "happy":      (".....", ".###.", "##.##", "#...#", "....."),
    "sad":        (".....", "..###", ".####", "#####", ".###."),
    "angry":      ("#....", "###..", "####.", "#####", ".###."),
    "jealous":    (".....", "#####", "#..##", "#..##", ".###."),
    "worried":    (".###.", "#...#", "#.#.#", "#...#", ".###."),
    "relieved":   (".....", "#...#", "##.##", ".###.", "....."),
    "thinking":   (".###.", "#..##", "#..##", "#...#", ".###."),
    "surprised":  ("..###..", ".#...#.", "#.....#", "#.....#", "#.....#", ".#...#.", "..###.."),
    "smug":       (".....", ".....", "#####", "#####", ".###."),
    "determined": (".....", ".....", "#####", "#####", "#####"),     # narrowed: the top rows dark
    "confused":   (".###.", "#...#", "#...#", "#...#", ".###."),
}
PX_CONFUSED_RIGHT = (".....", ".....", "#####", ".....", ".....")
PX_BLINK = (".....", ".....", ".....", "#####", ".....")
# Brows: (outer row, inner row) in a 4-row band over each eye, 0 the highest; a second pair is the
# right brow's.
PX_BROWS = {
    "neutral": ((2, 2),), "happy": ((1, 1),), "sad": ((3, 1),), "angry": ((1, 3),),
    "jealous": ((3, 3), (1, 2)), "worried": ((2, 0),), "relieved": ((2, 1),), "thinking": ((3, 3), (0, 1)),
    "surprised": ((0, 0),), "smug": ((3, 3), (1, 1)), "determined": ((2, 2),), "confused": ((0, 0), (1, 3)),
}
PX_MOUTHS = {
    "neutral":    ("...........", "..#######..", "...........", "..........."),
    "happy":      ("##.......##", ".#########.", "..#######..", "...#####..."),
    "sad":        ("...........", "...#####...", "..#.....#..", ".#.......#."),
    "angry":      ("#...#...#..", ".#.#.#.#.#.", "..#...#...#", "..........."),
    "jealous":    ("...........", ".....####..", "..###....#.", "..........."),
    "worried":    ("..##....##.", ".#..#..#..#", "#....##....", "..........."),
    "relieved":   ("...........", "#.........#", ".##.....##.", "...#####..."),
    "thinking":   ("...........", ".........#.", ".....####..", "..........."),
    "surprised":  ("....###....", "...#...#...", "...#...#...", "....###...."),
    "smug":       ("..........#", ".........#.", "..#######..", "..........."),
    "determined": ("#.........#", ".#########.", ".#.#.#.#.#.", "..#######.."),     # a grin: corners up, teeth
    "confused":   ("...........", ".......###.", "...####....", ".##........"),
}
PX_PRESS = ("...........", "...#####...", "...#####...", "...........")
PX_SMIRK = ("...........", ".........#.", "..#######..", "...........")


def _cells(grid, x0, y0, mirror=False):
    for r, row in enumerate(grid):
        for c, ch in enumerate(row[::-1] if mirror else row):
            if ch == "#":
                yield x0 + c, y0 + r


def _px_origin(a):
    """The dot grid's origin: the head's display, or else a grid laid on the left eye."""
    p = a.get("px", 4)
    return a.get("px_origin") or (a["lx"] - 2.5 * p, a["ey"] - 2.5 * p)


def _px_draw(cells, a, col, bloom=True):
    """Lit cells (grid coordinates relative to the display's origin) as squares with a bloom."""
    p = a.get("px", 4)
    ox, oy = _px_origin(a)
    cells = list(cells)
    if not cells:
        return ""
    lit = "".join("M %.1f %.1f h %.1f v %.1f h -%.1f Z " % (ox + c * p + .4, oy + r * p + .4, p - .8, p - .8, p - .8)
                  for c, r in cells)
    out = ""
    if bloom:
        glow = "".join("M %.1f %.1f h %.1f v %.1f h -%.1f Z " % (ox + c * p - .8, oy + r * p - .8, p + 1.6, p + 1.6, p + 1.6)
                       for c, r in cells)
        out += '<path d="%s" fill="%s" opacity="0.28"/>' % (glow.strip(), col)
    return out + '<path d="%s" fill="%s"/>' % (lit.strip(), col)


def _px_at(a, x, y):
    """The grid cell whose top-left corner is at (x, y)."""
    p = a.get("px", 4)
    ox, oy = _px_origin(a)
    return int(round((x - ox) / float(p))), int(round((y - oy) / float(p)))


def _px_grid_at(a, grid, cx, cy, mirror=False, dx=0):
    p = a.get("px", 4)
    c0, r0 = _px_at(a, cx - len(grid[0]) * p / 2.0, cy - len(grid) * p / 2.0)
    return list(_cells(grid, c0 + dx, r0, mirror))


@register(EYES, "pixel")
def _eyes_pixel(e, a, light, marks=()):
    lx, rx, y, b = a["lx"], a["rx"], a["ey"], a["by"]
    p = a.get("px", 4)
    col = _lit(a, marks)
    dx = -1 if "glance" in marks else 0
    cells = []
    if "blink" in marks:
        left, right = PX_BLINK, PX_BLINK
    elif e == "confused":
        left, right = PX_EYES[e], PX_CONFUSED_RIGHT
    else:
        left = right = PX_EYES[e]
    for x, grid, mirror in ((lx, left, False), (rx, right, True)):
        eye = _px_grid_at(a, grid, x, y, mirror, dx)
        if "glitch" in marks:                    # a torn scan line: the eye's middle rows slip sideways
            rows = sorted({r for _, r in eye})
            mid = rows[len(rows) // 2] if rows else None
            eye = [(c + (2 if r == mid else 0), r) for c, r in eye]
        cells += eye
    spec = PX_BROWS[e]
    for x, (o, i), side in ((lx, spec[0], -1), (rx, spec[-1], 1)):
        if "brow_up" in marks and side == 1:
            o, i = max(0, o - 1), max(0, i - 1)
        if "knit" in marks:
            i = min(3, i + 1)
        c0, r0 = _px_at(a, x - 2.5 * p, b - 2 * p)
        for k in range(5):                       # k = 0 at the outer end
            row = int(o + (i - o) * k / 4.0 + 0.5)
            col_ = c0 + (k if side < 0 else 4 - k)
            cells.append((col_, r0 + row))
    out = _px_draw(cells, a, col)
    if "twitch" in marks and "twitch" not in (a.get("own_marks") or ()):   # two cells beside the left eye flicker on
        c0, r0 = _px_at(a, lx - 2.5 * p, y - 2.5 * p)
        out += _px_draw([(c0 - 2, r0 + 1), (c0 - 2, r0 + 3)], a, col)
    return out


@register(MOUTHS, "pixel")
def _mouth_pixel(e, a, fill, marks=()):
    col = _lit(a, marks)
    grid = (PX_PRESS if e == "neutral" and "press" in marks else
            PX_SMIRK if e in ("neutral", "thinking") and "smirk" in marks else PX_MOUTHS[e])
    p = a.get("px", 4)
    c0, r0 = _px_at(a, a["mx"] - len(grid[0]) * p / 2.0, a["my"] - len(grid) * p / 2.0)
    cells = list(_cells(grid, c0, r0))
    if "glitch" in marks:                        # the mouth's top row slips, stray cells light up
        rows = sorted({r for _, r in cells})
        cells = [(c - (2 if rows and r == rows[0] else 0), r) for c, r in cells]
    out = _px_draw(cells, a, col)
    if "static" in marks:                        # the whole display flickers: the mouth is its last layer
        out += _static(a)
    if "glitch" in marks:
        out += _px_draw([(c0 + dc, r0 + dr) for dc, dr in ((-3, -9), (-2, -9), (12, 0), (13, 0), (14, 0), (2, 4), (3, 4))],
                        a, GLITCH[0], bloom=False)
    return out


# ---------------------------------------------------------------- heads
def _bolt(x, y, r=3.4, fill="#8A9097"):
    return _c(x, y, r, fill, INK, 2) + _p("M %.1f %.1f L %.1f %.1f" % (x - r * .55, y - r * .55, x + r * .55, y + r * .55),
                                          "none", INK, 1.4)


@register(HEADS, "robot_box")
def _robot_box(skin, look):
    """A retired industrial welding robot: a square head, the welding visor flipped down over the face."""
    edge = _shade(skin, 0.62)
    glass = look.get("screen", "#1C2B26")
    glow = look.get("glow", "#8FF3FF")
    steel, plate = "#6F767E", "#3A3F46"
    d = "M 40 58 Q 40 44 54 44 L 146 44 Q 160 44 160 58 L 160 148 Q 160 162 146 162 L 54 162 Q 40 162 40 148 Z"
    out = (_p("M 84 150 L 116 150 L 116 177 L 84 177 Z", steel, INK, 4)        # the neck: a ribbed column
           + _p("M 84 167 L 116 167 M 84 172 L 116 172", "none", INK, 2.5)
           + _p("M 76 44 L 76 26", "none", INK, 4) + _c(76, 22, 5.5, "#E0533A", INK, 3)   # a stubby antenna
           + _p(d, skin, INK, 5)
           + _p("M 48 56 Q 48 52 52 52 L 148 52", "none", _shade(skin, 1.35), 3, ' opacity="0.7"')
           + _bolt(52, 55) + _bolt(148, 55) + _bolt(54, 151) + _bolt(146, 151)
           + _p("M 88 50 L 88 58 M 96 50 L 96 58 M 104 50 L 104 58 M 112 50 L 112 58", "none", edge, 3)
           # the visor: a dark plate on hinge knobs, a pane of welding glass in it
           + _p(_rr(46, 62, 154, 130, 9), plate, INK, 4.5)
           + _p(_rr(54, 68, 146, 124, 5), glass, INK, 3)
           + _p("M 60 74 L 74 74", "none", "#FFFFFF", 2.5, ' opacity="0.35"')
           + _p(_rr(93, 127, 107, 134, 2.5), plate, INK, 2.5)                  # the tab that flips it up
           + _c(40, 96, 9, _shade(skin, 0.8), INK, 3.5) + _c(160, 96, 9, _shade(skin, 0.8), INK, 3.5)
           + _c(40, 96, 3.5, plate, None) + _c(160, 96, 3.5, plate, None)
           # the grille's dark box; the mouth style lights it and lays the slats over it
           + _p(_rr(74, 136, 126, 156, 5), "#22262A", None))
    a = dict(lx=78, rx=122, ey=101, by=81, mx=100, my=146, nx=100, ny=128,
             cheeks=((60, 140), (140, 140)), temple=(148, 86), top=44, ears=(40, 160, 96), chin=162,
             eyes_style="glow", mouth_style="grille", neck=False, no_brows=True, led_brows=True,
             glow=glow, lid=glass, screen_box=(54, 68, 146, 124), eye_w=18, eye_h=22,
             grille=(74, 136, 126, 156), grille_bar=plate, mouth_scale=1.0, twinkle_x=120, twinkle_y=28)
    return out, d, a, edge


@register(HEADS, "robot_dome")
def _robot_dome(skin, look):
    """An android nanny: a porcelain dome with painted features and a bun-like knob on top."""
    edge = _shade(skin, 0.62)
    accent = look.get("accent", "#A9C1DE")
    d = "M 45 106 C 45 60 68 40 100 40 C 132 40 155 60 155 106 C 155 146 132 170 100 170 C 68 170 45 146 45 106 Z"
    out = (_p("M 90 158 L 110 158 L 110 184 L 90 184 Z", skin, INK, 4)          # a slim jointed neck
           + _p("M 88 170 L 112 170 L 112 176 L 88 176 Z", accent, INK, 2.5)
           + _c(100, 26, 13, skin, INK, 4)                                     # the bun-like knob
           + _p("M 93 20 Q 98 16 104 17", "none", "#FFFFFF", 3)
           + _p(d, skin, INK, 5)
           + _e(100, 41, 16, 5, accent, INK, 3)
           + _p("M 54 104 C 56 78 74 62 100 60 C 126 62 144 78 146 104", "none", _shade(skin, 0.86), 2.5)
           + _p("M 62 76 Q 70 58 90 51", "none", "#FFFFFF", 4.5, ' opacity="0.9"')
           + _c(46, 116, 10, accent, INK, 3.5) + _c(46, 116, 4, _shade(accent, 0.7), None)
           + _c(154, 116, 10, accent, INK, 3.5) + _c(154, 116, 4, _shade(accent, 0.7), None))
    a = dict(lx=79, rx=121, ey=112, by=89, mx=100, my=148, nx=100, ny=131,
             cheeks=((68, 136), (132, 136)), temple=(146, 86), top=42, ears=(46, 154, 116), chin=170,
             eyes_style="painted", mouth_style="painted", neck=False,
             iris=look.get("iris", "#34466E"), paint=look.get("paint", "#C84B64"), lid=skin)
    return out, d, a, edge


@register(HEADS, "robot_vac")
def _robot_vac(skin, look):
    """A robot vacuum, seen from just above the front: a disc on a bumper with a dark sensor window."""
    edge = _shade(skin, 0.62)
    glow = look.get("glow", "#7DF9FF")
    window = look.get("screen", "#15181C")
    bumper = look.get("bumper", "#474C54")
    d = ("M 22 90 L 22 144 A 78 22 0 0 0 178 144 L 178 90 A 78 22 0 0 0 22 90 Z")
    band = "M 22 90 L 22 144 A 78 22 0 0 0 178 144 L 178 90 A 78 22 0 0 1 22 90 Z"
    brush = "#5B616A"
    out = (_p("M 46 154 L 30 158 M 46 154 L 32 166 M 46 154 L 40 170 M 154 154 L 170 158 M 154 154 L 168 166 "
              "M 154 154 L 160 170", "none", brush, 2.5)                          # the side brushes, spinning
           + _p(band, bumper, INK, 5)
           + _p("M 30 110 Q 100 142 170 110", "none", _shade(bumper, 1.35), 2.5, ' opacity="0.6"')
           + _e(100, 90, 78, 22, skin, INK, 5)
           + _e(100, 87, 46, 12, "none", _shade(skin, 0.8), 3)
           + _e(100, 86, 13, 4.5, _shade(skin, 1.3), INK, 2.5)
           + _e(100, 86, 6, 2.2, "#4CD964", None)                             # the status light
           + _p("M 44 80 Q 60 72 84 70", "none", "#FFFFFF", 3.5, ' opacity="0.55"')
           + _p(_rr(50, 116, 150, 148, 16), window, INK, 3.5)
           + _p("M 60 121 L 80 121", "none", "#FFFFFF", 2, ' opacity="0.3"'))
    a = dict(lx=79, rx=121, ey=132, by=114, mx=100, my=157, nx=100, ny=140,
             cheeks=((46, 152), (154, 152)), temple=(150, 92), top=68, ears=(22, 178, 118), chin=166,
             eyes_style="glow", mouth_style="glow", neck=False, no_brows=True,
             glow=glow, lid=window, screen_box=(50, 116, 150, 148), eye_w=16, eye_h=20,
             mouth_scale=0.62, status=(100, 86), twinkle_x=132, twinkle_y=54)
    return out, d, a, edge


# THE STOCK IS THE MACHINE'S STATE: the snacks can change as a tell, or empty out under stress. How full
# the shelves are follows the face the machine shows (cans / bags / bars left of four each), and four
# marks are drawn in the product window instead of on a face: pale -- half of whatever is left is gone,
# whatever the display shows (the one that gives away a feeling the face hides); bead -- a snack drops
# into its own pickup tray; twitch -- one snack sticks, hanging off its coil; flush -- the window
# lights up warm.
VENDING_STOCK = {
    "happy": (4, 4, 4), "smug": (4, 4, 4), "relieved": (4, 4, 4), "hopeful": (4, 4, 4), "determined": (4, 4, 4),
    "neutral": (4, 4, 3), "thinking": (4, 3, 4), "curious": (4, 4, 3), "surprised": (3, 4, 4),
    "skeptical": (3, 4, 3), "confused": (4, 3, 3), "embarrassed": (3, 3, 4), "jealous": (3, 2, 3),
    "angry": (2, 3, 2), "worried": (2, 2, 1), "tired": (2, 1, 2), "disappointed": (1, 2, 1), "sad": (1, 0, 1)}
VENDING_MARKS = ("pale", "bead", "twitch", "flush")
_VEND_ORDER = (1, 3, 0, 2)                    # which slot of a shelf empties first, then next...


def _vending_products(x0, y0, x1, y1, emotion="neutral", marks=()):
    shelves = 3
    h = (y1 - y0) / float(shelves)
    colors = (("#E74C3C", "#F1C40F", "#2ECC71", "#3498DB"), ("#F39C12", "#9B59B6", "#E67E22", "#1ABC9C"),
              ("#C0392B", "#16A085", "#F4D03F", "#8E44AD"))
    stock = list(VENDING_STOCK.get(emotion, (4, 4, 4)))
    if "pale" in marks:
        stock = [n // 2 for n in stock]
    stuck = None
    if "twitch" in marks:                      # the last snack left on the fullest shelf sticks
        i = max(range(shelves), key=lambda k: (stock[k], -k))
        if stock[i]:
            stuck = (i, sorted(s for s in range(4) if s not in _VEND_ORDER[:4 - stock[i]])[-1])

    def item(i, x, base, col, tilt=0):
        g = '<g transform="rotate(%d %.1f %.1f)">' % (tilt, x, base) if tilt else ""
        if i == 0:                               # cans
            s = _p(_rr(x - 4.5, base - 14, x + 4.5, base, 2), col, INK, 1.8)
        elif i == 1:                             # chip bags
            s = _p("M %.1f %.1f L %.1f %.1f L %.1f %.1f L %.1f %.1f Z" % (x - 6, base, x - 5, base - 14,
                   x + 5, base - 14, x + 6, base), col, INK, 1.8)
        else:                                    # candy bars
            s = _p(_rr(x - 6, base - 8, x + 6, base, 1.5), col, INK, 1.8)
        return g + s + ("</g>" if g else "")
    out = ""
    if "flush" in marks:
        out += _p(_rr(x0 + 1, y0 + 1, x1 - 1, y1 - 1, 3), "#FFE9A8", None, extra=' opacity="0.7"')
    for i in range(shelves):
        base = y0 + h * (i + 1) - 2
        gone = set(_VEND_ORDER[:4 - stock[i]])
        for j, col in enumerate(colors[i]):
            x = x0 + 9 + j * (x1 - x0 - 18) / 3.0
            # an empty slot shows its bare coil
            out += _p("M %.1f %.1f q 2 -3 4 0 q 2 3 4 0" % (x - 4, base - 3), "none", "#8A9097", 1.4)
            if j in gone:
                continue
            if stuck == (i, j):                  # pushed out over the edge, hanging on
                out += item(i, x + 2, base + 3, col, 28)
            else:
                out += item(i, x, base, col)
        out += _p("M %.1f %.1f L %.1f %.1f" % (x0, base + 1.5, x1, base + 1.5), "none", "#8A9097", 2.5)
    if "pale" in marks:                        # the window's light goes gray and thin
        out += _p(_rr(x0 + 1, y0 + 1, x1 - 1, y1 - 1, 3), "#9AA3AD", None, extra=' opacity="0.35"')
    return out


@register(HEADS, "vending")
def _vending(skin, look):
    """A vending machine: a dot-matrix display at the top shows the face."""
    edge = _shade(skin, 0.62)
    glow = look.get("glow", "#63F59A")
    screen = look.get("screen", "#10201A")
    px, ox, oy, cols, rows = 4, 54, 38, 23, 18          # the display's dot grid
    d = "M 42 210 L 42 36 Q 42 26 52 26 L 148 26 Q 158 26 158 36 L 158 210 Z"
    grid = "".join("M %d %d h 2.4 v 2.4 h -2.4 Z " % (ox + c * px + .8, oy + r * px + .8)
                   for c in range(cols) for r in range(rows))
    out = (_p(d, skin, INK, 5)
           + _p("M 150 32 L 150 204", "none", _shade(skin, 0.84), 5)
           + _p(_rr(49, 33, 151, 115, 7), _shade(skin, 0.72), INK, 3.5)
           + _p(_rr(ox, oy, ox + cols * px, oy + rows * px, 4), screen, INK, 2.5)
           + '<path d="%s" fill="%s" opacity="0.09"/>' % (grid.strip(), glow)
           # the product window: shelves of cans, bags and bars behind glass, stocked by the machine's state
           + _p(_rr(54, 121, 122, 183, 3), "#DCEBF0", INK, 3)
           + _vending_products(54, 121, 122, 183, look.get("_emotion", "neutral"), look.get("_marks") or ())
           + _p("M 60 178 L 84 124 M 70 180 L 92 131", "none", "#FFFFFF", 3, ' opacity="0.55"')
           + _p(_rr(54, 121, 122, 183, 3), "none", INK, 3)
           # the coin panel: a coin slot, a keypad, a return button
           + _p(_rr(127, 121, 147, 183, 3), _shade(skin, 0.8), INK, 3)
           + _p(_rr(131, 126, 143, 142, 2), "#D5DAE0", INK, 2)
           + _p("M 137 129 L 137 139", "none", INK, 2.5)
           + "".join(_p(_rr(x, y, x + 5, y + 5, 1), "#EEF1F4", INK, 1.5) for x in (131, 138) for y in (147, 155, 163))
           + _c(137, 175, 3.2, "#D5DAE0", INK, 1.8)
           + _p(_rr(58, 188, 142, 206, 3), "#2A2D33", INK, 3)
           + _p("M 64 193 L 136 193", "none", "#5B616A", 2.5))
    if "bead" in (look.get("_marks") or ()):   # a snack it dropped itself, lying in the pickup tray
        out += ('<g transform="rotate(-9 96 192)">' + _p(_rr(84, 187, 108, 196, 2), "#F39C12", INK, 2)
                + _p("M 90 190 L 102 190", "none", "#FFFFFF", 1.6, ' opacity="0.7"') + "</g>")
    a = dict(lx=80, rx=120, ey=72, by=50, mx=100, my=94, nx=100, ny=81,
             cheeks=((64, 94), (136, 94)), temple=(146, 88), top=26, ears=(54, 146, 72), chin=112,
             eyes_style="pixel", mouth_style="pixel", neck=False, no_brows=True,
             glow=glow, lid=screen, screen_box=(ox, oy, ox + cols * px, oy + rows * px),
             px=px, px_origin=(ox, oy), twinkle_x=132, twinkle_y=14,
             own_marks=VENDING_MARKS)          # drawn in the stock above, not on the display
    return out, d, a, edge
