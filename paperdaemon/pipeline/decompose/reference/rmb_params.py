r"""EVERY tuned constant of the decomposer, and what it means.

One place for the picture path's knobs. They were tuned against many rated
renderings -- the comments say what each number does and why it has the value it has,
and none of them is a guess to be re-derived. Changing a value here changes the drawing.

Four of them can be OVERRIDDEN for the duration of one decomposition
(`with rmb_params.overrides(...)`), which swaps the same module globals in a
try/finally, so the code that reads them must read them off this module
(`K.LINE_SCALE`) and never bind them at import.
"""
from rmscene.scene_items import Pen, PenColor

# One loop family, subcell geometry, no repair passes.
SUBCELL_GEOMETRY = True

# ================================================================ the picture path
PX_PER_GRID = 2.2         # page px per grid px: the resolution rm_lineart's XDoG constants were tuned at
# THE GRID MATCHES THE SOURCE. A cap on the working grid (the old one was 720) would downsample
# every 1024-px generation before the decomposer saw it, and a panel's 2-px gold lines would go in
# at 1.4 px, under the despeckle's floor -- the whole background came out as one black region.
# 1620 is the page's width: a source is never downsampled below what the tablet can show, and
# never upsampled (the code below never scales up).
GRID_MIN, GRID_MAX = 160, 1620   # NOT USED by decompose()/fit_box() any more -- the grid IS the source (see below)
# THE GRID IS THE SOURCE, EXACTLY. The decomposition looks at the entire source at its exact
# resolution, not at some made-up target resolution. No cap, no floor:
# a 1024-px picture is decomposed at 1024, a 4000-px one at 4000, a 120-px icon at 120. The
# XDoG sigma already scales with the grid (XDOG_SIGMA_REF * grid_w / 340) and every threshold in
# page px is converted through ppg, so nothing else had to move. `grid_max` is honored only when
# a caller passes it explicitly.

# THE FLESH GATE CORRECTS FOR THE PICTURE'S CAST; THE PICTURE IS NEVER TOUCHED. Measured on
# 7 Qwen-Image-2512 generations: their near-neutral pixels sit at Lab (a*,b*) ~ (3, 20), a yellow cast
# that moves skin from hue ~55 to ~70 deg and past the wood line (a/b 0.42 <=> 67 deg). klein sits
# at |cast| 5-8. White-balancing the pixels fixed the gate and wrecked the picture (pale skin to
# paper, grounds to gray), so the
# correction is a hue OFFSET applied inside _skin_key/_skin_px only, with a deadband so klein is
# untouched. The offset is the hue shift the cast induces on a flesh pixel of the wedge's typical
# chroma: atan2(|v| sin(theta_v - h_ref), C_ref + |v| cos(theta_v - h_ref)).
SKIN_CAST_ON = True
SKIN_CAST_DEADBAND = 10.0  # |median (a*,b*) of near-neutral pixels| below this: no offset (klein 5-8, Qwen ~20)
SKIN_CAST_REF_HUE = 55.0   # the canonical flesh hue the induced shift is measured at
SKIN_CAST_MAX_DEG = 25.0   # the offset is never larger than this

# A DARK COLOR IS A COLOR. Below BLACK_L a chromatic pixel that no wash rendered well was
# declared black before the "dark color = base wash + hatch" branch was reached, so an art nouveau
# panel's dark blue-green ground came out as one slab of marker with the ornament as filled-in
# holes. A dark area should be seen as dark blue and colored accordingly: blue with hatch
# shading. Now a pixel darker than BLACK_L with at least this chroma is ("base", its hue's
# wash) and the hatch carries its darkness; only achromatic darkness is black. Between CHROMA_MIN
# (8, where gray starts being color at all) and INK_CHROMA_MAX (20, a color's dark side).
# Measured on that panel: its ground (42% of the picture at L* < 12) has chroma 2.2 / 4.4 / 8.0
# / 11.4 at the 25/50/75/90th percentiles, hue ~87 (a dark olive; the corners run teal). At 10 the
# whole ground stayed black; 5 turns the tinted three quarters of it into its hue's wash + hatch and
# leaves the truly neutral quarter black. Below ~4 a cluster's hue is noise in a generated picture.
# Per CLUSTER this is a noisy test: median-cut averages a ground's olive and teal tints into
# near-gray cluster means (the panel's black share barely moved between 10 and 3), so it stays at
# 5 for clearly colored dark pixels, and the REGION rule below does the rest.
DARK_BASE_CHROMA = 5.0
# ...and ONLY ON A PICTURE THAT HAS A DARK FIELD. A flat illustration's outlines are dark too, and
# anti-aliasing tints them (a fox's black outline measures chroma 15 against its orange), so the
# rule turned clean black outlines into hatched washes -- measured on a flat cactus illustration.
# What separates them is AREA, by two orders of magnitude: the biggest black region of a flat
# illustration is ~100 px, an art nouveau ground's is 31,000. So the rule is armed per picture:
# this much of it must be dark AND its largest dark mass must be this big. Measured: every flat
# and line source in the rated and hold-out sets is excluded (cactus 7.9%, fox 7.7%, robot 5.7%,
# chess 4.2%), every painting in the sets qualifies (13.9-47%).
DARK_FIELD_MIN_COVER = 0.12    # share of the picture darker than BLACK_L
DARK_FIELD_MIN_REGION = 0.01   # ...and its largest connected dark mass, as a share of the picture
# A BLACK REGION WITH A CONSISTENT FAINT TINT IS A DARK COLOR. After the ink lines are
# taken, each remaining true-black component's mean (a*, b*) over all its source pixels is measured;
# a mean chroma at or above this makes it a wash of that hue (highlighters only) with dense hatch
# carrying the darkness, instead of a marker slab. Thousands of pixels average a faint tint out of
# the noise that defeats the per-cluster test. 0 turns the rule off.
DARK_REGION_CHROMA = 3.0
# ...measured against the picture's cast when the cast is beyond SKIN_CAST_DEADBAND: a Qwen ground
# at Lab (0.6, 3.0) is neutral in the numbers and dark blue to the eye, which is what the eye sees
# against a yellow-cast picture (simultaneous contrast). With the cast
# subtracted it reads (-3, -18): blue, so the B wash under the hatch. klein (no cast) is judged as is.
DARK_REGION_CAST_RELATIVE = True
DARK_REGION_CHROMA_ABS = 1.5     # ...only for regions with at least this much tint of their OWN: a pure black block
                                 # (chroma 0) is black under any cast. The panel's ground carries ~3.
EDGE_MARGIN_PAGE = 6.0    # the ink stays this far inside the given box (half the widest pen plus the ring's bloat)

# THE DEVICE PALETTE, measured from the desktop app's rendering of the calibration pages
# (screenshots of the calibration pages; the app is the reference renderer).
# Pens are opaque. The highlighter is a wash composited as a per-channel MINIMUM ("darken") over
# whatever is under it, so a stack of washes is exactly min() of its colors: all 63 combinations
# of the six verified to the unit. Pairs give real new colors (OM salmon, BM lavender, YB lime);
# every triple or deeper is a tan or an olive, so HL_MAX_LAYERS stops at 2.
PEN_RGB = {PenColor.BLACK: (0, 0, 0), PenColor.GRAY: (144, 144, 144), PenColor.YELLOW: (254, 253, 96),
           PenColor.GREEN: (169, 250, 92), PenColor.PINK: (255, 85, 207), PenColor.BLUE: (48, 74, 224),
           PenColor.RED: (194, 49, 50), PenColor.GREEN_2: (145, 218, 113), PenColor.CYAN: (116, 210, 232),
           PenColor.MAGENTA: (192, 127, 210), PenColor.YELLOW_2: (250, 231, 25)}
CHROMATIC = tuple(c for c in PEN_RGB if c not in (PenColor.BLACK, PenColor.GRAY))
PALETTE = dict(PEN_RGB)
HL_RGBA = {"O": (255, 195, 140), "Y": (255, 237, 117), "G": (172, 255, 133),
           "B": (190, 234, 254), "M": (242, 158, 255), "K": (199, 199, 198)}
HL_SCALE = 0.25           # highlighter width field -> page px (pens use 0.144); measured 0.25-0.26 on six widths
HL_WIDTHS_PAGE = (30.0, 16.0, 8.0)   # widest and finest: the spiral starts at the last and grows to the first
# THE WASH IS A SPIRAL: the highlighter stroke for a fill is one stroke, spiraling around the edge
# finely at first, and then using thicker and thicker ones until it fills in the space.
# Each pass steps in by half the previous width plus
# half its own, so passes abut and the fill cannot gap. This is how fast the width grows inward.
HL_SPIRAL_GROWTH = 1.8
HL_MAX_LAYERS = 2
HL_MAX_TURN = 20.0        # a wash loop never turns more than this per vertex (sharp turns are rounded off)
                          # the device notches the inner side of a turn by (w/2)(1 - cos(turn/2)) -- 1.5 % of w/2 at 20 deg
POCKET_L = 60.0           # a LIGHT low-chroma pocket enclosed by color is a lighter shade of that color (a canopy's
                          # highlights, a painting's pale passages) and takes the nearest wash; dark low-chroma
                          # pockets are shadows and keep their hatch. Below the chroma gate such pixels were tone
                          # -> paper between the washes
GAP_CLOSE_G = 6           # grid (= source) px. Achromatic pixels the color union CLOSES over (channels and notches
                          # narrower than twice this between/into color regions) join the bordering color nearest
                          # their own color. A gradient sky quantizes into bands of two washes with a strip of
                          # low-chroma "tone" between them, and that strip drew as paper, which cheapens the
                          # image. Color is the BASE layer (ink, black fills and hatch are all drawn
                          # over it), so an absorbed pixel keeps its tone/ink roles; paper (L* >= PAPER_L) is never
                          # absorbed: a flat illustration's white between two shapes is a color of its own.
GAP_CLOSE_PAGE = 15.0     # ...but never more than this many PAGE px: on a 200-px source drawn at 1300 a source px is
                          # 6.5 page px, and closing 12 of them would fill a 2 cm feature, not a gap.
HL_PREFERENCE = 2.0       # dE head start for a wash over a pen: the tablet mutes saturated pens more than washes
                          # and a wash is a tenth of the strokes; the pale sky wash was preferred to the cyan pen
                          # where the two were within a unit of each other
PAPER_L = 92.0            # L* at/above which a LOW-CHROMA pixel is paper...
PAPER_CHROMA = 30.0       # ...and a pixel this chromatic is a color however light: a saturated yellow has L* 97 (the
                          # cactus flowers' centers were "small color gaps"). Below it, light tints (a cream skull on
                          # red, a parchment background) are paper -- the tablet's paper is the nearest thing to them.
INK_L = 36.0              # achromatic pixels darker than this are INK (line core plus skirt): this mask
                          # half of its anti-aliased skirt. Higher takes the whole skirt and the line
                          # comes out fat; lower loses thin strokes altogether.
                          # as the original cluster threshold effectively was; that line work was the best of the
                          # versions compared for photoreal things. Letting the anti-aliased fringe in
                          # (L*<80 or <72) fattened every line.
FRINGE_L = 72.0           # gray within 1 px of ink core and lighter than INK_L is that line's own fringe: neither
                          # ink nor shading (black is dilated and the result subtracted from tone)
BLACK_L = 12.0            # cluster L* (0-100) below which achromatic ink is SOLID BLACK; darker than paper but lighter
                          # than this is hatched. A knob, not a fact: at 22 (measured midpoint between black and the
                          # densest hatch) a bicycle's near-black handlebar tape filled solid, as wanted --
                          # and so did a flat teapot's dark shadow that was meant to be hatched, and the photographs'
                          # deep shadows lost their modeling. The same darkness is an object in one picture and a
                          # shadow in the next; pixels cannot tell. decompose(black_l=...) sets it per source.
CHROMA_MIN = 8.0          # below this Lab chroma a cluster is gray whatever the palette says. Above it, color is
                          # used only when a device color is a BETTER match than the cluster's own gray -- i.e. the
                          # nearest palette entry is closer (in Lab, with the wash preference) than the chroma
                          # itself. That one rule replaces the older fixed gate of 20: a pale sky (chroma 15) is
                          # closer to the blue wash than to gray, so it is blue; shadowed skin (chroma 28) is closer
                          # to its own gray than to any pen or wash, so it hatches instead of painting red.
INK_CHROMA_MAX = 20.0     # a dark pixel of a cluster this chromatic is a COLOR's dark side, not ink: the anti-aliased
                          # fringe of a black line over a color fill is a dark mix of the two. Those clusters
                          # used to be color (chroma >= 20) and the line was measured at its core; the gray rule made
                          # them achromatic, they joined the ink mask, and every outline over color grew a pixel each
                          # side (thickened black lines and edges).
                          # Only near-black (L* < black_l) of such a cluster is ink; the rest is tone, and the gap
                          # closing gives it the neighboring color as its base.
DETAIL_PRECISE = 1.5      # detail at/above which the input is treated as PRECISE flat content (a rendered chart, a
                          # calendar, an app screen): no despeckling of the class masks, fainter gray lines drawn.
CLUSTERS = 256            # 64 capped the whole picture at 64 colors before anything
                          # else ran, so "hundreds of colors" was unreachable by construction. The
                          # cel merge below removes the duplicates this admits.
                          # (24 was worse: a small color area, the yellow center of a cactus flower, got no cluster of its
                          # own and took a neighbor's color.) The device palette caps the CLASSES at 30 either way
XDOG_SIGMA_REF = 1.6      # rm_lineart's sigma at a 340-px grid; scaled with the grid so ridges are found at the same image scale
XDOG_INK = 0.07

# page-px geometry. Width FIELDS are page px / WSCALE_DEFAULT (0.144).
FILL_HOLE_PAGE = 7.0      # an enclosed pocket of paper smaller than this square (or thinner than 1.5 grid px) is
                          # filled before a shape is painted or skeletonised: a pen cannot leave it, and a
                          # skeleton splits around it -- a red tube's highlight channel made its centerline
                          # two parallel noodles with a gap
FILL_CLOSE_G = 1          # a region is closed by this many grid px first: paper channels under 2 grid px are
                          # the marker's own resolution (a braid's darkest threads were a sponge)
FILL_THICK_PAGE = 9.0     # a PART of a component wider than this is a region, painted edge-exact; narrower parts
                          # are lines, one centerline stroke carrying the local width. A skull's outline
                          # is ~9 px; a bold marker line, a foliage clump, a junction blob are wider -- drawn as
                          # skeleton strokes they were the spaghetti in the thick areas
FILL_ZONE_MIN_PAGE = 20.0 # ...unless the thick part is smaller than this square: a knot where lines meet
                          # stays part of the line
LINE_SMOOTH = True        # Chaikin-smooth centerlines (the picture path); rm_paint_ui switches it off for straight UI lines
LINE_SCALE = 1.0          # drawn width vs measured: the measured width wins; a 0.8 scale never won a line-art comparison
RIDGE_MAX_PAGE = 4.5      # up to this thickness the XDoG ridge is the centerline; bolder lines are mask-thinned
TEXTURE_PIECES = 2.5      # texture test: mean raw skeleton piece length < this many times the local thickness.
                          # A line is many widths long; texture's skeleton is fragments about as long as they are
                          # wide. Fires on lighthouse rocks, not on horse legs.
FINELINER_MAX_PAGE = 3.2  # the split between fineliner and marker
MIN_SPAN_G = 5            # ink components smaller than this in both axes are specks. In GRID px = source px: noise
                          # is a property of the source (quantization and anti-aliasing flecks are 1-3 px), not of
                          # the page. As 20 page px this ate real parts whenever the box was small -- at
                          # 400 px a robot lost 53 of its 62 color pieces and a cactus its flowers (even just dots
                          # will do). `detail` scales it; the pen's own minimum mark is the floor.
MIN_SPAN_COLOR_G = 8     # color flecks smaller than this are quantization noise (confetti)
MIN_LEN_PAGE = 6.0        # a skeleton piece shorter than this on the page is a spur, not a mark (was 12: a 1.5 mm dash)
TONE_WIDTH_PAGE = 1.8     # pencil hatch line width, page px
TONE_PITCH_PAGE = 5.7     # ONE uniform hatch pitch, page px (uniform density)
HATCH_BRIDGE_G = 1.5      # a hatch line runs on across a gap in its region shorter than this (a speck), so
                          # shading is not dashed into noodles; a drawn line's halo (3 px) still breaks it
# Cel-shading: identify shaded regions conservatively, cel shade that
# down, and apply the hatching in the entire region at a uniform density. Hatching is
# not used to make the body of the drawing. So tone is posterised
# into two bands, each band's regions are kept only if they are large enough to
# be deliberate shading, and each is hatched at the same pitch: one direction for
# the light band, two for the dark. Anything darker than the dark band is solid
# black (the fill pass); anything lighter than the light band is paper.
CEL_BANDS = ((0.18, 0.34, (38.0,), 1.8),       # darkness lo, hi, hatch angles, pitch multiplier
             (0.34, 0.55, (38.0,), 1.0),       # light band (sparse, one direction) exists because an oak's canopy
             (0.55, 1.01, (38.0, -34.0), 1.0)) # sat at ~0.25 and was never a shading candidate (the tree came out bare)
                          # The dark band runs to 1.01, not 0.88. Pixels darker than 0.88 (L* < ~11) used to
                          # be black FILLS and needed no hatch; now a dark COLOR there is a wash (DARK_BASE_CHROMA)
                          # and the hatch is what carries its darkness -- a blue-black ground drawn as a flat pale
                          # blue wash was the fixture that found this. Black fills are unaffected (never hatched).
CEL_BLUR = 1.5            # grid px, before thresholding: shading is smooth, texture is not
CEL_MEDIAN = 5            # despeckle the band masks (7 erased an oak's leaf clumps)
CEL_MIN_AREA = 0.005      # an ISOLATED band region must cover this fraction of the grid to count
CEL_FIELD_COVER = 0.02    # ...unless the band's fragments together cover this much: then it is a textured FIELD
                          # (foliage, fur, grass) and only specks are dropped. An oak's canopy was 17.7%% tone in
                          # hundreds of clumps, every one under the isolated floor, so the tree was drawn bare.
CEL_SPECK_AREA = 0.0004   # the speck floor used inside a field
TONE_PEN = Pen.PENCIL_2
GRAY_LINE_L = 64.0        # a thin gray line lighter than this is drawn with the GRAY pen, else BLACK. Some gray
                          # strokes are better as really thin black lines -- a mid-gray
                          # hairline is a black line that anti-aliasing lightened, so it is black and THIN
GRAY_LINE_SCALE = 0.6     # gray-pass lines are drawn at this fraction of their measured footprint: the footprint of a
                          # light line is its blur, not its ink
GRAY_LINE_MIN_PAGE = 1.2  # ...but never thinner than this (page px)
SHADE_BUDGET = 0.20       # at most this fraction of the box may be hatched (0.35 overused the hatching
                          # on photoreal pictures: 57-78 % of the page shaded); the lightest tones go first, so
                          # the highlights and light mid-tones become paper, which gives more negative space.
                          # 1.0 = no budget.
GRAY_LINE_MAX_PAGE = 4.5  # a gray component is a LINE only if it is this thin (spokes, sutures) and line-like;
                          # a looser limit let 16-px gray blobs in a photograph's shadows become black worms
GRAY_DROP_G = 4.8         # grid (= source) px. Thin gray that is not a line is dropped as anti-aliasing / faint detail
                          # only when it is thin on the PAGE (1.6 x GRAY_LINE_MAX_PAGE, the skull-suture rule) AND thin in
                          # the SOURCE. The page test alone, at a 400-px box, called a robot's 8-12 px joints "faint
                          # detail" and the hatch shading that the 800 and 1300 pages have vanished.
                          # 4.8 grid px is what 7.2 page px meant at the tuning scale.
GRAY_LINE_PIECES = 3.0    # ...and its skeleton pieces are at least this many times its thickness
GRAY_LINE_MIN_LEN_PAGE = 30.0  # ...and it is at least this long: fur ticks and hatching are not drawn lines
                          # (without it a cat got too many thin lines and a hand too many connected lines)
GRAY_FIELD_COVER = 0.5    # a gray component is ENCLOSED when the strips just outside its box on at least three
                          # of four sides are this much non-paper (tone or ink). Enclosed gray is the texture of
                          # the region round it -- a photograph's mid-tones (pulling those out as lines cost a
                          # portrait a quarter of its hatch), the lighter threads of a braid inside
                          # solid black (coils) -- and is left to the hatch. Gray with paper on most
                          # sides is a drawn line: a spoke, a suture, a hairline running beside a black outline
                          # (a whole-neighborhood fraction dropped those too).
TONE_LINE_L = 78.0        # thin gray components darker than this may be LINES (the gray pen: a bicycle's
                          # spokes, a skull's light sutures). Lighter is shading only.



# ================================================================ UI mode: REMOVED
# The pixel-exact path and its 24 constants are gone; a picture that has to be
# exact goes on the page as the picture (rm_images.insert), not as strokes.

# ================================================================ the rest of the picture path
class overrides(object):
    def __init__(self, **kw):
        self.kw = kw
        self.old = {}

    def __enter__(self):
        g = globals()
        for k, v in self.kw.items():
            assert k in g, k
            self.old[k] = g[k]
            g[k] = v
        return self

    def __exit__(self, *exc):
        globals().update(self.old)
        return False


# ---------------------------------------------------------------- flesh tones and contours
# Color accuracy for human skin tones was poor (colors all over the place), and photoreal human faces
# have no line art, so they often come out as blobs. Hence the coherent flesh wash below, and edge
# detection that applies line art to them.

SKIN_COHERENT = True      # every flesh-like color becomes ONE wash, shaded by hatch, instead of each
                          # patch of a face independently picking red, salmon, tan or gray
SKIN_HUE_LO = 20.0        # Lab hue angle, degrees. Human skin of every tone sits in a narrow warm wedge;
SKIN_HUE_HI = 80.0        # what varies between people is lightness and chroma, not hue.
SKIN_CHROMA_MIN = 7.0     # below this it is gray, not flesh
SKIN_CHROMA_MAX = 45.0    # above it, a saturated warm object (a tomato, a brick) -- not flesh
# Hue alone is not enough: wood, sand, warm stone, forest floor and ginger fur all sit in the same wedge,
# and a gate built on hue swallowed them: color accuracy went way down on a photographed cat, a forest floor,
# a lighthouse and a car. Two ratios separate them cleanly on every sample
# measured. Skin is REDDER relative to yellow than wood/sand/stone (a/b), and it is MUTED for its
# lightness where fur, brick, rust and orange are saturated (chroma/L).
SKIN_AB_MIN = 0.42        # Lab a/b: below this it is a yellow-brown object, not flesh
SKIN_CL_MAX = 0.66        # chroma / L: above this it is a saturated warm object, not flesh
SKIN_L_MIN = 20.0         # darker than this is shadow, and hatch carries it
SKIN_WASH = ("hl", "O")   # the one flesh color on the device
SKIN_BASE_L = 68.0        # below this lightness the wash goes down as a BASE and hatch shades it

OUTLINE = True            # draw the form's contour even when the source has no line in it
# No soft contours and long lines only: more aggressive edge detection went too far, so the
# contour pass is kept between the two extremes.
OUTLINE_MIN_LEN_PAGE = 30.0   # A contour piece has to be at least this long
                              # to survive (14 kept too many), so short hooks and stubs go and whole edges stay.
OUTLINE_WIDTH_PAGE = 2.2      # a fine, even line: it describes the form, it is not the drawing
OUTLINE_XDOG = 0.07       # the contour pass gets its OWN edge threshold: the ink threshold finds a drawn
                          # line, and a nose bridge or a collarbone is not one. Higher = softer edges caught.
OUTLINE_CLEAR_G = 2.0         # keep this far (grid px) from ink already drawn, so nothing is doubled

# --- the contour pass can see soft form edges, and fences off only what it actually drew ---
# This is OFF. Measured cost, and it is worth knowing before turning it back on: on a
# photoreal front-on face the soft channel is what draws the NOSE. With it off the nose bridge,
# the nostrils and the philtrum all go -- the face keeps brows, eyes, mouth and jaw and has no
# nose. It is much less visible on a profile, a hand or a flat illustration.
# The middle ground, if that ever reads wrong: OUTLINE_SOFT = True with MIN_DEPTH 1.2 and
# FRAC 0.20, which keeps the nose bridge and drops everything shallower.
OUTLINE_SOFT = False           # a second, COARSE edge channel: shading boundaries, not drawn lines
OUTLINE_SOFT_SIGMA_G = 2.0     # grid px at width 340 -- the scale a nose bridge or a collarbone lives at
OUTLINE_SOFT_FRAC = 0.28       # within each region, the darkest fraction of that coarse response
OUTLINE_SOFT_MIN_AREA = 0.01   # a region smaller than this share of the grid has no usable percentile
OUTLINE_SOFT_MIN_BLOB = 0.0008 # and a shadow smaller than this share of the grid is not a form
OUTLINE_SOFT_MIN_DEPTH = 0.5   # gray levels: a region whose darkest slice is shallower than this
                               # is a smooth gradient, and gets no contour at all
OUTLINE_SOFT_BAND_G = 10.0     # grid px at width 340: a shadow up to this wide is a BAND and becomes one
                               # line down its middle; wider is a REGION and the hatcher shades it

# ================================================================ optional passes (OFF by default)
# Two optional passes, both switchable so variants can be compared side by side.
# `os.environ` so one process per variant can flip them.
import os as _os

# (A) A PER-PICTURE WHITE POINT. PAPER_L is an absolute 92, and the brightest 1% of the paintings
# measured is L* 78-87 -- so paper coverage is 0.0%, 61-73% of the picture classifies as "tone", and
# everything hatches. The whites of an eye are the same fact in miniature (that sclera is L* 78).
# On a page the PAPER IS THE BRIGHTEST INK THERE IS, so the picture's own lightest tone should land
# on it. Lightness only: hue and chroma are untouched, and it is the IDENTITY for 30 of the 33
# rated sources (they already reach L* 100), so nothing rated moves.
# Abandoned: a pure gain on L* lifts a light warm tone towards paper and takes its saturation
# with it, and accuracy drops badly on light warm colors in some color spaces. It did fix a
# robot's legs; that has to come from somewhere else, not from this.
V69_WHITE_POINT = _os.environ.get("RM_V69_WP", "0") == "1"
WP_LO_PCT, WP_HI_PCT = 1.0, 99.0     # the picture's own black and white points, as percentiles of L*
WP_MAX_GAIN = 2.2                    # never stretch harder than this: a deliberately flat picture stays flat
WP_MIN_SPAN = 4.0                    # ...and a span this small is not a picture, it is a swatch: leave it

# (B) FLOW-GUIDED STROKES. The hatch is straight lines at fixed angles and says nothing about form.
# rm_flow computes the edge-tangent flow and draws the hatch as streamlines of it, falling back to
# the fixed angle where the picture is not pointing anywhere.
V69_FLOW_HATCH = _os.environ.get("RM_V69_FLOW", "0") == "1"
# (B2) THE COLOR FILLS FOLLOW THE FORM. Every fill in this painter is a ring plus horizontal
# scanlines -- a printer's way of covering an area. With this on, the rows become streamlines of the
# same flow field, at the same pitch and width, so the coverage is identical and the marks run along
# the hair, the fold, the petal, and read as strokes.
# DEFAULT ON: fills are form-following strokes, not scanlines. The wash is a spiral, which
# follows the form by construction; this switch is what is left of the flow-guided path for
# the MARKER fills.
V69_FLOW_FILL = _os.environ.get("RM_V69_FLOWFILL", "1") == "1"
FLOW_FILL_MIN_LEN_G = 3.0            # a streamline shorter than this is a dot: let the rows/ring have it
# HOW OPEN the fill is. `_fill_region` was built to be "solid and EDGE-EXACT, so it reads as one
# shape and NEVER as strokes" -- rows at pitch 2 grid px, 4 wide, deliberately overlapping. That is
# the sentence to invert: at 1.0 the streamlines overlap and the fill is solid as today, and above
# it they separate and the marks read as marks with the paper (or the wash beneath) showing between
# them: a cel-shaded gradient of colors flowing along a woman's hair becomes
# distinguishable as actual colored strokes where it makes sense.
FLOW_FILL_OPEN = 1.0

# ================================================================ TRUE COLOR
# Measured on the tablet: a PEN ignores color_rgba and takes one
# of eleven enum colors; a HIGHLIGHTER honors ANY rgba. The palette of 29 fixed wash entries was
# never the real space. A chromatic cluster is painted its OWN color as a single
# highlighter wash -- no nearest-wash search, no pair mixes, no flesh wash, no dark-color rules.
# TRUE COLOR IS THE ONLY PATH. The ladder it used to guard
# -- the nearest-of-29-fixed-washes search, HL_PREFERENCE, the flesh gate, the dark-color rules --
# is deleted from the classifier, not switched off.
V70_TRUE_COLOR = True
TC_QUANT = 12                        # RGB rounded to this many levels per channel before it becomes a
                                     # class key: 64 clusters would otherwise make 64 wash colors and
                                     # the neighboring-region merge would never fire
# THE WHITE FLOOR. With color as the base layer, a white page under a warm filter is no longer
# paper -- it is a pale yellow, and true color would paint it across the whole sheet. Images that
# approach white should be floored to white, or the pale background gets painted all over the
# place. So the picture's own GROUND is measured from its border ring, and if that
# ring is light and uniform it becomes paper, along with everything at or above it. A dark painting
# has a dark border, the test does not fire, and nothing is floored.
# CONSERVATIVE BY CONSTRUCTION. Flooring must not always happen: sky blues and pale yellows must
# survive when they are there. So five tests must all pass, and a pale blue or a pale yellow that
# is a SUBJECT fails them: the ground must be near-neutral, it must be the lightest thing in the
# picture, all four edges must agree, the ring must be uniform, and there must be real content
# drawn on it.
# OFF by default: it punched holes out in areas it shouldn't. A conservative five-test gate still
# cannot tell a paper-colored ground from a pale wash that belongs to the picture, and when it is
# wrong it removes paint.
WHITE_FLOOR_ON = _os.environ.get("RM_WHITE_FLOOR", "0") == "1"
WHITE_FLOOR_MIN_L = 80.0      # the border's median lightness must be at least this to be a paper ground
WHITE_FLOOR_MAX_C = 15.0      # ...and this close to neutral. A pale sky or a pale yellow SUBJECT sits above it
WHITE_FLOOR_UNIFORM = 0.60    # ...and this fraction of the ring must sit within TOL of that median
WHITE_FLOOR_EDGE_TOL = 6.0    # ...and no single edge's median may differ from the ring's by more than this (dE)
WHITE_FLOOR_TOP_PCT = 97.0    # ...and the ground must be at least as light as this percentile of the picture
WHITE_FLOOR_TOP_SLACK = 3.0   # ...give or take this much
WHITE_FLOOR_MIN_INK = 0.02    # ...and this much of the picture must be genuinely dark: something is drawn on it
WHITE_FLOOR_RING = 0.03       # the ring is this fraction of the short side, at all four edges
WHITE_FLOOR_TOL_L = 5.0       # a pixel this much darker than the ground still counts as the ground
WHITE_FLOOR_TOL_C = 8.0       # ...if its color is this close to it (tight: a tint, not a color)
# HATCH IS SHADING, NOT DARKNESS. With a fixed palette the hatch was the only way to make anything
# darker than the palette could reach, so it ran from darkness 0.18 (L* ~82) upward and covered most
# of a picture. Now the wash carries the color itself, so hatch over a mid-tone flat is DOUBLE
# darkness: a robot came out muddy, every flat panel scribbled over. With true color on, only the
# darkest band hatches, and only below this darkness -- which is where a wash genuinely cannot reach.
# INK IS STILL INK. A black outline is a near-neutral dark pixel, and anti-aliasing tints it just
# enough (a cactus outline measures Lab chroma 12) to clear a plain chroma gate -- so it became a
# COLOR, and a color is painted with the highlighter, whose narrowest
# stroke is 8 page px. Every outline came out fat, blotchy and uneven. A pixel
# darker than INK_L with chroma under INK_CHROMA_MAX is ink, core and anti-aliased ramp alike.
# A dark FIELD still becomes a color, through the dark-region rule.
TC_INK_L = 36.0               # = INK_L. Below this and under TC_INK_CHROMA a pixel is INK, not color
TC_INK_CHROMA = 20.0          # = INK_CHROMA_MAX
# PAPER IS NEARLY NEUTRAL under true color. PAPER_CHROMA is 30, which was right when a wash could
# only be one of 29 fixed colors -- a light cream had nowhere better to go than paper. Now a cream
# is a color: sepia and warm variants must not be whited out.
TC_PAPER_CHROMA = 6.0

# ================================================================ A RIBBON IS A LINE
# The thick/thin split is by WIDTH alone (FILL_THICK_PAGE), so a bold outline becomes a region and
# is painted as a ring plus rows -- beads, and fatter than the line it came from. It is worst when
# the source is small and every source pixel is several page pixels: on a 200x200 source
# blown up 6x, lines go from super fine to FAT.
# A thick zone is asked what shape it is: mean thickness (2*area/perimeter) against its bounding
# box's diagonal. A long band scores in the tens, a disc 2.8, a square 2.8, a junction blob less.
# OFF. This sent an elongated THICK zone back down the centerline path, which is precisely where
# the spaghetti came from: a skeleton through a wide shape wanders and lumps at junctions. A thick
# ribbon is a shape and gets traced and filled like any other.
RIBBON_LINES = False
RIBBON_ASPECT = 5.0       # diag >= this * mean thickness -> the zone is a line, not a region
RIBBON_MAX_PAGE = 26.0    # ...unless it is thicker than this: that is a black slab, and it fills
RIBBON_CAP_PAGE = 26.0    # a recovered ribbon's centerline may be drawn this wide (else 1.2 x
                          # FILL_THICK_PAGE = 10.8, which would clip a bold line back to thin)

# ================================================================ THE FORM PASS CANNOT GAP
# A streamline stops at the mask edge, at a cell another line owns, or is dropped under min_len,
# and both fill painters then book the WHOLE core as painted -- so what it missed stayed paper.
# The flow pass now measures its own coverage and paints the
# rest with the rows it replaced. Same-color overlap is one layer on the device, so it is free.
FLOW_FILL_REPAIR = True
# ================================================================ UPSCALE TO THE PAGE
# One pre-decomposition action on the source: upscale and anti-alias (a high
# quality AA) if the image will land on a larger final canvas area, which also helps jaggedness.
# A 200 px source in a 1200 px box gives SIX page px per source px: every measured
# length is quantized to that step (the thickness variance) and every contour is that staircase
# magnified (the jaggedness). The grid is still the source -- resampled up, with the LANCZOS the
# grid was always built with, until one grid px is one PAGE px. Beyond that there is nothing on
# the page to hold the detail.
# OFF by default: upscaling slows the run down and produces artifacts that destroy the
# decomposition in some areas.
# Measured: 4-6x the strokes on a small source, and it made the holes WORSE (0.199 -> 0.223 of the
# source's non-paper area left white) because LANCZOS rings on a hard edge and the halo classifies
# as its own thing. The two things it was doing for us are now done properly instead -- a bold
# outline is a line because of RIBBON_LINES, and a thin mark survives because of DESPECKLE_MAX_PPG.
UPSCALE_TO_PAGE = _os.environ.get("RM_UPSCALE", "0") == "1"
UPSCALE_MIN = 1.25        # below this the source is already near page resolution: leave it alone
UPSCALE_MAX = 8.0         # a thumbnail does not become a painting; past 8x it is inventing edges
UPSCALE_MAX_PX = 2.4e6    # grid budget. The page itself is 1404 x 1872 = 2.6 Mpx
FLOW_COV_SLACK = 0.85

# ================================================================ despeckle
# THE DESPECKLE IS FOR PHOTOGRAPHS. quantize()'s 3x3 median "erases every line thinner than 2 px"
# (its own comment). In a photograph at one grid px per page px that line is unprintable noise; in
# a 512 px illustration blown onto a 1200 px page it is a mouth, and it is lost.
# OFF (0.0). Gating it on resolution was not enough: on a 1024-px source it still
# ran, and MEASURED there it erased 12.8% of the picture out of every class mask -- unclassified
# pixels went from 1.2% (the genuine paper) to 14.0%. That is a mustache that kept vanishing,
# a forest floor going white and a cheapened look: a 3x3 median removes everything thinner
# than 2 px, and a beard, leaf litter or fur is nothing but structure thinner than 2 px. Removing
# specks is absorb_specks's job now, and it absorbs them into the neighboring zone by color
# instead of deleting them. Set above 1 to bring the median back for a specific picture.
DESPECKLE_MAX_PPG = 0.0

# HOLES IN THE FILL. Between a color region and its ink outline lies the anti-aliased ramp, which
# is neither; growing color ONE grid px into it left a sliver of paper in some pictures, and holes
# in the fill are a defect that needs fixing. Ink is drawn after color, so
# growing the wash under the line is free.
# ZERO. Growing every color zone into its neighbor closes the hairline of
# paper along shared edges, but it does so by OVERLAPPING two different colors -- and the
# highlighter composites as a per-channel MINIMUM, so yellow over blue is literally green, and the
# fill spills out of the borders. The classes are
# already a partition, every pixel belongs to exactly one zone, and the painter's job is to cover
# its own zone to the edge and not past it. Closing a gap by overlapping was a band-aid.
COLOR_GROW_G = 0

# SHADING IN THE FILL'S OWN COLOR, DARKER (off). A chromatic region would hatch in the nearest of
# the eleven pen colors to its own mean hue; an achromatic one still hatches in black.
# Tried and reverted: coloring the hatch put same-hue on same-hue and flattened the picture.
# What is wanted is COLOR BEHIND THE HATCH. Black hatch over a colored wash is shading.
# Black hatch over bare paper is not.
HATCH_IN_COLOR = False
HATCH_COLOR_MIN_CHROMA = 10.0   # below this the region is gray and black hatch is right

# PUT THE BODY OF COLOR BEHIND THE HATCH. Where hatching is applied it needs the body of color
# behind it. The hatch runs
# over the achromatic classes, which are drawn as LINES and never washed -- and over anything the
# color pass dropped for being too small a component, which on a textured beard is all of it. So
# before a band is hatched, whatever it covers that no color class painted is washed in that
# patch's own mean color. It only ever adds paint where the hatch was already going.
HATCH_UNDER_WASH = True
HATCH_UNDER_MIN_G = 6            # a patch narrower than this in both axes is the ramp beside a
                                 # line, not a region: washing it would fatten every line

# A FLAT SHAPE STILL HAS A FORM: ITS OUTLINE. The flow field falls back to a FIXED 38 degrees where
# the structure tensor has no coherence, which is most of any flat illustration -- so the "form"
# strokes were just the old diagonal hatch. The fallback is the
# region's own distance transform: the tangent perpendicular to its gradient runs parallel to the
# boundary, so a fill runs concentrically around the shape and a strand runs along the strand.
FLOW_SHAPE_FALLBACK = True
FLOW_SHAPE_SMOOTH = 2.0          # blur on the distance transform: the medial axis is a ridge and
                                 # its gradient is unstable exactly there     # a stroke is credited with this fraction of its true half-width, so the
                          # repair errs towards painting a pixel twice rather than not at all
FLOW_FILL_WIDTH = 1.0                # stroke width multiplier. A mark reads as a MARK when it is bold enough
                                     # to see one of: at 1.0 the fill is the 4-grid-px rows it always was.
FLOW_SIGMA = 4.0                     # grid px the structure tensor is smoothed over: how far a stroke runs straight
FLOW_PRE_BLUR = 1.2                  # blur before differentiating: noise is not structure
FLOW_MIN_COHERENCE = 0.05            # below this the field is noise -> the fixed angle, i.e. the plain hatch

# ================================================================ A CEL PASS FOR COLOR
# A cel shader helps identify the fill zones. The hatch has one (cel_regions). Color needs one
# too -- median-cut works per pixel, so a textured
# area shatters into hundreds of slivers that all fall under the component floor and are dropped.
# That is the missing fill behind the hatch, the shredded beard, and the wash that came out as a
# mesh of thin lines. The CLUSTER MAP is majority-filtered at this radius (grid px) before the
# classes are built; ink keeps its own cluster so a line is never swallowed.
CEL_COLOR_R = 2
# The narrowest stroke the wash pass will lay down, in page px. A tip or a one-pixel core still has
# to be painted with something; below this the highlighter has nothing to give.
HL_MIN_PAGE = 3.0   # finest highlighter stroke worth laying down, page px

# ================================================================ CEL-SHADE TO THE DEVICE
# Cel shade to the tablet's color accuracy, or slightly below it, and then use line art, edge
# detection, wash filling and hatch shading accordingly. Median cut picks 64 clusters to minimize
# RGB error, and most of the distinctions it draws are ones the panel cannot show -- which is how a
# beard becomes forty interleaved zones, none big enough to paint. Any cluster within this Lab
# distance of a bigger one is merged into it, biggest first.
# A threshold of 12 looked principled: it is the SMALLEST GAP IN THE PANEL'S OWN PEN PALETTE. Of the
# nine colors the Paper Pro draws with its pens, the closest pair (red and magenta) are 11.7 dE
# apart and the next (cyan and gray) 12.8. But it was WRONG: it reduced the color zones
# significantly, where hundreds of colors were wanted (more gamut). The gap between the nine PEN
# colors is not the same thing as what the panel can DISPLAY -- Gallery 3 mixes four
# pigments per pixel and reMarkable quote over 20,000 colors. So the merge removes
# near-duplicates only: quantization noise goes, real color stays.
CEL_DE = 3.0
# ...and no palette entry is more saturated than the display can reach. None = leave the color
# alone and let the device compress it (which it does, perceptually, better than a hard clip).
DEVICE_CHROMA_MAX = None

# THE PANEL'S OWN BOX, from the one public measurement that exists of a reMarkable Paper Pro
# (nine pen colors photographed against a white card; no instrument reading exists and
# reMarkable publishes no profile). White measures L* 69.4 and black L* 30.4 -- 39 L* units of
# range, a contrast ratio near 6:1 -- and the most saturated color on the panel is C* ~= 30
# (yellow 30.6, blue 29.7), against 97-134 for the matching sRGB primaries. These are used ONLY to
# measure distances for the cel merge, never to alter a color that gets painted.
DEV_L_LO, DEV_L_HI = 30.0, 69.0     # (not applied: see _device_lab)
# The ceiling is deliberately far above the panel's measured C* ~30. Clamping to 30 made every
# saturated color the same color for merging purposes, which threw away exactly the gamut that
# is wanted. The device compresses out-of-gamut color perceptually and does it better than a clip; our
# job is to hand it the most color we can, not to pre-flatten it.
DEV_CHROMA_CEIL = 70.0

# ================================================================ HATCH ONLY WHAT IS SHADED
# Hatching should not be used as a blanket compromise, or it ends up over everything, light or
# dark, when stylistically it is most appealing for shadows, gradients and the like. So the
# decomposition has to know whether something is a shadow. It can:
# A SHADOW IS A DARKER VERSION OF ITS NEIGHBORS COLOR: paint in
# shade keeps its hue and loses lightness, a different object arrives with a different hue. A zone
# is shade if it borders a lighter zone of the same hue across a SOFT edge. See rm_paint.shadow_zones.
SHADOW_HATCH = True
SHADOW_L_STEP = 6.0       # L* a zone must be below its neighbor before it is a step at all
SHADOW_HUE_TOL = 22.0     # degrees of hue it may drift and still be the same paint (shade cools a
                          # little, ambient light being blue, so this is not zero)
SHADOW_MIN_CHROMA = 6.0   # below this both zones are gray and hue is meaningless: judge by L alone
SHADOW_MIN_BORDER = 12    # grid px of shared border before a pair is worth judging
SHADOW_EDGE_BLUR = 1.5    # the scale a shadows edge lives at
SHADOW_MAX_EDGE = 9.0     # mean gradient across the border above which it is a DRAWN edge, not a
                          # shadow's: an objects boundary is sharp, a shadows is not
# A majority window that straddles two thin dark shapes fills the light gap between them and they
# fuse (a violin's pegs got merged). A pixel may only take a label within this much luminance (0-255) of its own, which lets
# confetti merge and leaves every edge where it is.
CEL_MODE_MAX_DL = 26.0
# Only zones below this percentile of the pictures own lightness may count as shade. Every tonal
# step borders a lighter one of its own hue, so without this four zones in five were called shadow
# and the hatch went back over the whole picture.
SHADOW_L_PCT = 35.0
# A LINE CORE IS THIN; A SHADOW IS THICK. Solid black marker is for ink. Measured on a forest photograph:
# 37%% of the picture classified black, one component covering 29%% of the grid, filled solid -- the
# floor, both portraits and the castle ground came out as slabs. A black region thicker than this
# (2*area/perimeter, page px) is painted as a wash of its own mean color instead, and keeps its
# hatch. A bold outline at 12-18 page px stays a fill; a mass does not.
BLACK_MASS_THICK_PAGE = 24.0
# With color under it the hatch is texture, not a way of making darkness, so it opens up: one
# direction instead of two crossed, and this much extra pitch. At 1.0 with two families the dense
# band covered over half its area in black and read as a dot screen over the fill.
TC_HATCH_PITCH_MUL = 1.35   # denser than 2.2: more hatch was wanted, not less
# The MARKER spiral, same shape as the wash one: start at the finer end so the edge is exact, grow
# inward. 4 page px is roughly the 3-4 grid px ring and rows this replaced at a typical ppg.
# The ceiling has to be generous or a large solid area fills in many narrow rings that ABUT, and
# every seam between them shows as a concentric contour -- visible as rings across the bicycle's
# black ground. A pen is opaque and the strokes are the same color, so overlapping costs nothing.
MARKER_WIDTHS_PAGE = (48.0, 4.0)

# The last line of defense: rasterize every stroke back onto the grid and paint anything the
# classifier called non-paper that no stroke actually covers. It is what makes "nothing is left
# unpainted" a fact instead of an intention. p["backstop"] reports the share it had to fix.
FILL_BACKSTOP = False   # REMOVED: there should be no repair passes in the decomposer; the geometry has to be right.
# A stroke may taper along its length but it may not SPIKE: every point is capped at this multiple
# of its own branchs median width. The width comes from the whole components distance transform, so
# at a junction it is the distance out of the combined shape, and a violins peg was welded to its
# neck by the fat stroke that produced. 0 turns the cap off.
LINE_WIDTH_SPIKE = 2.0
# Whether the dark achromatic range (between the ink core and mid-gray) is washed as well as
# drawn. Washing ALL of it means the anti-aliased ramp beside every line is washed too, which
# fattens the line by its own halo -- measured on a violin drawing, 3x the black area of the source.
# Off: the ramp belongs to the line pass, and a dark area that is a real region still gets color
# from the hatch-under-wash pass.
DARK_GRAY_WASHED = False
# How much wider than its nominal width a stroke is CREDITED with painting, when deciding what is
# still uncovered. It was 0.35 px and that is exactly the size of the pinholes it left: paper in
# the middle of a solid fill, because the repair believed the gap was already painted. Zero means
# the model matches the renderer; negative would make the repair paranoid.
COVER_GRACE = -0.25
# A speck is absorbed into a neighboring zone only if that neighbor is within this Lab distance
# of it. Beyond it the speck is a FEATURE, not texture, and keeps its own color -- absorbing
# everything into the nearest zone cost a portrait an eye.
ABSORB_MAX_DE = 18.0
SPIRAL_MAX_PASSES = 64
# A speck is absorbed into a neighboring zone only when that neighbor is within this Lab
# distance of it. Beyond it the speck is a FEATURE, not texture, and keeps its own color --
# absorbing everything into the nearest zone cost a portrait an eye.

# A component smaller than this on the PAGE is not worth a stroke. Converted to grid px through
# ppg, so it means the same thing whatever resolution the source is.
DRAW_MIN_PAGE = 7.0
# ...and an area floor in grid px, so a one or two pixel fleck never becomes a stroke however big
# it lands on the page. Without it a 200-px source drawn at six page px per source px turned every
# anti-aliasing fleck into ink and came out half again as heavy as the picture.
DRAW_MIN_AREA = 6
# The dark achromatic range is a LINE class. Where it forms a REGION it also needs paint, or a
# tonal picture is hatch over bare paper; where it is only the ramp beside a line it must not be
# washed, or every line gains its halo as width. An opening at this radius (source px) separates
# the two.
TONE_REGION_WASH = True
TONE_REGION_OPEN = 1.5
# Mean luminance gradient INSIDE a zone (away from its edges) below which the zone is flat, and a
# flat zone is a color rather than a shadow however dark it is. Without it an art nouveau panels
# dark blue ground was hatched edge to edge and read as a net over the color.
SHADOW_MIN_INTERNAL_GRAD = 2.2

# The finest marker stroke worth laying down, page px. The border pass of a pen fill starts here
# so the loop hugs the shape and thin parts still have a contour to trace.
MARKER_MIN_PAGE = 2.0
# A component this small (grid px) is the anti-aliased boundary between two zones, whatever its
# color, and is given to the neighbor it matches best. Above it a component is a feature and is
# DRAWN. Measured: with a color gate instead, flat art came out 4.7%% speckled with paper.
ABSORB_MAX_AREA = 12
# PAPER IS THE COLOR THE PAGE ALREADY IS, and nothing else. At L* 92 with a little chroma the
# old test swallowed cream, ivory and warm off-white: a foxs cheek fur is L* 93 chroma 8 and came
# out as bare paper, which is 5%% of that picture blank. Nothing here is a taste call -- if the
# tablet would have to lay down ink to make the color, it is not paper.
TC_PAPER_L = 96.0
# The single hatch angle. There is one density and one direction; where hatching belongs it looks
# the same everywhere, and where it does not belong there is none.
HATCH_ANGLE = 38.0
# Where the single hatch becomes a crossed one, as a fraction of the shaded darkness range. Two
# densities, both uniform: shade, and deep shade.
HATCH_CROSS_AT = 0.55
# The second direction. Not a right angle to the first -- a lattice reads as a screen; an oblique
# cross reads as drawn.
HATCH_ANGLE_2 = -34.0
# How much of the previous loop each loop re-paints. 0.5 = half a stroke of overlap: each wash loop
# covers 50%% of the previous stroke, not just marginally.
# Nothing can fall between two loops even if the geometry is a pixel out.
LOOP_OVERLAP_FRAC = 0.5
# Black ink is traced and filled with loops, exactly like a wash, instead of being drawn as a
# skeleton centerline carrying a measured width. The skeleton wanders, lumps at junctions and made
# every dark mass a blob with wavy edges.
# Thin ink is a CENTERLINE, thick ink is a traced FILL -- the split draw_component already makes by
# width. Sending everything down the fill path put a closed loop around every 1-px line, which is
# two nearly-coincident paths with rounding on both: the line work boiled on an oak, a rose,
# a ship and a robot. Sending everything down the LINE path is what made the fox leg spaghetti.
INK_AS_FILL = True
# WHICH DARK PIECES ARE INK. Black lines in the source are valid and should be inked in the decomposition,
# but runaway edge detections must not put black all over the place where there is none. The good lines
# are long, are edges, do not appear everywhere they could, and look good; polka dots do not need ink.
# The ink mask takes every dark neutral pixel (L* < INK_L), so on a painting the dark paint
# between brush marks was filled solid black: a self-portrait painting inked 8% of the drawing where 0.8% of the source
# is black, 58,827 strokes, and its busiest area is the hardest to see for the ink. Measured on nine
# pictures: shape alone cannot tell a drawn line from dark paint (that painting's cracks are thin, long and more
# line-like than an owl drawing's outline pieces); two things can. (1) A BLACK CORE: a drawn line has truly black pixels
# (the 'black' class, L* < BLACK_L and neutral); dark paint has none. At a 10% core the owl, castle, koi and adventure
# scene keep 96-100% of their ink area, the self-portrait 13%, a pearl painting 1%. (2) For a piece without a core, LONG
# AND SPARSE: another painting's good background lines are >= 30 page px long and sit at 1-3 ink pieces per 100 x 100
# page px; the self-portrait's cracks are as long but sit at 6-17. A dark piece that is neither goes the mass way: a
# wash of its own color, left to the hatch.
# INK_CORE_MIN = 0 switches the whole rule off (everything dark and neutral is ink).
INK_CORE_MIN = 0.0            # share of a piece's pixels that must be truly black for it to be inked (0 = rule off)
INK_LINE_MIN_LEN_PAGE = 30.0  # a piece without a core is still inked when it is at least this long (page px)...
INK_LINE_MAX_DENSITY = 3.0    # ...and no denser than this many core-less ink pieces per INK_DENSITY_CELL_PAGE square (3x3 smoothed)
INK_DENSITY_CELL_PAGE = 100.0
# BLACK IS INK, AND INK IS NEUTRAL. Dark is not the same as black: the corners of an art nouveau
# panel are a dark brown at L* 7 with chroma 7, and calling them ink painted 80%% of them solid
# black and threw the color away. The panel cannot show L* 7 anyway -- its own black is L* 30 --
# so a dark brown is better served by being painted dark brown. Only a near-neutral dark pixel is
# ink.
BLACK_CHROMA = 20.0   # reverted: at 6 the dark structure of a painting fell out and it washed out
# The black threshold for a picture that HAS a dark field -- a painting or a photograph, where
# dark areas are color in shadow rather than ink. Line art keeps BLACK_L (12), where dark really
# is ink and an outline must fill solid.
BLACK_L_FIELD = 3.0
# Opening radius (source px) that separates a real gray TONE from the anti-aliased skirt of a
# drawn line. What survives is painted; what does not belongs to the line. 0 turns it off.
GRAY_HALO_OPEN = 1.0
# An ink component whose greatest THICKNESS is at or under this (page px) is drawn as one
# centerline; anything thicker is traced and filled. The decision is made once for the whole
# component so a single outline is never half line and half fill, which is what dashed it.
INK_ONE_METHOD = True
INK_THIN_PAGE = 20.0
# A shape whose greatest half-thickness is at or under this (grid px) is traced WITHOUT
# simplification or corner rounding. Smoothing the outline of a one-to-three pixel line lets its
# two sides wander independently, which is what makes line work boil.
INK_NO_SMOOTH_DEPTH = 2.5
# Paint a whole color zone in one call rather than once per connected piece. The loop geometry is
# per-pixel-depth either way, so the result is the same; the cost is not.
ZONE_AT_ONCE = True
# A shape thinner than INK_THIN_PAGE on the page is drawn as one stroke along its medial axis at
# its own width, instead of by tracing its outline. Contour tracing is unstable at two or three
# pixels: a plain ring measured 75%% unpainted at 2 px, 0%% at 3 px and 114 strokes at 5 px.
THIN_AS_MEDIAL = True
# A gray component is a lines anti-aliased skirt only if at least this share of it lies beside
# ink. Below that it goes somewhere of its own and is a real stroke -- a ships rigging line meets
# a mast at one end and runs away across the picture.
GRAY_HALO_SHARE = 0.85
# Half-window for smoothing a medial strokes width profile. The width is measured afresh at every
# point and the raw profile pulses; the path itself is smoothed once by the same reasoning.
MEDIAL_SMOOTH = 4
# Join skeleton fragments that meet end to end. A skeleton returns one piece per graph edge, so a
# single outline arrives as dozens of segments and each gets its own round cap -- the line reads as
# a string of beads. At a junction the straightest continuation wins.
CHAIN_SKELETON = True
CHAIN_MIN_COS = 0.2       # how sharply a continuation may turn and still count as the same stroke
# How far apart two skeleton fragments ends may be and still be joined into one stroke, in grid
# px. Measured on the foxs outline: the median gap between neighboring pieces is 3.0 px, so
# anything under that joins nothing. The jump is inside the ink, so it costs nothing to cross.
CHAIN_TOL = 6.0
# Share of the picture in genuinely chromatic zones above which it is a PAINTING rather than a
# drawing. A paintings dark areas are shadow and get washed; a drawings dark areas are ink and get
# filled. `_DARK_FIELD` cannot tell them apart -- it is true of the oak and the skull as well.
PAINTERLY_CHROMA_SHARE = 0.10
# The thickness above which a dark region is a MASS and gets washed in its own color instead of
# filled with marker, on a PAINTING or photograph. Lower than the line-art figure because a
# paintings darks are shadow: only a genuinely thin run there is line work.
BLACK_MASS_THICK_PAINT = 8.0

# INK IS NEUTRAL, AND "NEUTRAL" DEPENDS ON HOW DARK IT IS. Lab chroma falls with lightness along a
# blend toward black, so a single chroma cap (TC_INK_CHROMA) calls a saturated dark color "gray":
# the corners of an art nouveau panel are a warm field at L* 12 / chroma 8, and every one of those
# pixels was classed `tone` -- 83% of the corner -- which washed the field and the gold scrollwork
# in it as one mass. The ink rungs therefore also require chroma < INK_SAT x L. A neutral ramp is
# s ~ 0 at any lightness; that corner is s = 0.68.
INK_SAT = 0.40
INK_NEUTRAL = 3.0     # ...but a color this close to gray is neutral at ANY lightness, and pure black
                      # sits at L* 0 where no multiple of L can clear a floor. Same reasoning, and the
                      # same value, as CEL_DE: under ~3 the difference is not a color.

# THE CHAMFER TRANSFORM MEASURES PIXEL CENTERS. The outermost pixel of a mask reads 1.0 but its
# center is only half a pixel inside the edge the eye sees, so the geometric depth of the contour
# at chamfer level t is t/3 - EDGE_HALF_PX. At 0 the border pass sits half a pixel outside its own
# zone, and since the highlighter composites as a per-channel MINIMUM that half pixel can only
# darken the neighbor: every zone of a test panel rendered 15-20% darker than the color it was
# given, and the wash "burst out of the linework". 0.0 gives the unadjusted convention for comparison.
EDGE_HALF_PX = 0.25

# How much of the border pass's reach to hand BACK to the medial rescue. The loops paint half a
# stroke either side of their outer contour; at 0 the rescue starts exactly where that ends, at 1
# it starts a pixel earlier and the two overlap. Overlap is free (same color, minimum blend) and
# it is what keeps a fur stroke whole where the outline it joins is only just thick enough.
THIN_RESCUE_SLACK = 1

# Does the medial rescue get the whole mask, or only the parts the loops cannot reach? The whole
# mask keeps a skeleton continuous, which is what stops an outline coming out as a string of beads.
THIN_RESCUE_WHOLE = False

# A ramp belongs to what it ramps FROM. The gray-halo rule hands a gray band beside black ink back
# to that line; this does the same where the band lies beside a dark COLOR instead, because a 20%
# blend of a navy outline toward white is L* 30 / chroma 9 -- neutral for its darkness, and under
# INK_L -- so it was classed `tone` and drawn as black beads along a navy line. TONE_RAMP_L is how
# dark a color zone has to be to cast such a ramp; the share a component must have beside one is
# GRAY_HALO_SHARE, the same 0.85 the ink rule uses.
TONE_RAMP_TO_COLOR = False
TONE_RAMP_L = 45.0

# An ink speck smaller than the pen can draw AT ITS TRUE SIZE, sitting where a color zone already
# paints, is that color's anti-aliased edge -- not a mark. At a 200 px source one page pixel is
# six of them, so a navy outline's fringe reached the page as 245 black dots strung along it.
# Both halves matter: dropping a speck that nothing else covers would leave paper, so a speck on
# bare paper (an eye, a nostril, the ship's finest rigging) is still drawn.
INK_SPECK_ON_COLOR = True
INK_SPECK_COVERED = 0.9
