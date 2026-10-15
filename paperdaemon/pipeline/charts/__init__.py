r"""rm_chart -- a chart the model DESCRIBES, rendered for real, then traced.

The model should have a real chart creation tool, not an image generator: a chart-defining language
that can be fed to a script. This is it. The model emits a narrow JSON spec -- never code -- which is
validated as data and compiled to Vega-Lite, then rasterized by vl-convert. One pip wheel, no Node,
no browser, and verified to render with every socket blocked.

Measured while choosing it, against matplotlib, plotly and pygal on the same three charts:

  * Crispness is decided by STYLING, not by the library. Default matplotlib gave 973 colors and
    32% blended pixels; the same library tuned gave 17 and 5%. This path gives 2-3 colors and
    0.00%, which is what traces cleanly.
  * resvg anti-aliases unless BOTH shape-rendering="crispEdges" AND text-rendering="optimizeSpeed"
    are set. Neither alone is enough: 29 colors / 17.8% mush with neither, 29 / 38.6% with shapes
    only, 20 / 8.1% with text only, 2 / 0.00% with both.
  * plotly needs a Chromium subprocess and was 30x slower warm. pygal draws bars with no stroke, so
    a white series is invisible on white. gnuplot has no pip package at all.

Then decomposed through UI mode at the box rm_plan gives a large chart, 1450x1000: bar 3,071
strokes, line 2,707, hbar 3,463, under a second each, every label and value legible. For scale the
heaviest page ever pushed to the tablet was 17,106.

RENDER BETWEEN 1200 AND 1620 PX WIDE. UI_GRID_MAX is 1620 and the decomposer never upsamples, so
anything in that range is traced at full resolution. Below it, a 1-px rule becomes gray and the
thin-gray pass drops it -- that is how a whole line chart once came out as 66 strokes.

THE FONT IS A TRAP. vl-convert silently drops every piece of text for a font it does not have: no
error, no warning, a chart with perfect geometry and no labels at all. Arial, Segoe UI and Calibri
work here; DejaVu Sans and Helvetica render nothing. check_font() catches it at import rather than
letting it reach the page.
The house spec, which is the entire surface the model sees:

    {
      "type":       "bar" | "hbar" | "line",
      "title":      "Regional Revenue by Quarter",
      "x_label":    "Quarter",
      "y_label":    "Revenue (M USD)",
      "categories": ["Q1", "Q2", "Q3", "Q4"],
      "series":     [{"name": "North", "values": [42, 55, 61, 58]}],
      "value_labels": true
    }

At most four series; `hbar` takes exactly one and labels its bars. Small enough that a 27B model
does not drift, and every field is checked before anything renders. A title containing
`__import__('os').system('calc')` is accepted and drawn as inert text -- nothing here is ever
evaluated.
"""
from __future__ import annotations
import json
import threading
import os
import re

_FONT_READY = False


def _vlc():
    """vl_convert, imported on FIRST USE rather than at module load.

    It was a top-level import, and rm_host.py imports this module, and the daemon's venv did not
    have the wheel -- so the HOST died on import, instantly, every time, and never processed a job.
    Nothing said so: it looked like the loop simply was not running. One optional dependency of one
    tool must not be able to take down the worker; now a missing wheel costs you chart(), and the
    error says which wheel and which interpreter.
    """
    try:
        import vl_convert
        global _FONT_READY
        if not _FONT_READY:
            vl_convert.register_font_directory(_ensure_font())
            _FONT_READY = True
        return vl_convert
    except ImportError as ex:
        import sys
        raise SpecError("the chart renderer is not installed in this environment (%s). "
                        "Install it with:  uv pip install --python %s vl-convert-python"
                        % (ex, sys.executable))


# ---------------------------------------------------------------- constants
# THE TABLET'S OWN LETTERING. rm_text.G is the single-stroke font the device writes with;
# charts/font.py stretches each polyline into a filled outline and saves a real TTF, because
# Vega-Lite draws its own axis and legend text and cannot be handed paths. Built on demand and
# registered with the renderer at import -- vl-convert drops every glyph of a font it cannot
# find, silently, so a missing file has to be a loud failure instead.
FONT = "Remarkable Mono"
from paperdaemon import paths as _content
FONT_DIR = _content.generated_fonts_dir()


def _ensure_font():
    """Build the TTF if it is missing OR older than the glyph table it is made from.

    The letterforms live in draw/lettering.py and get edited there. A font file that only got built when
    absent would keep serving the old shapes for ever after; comparing mtimes makes an edit to a
    glyph show up on the next render.
    """
    f = os.path.join(FONT_DIR, "RemarkableMono-Regular.ttf")
    pipeline = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # THREE sources, not one: rm_serif replaces most of the lowercase on import, and rm_font is
    # the builder. An edit to either of those changed the letters and left the file alone.
    srcs = [os.path.join(pipeline, *n) for n in (("draw", "lettering.py"), ("draw", "serif.py"), ("draw", "accents.py"),
                                                 ("charts", "font.py"))]
    newest = max([os.path.getmtime(x) for x in srcs if os.path.exists(x)] or [0])
    stale = not os.path.exists(f) or newest > os.path.getmtime(f)
    if stale:
        from paperdaemon.pipeline.charts import font as rm_font
        rm_font.build(f)
    return FONT_DIR
# Average glyph advance as a fraction of the font size, for the places that have to
# measure a string before drawing it. Times is appreciably narrower than Arial, and the
# fitting code was tuned against Arial.
EM = 0.50                # the heavier pen's wider spacing (charts/font.py SIDE) widens every advance by ~6.6%
CAP = 0.66               # cap height, for matching an icon to a number
WIDTH = 1200             # target total PNG width in px
# WHITE FIRST, and it matters. Every bar carries a black outline, so a white fill is still a
# legible bar -- and a solid-black first series made a single-series chart 55.7%% dark pixels, which
# the decomposer UI mode reads as a DARK THEME and inverts: gray ground, white bars, wrong. Starting
# light drops that to a few percent, and costs the tablet far less ink besides.
# A DESATURATED PALETTE, chosen rather than measured.
#
# Not the reMarkable's own eleven pens and six highlighter washes: the device's highlighter yellow
# (#FFED75) and magenta (#F29EFF) are not colors anyone wants to look at on a screen, and the
# decomposer's pixel mapping is not a reason to constrain the palette.
#
# So: one family, even hue spacing, fills at roughly S28 L78 and inks at S34 L42. Every fill is
# light enough to take black text, which also kills the dark-theme trap -- a solid dark first
# series made a single-series chart 55.7% dark pixels, and the decomposer's UI mode reads that as
# a dark theme and inverts the page.
#
# The old names (blue, orange, green, magenta, yellow, gray) still resolve, because every spec in
# the gallery and every page a model has written uses them; they just resolve to better colors.
WASH = {
    "blue": "#B4C7D9", "teal": "#A9CBC9", "green": "#BCCFAB", "yellow": "#E0D2A4",
    "orange": "#DEBFA3", "red": "#D9B3AC", "magenta": "#CDB4C6", "plum": "#BEB6D0",
    "gray": "#CBCBCE", "white": "#FFFFFF",
    "ice": "#CFDDE9", "pale": "#E4E4E7",          # snow, and a windy day
}
WASH.update({"sage": WASH["green"], "clay": WASH["orange"], "sand": WASH["yellow"],
             "rose": WASH["magenta"], "slate": WASH["gray"], "cyan": WASH["teal"],
             "pink": WASH["magenta"], "lime": WASH["green"], "purple": WASH["plum"]})
# INKS: the same hues taken down to a line weight you can read on white.
INK = {
    "black": "#2E3136", "blue": "#4E6E8E", "teal": "#46807C", "green": "#6B8551",
    "yellow": "#96813F", "orange": "#A0703F", "red": "#9E5A4E", "magenta": "#8C5C7F",
    "plum": "#6C6491", "gray": "#5E6066",
}
INK.update({"sage": INK["green"], "clay": INK["orange"], "sand": INK["yellow"],
            "rose": INK["magenta"], "slate": INK["gray"], "cyan": INK["teal"],
            "pink": INK["magenta"], "lime": INK["green"], "purple": INK["plum"]})
# One dark gray for structure: rules, grid, cell borders, and every icon that has no reason to be
# colored: icons should mostly just be the same dark gray.
GRAY = "#3F434A"
RULE = "#8A8D93"
# Series order, chosen so neighbors stay distinct.
PALETTE_NAMES = ["blue", "orange", "green", "plum", "yellow", "teal", "red", "gray"]
PALETTE = [WASH[n] for n in PALETTE_NAMES] + [WASH["white"]]
LINE_INK = [INK[n] for n in PALETTE_NAMES]
DASHES = [[1, 0], [11, 7], [3, 5], [13, 5, 3, 5]]
SHAPES = ["circle", "square", "triangle", "diamond"]
MARKER_FILL = LINE_INK          # a marker in its own line's ink
MAX_SERIES = 6                  # six distinguishable series is already a busy tablet page
# Everything the model may ask for. bar/hbar/line are the original three; the rest add variety, and
# each earns its place on e-ink: pie and donut read off their own labels rather than a legend,
# heatmap uses the one encoding a grayscale device has, table and calendar are grids of text and
# trace almost perfectly.
TYPES = ("bar", "hbar", "line", "area", "scatter", "stacked", "pie", "donut",
         "heatmap", "waffle", "funnel", "gauge", "timeline", "gantt",
         "table", "calendar", "week", "agenda", "checklist", "habit", "yearmap",
         "cards", "progress",
         "candle", "radar", "dist", "violin", "sankey", "pictograph", "map",
         "stock", "bullet", "slope", "dumbbell", "bump", "matrix", "sparkbars", "quadrant",
         "waterfall", "histogram", "bubble", "lollipop", "diverging", "pyramid", "marimekko",
         "treemap", "venn", "ridgeline", "polar", "tree", "flow", "kanban", "journey", "clock",
         "step", "posts")
# Types that do NOT take categories/series -- they carry their own shape and are dispatched
# straight to a builder. Kept in ONE place; it used to be spelled out three times and a new type
# added to two of them fell through to the generic validator and rendered as a bar chart.
GRIDLIKE = ("table", "calendar", "week", "gantt", "cards", "progress",
            "agenda", "checklist", "habit", "yearmap", "timeline", "waffle",
            "funnel", "gauge", "candle", "radar", "dist", "violin", "sankey",
            "pictograph", "map", "stock", "bullet", "slope", "dumbbell",
            "bump", "matrix", "sparkbars", "quadrant",
            "waterfall", "histogram", "bubble", "lollipop", "diverging", "pyramid",
            "marimekko", "treemap", "venn", "ridgeline", "polar", "tree", "flow", "kanban",
            "journey", "clock", "posts")

# Rules and fills crisp (resvg anti-aliases shapes by default). TEXT STAYS ANTI-ALIASED: the font's strokes are
# thinner than a pixel at label sizes, and drawn without anti-aliasing a stem that misses the pixel centers is not
# drawn at all -- the weekday header read "-ue" and "-hu" (T and M lost their stems).
_CRISP = 'shape-rendering="crispEdges" text-rendering="geometricPrecision" '


# ---------------------------------------------------------------- validation
class SpecError(ValueError):
    pass

from paperdaemon.pipeline.charts.tabletop import TYPES as TABLETOP_TYPES
TYPES += TABLETOP_TYPES


# ---------------------------------------------------------------- what each type can DO
# The model is only as capable as what it is told at the moment it writes a spec. Without being told
# that a week day carries a card, it writes a text list over the calendar when asked for "on this
# day" facts. This is the card it is given at every chart or calendar step: one line per type --
# what it is for, the spec's fields, and what the host fills in by itself. It sits next to TYPES
# and _validate_grid on purpose, and test_rails_offline checks that every type in TYPES has an
# entry, so the two cannot drift.
POWERS = {
    # --- numbers -----------------------------------------------------------------------------
    "bar": "compare values across categories -- categories:[...], series:[{name, values:[...]}] (up to 6 series); title, x_label, y_label",
    "hbar": "ranked bars with their labels, ONE series -- same fields as bar",
    "stacked": "parts of each category's total, bars split by series -- bar fields",
    "line": "a trend over time or order -- bar fields; several series fine",
    "area": "a trend with the volume under it -- bar fields",
    "step": "a value that changes in jumps (prices, levels) -- bar fields",
    "scatter": "two measures against each other -- bar fields",
    "pie": "shares of a whole, ONE series, at most 7 slices, no negatives -- bar fields",
    "donut": "pie with a hole -- pie fields",
    "histogram": "how values are distributed -- values:[numbers, 5+], bins (2-60)",
    "dist": "distributions side by side -- groups:[{name, values:[4+ numbers]}]",
    "violin": "dist drawn as violins -- groups:[{name, values}]",
    "ridgeline": "many distributions stacked -- groups:[{name, values:[4+]}]",
    "bubble": "three measures: x, y and size -- items:[{label, x, y, size}]",
    "lollipop": "clean ranked values -- items:[{label, value}]",
    "diverging": "values above and below zero -- items:[{label, value}]",
    "waterfall": "a total built up and down step by step -- items:[{label, value}]",
    "bullet": "progress against a target -- items:[{label, value, target}]",
    "slope": "before -> after for each item -- items:[{label, before, after}]",
    "dumbbell": "the gap between two values per item -- items:[{label, a, b}]",
    "bump": "rank changes over time -- series:[{name, values:[ranks]}], categories",
    "pyramid": "two sides per band (population pyramid) -- bands:[{band, a, b}]",
    "marimekko": "shares within shares -- columns:[{name, value, parts:[...]}]",
    "treemap": "sizes as nested areas -- items:[{label, value > 0}]",
    "waffle": "a share as a grid of squares -- parts:[...]",
    "funnel": "stages that narrow -- stages:[...]",
    "gauge": "one value on a dial -- value, min, max, label (all optional)",
    "polar": "values around a circle -- items:[{label, value}]",
    "radar": "several scores per item on shared axes -- axes:[3+], series:[{name, values}]",
    "sparkbars": "a row of tiny bar charts -- rows:[{label, values:[...]}]",
    "matrix": "items placed on two axes -- items:[{label, x, y}]",
    "quadrant": "a 2x2 (effort/impact) -- items:[{label, x, y}]",
    "heatmap": "a grid of shaded values -- bar fields (categories x series)",
    "pictograph": "counts as rows of icons -- rows:[{label, value, icon}], each (icons per unit)",
    "candle": "open/high/low/close bars -- bars:[{t, open, high, low, close}]",
    "stock": "a price line -- bars:[{t, close}]",
    "sankey": "flows from one thing to another -- links:[{from, to, value > 0}]",
    "venn": "overlap of 2 or 3 sets -- sets:[{name, ...}]",
    # --- time and plans ----------------------------------------------------------------------
    "calendar": ("A MONTH. year, month; marks:{\"14\": {events:[{text, at:\"HH:MM\", icon, kind}], "
                 "card:{year, title, text:[3 lines]}}}. AUTOMATIC -- never ask for or write these: "
                 "the forecast for each day it covers (sun/cloud/rain, highs/lows, UV, sunrise/"
                 "sunset as clock faces, wind and its direction), public holidays and observances, "
                 "the user's home place as the place. EVENTS: up to 4 a day, about 15 characters each (13 with "
                 "a time, 10 with time and icon), a line never wraps; kind = holiday|birthday|"
                 "personal|national|season|history colors its pill; icon = an icon name. CARD: an "
                 "'on this day' fact as a HAIKU (5-7-5 syllables, about 21 characters a line -- a "
                 "longer line runs over once; title ONE word; the year of the event), shown on a day "
                 "with 3 entries or fewer -- the step comes with Wikipedia's facts for the month; "
                 "3-6 cards a month; a month with six week-rows has no room for cards (use a week)"),
    "week": ("THE SEVEN DAYS FROM TODAY (or start:\"YYYY-MM-DD\"). days:{\"Thu\" or \"2026-09-24\": "
             "{events:[{text, at:\"HH:MM\", icon, kind}], card:{year, title, text:[3 lines]}}}. "
             "AUTOMATIC: the full forecast per day (sky, highs/lows, rain chance, UV, humidity, "
             "sunrise/sunset as clock faces, wind and direction, the hourly curve), holidays and "
             "observances, the user's home place. EVENTS as in calendar (up to 4 a day, ~15 characters, never "
             "wraps; kind colors the pill). CARD: an 'on this day' fact per day as a HAIKU (5-7-5, "
             "about 21 characters a line, a longer line runs over once, ONE-word title, the year) -- "
             "the step comes with the facts for its dates. News or world events of the week are EVENTS (short); "
             "anniversaries and 'on this day' facts are CARDS"),
    "agenda": "a day's schedule as a list -- items:[{start, end, text}], times like \"09:00\" (no end: an hour)",
    "timeline": "dated events along a line -- events:[{date or year, text}]",
    "gantt": "tasks over time -- tasks:[{name, start, end}] (end after start)",
    "clock": "a day as a 24-hour dial -- blocks:[{start, end, label}] (hours 0-24)",
    "habit": "a habit tracker grid -- habits:[...]",
    "yearmap": "a whole year of days as a grid (all fields optional)",
    "journey": "stages of an experience -- steps:[{label, ...}]",
    "flow": "a process as boxes and arrows -- steps:[{text, ...}]",
    "kanban": "columns of cards (to do / doing / done) -- columns:[{name, items:[...]}]",
    "checklist": "a list with boxes to tick -- items:[...]",
    "progress": "progress bars -- items:[{label, value}]",
    # --- text, grids, places -----------------------------------------------------------------
    "table": "rows and columns of text -- columns:[...], rows:[[...], ...] (up to 24 rows)",
    "cards": "a row of stat cards, one big value each -- items:[{label, value, note?}]",
    "posts": ("social posts CLIPPED onto the page as cards, laid out by the chart two to a row -- "
              "where, who, when, the title, the picture, the text, votes and replies, the top "
              "comments. The HOST fetches the real posts from source: 'r/<sub>' (Reddit; sort "
              "'hot'|'top'|'new', period 'day'|'week'|'month'|'year'|'all' for top), '4chan/<board>', "
              "'hn' (Hacker News; 'hn/new', 'hn/ask', 'hn/show'), 'bsky' (Bluesky's hot feed) or "
              "'bsky/<handle>', 'mastodon/<server>' or 'mastodon/<server>/tags/<tag>', 'x/<post "
              "link>' (one post on X). SEARCH Reddit with search: 'the words' and source 'reddit' "
              "(sitewide) or 'r/<sub>' (inside it), sort 'relevance'|'top'|'new'. count 1-4, all in "
              "ONE chart; never invent a post or write them out as a list. Instagram and Facebook "
              "cannot be read."),
    "tree": "a hierarchy -- nodes:[{id, parent, label}] (ids unique, parent an existing id)",
    "map": "points on a world or US map -- map:'world'|'us', points:[{lat, lon, label}]",
    # --- tabletop printables (their own schemas; rarely wanted on the tablet) -----------------
    "game_board": "a printable game board", "player_mat": "a player mat", "card_deck": "a deck of game cards",
    "character_sheet": "an RPG character sheet", "gm_screen": "a game master's screen",
    "encounter_tracker": "an initiative/encounter tracker", "adventure": "an adventure booklet page",
    "token_sheet": "a sheet of game tokens",
    "dialog": ("characters talking, as faces and speech bubbles -- lines:[{speaker: a character id "
               "from the game roster, emotion: neutral|happy|sad|angry|jealous|worried|relieved|thinking|"
               "surprised|smug|determined|confused|curious|hopeful|embarrassed|disappointed|skeptical|tired, text}] in order; {narrator: text} is the game "
               "master (no face, no bubble); a speaker with no text is an emote. page 'strip' fits under "
               "a board"),
}


def powers(types=None):
    """The capability card, as text: every type (or just `types`), one line each."""
    ts = [t for t in (types or TYPES) if t in POWERS]
    return "\n".join("  %-10s %s" % (t, POWERS[t]) for t in ts)


def validate(spec):
    if not isinstance(spec, dict):
        raise SpecError("spec must be a JSON object")
    t = spec.get("type")
    if t in TABLETOP_TYPES:
        from paperdaemon.pipeline.charts import tabletop as rm_tabletop
        return rm_tabletop.validate(spec)
    if t in GRIDLIKE:
        return _validate_grid(spec, t)
    if t not in TYPES:
        raise SpecError("type must be one of %s, got %r" % ("|".join(TYPES), t))
    cats = spec.get("categories")
    if not isinstance(cats, list) or not cats or not all(isinstance(c, str) for c in cats):
        raise SpecError("categories must be a non-empty list of strings")
    series = spec.get("series")
    if not isinstance(series, list) or not series:
        raise SpecError("series must be a non-empty list")
    if len(series) > MAX_SERIES:
        raise SpecError("at most %d series supported, got %d" % (MAX_SERIES, len(series)))
    for i, s in enumerate(series):
        if not isinstance(s, dict) or "name" not in s or "values" not in s:
            raise SpecError("series[%d] needs 'name' and 'values'" % i)
        v = s["values"]
        if not isinstance(v, list) or len(v) != len(cats):
            raise SpecError("series[%d] %r: %s values but %d categories"
                            % (i, s.get("name"), len(v) if isinstance(v, list) else "?",
                               len(cats)))
        for x in v:
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise SpecError("series[%d] %r: values must all be numbers"
                                % (i, s.get("name")))
    if t in ("hbar", "pie", "donut") and len(series) != 1:
        raise SpecError("%s supports exactly one series" % t)
    if t in ("pie", "donut"):
        if any(v < 0 for v in series[0]["values"]):
            raise SpecError("a %s cannot show negative values" % t)
        if len(cats) > 7:
            raise SpecError("at most 7 slices in a %s; past that the labels collide" % t)
    return spec


def _validate_grid(spec, t):
    """table and calendar carry their own shape -- cells, not series."""
    if t == "table":
        cols, rows = spec.get("columns"), spec.get("rows")
        if not isinstance(cols, list) or not cols or not all(isinstance(c, str) for c in cols):
            raise SpecError("table needs 'columns': a non-empty list of strings")
        if not isinstance(rows, list) or not rows:
            raise SpecError("table needs 'rows': a non-empty list of lists")
        for i, r in enumerate(rows):
            if not isinstance(r, list) or len(r) != len(cols):
                raise SpecError("row %d has %s cells but there are %d columns"
                                % (i, len(r) if isinstance(r, list) else "?", len(cols)))
        if len(rows) > 24:
            raise SpecError("at most 24 rows in a table; split it across pages")
    elif t in ("cards", "progress", "agenda", "checklist", "habit",
               "timeline", "waffle", "funnel"):
        key = {"cards": "items", "progress": "items", "agenda": "items",
               "checklist": "items", "habit": "habits", "timeline": "events",
               "waffle": "parts", "funnel": "stages"}[t]
        items = spec.get(key)
        if not isinstance(items, list) or not items:
            raise SpecError("%s needs %r: a non-empty list" % (t, key))
        if t == "agenda":
            _agenda_items(spec)
        if t == "progress":
            for i, c in enumerate(items):
                if not isinstance(c, dict) or "label" not in c or "value" not in c:
                    raise SpecError("progress item %d needs 'label' and 'value'" % i)
    elif t == "posts":
        posts = spec.get("posts")
        if not isinstance(posts, list) or not posts:
            raise SpecError("posts needs 'source' (e.g. 'r/pics', and the host fetches them) or "
                            "'posts': a non-empty list of {title, community, author, ...}")
        for i, p in enumerate(posts):
            if not isinstance(p, dict) or not str(p.get("title") or "").strip():
                raise SpecError("post %d needs a 'title'" % i)
        if len(posts) > 4:
            raise SpecError("at most 4 posts on one page -- ask for fewer, or another page")
    elif t in ("yearmap", "gauge"):
        pass                     # both carry only scalars, and every field has a default
    elif t == "week":
        days = spec.get("days") or {}
        if not isinstance(days, dict):
            raise SpecError("week 'days' must be keyed by YYYY-MM-DD or a weekday name, each a "
                            "list of entries or {\"events\": [...], \"card\": {...}}")
        for k, v in days.items():
            if isinstance(v, dict):
                if v.get("card") is not None:
                    _validate_card("days[%r]" % k, v["card"],
                                   _page(spec, PAGES["tablet"][0], None)[0] / 7.0)
                if not isinstance(v.get("events", []), list):
                    raise SpecError("days[%r]['events'] must be a list" % k)
            elif not isinstance(v, list):
                raise SpecError("days[%r] must be a list of entries or a dict with events/card" % k)
        if not spec.get("weather") and (spec.get("lat") is None or spec.get("lon") is None):
            raise SpecError("a week always carries the forecast: give 'lat' and 'lon' (or "
                            "weather=rm_weather.week(lat, lon, start))")
        if spec.get("start"):
            import datetime as _d
            try:
                _d.date.fromisoformat(str(spec["start"]))
            except ValueError:
                raise SpecError("'start' must be a date, YYYY-MM-DD")

    elif t in ("candle", "stock"):
        bars = spec.get("bars")
        if not isinstance(bars, list) or not bars:
            raise SpecError("%s needs 'bars': a non-empty list" % t)
        need = ("open", "high", "low", "close") if t == "candle" else ("close",)
        for i, b in enumerate(bars):
            if not isinstance(b, dict) or "t" not in b:
                raise SpecError("%s bar %d needs 't'" % (t, i))
            for k in need:
                if not isinstance(b.get(k), (int, float)) or isinstance(b.get(k), bool):
                    raise SpecError("%s bar %d needs a numeric %r" % (t, i, k))
            if t == "candle" and not (b["low"] <= min(b["open"], b["close"]) and
                                      b["high"] >= max(b["open"], b["close"])):
                raise SpecError("candle bar %d: low/high do not bracket open/close" % i)
    elif t == "radar":
        axes, series = spec.get("axes"), spec.get("series")
        if not isinstance(axes, list) or len(axes) < 3:
            raise SpecError("radar needs 'axes': at least three")
        if not isinstance(series, list) or not series:
            raise SpecError("radar needs 'series'")
        for i, s in enumerate(series):
            if not isinstance(s, dict) or "name" not in s or "values" not in s:
                raise SpecError("radar series %d needs 'name' and 'values'" % i)
            if len(s["values"]) != len(axes):
                raise SpecError("radar series %r: %d values but %d axes"
                                % (s["name"], len(s["values"]), len(axes)))
    elif t in ("dist", "violin"):
        groups = spec.get("groups")
        if not isinstance(groups, list) or not groups:
            raise SpecError("%s needs 'groups': a non-empty list" % t)
        for i, g in enumerate(groups):
            if not isinstance(g, dict) or "name" not in g or not g.get("values"):
                raise SpecError("%s group %d needs 'name' and a non-empty 'values'" % (t, i))
            if len(g["values"]) < 4:
                raise SpecError("%s group %r: need at least 4 values to show a distribution"
                                % (t, g["name"]))
    elif t == "sankey":
        links = spec.get("links")
        if not isinstance(links, list) or not links:
            raise SpecError("sankey needs 'links': a non-empty list")
        for i, l in enumerate(links):
            if not isinstance(l, dict) or not all(k in l for k in ("from", "to", "value")):
                raise SpecError("sankey link %d needs 'from', 'to' and 'value'" % i)
            if l["value"] <= 0:
                raise SpecError("sankey link %d: value must be positive" % i)
    elif t == "pictograph":
        rows = spec.get("rows")
        if not isinstance(rows, list) or not rows:
            raise SpecError("pictograph needs 'rows': a non-empty list")
        each = spec.get("each", 1)
        if not isinstance(each, (int, float)) or each <= 0:
            raise SpecError("pictograph 'each' must be a positive number")
        for i, r in enumerate(rows):
            if not isinstance(r, dict) or "label" not in r or "value" not in r:
                raise SpecError("pictograph row %d needs 'label' and 'value'" % i)
            if r.get("icon", "star") not in ICONS and r.get("icon") not in ALIASES:
                raise SpecError("no icon %r; have %s"
                                % (r.get("icon"), ", ".join(sorted(ICONS))))
            if r["value"] / float(each) > 40:
                raise SpecError("pictograph row %r would need %d icons; raise 'each'"
                                % (r["label"], round(r["value"] / float(each))))
    elif t == "map":
        if spec.get("map", "world") not in ("world", "us"):
            raise SpecError("map must be 'world' or 'us'")
        for p in (spec.get("points") or []):
            if not isinstance(p, dict) or "lat" not in p or "lon" not in p:
                raise SpecError("each map point needs 'lat' and 'lon'")
    elif t in ("bullet", "slope", "dumbbell", "bump", "matrix", "sparkbars", "quadrant",
               "waterfall", "bubble", "lollipop", "diverging", "pyramid", "treemap",
               "tree", "flow", "journey", "clock", "polar", "marimekko"):
        key = {"bullet": "items", "slope": "items", "dumbbell": "items", "bump": "series",
               "matrix": "items", "sparkbars": "rows", "quadrant": "items",
               "waterfall": "items", "bubble": "items", "lollipop": "items",
               "diverging": "items", "pyramid": "bands", "treemap": "items", "tree": "nodes",
               "flow": "steps", "journey": "steps", "clock": "blocks", "polar": "items",
               "marimekko": "columns"}[t]
        items = spec.get(key)
        if not isinstance(items, list) or not items:
            raise SpecError("%s needs %r: a non-empty list" % (t, key))
        need = {"bullet": ("label", "value", "target"),
                "slope": ("label", "before", "after"),
                "dumbbell": ("label", "a", "b"),
                "bump": ("name", "values"),
                "matrix": ("label", "x", "y"),
                "sparkbars": ("label", "values"),
                "quadrant": ("label", "x", "y"),
                "waterfall": ("label",),
                "bubble": ("label", "x", "y", "size"),
                "lollipop": ("label", "value"),
                "diverging": ("label", "value"),
                "pyramid": ("band", "a", "b"),
                "treemap": ("label", "value"),
                "tree": ("id",),
                "flow": ("text",),
                "journey": ("label",),
                "clock": ("start", "end"),
                "polar": ("label", "value"),
                "marimekko": ("name", "value", "parts")}[t]
        for i, it in enumerate(items):
            if not isinstance(it, dict) or not all(k in it for k in need):
                raise SpecError("%s %s[%d] needs %s" % (t, key, i, ", ".join(need)))
        if t == "clock":
            for i, b in enumerate(items):
                if not 0 <= b["start"] < b["end"] <= 24:
                    raise SpecError("clock block %d: need 0 <= start < end <= 24" % i)
        if t == "treemap" and any(float(i["value"]) <= 0 for i in items):
            raise SpecError("treemap values must all be positive -- area cannot show a zero")
        if t == "tree":
            ids = set(str(nd["id"]) for nd in items)
            if len(ids) != len(items):
                raise SpecError("tree node ids must be unique")
            for nd in items:
                p = nd.get("parent")
                if p not in (None, "") and str(p) not in ids:
                    raise SpecError("tree node %r has parent %r, which is not a node"
                                    % (nd["id"], p))
    elif t == "histogram":
        vals = spec.get("values")
        if not isinstance(vals, list) or len(vals) < 5:
            raise SpecError("histogram needs 'values': at least five numbers")
        if not isinstance(spec.get("bins", 12), int) or not 2 <= spec.get("bins", 12) <= 60:
            raise SpecError("histogram 'bins' must be an integer 2-60")
    elif t == "ridgeline":
        groups = spec.get("groups")
        if not isinstance(groups, list) or not groups:
            raise SpecError("ridgeline needs 'groups': a non-empty list")
        for i, g in enumerate(groups):
            if not isinstance(g, dict) or "name" not in g or len(g.get("values") or []) < 4:
                raise SpecError("ridgeline group %d needs 'name' and 4+ 'values'" % i)
    elif t == "venn":
        sets = spec.get("sets")
        if not isinstance(sets, list) or len(sets) not in (2, 3):
            raise SpecError("venn needs 'sets': two or three of them")
        for s in sets:
            if not isinstance(s, dict) or "name" not in s:
                raise SpecError("each venn set needs a 'name'")
    elif t == "kanban":
        cols = spec.get("columns")
        if not isinstance(cols, list) or not cols:
            raise SpecError("kanban needs 'columns': a non-empty list")
        for i, c in enumerate(cols):
            if not isinstance(c, dict) or "name" not in c:
                raise SpecError("kanban column %d needs a 'name'" % i)
    elif t == "gantt":
        tasks = spec.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise SpecError("gantt needs 'tasks': a non-empty list")
        for i, tk in enumerate(tasks):
            if not isinstance(tk, dict) or not all(k in tk for k in ("name", "start", "end")):
                raise SpecError("task %d needs name, start and end" % i)
            if tk["end"] <= tk["start"]:
                raise SpecError("task %r ends before it starts" % tk.get("name"))
    else:
        if not isinstance(spec.get("year"), int) or not isinstance(spec.get("month"), int):
            raise SpecError("%s needs integer 'year' and 'month'" % t)
        for d, mk in (spec.get("marks") or {}).items():
            if isinstance(mk, dict):
                if mk.get("card") is not None:
                    _validate_card("day %s" % d, mk["card"], _page(spec, *PAGES["tablet"])[0] / 7.0)
                    import calendar as _cc
                    if len(_cc.Calendar(firstweekday=_first_day(spec))
                           .monthdayscalendar(spec["year"], spec["month"])) == 6:
                        raise SpecError("day %s: %d-%02d has six rows and its cells have no room "
                                        "for a haiku card under five events; put the card on the "
                                        "week instead" % (d, spec["year"], spec["month"]))
                for e in mk.get("events") or []:
                    if isinstance(e, dict) and e.get("kind") and e["kind"] not in KINDS:
                        raise SpecError("day %s: unknown event kind %r; kinds are %s"
                                        % (d, e["kind"], ", ".join(KINDS)))
        # A DAY CELL MUST BE AT LEAST SQUARE. A short calendar cannot hold a day number, the
        # weather and a note without one of them landing on another, and shrinking the type to
        # make it fit produces a month nobody can read. Refuse the page instead of drawing a bad
        # one -- the caller can pick a taller preset or drop the height.
        import calendar as _c
        w, h = _page(spec)
        if h:
            wk = len(_c.Calendar(firstweekday=_first_day(spec))
                     .monthdayscalendar(spec["year"], spec["month"]))
            cw = w / 7.0
            hdr = max(34.0, min(56.0, cw * 0.22))
            if (spec.get("weather") or spec.get("lat") is not None) and cw < 165.0:
                raise SpecError(
                    "a %gx%g calendar gives %.0f-wide day cells -- a weather calendar needs at "
                    "least 165, so width %.0f or more. (Without weather it is fine.)"
                    % (w, h, cw, 165.0 * 7))
            if (h - hdr) / wk < cw:
                raise SpecError(
                    "a %gx%g calendar gives %d-day cells %.0f x %.0f -- a day cell has to be at "
                    "least square. Use height %.0f or more, or a taller page."
                    % (w, h, wk * 7, cw, (h - hdr) / wk, hdr + cw * wk))
        if not 1 <= spec["month"] <= 12:
            raise SpecError("month must be 1-12")
        for d, _ in (spec.get("marks") or {}).items():
            if not str(d).isdigit() or not 1 <= int(d) <= 31:
                raise SpecError("marks keys must be day numbers 1-31, got %r" % (d,))
    return spec


# ---------------------------------------------------------------- VL compile
def _config():
    # SIZED FOR THE TABLET. Sizes tuned on a monitor read small and light on the page: labels 26, axis
    # titles 28, the chart's title 34 (at 20/22/28 they were still too small to read on the tablet).
    axis = {"labelColor": "black", "titleColor": "black", "domainColor": "black",
            "tickColor": "black", "domainWidth": 2.6, "tickWidth": 2.6, "tickSize": 8,
            "labelFontSize": 26, "titleFontSize": 28, "titleFontWeight": "bold",
            "labelLimit": 0,        # default 180px SILENTLY truncates labels
            "grid": False, "labelPadding": 6}
    # d3 formats a negative with U+2212, which the font does not have; the locale says use the hyphen
    loc = {"number": {"decimal": ".", "thousands": ",", "grouping": [3], "currency": ["$", ""], "minus": "-"}}
    # A text cut short by its `limit` ends in Vega's own ellipsis, which is added after _in_font has
    # mapped every string -- and U+2026 is not in the font, so the whole line would be set in the
    # fallback face. Two full stops are what _in_font makes of an ellipsis.
    return {"background": "white", "view": {"stroke": None}, "font": FONT, "axis": axis, "locale": loc,
            "mark": {"ellipsis": ".."}, "text": {"ellipsis": ".."},
            "title": {"color": "black", "fontSize": 34, "fontWeight": "bold",
                      "anchor": "middle", "offset": 16},
            "legend": {"labelColor": "black", "titleColor": "black", "labelFontSize": 26,
                       "titleFontSize": 26, "symbolStrokeColor": "black", "symbolStrokeWidth": 2.6,
                       "symbolSize": 240, "orient": "top-left", "direction": "vertical",
                       "fillColor": "white", "strokeColor": "black", "padding": 12,
                       "cornerRadius": 0, "offset": 10},
            "range": {"category": PALETTE}}


_GRID = {"grid": True, "gridColor": "black", "gridWidth": 1.4,
         "gridDash": [1, 6], "gridOpacity": 1}


# Weather icons as SVG PATHS, not glyphs. A unicode ☀ depends on the font having it, and
# vl-convert drops text it cannot render SILENTLY -- no error, no warning, an icon-less forecast.
# A path always draws, and bold simple shapes are what survives tracing.
# ---------------------------------------------------------------- icons
# Lucide (ISC), generated into rm_icons.py. They replaced a hand-drawn set whose shapes did not read
# (a cake that looked like a box with sticks, a plane like a paper dart, a warning triangle missing
# its left side). Drawing icons by hand in path data is not a thing to do when a professionally
# drawn set exists under a permissive license.
#
# They are STROKE outlines on a unit box, so every mark that uses one sets filled=False and a
# strokeWidth. A fill closes them into blobs.
from paperdaemon.pipeline.charts.icons import ICONS
from paperdaemon import net as _net

# The pen each icon is drawn in. Black unless the subject has an obvious color, and never a wash:
# a highlighter color as a 2px line is invisible.
# ONE DARK GRAY for nearly everything. The three exceptions below are semantic rather than decorative -- a tick that is not green and
# a warning that is not red are harder to read, not more tasteful.
# Icons are BLACK, like the lettering -- they are drawn at the same stroke as the type and read
# as part of it. Only the three whose meaning is a color keep one.
ICON_INK = dict((k, "black") for k in ICONS)
ICON_INK.update({"check": INK["green"], "cross": INK["red"], "alert": INK["red"]})


def _compose(parts):
    """Glyphs set together in one box: [(path, scale, dx, dy), ...] -> one polyline path."""
    from paperdaemon.pipeline.draw import glyphs as _GL
    out = []
    for d, sc, dx, dy in parts:
        for poly in _GL.flatten(d):
            out.append("M " + " L ".join("%s %s" % (_GL._g(x * sc + dx), _GL._g(y * sc + dy))
                                          for x, y in poly))
    return " ".join(out)


# WIND IS A MODIFIER, not a weather of its own: a windy day is still a sunny or a cloudy one.
# Two composites -- the sky glyph up and to the left, the wind lines down and to the right.
ICONS["sun-wind"] = _compose([(ICONS["sun"], 0.62, -0.30, -0.30), (ICONS["wind"], 0.62, 0.32, 0.36)])
ICONS["cloud-wind"] = _compose([(ICONS["cloud"], 0.66, -0.26, -0.28), (ICONS["wind"], 0.62, 0.32, 0.38)])
ICON_INK["sun-wind"] = ICON_INK["cloud-wind"] = "black"
# Names the old hand-drawn set had that Lucide spells differently, or does not have at all.
# Resolved everywhere an icon is looked up, so a spec written against the old names still draws
# something sensible instead of silently drawing nothing.
ALIASES = {"firework": "sparkle", "wreath": "tree", "balloon": "party", "snowman": "snow",
           "x": "cross", "tick": "check", "warning": "alert", "birthday": "cake",
           "present": "gift", "airplane": "plane", "airplane": "plane", "location": "pin",
           "temperature": "thermo", "note": "music", "todo": "check", "done": "check",
           "meeting": "users", "call": "phone"}


def icon_path(name, default="star"):
    """Look an icon up through the alias table. None if there is genuinely no such icon."""
    n = ALIASES.get(name, name)
    return ICONS.get(n) or (ICONS.get(ALIASES.get(default, default)) if default else None)


ICON_FILL = ICON_INK          # kept so older call sites keep resolving


def _cards_vl(spec, cfg, schema):
    """Big-number cards -- the thing a dashboard page actually gets read for.

    Pixels, because the band version anchored the rect to a y VALUE and the three text layers to
    fixed dy offsets around it, and the two never agreed: the label floated above the card and the
    number was sliced in half by the card's top edge. Here the card and its three lines are laid
    out from the same numbers.
    """
    items = spec.get("items") or []
    n = max(1, len(items))
    W, H = _page(spec, float(WIDTH), 250.0)
    H = H or 250.0
    GAP = 18.0
    CW = (W - GAP * (n - 1)) / n
    px = _Px(W, H)
    cards, labels, values, notes = [], [], [], []
    for i, c in enumerate(items):
        x0 = i * (CW + GAP)
        cx = x0 + CW / 2.0
        cards.append({"x0": x0, "y0": 8, "x1": x0 + CW, "y1": H - 8,
                      "fill": WASH.get(c.get("color", "white"), "#FFFFFF")})
        labels.append({"x": cx, "y": 46, "t": str(c.get("label", ""))})
        values.append({"x": cx, "y": H / 2 + 8, "t": str(c.get("value", ""))})
        if c.get("note"):
            notes.append({"x": cx, "y": H - 40, "t": str(c["note"])})
    # the value gets whatever size still fits the narrowest card
    longest = max([len(str(c.get("value", ""))) for c in items] + [1])
    size = int(max(26, min(54, (CW - 28) / (0.62 * longest))))
    return px.spec(spec.get("title", ""), [
        px.rect(cards, strokeWidth=1.6, stroke=GRAY, cornerRadius=8),
        px.text(labels, 22, False, color=GRAY),
        px.text(values, size, True),
        px.text(notes, 20, False, color=GRAY)], cfg, schema)


def _posts_vl(spec, cfg, schema):
    """Social posts CLIPPED onto the page: one card per post, the way the site shows it -- where it
    was posted and by whom, when, the title, the picture, the text, and what the post links to.

    The posts are real: the host fills `posts` from the site itself (rm_host._fill_posts) and the
    model never writes one. A picture arrives as a data: URI with its own size, so the card is laid
    out around it.

    THE CHART LAYS THE POSTS OUT, not the model, and several posts go into one chart object. A card
    is HALF the chart's width, cards run two to a row (a row as tall as its taller card), and one
    post is one half-width card on a canvas of its own width. Each card carries what the site shows:
    where and by whom, when, the title, the picture, the text, the votes and comments when the
    source gives them, and its top comments.
    """
    import textwrap
    posts = spec.get("posts") or []
    PAD, GAP = 22.0, 24.0
    cols = 1 if len(posts) <= 1 else 2
    CW = (float(WIDTH) - GAP) / 2.0                    # a card is half the chart, however many there are
    W = CW * cols + GAP * (cols - 1)
    inner = CW - 2 * PAD
    EM = 0.48        # Remarkable Mono's advance per character: 0.45 measured off a render at the fine pen, plus the
                     # heavier pen's wider spacing (charts/font.py SIDE)
    # THE SIZES, one table: what each line is drawn at is what it is wrapped at (at 16-19 the secondary lines were
    # too small to read on the tablet)
    S = {"head": 24, "who": 22, "title": 30, "link": 21, "body": 23, "foot": 22, "cwho": 20, "ctext": 22}
    cw = lambda size, indent=0: max(8, int((inner - indent) / (EM * size)))   # monospace: chars per line
    L = dict((k, []) for k in ("rects", "heads", "whos", "titles", "links", "bodies", "feet",
                                "cwho", "ctext", "rules"))
    imgs = []
    # ONE SOURCE IS NAMED ONCE. When every card comes from the same place the chart's title says it,
    # and "Bluesky" over each of four Bluesky posts under "Bluesky, hot" would be four lines of
    # nothing. Cards from several places (r/all) keep their own, and so do cards
    # whose one place the title does NOT name: a search, "Reddit: framework 13", all from r/framework.
    _comms = set(str(p.get("community") or "") for p in posts)
    same = len(_comms) == 1 and next(iter(_comms)).lower() in str(spec.get("title") or "").lower()

    def lines(s, width, cap):
        """Wrapped to `width` characters, at most `cap` lines -- the last one ending ".." when the
        text runs on, rather than stopping mid-sentence."""
        got = textwrap.wrap(str(s or ""), width)
        if len(got) > cap:
            got = got[:cap]
            got[-1] = got[-1][:max(1, width - 2)].rstrip() + ".."
        return got

    def card(p, x0, y0):
        """Lay one card out at (x0, y0) -> its height."""
        y = y0 + PAD
        if not same:
            y += 20
            L["heads"].append({"x": x0 + PAD, "y": y, "t": str(p.get("community") or "")[:cw(S["head"])]})
        who = " . ".join(s for s in (str(p.get("author") or ""), str(p.get("posted") or "")) if s)
        if who:
            y += 22 if same else 30
            L["whos"].append({"x": x0 + PAD, "y": y, "t": who[:cw(S["who"])]})
        y += 8
        for ln in lines(p.get("title"), cw(S["title"]), 5):
            y += 38
            L["titles"].append({"x": x0 + PAD, "y": y, "t": ln})
        if p.get("link"):
            y += 30
            L["links"].append({"x": x0 + PAD, "y": y, "t": str(p["link"])[:cw(S["link"])]})
        im = p.get("image") or {}
        if im.get("url") and im.get("w") and im.get("h"):
            w_ = inner
            h_ = min(w_ * float(im["h"]) / float(im["w"]), 1.05 * inner)      # a tall photo, not a scroll
            w_ = h_ * float(im["w"]) / float(im["h"])
            y += 14
            imgs.append({"url": im["url"], "x": x0 + PAD + (inner - w_) / 2.0, "y": y, "w": w_, "h": h_})
            y += h_
        for ln in lines(p.get("text"), cw(S["body"]), 6):
            y += 30
            L["bodies"].append({"x": x0 + PAD, "y": y, "t": ln})
        # each site's own words for its numbers: Reddit votes, Hacker News points, Bluesky likes
        foot = " . ".join(s for s in (
            _count(p["score"], p.get("score_label") or "votes") if p.get("score") is not None else "",
            _count(p["comments"], p.get("comments_label") or "comments") if p.get("comments") is not None else "",
            str(p.get("site") or "")) if s)
        if foot:
            y += 36
            L["feet"].append({"x": x0 + PAD, "y": y, "t": foot[:cw(S["foot"])]})
        for c in (p.get("top") or [])[:2]:
            y += 16
            top_ = y
            head = "%s%s" % (c.get("author") or "", ("  " + _count(c["score"], p.get("score_label") or "votes"))
                             if c.get("score") is not None else "")
            y += 26
            L["cwho"].append({"x": x0 + PAD + 14, "y": y, "t": head[:cw(S["cwho"], 14)]})
            for ln in lines(c.get("text"), cw(S["ctext"], 14 + 8), 3):      # its own indent, and a letter of air
                y += 28
                L["ctext"].append({"x": x0 + PAD + 14, "y": y, "t": ln})
            L["rules"].append({"x0": x0 + PAD, "y0": top_ + 4, "x1": x0 + PAD + 4, "y1": y + 6})
        return y + PAD - y0

    # TWO COLUMNS THAT FILL ON THEIR OWN: each card goes under the shorter column. A row as tall as
    # its tallest card left a picture post's neighbor with half a card of empty paper under it.
    colh = [0.0] * cols
    for p in posts:
        c = colh.index(min(colh))
        x0 = c * (CW + GAP)
        h = card(p, x0, colh[c])
        L["rects"].append({"x0": x0 + 2, "y0": colh[c] + 2, "x1": x0 + CW - 2, "y1": colh[c] + h})
        colh[c] += h + GAP
    H = max(120.0, max(colh) - GAP + 4)
    px = _Px(W, H)
    layers = [px.rect(L["rects"], fill="#FFFFFF", strokeWidth=2.4, cornerRadius=14),
              px.rect(L["rules"], fill="#B0B0B0", strokeWidth=0),
              px.text(L["heads"], S["head"], True, align="left", baseline="alphabetic"),
              px.text(L["whos"], S["who"], False, color=GRAY, align="left", baseline="alphabetic"),
              px.text(L["titles"], S["title"], True, align="left", baseline="alphabetic"),
              px.text(L["links"], S["link"], False, color=GRAY, align="left", baseline="alphabetic"),
              px.text(L["bodies"], S["body"], False, align="left", baseline="alphabetic"),
              px.text(L["feet"], S["foot"], False, color=GRAY, align="left", baseline="alphabetic"),
              px.text(L["cwho"], S["cwho"], True, color=GRAY, align="left", baseline="alphabetic"),
              px.text(L["ctext"], S["ctext"], False, align="left", baseline="alphabetic")]
    for im in imgs:              # one layer each: an image mark's size is a mark property
        layers.append({"data": {"values": [im]},
                       "mark": {"type": "image", "width": im["w"], "height": im["h"],
                                "align": "left", "baseline": "top", "aspect": False},
                       "encoding": px.xy(url={"field": "url", "type": "nominal"})})
    return px.spec(spec.get("title", ""), [l for l in layers if l["data"]["values"]], cfg, schema)


def _short(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    return ("%.1fk" % (n / 1000.0)).replace(".0k", "k") if n >= 1000 else "%d" % n


def _count(n, word):
    """'1.2k votes', '1 like', '1 reply' -- the number short, the word singular for one."""
    one = {"replies": "reply"}.get(word) or (word[:-1] if word.endswith("s") else word)
    return "%s %s" % (_short(n), one if str(_short(n)) == "1" else word)


def _progress_vl(spec, cfg, schema):
    """Progress against a target -- a track, a fill, and the number."""
    items = spec.get("items") or []
    rows = [{"t": str(c["label"]), "v": float(c["value"]), "max": float(c.get("max", 100)),
             "fill": WASH.get(c.get("color", "green"), WASH["green"]),
             "lab": "%g / %g" % (c["value"], c.get("max", 100))} for c in items]
    names = [r["t"] for r in rows]
    top = max([r["max"] for r in rows] or [100])
    pad = 8 + int(max([len(n) for n in names] or [4]) * 8.0)
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": max(320, WIDTH - pad - 200), "height": 58 * len(rows) + 56,
            "data": {"values": rows},
            "layer": [
                {"mark": {"type": "bar", "fill": "#FFFFFF", "stroke": "black", "strokeWidth": 2,
                          "height": {"band": 0.58}},
                 "encoding": {"x": {"field": "max", "type": "quantitative",
                                    "scale": {"domain": [0, top], "nice": False},
                                    "title": None}}},
                {"mark": {"type": "bar", "stroke": "black", "strokeWidth": 1.5,
                          "height": {"band": 0.58}},
                 "encoding": {"x": {"field": "v", "type": "quantitative"},
                              "color": {"field": "fill", "type": "nominal", "scale": None,
                                        "legend": None}}},
                {"mark": {"type": "text", "align": "left", "dx": 9, "fontSize": 22,
                          "fontWeight": "bold", "font": FONT, "color": "black"},
                 "encoding": {"x": {"field": "max", "type": "quantitative"},
                              "text": {"field": "lab", "type": "nominal"}}}],
            "encoding": {"y": {"field": "t", "type": "nominal", "sort": names, "title": None,
                               "axis": {"titlePadding": pad}}},
            "config": cfg}


GEO = _content.geo_dir()


# The wash names a spec uses are fill names; the pen set is not the same set. "orange" has no pen
# at all (it fell through to blue, silently), and the green and yellow pens are highlighter-bright
# -- fine as a fill, illegible as a 2px line. pen() maps a color name to something you can see.
PEN_FOR = {"orange": "red", "white": "gray", "lime": "green"}


def pen(name, on="#FFFFFF"):
    c = INK.get(name) or INK.get(PEN_FOR.get(name, ""), "#000000")
    return _readable(c, on)


# ---------------------------------------------------------------- page sizes
# The reMarkable's safe area (rm_page.SAFE_AREA) on its 1620 x 2160 sheet is PORTRAIT. Everything here
# was drawn 1200 wide and landscape-ish because that is what a chart on a screen looks like; a page
# meant for the tablet wants the other orientation.
MAX_EVENTS = 5          # per calendar day, as accepted from a spec (the validator's cap)
MONTH_EVENTS = 4        # what a month cell DRAWS -- the type and figures are sized for the tablet
# WHAT A DAY HAS decides its color. An event carries a `kind`; the day takes the color of the
# weightiest kind on it -- a birthday outranks a factoid -- unless the mark names a color itself.
# `calendar` is the what's-on month: holidays, birthdays, national days, history. `weather_calendar`
# is the forecast month, and the big holidays go on it too because they are days, not weather.
KINDS = ("holiday", "birthday", "personal", "national", "season", "history")   # precedence order
# `personal` has no wash of its own: a week where every day has an errand on it would be a green
# page, and the color would stop meaning anything. Name a `color` on the mark if a day should have one.
# NONE OF THESE IS A SKY COLOR. The sky takes yellow, blue, ice and plum; the kinds take the rest,
# so an event's pill never vanishes into the day it sits on (a blue national pill on a blue rain
# day did exactly that). History is the card's gray slip, not a wash.
# Teal is the blue family and clashed with a rain day; observances take gray, the seasons orange.
KIND_COLOR = {"holiday": "red", "birthday": "magenta", "national": "gray", "season": "orange"}
KIND_ICON = {"birthday": "cake"}       # the rest carry their own, or none
# EVERY EVENT LINE SITS ON A PILL colored by its kind. Personal gets green here -- a pill is
# not a whole day, so the wash that was too much on a cell is right on a line. No kind: pale.
PILL_COLOR = dict(KIND_COLOR, personal="green")
PILL_H = 1.12                          # pill height in em of the line; the pitch is EV_LEAD


def pill_fill(kind):
    """A pill's color: its kind's wash. Pills sit below the rule, on white, since the day's color
    ends above it -- so the wash reads, and the darker mid-tones tried before it were only hard
    to read."""
    return WASH[PILL_COLOR.get(kind, "pale")]


# THE WEATHER MONTH IS COLORED BY THE WEATHER -- by what the sky DOES, not by the thermometer.
# A sunny day is yellow, a wet day blue, snow a lighter blue, a storm plum; cloud, part, fog and
# wind stay WHITE. Gray is a poor color for a calendar, and wind is a modifier -- a windy day
# takes the color of its sky.
COND_WASH = {"sun": "yellow", "sun-wind": "yellow", "rain": "blue", "snow": "ice", "storm": "plum"}


def weather_wash(wd):
    """The wash for a day's forecast, or None for a neutral (white) day."""
    name = COND_WASH.get((wd or {}).get("icon"))
    return WASH[name] if name else None


# THE CARD sits where the weather rows sit: it starts tight under the day number, at the same
# height in every cell, and may reach no lower than the UV row may -- so the five event lines are
# never touched. One geometry, shared by the drawing and by calendar_limits(), so what the skill
# is told is what gets drawn.
CARD_FILL = "#ECECEF"
# the rule under the year: a plain hairline, drawn in its own thin layer. Frills were tried --
# spirals, leaves, tendrils -- and at a cell's scale they were clutter; the straight line reads.
ORNAMENT = "M -0.86 0 L 0.86 0"


CARD_SZ = 19.0           # the card's type (13 is too small on the tablet); a haiku
                         # line that does not fit at this size runs over once (_card_lines)
RUNOVER = 1.2            # a run-over line is indented this many ems, the way verse is set


def _haiku_lines(card):
    """The card's lines. `text` is a list of three, or one string split on newlines or ' / '."""
    t = (card or {}).get("text")
    if isinstance(t, (list, tuple)):
        lines = [str(x).strip() for x in t]
    else:
        t = str(t or "")
        parts = t.split("\n") if "\n" in t else t.split(" / ")
        lines = [p.strip() for p in parts]
    return [ln for ln in lines if ln]


def _syllables(word):
    """A syllable count good enough to tell a haiku from prose. Numbers count a syllable a digit."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return len(re.sub(r"[^0-9]", "", word))
    if len(w) <= 3:
        return 1
    if w in _SYL_EXCEPT:
        return _SYL_EXCEPT[w]
    # silent endings: -e, -ed, -es -- except a spoken -es after s, x, z, ch, sh ("finches"), and
    # the -le that follows a consonant ("table", "little"; but "smile", "whole" lose theirs)
    if re.search(r"[^aeiouy]le$", w):
        pass
    elif re.search(r"(?:[sxz]|ch|sh)es$", w):
        pass
    else:
        w = re.sub(r"(?:e|ed|es)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


_SYL_EXCEPT = {"hundred": 2, "wicked": 2, "naked": 2, "sacred": 2, "rugged": 2, "beloved": 3,
               "everett": 3, "science": 2, "quiet": 2, "poem": 2, "poet": 2, "diet": 2,
               "area": 3, "idea": 3, "create": 2, "being": 2, "seeing": 2, "going": 2, "doing": 2,
               "flying": 2, "crying": 2, "dying": 2, "lying": 2, "trying": 2, "saying": 2}


def _haiku_check(lines):
    """None if `lines` read as a haiku -- three lines of about 5, 7, 5 syllables (one off allowed,
    the counter is a heuristic) -- else what is wrong with them."""
    if len(lines) != 3:
        return "%d line%s; a haiku has three" % (len(lines), "" if len(lines) == 1 else "s")
    counts = [sum(_syllables(w) for w in re.split(r"[\s-]+", ln) if w) for ln in lines]
    for i, (c, want) in enumerate(zip(counts, (5, 7, 5))):
        if abs(c - want) > 1:
            return ("line %d has about %d syllables, wanted %d (counted %s)"
                    % (i + 1, c, want, " / ".join(str(x) for x in counts)))
    return None


def _card_lines(card, units, max_lines):
    """The card's lines as (text, runover). Each haiku line is set whole when it fits; one that does
    not is broken ONCE at a space and the rest set RUNOVER ems in, the way verse is set. The card's
    type is 19 (13 read too small on the tablet), and at that size a seven-syllable line does not
    always fit a day's width -- so it runs over rather than being cut or refused. A line that would need a second break is cut; the validator refuses it first."""
    from paperdaemon.pipeline.draw import glyphs as _GL
    out = []
    indent = RUNOVER / CAPF                          # the run-over's indent, in cap units
    for ln in _haiku_lines(card):
        if _GL.measure(ln, TRACK) <= units:
            out.append((ln, False))
            continue
        words, head = ln.split(), []
        while words and _GL.measure(" ".join(head + [words[0]]), TRACK) <= units:
            head.append(words.pop(0))
        if not head:
            head = [words.pop(0)]
        # A RUN-OVER OF ONE WORD reads as a mistake ("Little Rock Nine walk / in"). Two words go
        # down when they fit.
        if len(words) == 1 and len(head) >= 3 and \
                _GL.measure(" ".join([head[-1]] + words), TRACK) <= units - indent:
            words.insert(0, head.pop())
        out.append((" ".join(head), False))
        if words:
            out.append((_GL.fit(" ".join(words), units - indent, TRACK), True))
    return out[:max_lines]


def _needs_two_breaks(ln, units):
    """True if a haiku line cannot be set in one line plus one run-over."""
    from paperdaemon.pipeline.draw import glyphs as _GL
    if _GL.measure(ln, TRACK) <= units:
        return False
    words, head = ln.split(), []
    while words and _GL.measure(" ".join(head + [words[0]]), TRACK) <= units:
        head.append(words.pop(0))
    if not head:
        return True
    return _GL.measure(" ".join(words), TRACK) > units - RUNOVER / CAPF


def _card_units(cw):
    """How wide a card line is, in cap heights of the card's type."""
    pad = max(9.0, cw * 0.055)
    cpad = max(4.0, cw * 0.02)
    return _units(cw - 2 * pad, CARD_SZ)


def _card_head(card):
    """'1504 - David': the year and the card's one-word title, or just the year."""
    year = str((card or {}).get("year", "")).strip()
    title = str((card or {}).get("title", "")).strip()
    return (year + " - " + title) if (year and title) else (year or title)


def _validate_card(where, card, cw):
    if not isinstance(card, dict) or not _haiku_lines(card):
        raise SpecError("%s: 'card' must be {\"year\": 1846, \"title\": \"Neptune\", "
                        "\"text\": [line, line, line]}" % where)
    title = str(card.get("title", "")).strip()
    if title and len(title.split()) != 1:
        raise SpecError("%s: a card's 'title' is ONE word (got %r)" % (where, title))
    from paperdaemon.pipeline.draw import glyphs as _GL
    if _GL.measure(_card_head(card), TRACK) > _card_units(cw) * CARD_SZ / (CARD_SZ * 1.15):
        raise SpecError("%s: '%s' is too wide for the head of a card; a shorter title"
                        % (where, _card_head(card)))
    bad = _haiku_check(_haiku_lines(card))
    if bad:
        raise SpecError("%s: a card is a HAIKU, three lines of 5, 7, 5 syllables -- %s" % (where, bad))
    units = _card_units(cw)
    for i, ln in enumerate(_haiku_lines(card)):
        if _needs_two_breaks(ln, units):
            raise SpecError("%s: haiku line %d is too long for the card -- a line may run over "
                            "ONCE; about %d characters fit on two lines; shorten it"
                            % (where, i + 1, int(2 * units / 0.65)))


def _card_geom(cw, ch, pad, big, note):
    """(top, bottom, text size, year size, inner pad, leading, head) of a day's card, the first two
    as offsets from the top of the cell. `head` is the year line plus the flourish under it."""
    ev_block = note * (0.35 + 0.40 + EV_LEAD * (MONTH_EVENTS - 1)) + note * 0.30
    top = pad + big + note * 0.45
    bot = ch - pad - ev_block
    card_sz = CARD_SZ
    year_sz = card_sz * 1.15
    cpad = max(4.0, cw * 0.02)
    lead = card_sz * 1.22
    head = year_sz * 1.05                          # the head, the hairline, and the haiku tight under it
    return top, bot, card_sz, year_sz, cpad, lead, head


def _mark_events(m):
    """A mark's events as a list of dicts. Older specs said note/notes/at/icon; those still work."""
    evs = m.get("events")
    if not evs:
        body = m.get("notes") or ([m["note"]] if m.get("note") else [])
        evs = [{"text": t, "at": m.get("at") if i == 0 else None,
                "icon": m.get("icon") if i == 0 else None} for i, t in enumerate(body)]
    return [(dict(e) if isinstance(e, dict) else {"text": str(e)}) for e in evs]
# an event line: the dial, the icon and the gap after each, in em of the line's type size.
# The calendar draws with these and calendar_limits() measures with them -- one set, no drift.
EV_CLOCK, EV_ICON, EV_GAP = 0.80, 0.86, 0.30
EV_LEAD = 1.28           # line pitch of an event line, in em
# rm_glyphs.measure() and fit() work in CAP HEIGHTS, and the tablet font's cap is 0.70 of the type
# size (rm_font: CAP 700 / UPM 1000). A width in px is measure * CAPF * size. Every fit in this
# file goes through _units(); comparing cap units to px / size left a third of each line empty.
CAPF = 0.70
# THE CHART FONT'S OWN LETTER SPACING, in cap heights: a letter's advance is its stroke width plus a side bearing
# each side (charts/font.py), so every measure and fit here passes this, not the tablet lettering's TRACK -- with
# that, a heavier font's wider bearings were measured 7% short and text ran out of its bubble.
from paperdaemon.pipeline.charts import font as _FONT
TRACK = 2.0 * _FONT.SIDE / _FONT.CAP


def _units(px, size):
    """Pixels -> the cap-height units rm_glyphs measures in, at this type size."""
    return px / (size * CAPF)

PAGES = {
    "tablet": (1450, 1960),          # the safe area, portrait -- a full page on the device
    "tablet-wide": (1960, 1450),     # the same area, turned
    "half": (1450, 960),             # top or bottom half of a tablet page
    "third": (1450, 640),
    "strip": (1450, 380),            # a band across the page
    "wide": (1200, 675),             # 16:9, for a screen
    "square": (1100, 1100),
}


def _page(spec, default_w=None, default_h=None):
    """(width, height) for a chart: explicit width/height win, then a named page, then defaults."""
    name = spec.get("page")
    if name:
        if name not in PAGES:
            raise SpecError("no page size %r; have %s" % (name, ", ".join(sorted(PAGES))))
        w, h = PAGES[name]
    else:
        w, h = (default_w if default_w is not None else WIDTH), default_h
    return float(spec.get("width", w)), (float(spec["height"]) if spec.get("height") else
                                         (float(h) if h else None))


# ---------------------------------------------------------------- how much page a chart wants
# Written for the model that plans a page, not for this module. Every builder already knows its
# own proportions; nothing upstream did, so a request would ask for a month calendar and a bar
# chart side by side on one sheet and the calendar would come out three inches tall.
#
#   aspect   drawn height / drawn width at a sensible size. 1.35 is portrait, 0.55 is a band.
#   page     the preset to reach for when this is the ONLY thing on the sheet.
#   share    how much of a tablet page to give it when it is sharing: 1.0 a whole page,
#            0.5 a half, 0.33 a third.
#   cap      how many items, series, rows or slices before it stops being readable.
LAYOUT = {
    # full-page planning surfaces
    # min_cell: a day cell may not be wider than it is tall -- validate() refuses
    # drawn for the portrait safe area; other sizes work but are not what it is tuned to
    "calendar":  dict(aspect=1.35, page="tablet", share=1.0, cap=31, min_cell=1.0,
                      only="tablet"),
    "agenda":    dict(aspect=1.35, page="tablet", share=1.0, cap=20),
    "yearmap":   dict(aspect=0.30, page="strip", share=0.33, cap=366),
    # a week is one row of day columns: the tablet page, each column as tall as the page allows
    # the week is one row of day columns, about 3.8 cell-widths tall: the forecast in full, five
    # entries, and an on-this-day card at the foot
    "week":      dict(aspect=0.60, page="half", share=0.6, cap=7),
    "habit":     dict(aspect=0.40, page="half", share=0.5, cap=8),
    "kanban":    dict(aspect=0.75, page="tablet-wide", share=1.0, cap=5),
    "table":     dict(aspect=0.60, page="half", share=0.5, cap=24),
    "checklist": dict(aspect=0.70, page="half", share=0.5, cap=14),
    "tree":      dict(aspect=0.60, page="tablet-wide", share=1.0, cap=24),
    "flow":      dict(aspect=0.45, page="half", share=0.5, cap=12),
    "gantt":     dict(aspect=0.45, page="half", share=0.5, cap=14),
    "map":       dict(aspect=0.55, page="half", share=0.5, cap=1),
    # bands: wide and short, two or three stack on a page
    "cards":     dict(aspect=0.21, page="strip", share=0.25, cap=5),
    "posts":     dict(aspect=1.10, page="tablet-wide", share=1.0, cap=4),
    "progress":  dict(aspect=0.30, page="strip", share=0.33, cap=8),
    "gauge":     dict(aspect=0.50, page="third", share=0.33, cap=1),
    "timeline":  dict(aspect=0.32, page="strip", share=0.33, cap=7),
    "journey":   dict(aspect=0.25, page="strip", share=0.25, cap=8),
    "sparkbars": dict(aspect=0.30, page="third", share=0.33, cap=10),
    "bullet":    dict(aspect=0.35, page="third", share=0.33, cap=8),
    # ordinary charts: a bit wider than tall
    "bar":       dict(aspect=0.55, page="wide", share=0.5, cap=24),
    "hbar":      dict(aspect=0.50, page="half", share=0.5, cap=20),
    "stacked":   dict(aspect=0.55, page="wide", share=0.5, cap=24),
    "line":      dict(aspect=0.50, page="wide", share=0.5, cap=40),
    "step":      dict(aspect=0.50, page="wide", share=0.5, cap=40),
    "area":      dict(aspect=0.50, page="wide", share=0.5, cap=40),
    "scatter":   dict(aspect=0.62, page="wide", share=0.5, cap=80),
    "bubble":    dict(aspect=0.70, page="half", share=0.5, cap=20),
    "candle":    dict(aspect=0.52, page="wide", share=0.5, cap=30),
    "stock":     dict(aspect=0.50, page="wide", share=0.5, cap=90),
    "histogram": dict(aspect=0.48, page="wide", share=0.5, cap=40),
    "heatmap":   dict(aspect=0.45, page="half", share=0.5, cap=60),
    "waterfall": dict(aspect=0.52, page="wide", share=0.5, cap=12),
    "dist":      dict(aspect=0.58, page="wide", share=0.5, cap=8),
    "violin":    dict(aspect=0.62, page="wide", share=0.5, cap=6),
    "ridgeline": dict(aspect=0.45, page="half", share=0.5, cap=12),
    "bump":      dict(aspect=0.45, page="wide", share=0.5, cap=8),
    "slope":     dict(aspect=0.95, page="third", share=0.33, cap=10),
    "dumbbell":  dict(aspect=0.40, page="third", share=0.33, cap=12),
    "diverging": dict(aspect=0.45, page="half", share=0.5, cap=14),
    "lollipop":  dict(aspect=0.45, page="half", share=0.5, cap=20),
    "pyramid":   dict(aspect=0.45, page="half", share=0.5, cap=12),
    "marimekko": dict(aspect=0.62, page="half", share=0.5, cap=6),
    # things that want to be square-ish
    "pie":       dict(aspect=0.66, page="half", share=0.5, cap=7),
    "donut":     dict(aspect=0.66, page="half", share=0.5, cap=7),
    "radar":     dict(aspect=0.73, page="half", share=0.5, cap=4),
    "polar":     dict(aspect=0.92, page="square", share=0.5, cap=12),
    "clock":     dict(aspect=1.00, page="square", share=0.5, cap=12),
    "venn":      dict(aspect=0.69, page="half", share=0.5, cap=3),
    "waffle":    dict(aspect=1.15, page="third", share=0.33, cap=6),
    "treemap":   dict(aspect=0.60, page="half", share=0.5, cap=14),
    "quadrant":  dict(aspect=0.82, page="half", share=0.5, cap=14),
    "matrix":    dict(aspect=0.82, page="half", share=0.5, cap=14),
    "sankey":    dict(aspect=0.60, page="half", share=0.5, cap=10),
    "funnel":    dict(aspect=0.45, page="half", share=0.5, cap=7),
    "pictograph": dict(aspect=0.35, page="third", share=0.33, cap=6),
}
_LAYOUT_DEFAULT = dict(aspect=0.55, page="wide", share=0.5, cap=20)


def calendar_limits(spec=None):
    """What a calendar day can actually hold, measured -- not estimated.

    `event_chars` is a HARD limit: anything longer is cut, because a day cell never wraps.
    """
    from paperdaemon.pipeline.draw import glyphs as _GL
    sp = dict(spec or {})
    sp.setdefault("type", "calendar")
    sp.setdefault("year", 2026)
    sp.setdefault("month", 1)
    w, h = _page(sp, *PAGES["tablet"])
    cw = w / 7.0
    hdr = max(34.0, min(56.0, cw * 0.22))
    import calendar as _c
    weeks = len(_c.Calendar(firstweekday=_first_day(sp))
                .monthdayscalendar(int(sp["year"]), int(sp["month"])))
    ch = (h - hdr) / weeks if h else cw * 1.15
    pad = max(9.0, cw * 0.055)
    note = max(12.0, min(26.0, ch * 0.115))          # the month builder's entry size
    plain = _units(cw - 2 * pad, note)
    with_time = _units(cw - 2 * pad - note * (EV_CLOCK + EV_GAP), note)
    with_both = _units(cw - 2 * pad - note * (EV_CLOCK + EV_GAP) - note * (EV_ICON + EV_GAP), note)
    # average lowercase advance in this font, and the widest letter, so the limit can be
    # quoted two ways: what USUALLY fits, and what is GUARANTEED to
    G = _GL._font()
    avg = sum(G[c][0] for c in "abcdefghijklmnopqrstuvwxyz") / 26.0 + _GL.TRACK
    wide = G["m"][0] + _GL.TRACK
    big = max(22.0, min(62.0, min(ch * 0.22, cw * 0.29)))
    c_top, c_bot, card_sz, year_sz, cpad, lead, head = _card_geom(cw, ch, pad, big, note)
    # WHETHER A CARD FITS is the builder's rule, stated: a five-row month shows a card on a day
    # with three entries or fewer, and the day's weather grid gives up rows (wind first) to make
    # the room (see _grid_vl); a six-row month has no room for one at all (the validator refuses).
    card_units = _units(cw - 2 * pad, card_sz)
    six = weeks >= 6
    return {"page_px": (int(w), int(h)), "cell_px": (int(cw), int(ch)),
            "card": ("no room: this month has six rows -- put the card on the week" if six else
                     "a HAIKU: three lines of 5, 7, 5 syllables, each about card_line_chars; a longer "
                     "line runs over ONCE (about twice that); shown when the day has three entries "
                     "or fewer"),
            "card_lines": 0 if six else 3,
            "card_line_chars": int(card_units / avg),      # before a line runs over (once)
            "events": MONTH_EVENTS,
            "event_chars": int(plain / avg),
            "event_chars_worst": int(plain / wide),
            "event_chars_with_clock": int(with_time / avg),
            "event_chars_with_clock_and_icon": int(with_both / avg),
            "wrap": "never -- a line longer than this is cut and ends in .."}


def advise(chart_type):
    """What a chart of this type wants: aspect, a page preset, a share of a sheet, an item cap.

    For whatever is planning the page. `rm_chart.advise("calendar")` beats guessing, and guessing
    is what produced a request for a month calendar and a bar chart side by side on one sheet.
    """
    if chart_type in TABLETOP_TYPES:
        from paperdaemon.pipeline.charts import tabletop as rm_tabletop
        return rm_tabletop.advise(chart_type)
    d = dict(_LAYOUT_DEFAULT)
    d.update(LAYOUT.get(chart_type, {}))
    w, h = PAGES.get(d["page"], (WIDTH, None))
    d["type"] = chart_type
    d["suggested"] = (w, int(round(w * d["aspect"])))
    if chart_type == "calendar":
        d.update(calendar_limits({"type": chart_type}))
    return d


def weather_icon(kind, pct=None):
    """The weather glyph, unchanged, with the chance of precipitation set OVER it.

    The icon does not move or resize -- it is the stock glyph. Where the figure sits, the icon's
    own strokes stop short of it and pick up again on the far side, which is what a draughtsman
    does and what knocking a white hole in the glyph was a poor imitation of. At 0.52 cap the
    figure covers the middle of the cloud; the crown, both flanks and everything that falls from
    it survive, so it still reads as weather, and the figure reads from across the room.
    """
    base = icon_path(kind, None)
    if base is None or pct is None or kind not in ("rain", "snow", "storm"):
        return base
    from paperdaemon.pipeline.draw import glyphs as rm_glyphs
    return rm_glyphs.over(base, "%d%%" % round(pct), 0.52, 0.0, -0.22)


UV_DISC, UV_CAP = 0.52, 0.46    # the sun's disc, and the letters inside it, in the unit box


def uv_icon():
    """The sun with UV INSIDE its disc, the way a chance of rain sits inside its cloud.

    Lucide's sun keeps its disc at a third of the box and starts its rays at two thirds. Letters
    that fit a disc that small cannot be read, and letters that can be read swallow the disc
    whole -- which is what happened: the icon had become UV between two dashes. So the rays are
    the stock ones and the disc is drawn out to 0.52, leaving a clear gap inside the rays, with
    UV set inside it. Nothing is cut; the ring closes round the letters.
    """
    from paperdaemon.pipeline.draw import glyphs as rm_glyphs
    rays = " ".join(sub for sub in re.split(r"(?=M )", icon_path("sun_ring"))
                    if sub.strip() and " A " not in sub)
    r = rm_glyphs._g(UV_DISC)
    disc = "M -%s 0 A %s %s 0 1 0 %s 0 A %s %s 0 1 0 -%s 0 Z" % (r, r, r, r, r, r, r)
    return rm_glyphs.over(rays + " " + disc, "UV", UV_CAP, 0.0, 0.0, 0.05)


def _lum(hexc):
    """Relative luminance, 0..1. Rough sRGB weights -- precise enough to answer "can I see it"."""
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _readable(ink, on):
    """The icon's own pen, or black when that pen would vanish against the cell it sits on.

    The device's green and yellow pens are highlighter-bright: #A9FA5C drawn as a 2px line on the
    green wash #ACFF85 is invisible, and so is the yellow star on a yellow day. Color is only
    worth having when it survives the background.
    """
    try:
        return ink if abs(_lum(ink) - _lum(on)) >= 0.28 else "#000000"
    except Exception:
        return "#000000"


def _kde(vals, steps=72):
    """Gaussian kernel density over the sample's OWN range, Silverman's rule for the bandwidth.

    Small enough to carry rather than depend on scipy, and doing it here is what lets each violin
    use its own extent instead of one global one.
    """
    import math as _m
    n = len(vals)
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return [(lo, 1.0)]
    mean = sum(vals) / n
    sd = (sum((v - mean) ** 2 for v in vals) / max(n - 1, 1)) ** 0.5 or (hi - lo) / 6.0
    s = sorted(vals)
    q1, q3 = s[n // 4], s[(3 * n) // 4]
    spread = min(sd, (q3 - q1) / 1.34) or sd
    bw = 0.9 * spread * n ** (-0.2) or (hi - lo) / 10.0
    lo, hi = lo - bw, hi + bw
    out = []
    for i in range(steps + 1):
        x = lo + (hi - lo) * i / steps
        d = sum(_m.exp(-0.5 * ((x - v) / bw) ** 2) for v in vals) / (n * bw * 2.5066282746)
        out.append((x, d))
    return out


class _Px(object):
    """Pixel-space drawing on a Vega-Lite canvas.

    Several of these charts have no Vega-Lite mark (sankey, radar, treemap, venn, a tree) and are
    laid out here in pixels instead. They all need the same thing: two quantitative scales pinned
    to the canvas with y running downward, and axes off. Writing that out per chart was four lines
    of noise per layer and a place to get the sign of y wrong.
    """

    def __init__(self, w, h):
        self.w, self.h = float(w), float(h)
        self._x = {"scale": {"domain": [0, self.w], "nice": False}, "axis": None}
        self._y = {"scale": {"domain": [self.h, 0], "nice": False}, "axis": None}

    def xy(self, fx="x", fy="y", **kw):
        d = {"x": dict(field=fx, type="quantitative", **self._x),
             "y": dict(field=fy, type="quantitative", **self._y)}
        d.update(kw)
        return d

    def rect(self, vals, **mark):
        m = {"type": "rect", "stroke": "black", "strokeWidth": 1}
        m.update(mark)
        e = self.xy("x0", "y0", x2={"field": "x1"}, y2={"field": "y1"})
        if any("fill" in v for v in vals):
            e["color"] = {"field": "fill", "type": "nominal", "scale": None, "legend": None}
            m.pop("fill", None)
        return {"data": {"values": vals}, "mark": m, "encoding": e}

    def text(self, vals, size=15, bold=False, color="black", field="t", **mark):
        m = {"type": "text", "fontSize": size, "font": FONT, "color": color}
        vals = [dict(v, **{field: _in_font(v[field])}) if isinstance(v.get(field), str) else v
                for v in vals]
        if bold:
            m["fontWeight"] = "bold"
        m.update(mark)
        return {"data": {"values": vals}, "mark": m,
                "encoding": self.xy(text={"field": field, "type": "nominal"})}

    def line(self, vals, key="k", **mark):
        # ORDER MATTERS AND IS NOT FREE. A line mark sorts its points by x unless told otherwise,
        # which turns every elbow whose child sits to the LEFT of its parent into a diagonal
        # slash across the drawing. Rows carry "o"; pass it through.
        m = {"type": "line", "strokeWidth": 2, "color": "black"}
        m.update(mark)
        enc = self.xy(detail={"field": key, "type": "nominal"})
        if vals and "o" in vals[0]:
            enc["order"] = {"field": "o", "type": "quantitative"}
        return {"data": {"values": vals}, "mark": m, "encoding": enc}

    def spec(self, title, layers, cfg, schema, **kw):
        d = {"$schema": schema, "title": title, "width": self.w, "height": self.h,
             "layer": layers, "config": dict(cfg, view={"stroke": None})}
        d.update(kw)
        return d


def _wrap2(s, n):
    """Split a label onto at most two lines of about n characters, breaking on spaces.

    Vega's `limit` truncates with an ellipsis and its text mark does not wrap, so anything that has
    to sit inside a fixed cell gets wrapped HERE. Two lines, because a third would run a calendar
    day into the day below it.
    """
    s = (s or "").strip()
    if len(s) <= n or " " not in s:
        return s, ""
    cut = s.rfind(" ", 0, n + 1)
    if cut <= 0:
        cut = s.find(" ", n)
    return s[:cut], s[cut + 1:]


def _candle_vl(spec, cfg, schema):
    """Open-high-low-close. A wick from low to high, a body from open to close, hollow when it
    closed up and solid when it closed down -- the convention that survives having no color."""
    bars = spec.get("bars") or []
    rows = [{"t": str(b["t"]), "o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"],
             "up": 1 if b["close"] >= b["open"] else 0,
             "lo": min(b["open"], b["close"]), "hi": max(b["open"], b["close"])} for b in bars]
    ups, downs = WASH.get(spec.get("up", "green"), WASH["green"]), \
        WASH.get(spec.get("down", "magenta"), WASH["magenta"])
    lo = min(r["l"] for r in rows)
    hi = max(r["h"] for r in rows)
    pad = (hi - lo) * 0.06 or 1.0
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 90, "height": 560, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "rule", "strokeWidth": 2, "color": "black"},
                 "encoding": {"y": {"field": "l", "type": "quantitative",
                                    "title": spec.get("y_label"),
                                    # an explicit padded domain: the top wick sat ON the axis line
                                    "scale": {"domain": [lo - pad, hi + pad], "nice": False}},
                              "y2": {"field": "h"}}},
                {"mark": {"type": "bar", "stroke": "black", "strokeWidth": 2,
                          "width": {"band": 0.62}},
                 "encoding": {"y": {"field": "lo", "type": "quantitative"},
                              "y2": {"field": "hi"},
                              "color": {"field": "up", "type": "nominal", "legend": None,
                                        "scale": {"domain": [1, 0], "range": [ups, downs]}}}}],
            "encoding": {"x": {"field": "t", "type": "nominal", "sort": [r["t"] for r in rows],
                               "title": spec.get("x_label"), "axis": {"labelAngle": 0}}},
            "config": cfg}


def _radar_vl(spec, cfg, schema):
    """A spider. Vega-Lite has no polar mark, so the polygon is solved here in pixels and drawn as
    an ordinary closed line -- which is all a radar chart ever was.

    The fill and the outline are SEPARATE layers. `line` with `filled` gave a translucent blob and
    no edge at all: three overlapping washes with nothing to tell them apart.
    """
    import math as _m
    axes = spec.get("axes") or []
    series = spec.get("series") or []
    top = float(spec.get("max") or max([max(s["values"]) for s in series] or [1]))
    W, H = 900, 660
    CX, CY, R = W / 2.0, H / 2.0 + 6, 232.0
    na = len(axes)
    def at(i, frac):
        a = 2 * _m.pi * i / na
        return CX + R * frac * _m.sin(a), CY - R * frac * _m.cos(a)
    webs, spokes, rows, pts, labels, ticks = [], [], [], [], [], []
    for ring in (0.25, 0.5, 0.75, 1.0):
        for j in range(na + 1):
            x, y = at(j % na, ring)
            webs.append({"ring": ring, "o": j, "x": x, "y": y})
        ticks.append(dict(zip(("x", "y"), at(0, ring)), t=("%g" % (top * ring))))
    for i in range(na):
        spokes.append({"sp": i, "o": 0, "x": CX, "y": CY})
        spokes.append(dict(zip(("x", "y"), at(i, 1.0)), sp=i, o=1))
    for s in series:
        for j in range(na + 1):
            i = j % na
            x, y = at(i, float(s["values"][i]) / top)
            rows.append({"s": s["name"], "o": j, "x": x, "y": y})
            if j < na:
                pts.append({"s": s["name"], "x": x, "y": y})
    for i, a in enumerate(axes):
        x, y = at(i, 1.0)
        labels.append({"x": CX + (x - CX) * 1.20, "y": CY + (y - CY) * 1.16, "t": str(a),
                       "al": "left" if x > CX + 4 else ("right" if x < CX - 4 else "center")})
    names = [s["name"] for s in series]
    n = len(names)
    sc = {"x": {"scale": {"domain": [0, W], "nice": False}, "axis": None},
          "y": {"scale": {"domain": [H, 0], "nice": False}, "axis": None}}
    def enc(**kw):
        d = {"x": dict(field="x", type="quantitative", **sc["x"]),
             "y": dict(field="y", type="quantitative", **sc["y"])}
        d.update(kw)
        return d
    order = {"field": "o", "type": "quantitative"}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": W, "height": H,
            # Layers SHARE a color scale by default, so the wash scale defined first silently
            # overwrote the ink scale: outlines and markers came out in the same pale wash as the
            # fills, and no legend rendered at all.
            "resolve": {"scale": {"color": "independent"}},
            "layer": [
                {"data": {"values": spokes},
                 "mark": {"type": "line", "strokeWidth": 1, "color": RULE},
                 "encoding": enc(detail={"field": "sp", "type": "nominal"}, order=order)},
                {"data": {"values": webs},
                 "mark": {"type": "line", "strokeWidth": 1.2, "color": RULE},
                 "encoding": enc(detail={"field": "ring", "type": "nominal"}, order=order)},
                # A FILLED LINE, not an area. `area` needs a baseline, and giving it one (y2 at the
                # center) turned the chart into a 5000-pixel spike -- a radar's fill is a closed
                # polygon, and a line mark that closes on itself is the only polygon Vega-Lite has.
                {"data": {"values": rows},
                 "mark": {"type": "line", "filled": True, "fillOpacity": 0.4,
                          "strokeWidth": 0, "stroke": None},
                 "encoding": enc(detail={"field": "s", "type": "nominal"}, order=order,
                                 color={"field": "s", "type": "nominal", "legend": None,
                                        "scale": {"domain": names, "range": PALETTE[:n]}})},
                {"data": {"values": rows},
                 "mark": {"type": "line", "strokeWidth": 3.5},
                 "encoding": enc(detail={"field": "s", "type": "nominal"}, order=order,
                                 color={"field": "s", "type": "nominal", "title": None,
                                        "scale": {"domain": names,
                                                  "range": LINE_INK[:n]}})},
                {"data": {"values": pts},
                 "mark": {"type": "point", "size": 130, "filled": True, "opacity": 1,
                          "stroke": "black", "strokeWidth": 1.4},
                 "encoding": enc(color={"field": "s", "type": "nominal", "legend": None,
                                        "scale": {"domain": names, "range": LINE_INK[:n]}})},
                {"data": {"values": ticks},
                 "mark": {"type": "text", "fontSize": 18, "font": FONT, "color": GRAY,
                          "align": "left", "dx": 5, "dy": -4},
                 "encoding": enc(text={"field": "t", "type": "nominal"})},
                {"data": {"values": labels},
                 "mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black"},
                 "encoding": enc(text={"field": "t", "type": "nominal"},
                                 align={"field": "al", "type": "nominal"})}],
            "config": dict(cfg, view={"stroke": None},
                           legend=dict(cfg["legend"], orient="top-right", symbolType="stroke",
                                       symbolStrokeWidth=4))}


def _dist_vl(spec, cfg, schema):
    """Distribution: a box plot, or a violin when asked. Raw values in, shape out -- the point is
    to show the SPREAD, which a bar of means hides completely."""
    groups = spec.get("groups") or []
    rows = [{"g": g["name"], "v": float(v)} for g in groups for v in g["values"]]
    names = [g["name"] for g in groups]
    if spec.get("violin"):
        lo, hi = min(r["v"] for r in rows), max(r["v"] for r in rows)
        pad = (hi - lo) * 0.05 or 1.0
        # The density is computed HERE, per group, over that group's own range. Vega's density
        # transform takes one global extent, so the fast group's curve was zero across four fifths
        # of the axis and drew as a full-height hairline -- which reads as a rendering fault, not
        # as "no data here".
        dens = []
        for g in groups:
            for v, d in _kde([float(x) for x in g["values"]]):
                dens.append({"g": g["name"], "value": v, "density": d})
        return {"$schema": schema, "title": spec.get("title", ""),
                # PER FACET, not the whole chart. `width` on a faceted spec is each column's
                # width, and WIDTH-200 made a six-thousand-pixel strip.
                "width": int(min(260, (WIDTH - 260) / max(1, len(names)))), "height": 620,
                "data": {"values": dens},
                "mark": {"type": "area", "orient": "horizontal", "stroke": "black",
                         "strokeWidth": 1.5, "interpolate": "monotone"},
                "encoding": {
                    "y": {"field": "value", "type": "quantitative", "title": spec.get("y_label"),
                          "scale": {"domain": [lo - pad, hi + pad], "nice": False}},
                    "x": {"field": "density", "type": "quantitative", "stack": "center",
                          "impute": None, "title": None,
                          "axis": {"labels": False, "values": [], "grid": False,
                                   "ticks": False, "domain": False}},
                    "column": {"field": "g", "type": "nominal", "sort": names, "spacing": 6,
                               "header": {"titleOrient": "bottom", "labelOrient": "bottom",
                                          "labelPadding": 6, "title": None,
                                          "labelFontSize": 26, "labelFontWeight": "bold"}},
                    "color": {"field": "g", "type": "nominal", "legend": None,
                              "scale": {"domain": names, "range": PALETTE[:len(names)]}}},
                "config": dict(cfg, view={"stroke": None})}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 200, "height": 560, "data": {"values": rows},
            "mark": {"type": "boxplot", "extent": "min-max", "size": 54,
                     "median": {"color": "black", "strokeWidth": 3},
                     "rule": {"strokeWidth": 2, "color": "black"},
                     # WITHOUT a size the whisker caps run the full band -- four rules across the
                     # entire plot instead of four small caps.
                     "ticks": {"color": "black", "strokeWidth": 2.5, "size": 34}},
            "encoding": {
                "x": {"field": "g", "type": "nominal", "sort": names,
                      "title": spec.get("x_label"), "axis": {"labelAngle": 0}},
                "y": {"field": "v", "type": "quantitative", "title": spec.get("y_label"),
                      "scale": {"zero": False}},
                "color": {"field": "g", "type": "nominal", "legend": None,
                          "scale": {"domain": names, "range": PALETTE[:len(names)]}}},
            "config": cfg}


def _sankey_vl(spec, cfg, schema):
    """Flows between two columns, laid out here in pixels.

    Each ribbon is an AREA with an explicit y2. Emitting the four corners as a closed polygon
    instead let Vega-Lite's default y-stacking loose on the numbers and produced a 5000-pixel-tall
    chart of disconnected wedges. y/y2 never stacks, and sampling a smoothstep across the gap gives
    the curve a real sankey has.
    """
    links = spec.get("links") or []
    lefts, rights = [], []
    for l in links:
        if l["from"] not in lefts:
            lefts.append(l["from"])
        if l["to"] not in rights:
            rights.append(l["to"])
    W, H, XL, XR, GAP, NW = 1060.0, 600.0, 250.0, 810.0, 16.0, 15.0
    tot = float(sum(l["value"] for l in links)) or 1.0
    def stack(names, key):
        out, y = {}, 0.0
        span = H - GAP * (len(names) - 1)
        for nm in names:
            v = sum(l["value"] for l in links if l[key] == nm)
            out[nm] = [y, y + span * v / tot]
            y = out[nm][1] + GAP
        return out
    L, R = stack(lefts, "from"), stack(rights, "to")
    lc = dict((k, v[0]) for k, v in L.items())
    rc = dict((k, v[0]) for k, v in R.items())
    ribbons, mids = [], []
    lspan = H - GAP * (len(lefts) - 1)
    rspan = H - GAP * (len(rights) - 1)
    for k, l in enumerate(links):
        a0 = lc[l["from"]]
        a1 = a0 + lspan * l["value"] / tot
        b0 = rc[l["to"]]
        b1 = b0 + rspan * l["value"] / tot
        lc[l["from"]], rc[l["to"]] = a1, b1
        fill = WASH.get(l.get("color", "blue"), WASH["blue"])
        for i in range(25):
            f = i / 24.0
            e = f * f * (3 - 2 * f)                      # smoothstep, so the ribbon eases
            ribbons.append({"k": k, "x": XL + NW + (XR - NW - XL - NW) * f,
                            "y0": a0 + (b0 - a0) * e, "y1": a1 + (b1 - a1) * e,
                            "fill": fill})
        # At the ribbon's LEFT end, not its middle: every ribbon's middle is the same x, so the
        # numbers stacked on top of each other ("21" printed over "9").
        mids.append({"x": XL + NW + 14, "y": (a0 + a1) / 2.0, "t": str(l["value"])})
    nodes, labels = [], []
    for nm, (y0, y1) in list(L.items()) + list(R.items()):
        left = nm in L and (nm not in R or links[0]["from"] == nm)
        x = XL if nm in L else XR
        nodes.append({"nm": nm, "x0": x - NW, "x1": x + NW, "y0": y0, "y1": y1})
        labels.append({"x": x - NW - 12 if nm in L else x + NW + 12, "y": (y0 + y1) / 2.0,
                       "t": nm, "al": "right" if nm in L else "left"})
    sc = {"x": {"scale": {"domain": [0, W], "nice": False}, "axis": None},
          "y": {"scale": {"domain": [H + 24, -24], "nice": False}, "axis": None}}
    def xy(fx, fy):
        return {"x": dict(field=fx, type="quantitative", **sc["x"]),
                "y": dict(field=fy, type="quantitative", **sc["y"])}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": W, "height": H + 48,
            "layer": [
                {"data": {"values": ribbons},
                 "mark": {"type": "area", "interpolate": "linear", "opacity": 0.8,
                          "stroke": "black", "strokeWidth": 0.8},
                 # NO `order` channel. It is not needed -- the samples are emitted left to right --
                 # and adding it splits the area into one degenerate mark per sample: 175 vertical
                 # hairlines where seven ribbons should be.
                 "encoding": dict(xy("x", "y0"), y2={"field": "y1"},
                                  detail={"field": "k", "type": "nominal"},
                                  color={"field": "fill", "type": "nominal", "scale": None,
                                         "legend": None})},
                {"data": {"values": nodes},
                 "mark": {"type": "rect", "fill": GRAY, "stroke": "black",
                          "strokeWidth": 1},
                 "encoding": dict(xy("x0", "y0"), x2={"field": "x1"}, y2={"field": "y1"})},
                {"data": {"values": mids},
                 "mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black", "align": "left"},
                 "encoding": dict(xy("x", "y"), text={"field": "t", "type": "nominal"})},
                {"data": {"values": labels},
                 "mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black"},
                 "encoding": dict(xy("x", "y"), text={"field": "t", "type": "nominal"},
                                  align={"field": "al", "type": "nominal"})}],
            "config": dict(cfg, view={"stroke": None})}


def _pictograph_vl(spec, cfg, schema):
    """Counting in pictures: one icon is N of the thing, and you read the row by counting."""
    rows_in = spec.get("rows") or []
    each = float(spec.get("each", 1))
    cells = []
    for r, row in enumerate(rows_in):
        n = int(round(float(row["value"]) / each))
        for i in range(n):
            cells.append({"r": row["label"], "i": i,
                          "icon": icon_path(row.get("icon", "star")),
                          "fill": pen(row.get("color", "blue"))})
    widest = max([len([c for c in cells if c["r"] == row["label"]]) for row in rows_in] or [1])
    names = [r["label"] for r in rows_in]
    totals = [{"r": r["label"], "i": widest, "t": spec.get("fmt", "%g") % float(r["value"])}
              for r in rows_in]
    yenc = {"field": "r", "type": "nominal", "sort": names, "title": None,
            "axis": {"domain": False, "ticks": False, "labelFontSize": 17, "labelLimit": 0}}
    xenc = {"field": "i", "type": "ordinal", "axis": None,
            "scale": {"domain": list(range(widest + 1))}}
    key = "one %s = %s" % (spec.get("icon_word", "icon"),
                           (spec.get("fmt", "%g") % float(each)) +
                           (" " + spec["unit"] if spec.get("unit") else ""))
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": min(WIDTH - 220, 58 * (widest + 1) + 40), "height": 66 * len(rows_in) + 20,
            "layer": [
                {"data": {"values": cells},
                 "mark": {"type": "point", "size": 1500, "filled": False, "strokeWidth": 2,
                          "opacity": 1, "strokeCap": "round", "strokeJoin": "round"},
                 "encoding": {
                     "x": xenc, "y": yenc,
                     "shape": {"field": "icon", "type": "nominal", "scale": None,
                               "legend": None},
                     "stroke": {"field": "fill", "type": "nominal", "scale": None,
                                "legend": None}}},
                # the number as well as the picture: counting 12 books is not the point of a
                # pictograph, seeing that it is about twice the row below it is
                {"data": {"values": totals},
                 "mark": {"type": "text", "fontSize": 18, "fontWeight": "bold", "font": FONT,
                          "color": "black", "align": "left", "dx": 10},
                 "encoding": {"x": xenc, "y": yenc,
                              "text": {"field": "t", "type": "nominal"}}}],
            "title": {"text": spec.get("title", ""), "subtitle": key,
                      "subtitleFontSize": 15, "subtitleColor": "#404040"},
            "config": cfg}


_GEO_CACHE = {}


def _topo(which):
    """The topojson, READ AND INLINED rather than referenced by URL.

    A `data.url` pointing at a file on disk rendered a blank page with a NaN legend
    and no error: vl-convert's loader will not open a local file. Reading it here costs 0.1 MB in
    the spec and works offline, which is the whole point of having the atlas on disk.
    """
    if which not in _GEO_CACHE:
        src = os.path.join(GEO, "world-110m.json" if which == "world" else "us-10m.json")
        if not os.path.exists(src):
            raise SpecError("map data not found at %s -- expected the world-atlas / us-atlas "
                            "topojson there" % src)
        with open(src, encoding="utf-8") as f:
            _GEO_CACHE[which] = json.load(f)
    return _GEO_CACHE[which]


def _map_vl(spec, cfg, schema):
    """A real map: country outlines from world-atlas, states from us-atlas.

    Values may be keyed by the atlas's own id ("840", "06") OR by the region's NAME ("United
    States of America", "Utah") -- names are what a model actually emits, and the atlas carries
    them in properties.name, so there is no reason to make anyone look up numeric codes.
    """
    which = spec.get("map", "world")
    topo = _topo(which)
    obj = "countries" if which == "world" else "states"
    by_name = dict((str(g.get("properties", {}).get("name", "")).lower(), g.get("id"))
                   for g in topo["objects"][obj]["geometries"])
    vals, unknown = [], []
    for k, v in (spec.get("values") or {}).items():
        rid = str(k) if str(k).isdigit() else by_name.get(str(k).lower())
        if rid is None:
            unknown.append(str(k))
            continue
        vals.append({"id": rid, "v": float(v)})
    if unknown:
        raise SpecError("no region called %s on the %s map" % (", ".join(unknown[:4]), which))
    proj = spec.get("projection") or ("naturalEarth1" if which == "world" else "albersUsa")
    data = {"values": topo, "format": {"type": "topojson", "feature": obj}}
    # Antarctica is a quarter of the drawing and carries data on no chart anyone makes. Dropping
    # it also lets the projection fit the rest of the world into the full height.
    drop = ([] if which != "world" or spec.get("antarctica")
            else [{"filter": "datum.id !== '010' && datum.id !== '260'"}])
    layers = [{"data": data, "transform": drop,
               "mark": {"type": "geoshape", "fill": "#FFFFFF", "stroke": "black",
                        "strokeWidth": 0.8}}]
    if vals:
        layers.append({
            "data": data,
            "transform": drop + [{"lookup": "id", "from": {"data": {"values": vals},
                                                           "key": "id", "fields": ["v"]}}],
            "mark": {"type": "geoshape", "stroke": "black", "strokeWidth": 0.8},
            "encoding": {"color": {"field": "v", "type": "quantitative",
                                   "title": spec.get("legend_title"),
                                   "scale": {"range": [WASH["white"], WASH["blue"],
                                                       INK["cyan"], INK["blue"]]},
                                   "legend": {"orient": "bottom-left", "direction": "horizontal",
                                              "gradientLength": 260, "titleFontSize": 15,
                                              "labelFontSize": 14, "offset": -10}}}})
    for pt in (spec.get("points") or []):
        layers.append({
            "data": {"values": [{"lon": float(pt["lon"]), "lat": float(pt["lat"]),
                                 "t": str(pt.get("label", ""))}]},
            "mark": {"type": "point", "size": 260, "filled": True, "opacity": 1,
                     "fill": WASH.get(pt.get("color", "magenta"), WASH["magenta"]),
                     "stroke": "black", "strokeWidth": 2},
            "encoding": {"longitude": {"field": "lon", "type": "quantitative"},
                         "latitude": {"field": "lat", "type": "quantitative"}}})
        if pt.get("label"):
            layers.append({
                "data": {"values": [{"lon": float(pt["lon"]), "lat": float(pt["lat"]),
                                     "t": str(pt["label"])}]},
                "mark": {"type": "text", "fontSize": 15, "fontWeight": "bold", "font": FONT,
                         "color": "black", "align": "left", "dx": 12, "dy": -2},
                "encoding": {"longitude": {"field": "lon", "type": "quantitative"},
                             "latitude": {"field": "lat", "type": "quantitative"},
                             "text": {"field": "t", "type": "nominal"}}})
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 90, "height": 620,
            "projection": {"type": proj}, "layer": layers,
            "config": dict(cfg, view={"stroke": None})}


def _stock_vl(spec, cfg, schema):
    """A price line with the things a price line always wants: a shaded band under it, a moving
    average, event pins, and the last value called out. Not a generic line chart."""
    bars = spec.get("bars") or []
    rows = [{"i": i, "t": str(b["t"]), "c": float(b["close"]),
             "v": float(b.get("volume", 0))} for i, b in enumerate(bars)]
    win = int(spec.get("ma", 0) or 0)
    if win > 1:
        for i, r in enumerate(rows):
            lo = max(0, i - win + 1)
            r["ma"] = sum(x["c"] for x in rows[lo:i + 1]) / float(i - lo + 1)
    up = rows[-1]["c"] >= rows[0]["c"]
    ink = INK["green"] if up else INK["red"]
    fill = WASH["green"] if up else WASH["magenta"]
    # An area mark's implicit y2 is ZERO, so the band filled the whole plot from the axis up and
    # dragged the domain down with it. A floor just under the data keeps it a band.
    lo = min(r["c"] for r in rows)
    hi = max(r["c"] for r in rows)
    span = (hi - lo) or 1.0
    floor, ceil = lo - span * 0.18, hi + span * 0.16
    for r in rows:
        r["floor"] = floor
    H = 560
    yenc = {"field": "c", "type": "quantitative", "title": spec.get("y_label"),
            "scale": {"domain": [floor, ceil], "nice": False}}
    xenc = {"field": "i", "type": "quantitative", "title": spec.get("x_label"),
            "scale": {"domain": [0, len(rows) - 1], "nice": False},
            "axis": {"labelExpr": "", "values": [], "ticks": False, "domain": True}}
    # The x axis is an INDEX, so labels are drawn as their own text layer at a chosen stride --
    # a date on every bar is unreadable and Vega's own thinning rotates them to 90 degrees.
    step = max(1, len(rows) // 8)
    ticks = [dict(r, lab=r["t"]) for r in rows[::step]]
    layers = [
        {"mark": {"type": "area", "line": False, "color": fill, "opacity": 0.55},
         "encoding": {"x": xenc, "y": yenc, "y2": {"field": "floor"}}},
        {"mark": {"type": "line", "color": ink, "strokeWidth": 3},
         "encoding": {"x": xenc, "y": {"field": "c", "type": "quantitative"}}}]
    if win > 1:
        layers.append({"mark": {"type": "line", "color": "black", "strokeWidth": 2,
                                "strokeDash": [10, 6]},
                       "encoding": {"x": xenc, "y": {"field": "ma", "type": "quantitative"}}})
    for ev in (spec.get("events") or []):
        i = next((r["i"] for r in rows if r["t"] == str(ev.get("t"))), None)
        if i is None:
            continue
        layers.append({"data": {"values": [{"i": i, "lab": ev.get("label", "")}]},
                       "mark": {"type": "rule", "strokeWidth": 2, "color": GRAY,
                                "strokeDash": [4, 4]},
                       "encoding": {"x": xenc}})
        layers.append({"data": {"values": [{"i": i, "lab": ev.get("label", "")}]},
                       "mark": {"type": "text", "fontSize": 22, "font": FONT, "color": "black",
                                "align": "left", "baseline": "top", "dx": 6, "dy": 6,
                                "fontWeight": "bold"},
                       "encoding": {"x": xenc, "y": {"value": 0},
                                    "text": {"field": "lab", "type": "nominal"}}})
    last = rows[-1]
    layers += [
        {"data": {"values": [last]},
         "mark": {"type": "point", "size": 200, "filled": True, "color": ink,
                  "stroke": "black", "strokeWidth": 2, "opacity": 1},
         "encoding": {"x": xenc, "y": {"field": "c", "type": "quantitative"}}},
        {"data": {"values": [dict(last, lab="%s  %s" % (last["t"],
                                                        spec.get("fmt", "%g") % last["c"]))]},
         "mark": {"type": "text", "fontSize": 24, "fontWeight": "bold", "font": FONT,
                  "color": "black", "align": "right", "dx": -10, "dy": -20},
         "encoding": {"x": xenc, "y": {"field": "c", "type": "quantitative"},
                      "text": {"field": "lab", "type": "nominal"}}},
        {"data": {"values": ticks},
         "mark": {"type": "text", "fontSize": 22, "font": FONT, "color": "black",
                  "baseline": "top", "dy": 10},
         "encoding": {"x": xenc, "y": {"value": H},
                      "text": {"field": "lab", "type": "nominal"}}}]
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 120, "height": H, "data": {"values": rows},
            "layer": layers, "config": cfg}


def _bullet_vl(spec, cfg, schema):
    """Actual against target, one row each -- the densest honest way to show 'are we on track'.

    Measured as a PERCENTAGE OF TARGET, not in raw units. Raw units share one x scale across rows,
    so a row whose target is 2 got a track two pixels long next to a row whose target is 30; the
    gray track is supposed to mean the same thing on every line, and at 100% it does.
    """
    items = spec.get("items") or []
    rows = []
    for it in items:
        tgt = float(it["target"]) or 1.0
        pct = 100.0 * float(it["value"]) / tgt
        p = min(pct, 170.0)
        rows.append({"l": it["label"], "v": float(it["value"]), "t": tgt, "pct": p,
                     # the label goes INSIDE the bar once the bar is nearly full width, or it
                     # runs off the plot ("40 / 24" lost its first character)
                     "lx": p, "la": "right" if p > 140 else "left",
                     "ldx": -10 if p > 140 else 10,
                     "lab": "%g / %g" % (float(it["value"]), tgt),
                     "hit": "yes" if float(it["value"]) >= tgt else "no"})
    names = [r["l"] for r in rows]
    yenc = {"field": "l", "type": "nominal", "sort": names, "title": None,
            "axis": {"labelFontSize": 26, "labelLimit": 0, "domain": False, "ticks": False}}
    ttl = spec.get("x_label") or "% of target"
    xsc = {"domain": [0, 170], "nice": False}
    xax = {"values": [0, 50, 100, 150], "labelExpr": "datum.value + '%'"}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 300, "height": 56 * len(rows) + 30, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "bar", "color": "#EDEDED", "stroke": "black",
                          "strokeWidth": 1, "height": {"band": 0.78}},
                 "encoding": {"x": {"datum": 170, "type": "quantitative", "scale": xsc,
                                    "title": ttl, "axis": xax},
                              "y": yenc}},
                {"mark": {"type": "bar", "stroke": "black", "strokeWidth": 1.5,
                          "height": {"band": 0.46}},
                 # every x channel carries the title, or the axes merge and one of the untitled
                 # ones wins -- the axis came out labeled "pct", the field name
                 "encoding": {"x": {"field": "pct", "type": "quantitative", "scale": xsc,
                                    "title": ttl, "axis": xax},
                              "y": yenc,
                              "color": {"field": "hit", "type": "nominal", "legend": None,
                                        "scale": {"domain": ["yes", "no"],
                                                  "range": [WASH["green"], WASH["magenta"]]}}}},
                {"mark": {"type": "tick", "color": "black", "thickness": 5, "size": 42},
                 "encoding": {"x": {"datum": 100, "type": "quantitative", "scale": xsc,
                                    "title": ttl, "axis": xax},
                              "y": yenc}},
                ] + [
                # Two layers, because `align` driven from a field does nothing: every label came
                # out centered on the bar's end and "40 / 24" was cut in half by the bar edge.
                {"data": {"values": [r for r in rows if r["la"] == side]},
                 "mark": {"type": "text", "fontSize": 22, "font": FONT, "color": "black",
                          "fontWeight": "bold", "align": side,
                          "dx": 10 if side == "left" else -10},
                 "encoding": {"x": {"field": "lx", "type": "quantitative", "scale": xsc,
                                    "title": ttl, "axis": xax},
                              "y": yenc,
                              "text": {"field": "lab", "type": "nominal"}}}
                for side in ("left", "right") if any(r["la"] == side for r in rows)],
            "config": cfg}


def _slope_vl(spec, cfg, schema):
    """Before and after, joined. Rank change and magnitude in one read; a paired bar chart hides
    both behind a mental subtraction."""
    items = spec.get("items") or []
    a_lab, b_lab = spec.get("before_label", "Before"), spec.get("after_label", "After")
    rows = []
    for it in items:
        rows.append({"l": it["label"], "side": a_lab, "x": 0, "v": float(it["before"])})
        rows.append({"l": it["label"], "side": b_lab, "x": 1, "v": float(it["after"])})
    names = [it["label"] for it in items]
    n = len(names)
    vs = [r["v"] for r in rows]
    pad = (max(vs) - min(vs)) * 0.08 or 1.0
    ylo = max(0.0, min(vs) - pad) if min(vs) >= 0 else min(vs) - pad
    base = {"x": {"field": "x", "type": "quantitative", "axis": None,
                  "scale": {"domain": [-0.42, 1.42], "nice": False}},
            "y": {"field": "v", "type": "quantitative", "title": spec.get("y_label"),
                  # padding pushed the domain to -5 on a chart of counts
                  "scale": {"domain": [ylo, max(vs) + pad], "nice": False}}}
    col = {"field": "l", "type": "nominal", "legend": None,
           "scale": {"domain": names, "range": (LINE_INK * 4)[:n]}}
    heads = [{"l": it["label"], "x": 0, "v": float(it["before"]),
              "lab": "%s  %g" % (it["label"], it["before"])} for it in items]
    tails = [{"l": it["label"], "x": 1, "v": float(it["after"]),
              "lab": "%g  %s" % (it["after"], it["label"])} for it in items]
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 480, "height": 560, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "line", "strokeWidth": 3},
                 "encoding": dict(base, color=col, detail={"field": "l", "type": "nominal"})},
                {"mark": {"type": "point", "size": 140, "filled": True, "stroke": "black",
                          "strokeWidth": 1.5},
                 "encoding": dict(base, color=col)},
                {"data": {"values": heads},
                 "mark": {"type": "text", "align": "right", "dx": -12, "fontSize": 22,
                          "font": FONT, "color": "black"},
                 "encoding": dict(base, text={"field": "lab", "type": "nominal"})},
                {"data": {"values": tails},
                 "mark": {"type": "text", "align": "left", "dx": 12, "fontSize": 22,
                          "font": FONT, "color": "black"},
                 "encoding": dict(base, text={"field": "lab", "type": "nominal"})},
                {"data": {"values": [{"x": 0, "t": a_lab}, {"x": 1, "t": b_lab}]},
                 "mark": {"type": "text", "fontSize": 24, "fontWeight": "bold", "font": FONT,
                          "color": "black", "baseline": "bottom", "dy": -8},
                 "encoding": {"x": base["x"], "y": {"value": 0},
                              "text": {"field": "t", "type": "nominal"}}}],
            "config": cfg}


def _dumbbell_vl(spec, cfg, schema):
    """Two values per row with the gap drawn. The gap IS the story, so give it a line."""
    items = spec.get("items") or []
    a_lab, b_lab = spec.get("a_label", "A"), spec.get("b_label", "B")
    names = [it["label"] for it in items]
    rows = [{"l": it["label"], "a": float(it["a"]), "b": float(it["b"])} for it in items]
    pts = ([{"l": r["l"], "v": r["a"], "k": a_lab} for r in rows] +
           [{"l": r["l"], "v": r["b"], "k": b_lab} for r in rows])
    allv = [v for r in rows for v in (r["a"], r["b"])]
    pad = (max(allv) - min(allv)) * 0.08 or 1.0
    xlo = max(0.0, min(allv) - pad) if min(allv) >= 0 else min(allv) - pad
    xsc = {"domain": [xlo, max(allv) + pad], "nice": False}
    yenc = {"field": "l", "type": "nominal", "sort": names, "title": None,
            "axis": {"labelFontSize": 26, "labelLimit": 0, "domain": False, "ticks": False}}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 300, "height": 52 * len(rows) + 30,
            "layer": [
                {"data": {"values": rows},
                 "mark": {"type": "rule", "strokeWidth": 4, "color": RULE},
                 "encoding": {"y": yenc,
                              "x": {"field": "a", "type": "quantitative",
                                    "title": spec.get("x_label"), "scale": xsc,
                                    "axis": {"tickCount": 8}},       # every 40 px, its 26 px labels ran together
                              "x2": {"field": "b"}}},
                {"data": {"values": pts},
                 "mark": {"type": "point", "size": 260, "filled": True, "stroke": "black",
                          "strokeWidth": 2, "opacity": 1},
                 "encoding": {"y": yenc,
                              "x": {"field": "v", "type": "quantitative", "scale": xsc},
                              "color": {"field": "k", "type": "nominal", "title": None,
                                        "scale": {"domain": [a_lab, b_lab],
                                                  "range": [WASH["blue"], WASH["orange"]]}},
                              "shape": {"field": "k", "type": "nominal", "title": None,
                                        "scale": {"domain": [a_lab, b_lab],
                                                  "range": ["circle", "diamond"]}}}}],
            # the legend defaults to top-left, which is INSIDE the plot and on top of the first row
            "config": dict(cfg, legend=dict(cfg["legend"], orient="bottom-right",
                                            direction="horizontal", offset=6))}


def _bump_vl(spec, cfg, schema):
    """Rank over time. Position is rank, not value, so crossings are the whole point -- y is
    inverted because rank 1 belongs at the top."""
    series = spec.get("series") or []
    periods = spec.get("periods") or [str(i + 1) for i in range(len(series[0]["values"]))]
    rows = [{"s": s["name"], "p": periods[i], "pi": i, "r": int(v)}
            for s in series for i, v in enumerate(s["values"])]
    names = [s["name"] for s in series]
    worst = max(r["r"] for r in rows)
    np_ = len(periods)
    # Room on the right for the series NAME. No legend was rendering at all, and a name at the end
    # of its own line beats a lookup table anyway -- the end of the line is where the eye already is.
    base = {"x": {"field": "pi", "type": "quantitative", "title": None,
                  "scale": {"domain": [-0.5, np_ - 1 + 2.4], "nice": False},
                  "axis": {"values": list(range(np_)),
                           "labelExpr": "%s[datum.value]" % json.dumps(periods),
                           "labelFontSize": 26, "grid": True, "gridDash": [2, 6],
                           "gridColor": "#BBBBBB"}},
            "y": {"field": "r", "type": "quantitative", "title": "Rank",
                  "scale": {"domain": [worst + 0.5, 0.5], "nice": False},
                  "axis": {"values": list(range(1, worst + 1)), "labelFontSize": 26}}}
    col = {"field": "s", "type": "nominal", "legend": None,
           "scale": {"domain": names, "range": (LINE_INK * 4)[:len(names)]}}
    ends = [{"s": s["name"], "pi": np_ - 1, "r": int(s["values"][-1])} for s in series]
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 180, "height": 70 * worst + 60, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "line", "strokeWidth": 4, "interpolate": "monotone"},
                 "encoding": dict(base, color=col, detail={"field": "s", "type": "nominal"})},
                {"mark": {"type": "point", "size": 300, "filled": True, "stroke": "black",
                          "strokeWidth": 2, "opacity": 1},
                 "encoding": dict(base, color=col)},
                {"mark": {"type": "text", "fontSize": 13, "fontWeight": "bold", "font": FONT,
                          "color": "white"},
                 "encoding": dict(base, text={"field": "r", "type": "quantitative"})},
                {"data": {"values": ends},
                 "mark": {"type": "text", "fontSize": 24, "fontWeight": "bold", "font": FONT,
                          "align": "left", "dx": 20},
                 "encoding": dict(base, text={"field": "s", "type": "nominal"}, color=col)}],
            "config": cfg}


def _matrix_vl(spec, cfg, schema):
    """Two-by-two with the labels living in the quadrants, for effort/impact and its cousins."""
    return _quadrant_vl(spec, cfg, schema)


def _quadrant_vl(spec, cfg, schema):
    items = spec.get("items") or []
    xm = float(spec.get("x_mid", 50))
    ym = float(spec.get("y_mid", 50))
    lo_x, hi_x = spec.get("x_range", [0, 100])
    lo_y, hi_y = spec.get("y_range", [0, 100])
    # Labels flip to the left of their marker in the right-hand fifth of the plot; at the default
    # they ran straight off the edge ("second tablet" lost its last three letters).
    flip = lo_x + (hi_x - lo_x) * 0.62
    rows = [{"l": it["label"], "x": float(it["x"]), "y": float(it["y"]),
             "al": "right" if float(it["x"]) > flip else "left",
             "dx": -16 if float(it["x"]) > flip else 16} for it in items]
    qn = spec.get("quadrants") or {}
    # Anchored at each quadrant's OUTER corner, not at (x0,y0) -- which for the top two is the
    # middle of the chart, where both titles ended up sitting on the divider.
    bands = [{"x0": lo_x, "x1": xm, "y0": ym, "y1": hi_y, "t": qn.get("tl", ""),
              "lx": lo_x, "ly": hi_y, "al": "left", "ba": "top", "f": WASH["blue"]},
             {"x0": xm, "x1": hi_x, "y0": ym, "y1": hi_y, "t": qn.get("tr", ""),
              "lx": hi_x, "ly": hi_y, "al": "right", "ba": "top", "f": WASH["green"]},
             {"x0": lo_x, "x1": xm, "y0": lo_y, "y1": ym, "t": qn.get("bl", ""),
              "lx": lo_x, "ly": lo_y, "al": "left", "ba": "bottom", "f": WASH["gray"]},
             {"x0": xm, "x1": hi_x, "y0": lo_y, "y1": ym, "t": qn.get("br", ""),
              "lx": hi_x, "ly": lo_y, "al": "right", "ba": "bottom", "f": WASH["orange"]}]
    xenc = {"field": "x", "type": "quantitative", "title": spec.get("x_label"),
            "scale": {"domain": [lo_x, hi_x], "nice": False}}
    yenc = {"field": "y", "type": "quantitative", "title": spec.get("y_label"),
            "scale": {"domain": [lo_y, hi_y], "nice": False}}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 420, "height": 640,
            "layer": [
                {"data": {"values": bands},
                 "mark": {"type": "rect", "opacity": 0.5},
                 "encoding": {"x": {"field": "x0", "type": "quantitative",
                                    "scale": xenc["scale"], "title": spec.get("x_label")},
                              "x2": {"field": "x1"},
                              "y": {"field": "y0", "type": "quantitative",
                                    "scale": yenc["scale"], "title": spec.get("y_label")},
                              "y2": {"field": "y1"},
                              "color": {"field": "f", "type": "nominal", "scale": None,
                                        "legend": None}}},
                ] + [
                # ONE LAYER PER CORNER, with align/baseline/dx/dy fixed in the mark. Driving them
                # from a data field left every label centered on its anchor: `align` and `xOffset`
                # are not pass-through channels, and a nominal field through them does nothing
                # useful. Four literal layers cost nothing and are unambiguous.
                {"data": {"values": [b]},
                 "mark": {"type": "text", "fontSize": 24, "fontWeight": "bold", "font": FONT,
                          "color": GRAY, "align": b["al"], "baseline": b["ba"],
                          "dx": 16 if b["al"] == "left" else -16,
                          "dy": 16 if b["ba"] == "top" else -16},
                 "encoding": {"x": {"field": "lx", "type": "quantitative",
                                    "scale": xenc["scale"]},
                              "y": {"field": "ly", "type": "quantitative",
                                    "scale": yenc["scale"]},
                              "text": {"field": "t", "type": "nominal"}}}
                for b in bands if b["t"]] + [
                {"data": {"values": rows},
                 "mark": {"type": "point", "size": 240, "filled": True, "color": "white",
                          "stroke": "black", "strokeWidth": 2, "opacity": 1},
                 "encoding": {"x": xenc, "y": yenc}}] + [
                {"data": {"values": [r for r in rows if r["al"] == side]},
                 "mark": {"type": "text", "fontSize": 22, "font": FONT, "color": "black",
                          "align": side, "dy": -2,
                          "dx": 16 if side == "left" else -16},
                 "encoding": {"x": xenc, "y": yenc,
                              "text": {"field": "l", "type": "nominal"}}}
                for side in ("left", "right") if any(r["al"] == side for r in rows)],
            "config": dict(cfg, view={"stroke": "black", "strokeWidth": 1})}


def _sparkbars_vl(spec, cfg, schema):
    """A table whose middle column is a chart: a name, the shape of how it got there, where it is
    now, and the change. A dashboard row, on one line.

    Laid out in pixels like the sankey and the radar. `yOffset` on a bar mark was the first attempt
    and it drew every bar the same height -- offsets shift a bar, they do not scale it.
    """
    rows_in = spec.get("rows") or []
    W = 1060.0
    LBL, X0, X1, NOW, DEL = 232.0, 258.0, 760.0, 800.0, W
    RH, BH = 58.0, 40.0
    bars, names, labels, base = [], [], [], []
    for ri, r in enumerate(rows_in):
        vals = [float(v) for v in r["values"]]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        cy = ri * RH + RH / 2.0
        bot = cy + BH / 2.0
        w = (X1 - X0) / len(vals)
        for i, v in enumerate(vals):
            # Scaled between the row's OWN min and max: a sparkline is about shape, and a common
            # zero baseline would flatten every row that does not start near zero.
            h = 6.0 + (BH - 6.0) * (v - lo) / span
            bars.append({"ri": ri, "x0": X0 + i * w + 1.5, "x1": X0 + (i + 1) * w - 1.5,
                         "y0": bot - h, "y1": bot,
                         "fill": INK["blue"] if i == len(vals) - 1 else WASH["blue"]})
        base.append({"x0": X0, "x1": X1, "y0": bot, "y1": bot + 1.5})
        names.append({"x": LBL, "y": cy, "t": str(r["label"])})
        d = (100.0 * (vals[-1] - vals[0]) / abs(vals[0])) if vals[0] else 0.0
        labels.append({"x": NOW, "y": cy, "t": spec.get("fmt", "%g") % vals[-1],
                       "x2": DEL, "d": ("%+.0f%%" % d) if vals[0] else "",
                       # black for up, the red pen for down. The device's green pen is #A9FA5C --
                       # a highlighter green that is simply not legible as small bold text.
                       "dc": "#000000" if d >= 0 else INK["red"]})
    H = RH * len(rows_in)
    sc = {"x": {"scale": {"domain": [0, W], "nice": False}, "axis": None},
          "y": {"scale": {"domain": [H, 0], "nice": False}, "axis": None}}
    def xy(fx, fy):
        return {"x": dict(field=fx, type="quantitative", **sc["x"]),
                "y": dict(field=fy, type="quantitative", **sc["y"])}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": W, "height": H,
            "layer": [
                {"data": {"values": base},
                 "mark": {"type": "rect", "fill": "#C0C0C0"},
                 "encoding": dict(xy("x0", "y0"), x2={"field": "x1"}, y2={"field": "y1"})},
                {"data": {"values": bars},
                 "mark": {"type": "rect", "stroke": "black", "strokeWidth": 0.7},
                 "encoding": dict(xy("x0", "y0"), x2={"field": "x1"}, y2={"field": "y1"},
                                  color={"field": "fill", "type": "nominal", "scale": None,
                                         "legend": None})},
                {"data": {"values": names},
                 "mark": {"type": "text", "fontSize": 24, "font": FONT, "color": "black",
                          "align": "right"},
                 "encoding": dict(xy("x", "y"), text={"field": "t", "type": "nominal"})},
                {"data": {"values": labels},
                 "mark": {"type": "text", "fontSize": 26, "fontWeight": "bold", "font": FONT,
                          "color": "black", "align": "left"},
                 "encoding": dict(xy("x", "y"), text={"field": "t", "type": "nominal"})},
                {"data": {"values": labels},
                 "mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "align": "right"},
                 "encoding": dict(xy("x2", "y"), text={"field": "d", "type": "nominal"},
                                  color={"field": "dc", "type": "nominal", "scale": None,
                                         "legend": None})}],
            "config": dict(cfg, view={"stroke": None})}


def _waterfall_vl(spec, cfg, schema):
    """How a number got from one value to another. Every bar starts where the last one stopped, so
    the CONTRIBUTIONS are what you read, not the running total."""
    items = spec.get("items") or []
    rows, run = [], float(spec.get("start", 0))
    if spec.get("start_label"):
        rows.append({"l": spec["start_label"], "y0": 0.0, "y1": run, "k": "total",
                     "lab": spec.get("fmt", "%g") % run})
    for it in items:
        if it.get("total"):
            rows.append({"l": it["label"], "y0": 0.0, "y1": run, "k": "total",
                         "lab": spec.get("fmt", "%g") % run})
            continue
        d = float(it["value"])
        rows.append({"l": it["label"], "y0": run, "y1": run + d,
                     "k": "up" if d >= 0 else "down",
                     "lab": ("%+" + spec.get("fmt", "%g")[1:]) % d})
        run += d
    if spec.get("end_label"):
        rows.append({"l": spec["end_label"], "y0": 0.0, "y1": run, "k": "total",
                     "lab": spec.get("fmt", "%g") % run})
    names = [r["l"] for r in rows]
    conn = []
    for a, b in zip(rows, rows[1:]):
        conn.append({"i": names.index(a["l"]), "y": a["y1"], "l": a["l"], "l2": b["l"]})
    for r in rows:
        r["ly"] = max(r["y0"], r["y1"])   # the label goes above the bar, falling or rising
    lo = min([0.0] + [min(r["y0"], r["y1"]) for r in rows])
    hi = max(max(r["y0"], r["y1"]) for r in rows)
    pad = (hi - lo) * 0.10 or 1.0
    if lo >= 0:
        lo = 0.0                          # no -2 GB tick on a chart of gigabytes
    else:
        lo -= pad
    xenc = {"field": "l", "type": "nominal", "sort": names, "title": spec.get("x_label"),
            "axis": {"labelAngle": 0, "labelFontSize": 26, "labelLimit": 0}}
    yenc = {"field": "y0", "type": "quantitative", "title": spec.get("y_label"),
            "scale": {"domain": [lo, hi + pad], "nice": False}}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 120, "height": 560, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "rule", "color": RULE, "strokeWidth": 1.5,
                          "strokeDash": [3, 3], "xOffset": 4, "x2Offset": -4},
                 "data": {"values": conn},
                 "encoding": {"x": dict(xenc, title=None),
                              "x2": {"field": "l2"},
                              "y": {"field": "y", "type": "quantitative",
                                    "scale": yenc["scale"]}}},
                {"mark": {"type": "bar", "stroke": "black", "strokeWidth": 1.5,
                          "width": {"band": 0.66}},
                 "encoding": {"x": xenc, "y": yenc, "y2": {"field": "y1"},
                              "color": {"field": "k", "type": "nominal", "legend": None,
                                        "scale": {"domain": ["up", "down", "total"],
                                                  "range": [WASH["green"], WASH["magenta"],
                                                            WASH["blue"]]}}}},
                {"mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black", "baseline": "bottom", "dy": -6},
                 "encoding": {"x": xenc,
                              "y": {"field": "ly", "type": "quantitative",
                                    "scale": yenc["scale"]},
                              "text": {"field": "lab", "type": "nominal"}}}],
            "config": cfg}


def _histogram_vl(spec, cfg, schema):
    """Counts per bin. Binned HERE, because Vega's binning would pick its own boundaries and the
    spec should be able to say 'ten bins' and get ten."""
    vals = [float(v) for v in (spec.get("values") or [])]
    nb = int(spec.get("bins", 12))
    lo, hi = min(vals), max(vals)
    w = (hi - lo) / nb or 1.0
    counts = [0] * nb
    for v in vals:
        counts[min(nb - 1, int((v - lo) / w))] += 1
    rows = [{"x0": lo + i * w, "x1": lo + (i + 1) * w, "c": c, "mid": lo + (i + 0.5) * w}
            for i, c in enumerate(counts)]
    mean = sum(vals) / len(vals)
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 120, "height": 540, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "bar", "stroke": "black", "strokeWidth": 1.2,
                          "color": WASH.get(spec.get("color", "blue"), WASH["blue"])},
                 "encoding": {"x": {"field": "x0", "type": "quantitative",
                                    "title": spec.get("x_label"), "bin": {"binned": True},
                                    "scale": {"domain": [lo, hi], "nice": False}},
                              "x2": {"field": "x1"},
                              "y": {"field": "c", "type": "quantitative",
                                    "title": spec.get("y_label", "count")}}},
                {"data": {"values": [{"m": mean}]},
                 "mark": {"type": "rule", "strokeWidth": 3, "color": INK["red"],
                          "strokeDash": [9, 5]},
                 "encoding": {"x": {"field": "m", "type": "quantitative",
                                    "scale": {"domain": [lo, hi], "nice": False}}}},
                {"data": {"values": [{"m": mean, "t": "mean %s"
                                      % (spec.get("fmt", "%.1f") % mean)}]},
                 "mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": INK["red"], "align": "left", "dx": 8, "dy": 8,
                          "baseline": "top"},
                 "encoding": {"x": {"field": "m", "type": "quantitative",
                                    "scale": {"domain": [lo, hi], "nice": False}},
                              "y": {"value": 0},
                              "text": {"field": "t", "type": "nominal"}}}],
            "config": cfg}


def _bubble_vl(spec, cfg, schema):
    """Three numbers per point: two positions and a size. The size is area, not radius -- radius
    triples the apparent difference and is the oldest lie in the chart book."""
    items = spec.get("items") or []
    rows = [{"l": it["label"], "x": float(it["x"]), "y": float(it["y"]),
             "s": float(it["size"]),
             "g": str(it.get("group", "")),
             "fill": WASH.get(it.get("color", PALETTE_NAMES[i % len(PALETTE_NAMES)]),
                              WASH["blue"])} for i, it in enumerate(items)]
    big = max(r["s"] for r in rows) or 1.0
    for r in rows:
        r["area"] = 200 + 4200 * (r["s"] / big)
    import math as _m
    xs = [r["x"] for r in rows]
    ys = [r["y"] for r in rows]
    H = 620
    def dom(v, f=0.16):
        pad = (max(v) - min(v)) * f or 1.0
        return [min(v) - pad, max(v) + pad]
    xd, yd = dom(xs), dom(ys, 0.22)
    # The label sits BELOW its bubble, and the drop is computed in DATA units from the bubble's
    # own radius -- centered on the mark it was unreadable, and Vega will not take a per-datum dy.
    per_px = (yd[1] - yd[0]) / float(H)
    for r in rows:
        r["ly"] = r["y"] - (_m.sqrt(r["area"] / _m.pi) + 15) * per_px
    xenc = {"field": "x", "type": "quantitative", "title": spec.get("x_label"),
            "scale": {"domain": xd, "nice": False}}
    yenc = {"field": "y", "type": "quantitative", "title": spec.get("y_label"),
            "scale": {"domain": yd, "nice": False}}
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 260, "height": H, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "point", "filled": True, "opacity": 0.85,
                          "stroke": "black", "strokeWidth": 1.6},
                 "encoding": {"x": xenc, "y": yenc,
                              "size": {"field": "area", "type": "quantitative", "legend": None,
                                       "scale": None},
                              "color": {"field": "fill", "type": "nominal", "scale": None,
                                        "legend": None}}},
                {"mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black", "baseline": "top"},
                 "encoding": {"x": xenc,
                              "y": {"field": "ly", "type": "quantitative",
                                    "scale": yenc["scale"]},
                              "text": {"field": "l", "type": "nominal"}}}],
            "config": cfg}


def _lollipop_vl(spec, cfg, schema):
    """A bar chart on a diet. Twenty categories of bar is a wall of ink; twenty stems and dots is
    a readable page, and the tablet thanks you for it."""
    items = spec.get("items") or []
    rows = [{"l": it["label"], "v": float(it["value"]), "zero": 0,
             "fill": WASH.get(it.get("color", "blue"), WASH["blue"]),
             "lab": spec.get("fmt", "%g") % float(it["value"])} for it in items]
    if spec.get("sort", True):
        rows.sort(key=lambda r: -r["v"])
    names = [r["l"] for r in rows]
    top = max(r["v"] for r in rows)
    low = min([0.0] + [r["v"] for r in rows])        # a negative value is drawn inside the plot, not off its left
    yenc = {"field": "l", "type": "nominal", "sort": names, "title": None,
            "axis": {"labelFontSize": 26, "labelLimit": 0, "domain": False, "ticks": False}}
    xenc = {"field": "v", "type": "quantitative", "title": spec.get("x_label"),
            "scale": {"domain": [low - (top - low) * 0.12 if low < 0 else 0, top + (top - low) * 0.12],
                      "nice": False}}         # room past each end for the value beside the dot
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 320, "height": 42 * len(rows) + 40, "data": {"values": rows},
            "layer": [
                # x from a FIELD, not a datum: `x: {datum: 0}` alongside `x2: {field: ...}`
                # crashes the compiler outright ("Cannot read properties of undefined").
                {"mark": {"type": "rule", "strokeWidth": 3, "color": RULE},
                 "encoding": {"y": yenc,
                              "x": {"field": "zero", "type": "quantitative",
                                    "scale": xenc["scale"], "title": spec.get("x_label")},
                              "x2": {"field": "v"}}},
                {"mark": {"type": "point", "size": 330, "filled": True, "opacity": 1,
                          "stroke": "black", "strokeWidth": 2},
                 "encoding": {"y": yenc, "x": xenc,
                              "color": {"field": "fill", "type": "nominal", "scale": None,
                                        "legend": None}}},
                # the value beside its dot, on the side away from the stem: right of a positive, left of a negative
                {"transform": [{"filter": "datum.v >= 0"}],
                 "mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black", "align": "left", "dx": 16},
                 "encoding": {"y": yenc, "x": xenc,
                              "text": {"field": "lab", "type": "nominal"}}},
                {"transform": [{"filter": "datum.v < 0"}],
                 "mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black", "align": "right", "dx": -16},
                 "encoding": {"y": yenc, "x": xenc,
                              "text": {"field": "lab", "type": "nominal"}}}],
            "config": cfg}


def _diverging_vl(spec, cfg, schema):
    """Bars from a center line: agree/disagree, over/under, gained/lost. One axis, two directions,
    and the zero is where the eye lands first."""
    items = spec.get("items") or []
    rows = [{"l": it["label"], "v": float(it["value"]),
             "k": "pos" if float(it["value"]) >= 0 else "neg",
             "lab": spec.get("fmt", "%g") % float(it["value"])} for it in items]
    if spec.get("sort", True):
        rows.sort(key=lambda r: -r["v"])
    for r in rows:
        r["la"] = "left" if r["v"] >= 0 else "right"
    names = [r["l"] for r in rows]
    m = max(abs(r["v"]) for r in rows) * 1.18
    yenc = {"field": "l", "type": "nominal", "sort": names, "title": None,
            "axis": {"labelFontSize": 26, "labelLimit": 0, "domain": False, "ticks": False,
                     "labelPadding": 10}}
    xenc = {"field": "v", "type": "quantitative", "title": spec.get("x_label"),
            "scale": {"domain": [-m, m], "nice": False}}
    pos = WASH.get(spec.get("positive", "green"), WASH["green"])
    neg = WASH.get(spec.get("negative", "magenta"), WASH["magenta"])
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 300, "height": 46 * len(rows) + 40, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "bar", "stroke": "black", "strokeWidth": 1.4,
                          "height": {"band": 0.7}},
                 "encoding": {"y": yenc, "x": xenc,
                              "color": {"field": "k", "type": "nominal", "legend": None,
                                        "scale": {"domain": ["pos", "neg"],
                                                  "range": [pos, neg]}}}},
                {"mark": {"type": "rule", "strokeWidth": 2.5, "color": "black"},
                 "encoding": {"x": {"datum": 0, "type": "quantitative",
                                    "scale": xenc["scale"]}}}] + [
                {"data": {"values": [r for r in rows if r["la"] == side]},
                 "mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black", "align": side,
                          "dx": 8 if side == "left" else -8},
                 "encoding": {"y": yenc, "x": xenc,
                              "text": {"field": "lab", "type": "nominal"}}}
                for side in ("left", "right") if any(r["la"] == side for r in rows)],
            "config": cfg}


def _pyramid_vl(spec, cfg, schema):
    """Two populations back to back on a shared band axis -- ages, shifts, cohorts."""
    bands = spec.get("bands") or []
    a_lab, b_lab = spec.get("a_label", "A"), spec.get("b_label", "B")
    rows = ([{"b": x["band"], "v": -float(x["a"]), "k": a_lab,
              "lab": spec.get("fmt", "%g") % float(x["a"])} for x in bands] +
            [{"b": x["band"], "v": float(x["b"]), "k": b_lab,
              "lab": spec.get("fmt", "%g") % float(x["b"])} for x in bands])
    names = [x["band"] for x in bands]
    m = max(abs(r["v"]) for r in rows) * 1.18
    yenc = {"field": "b", "type": "nominal", "sort": list(reversed(names)), "title": None,
            "axis": {"labelFontSize": 24, "labelLimit": 0, "domain": False, "ticks": False,
                     "labelPadding": 8}}
    xenc = {"field": "v", "type": "quantitative", "title": spec.get("x_label"),
            "scale": {"domain": [-m, m], "nice": False},
            "axis": {"labelExpr": "abs(datum.value)", "tickCount": 8}}   # every 40 px they ran together
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 260, "height": 40 * len(names) + 50, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "bar", "stroke": "black", "strokeWidth": 1.2,
                          "height": {"band": 0.84}},
                 "encoding": {"y": yenc, "x": xenc,
                              "color": {"field": "k", "type": "nominal", "title": None,
                                        "scale": {"domain": [a_lab, b_lab],
                                                  "range": [WASH["blue"], WASH["orange"]]}}}},
                {"mark": {"type": "rule", "strokeWidth": 2, "color": "black"},
                 "encoding": {"x": {"datum": 0, "type": "quantitative",
                                    "scale": xenc["scale"]}}}],
            "config": dict(cfg, legend=dict(cfg["legend"], orient="top",            # above the bars: inside the plot it sat on the longest one
                                           
                                            direction="horizontal"))}


def _marimekko_vl(spec, cfg, schema):
    """A stacked bar whose WIDTH also means something -- share within a segment, and the size of
    the segment, on one picture."""
    cols = spec.get("columns") or []
    # THE SHAPE THE MODEL IS TOLD (POWERS): each column carries its own parts, [{name, value, color?}]. The bands
    # are the part names in the order they first appear, each in its own palette color unless the spec names one.
    parts, seen = [], set()
    for c in cols:
        for p in c.get("parts") or []:
            if isinstance(p, dict) and p.get("name") is not None and str(p["name"]) not in seen:
                seen.add(str(p["name"]))
                parts.append({"name": str(p["name"]),
                              "color": p.get("color") or PALETTE_NAMES[len(parts) % len(PALETTE_NAMES)]})
    W, H = 1060.0, 600.0
    px = _Px(W, H + 112)
    tot = float(sum(c["value"] for c in cols)) or 1.0
    rects, heads, cells = [], [], []
    x = 0.0
    for c in cols:
        w = (W - 6 * (len(cols) - 1)) * c["value"] / tot
        have = dict((str(q.get("name")), float(q.get("value") or 0)) for q in c.get("parts") or []
                    if isinstance(q, dict))
        shares = [have.get(p["name"], 0.0) for p in parts]
        s = sum(shares) or 1.0
        y = 0.0
        for p, v in zip(parts, shares):
            h = H * v / s
            rects.append({"x0": x, "x1": x + w, "y0": y, "y1": y + h,
                          "fill": WASH.get(p.get("color", "blue"), WASH["blue"])})
            if h > 34 and w > 64:
                cells.append({"x": x + w / 2.0, "y": y + h / 2.0,
                              "t": "%.0f%%" % (100.0 * v / s)})
            y += h
        heads.append({"x": x + w / 2.0, "y": H + 24, "t": str(c["name"])})
        heads.append({"x": x + w / 2.0, "y": H + 52,
                      "t": spec.get("fmt", "%g") % c["value"]})
        x += w + 6
    # a key, because the segment labels are percentages and nothing else says what the bands are
    sw, kt, kx = [], [], 8.0
    for p in parts:
        sw.append({"x0": kx, "x1": kx + 26, "y0": H + 82, "y1": H + 102,
                   "fill": WASH.get(p.get("color", "blue"), WASH["blue"])})
        kt.append({"x": kx + 34, "y": H + 92, "t": str(p["name"])})
        kx += 56 + EM * 22 * len(str(p["name"]))
    return px.spec(spec.get("title", ""), [
        px.rect(rects),
        px.text(cells, 22, True),
        px.text(heads, 22, True),
        px.rect(sw),
        px.text(kt, 22, True, align="left")], cfg, schema)

def _worst(row, side):
    """Bruls' aspect-ratio cost for a candidate row -- the whole of squarify is this one number."""
    s = sum(row)
    if s <= 0:
        return 1e18
    return max(side * side * max(row) / (s * s), s * s / (side * side * min(row)))


def _squarify(vals, x, y, w, h):
    """Values (already scaled so their sum is w*h) into rectangles with sane aspect ratios.

    The first attempt at this recomputed the scale factor inside the loop and dropped the last row
    on the floor: half the items vanished into a black sliver. This is the textbook version --
    take items into the current row while the worst aspect ratio improves, then lay the row along
    whichever side is shorter and shrink the remaining box.
    """
    out, vals = [], list(vals)
    while vals and w > 0.5 and h > 0.5:
        side = min(w, h)
        row, i = [vals[0]], 1
        while i < len(vals) and _worst(row + [vals[i]], side) <= _worst(row, side):
            row.append(vals[i])
            i += 1
        s = sum(row)
        if w <= h:
            rh = s / w
            cx = x
            for v in row:
                rw = v / rh if rh else 0.0
                out.append((cx, y, cx + rw, y + rh))
                cx += rw
            y += rh
            h -= rh
        else:
            rw = s / h
            cy = y
            for v in row:
                rh2 = v / rw if rw else 0.0
                out.append((x, cy, x + rw, cy + rh2))
                cy += rh2
            x += rw
            w -= rw
        vals = vals[i:]
    return out


def _treemap_vl(spec, cfg, schema):
    """Squarified treemap: area is the value. Vega-Lite has no hierarchy transform, so the layout
    is solved here -- and squarified rather than slice-and-dice, because a 400:1 sliver carries no
    information even when its area is technically correct."""
    items = sorted((spec.get("items") or []), key=lambda i: -float(i["value"]))
    W, H = 1060.0, 640.0
    px = _Px(W, H)
    vals = [float(i["value"]) for i in items]
    k = (W * H) / (sum(vals) or 1.0)
    boxes = _squarify([v * k for v in vals], 0.0, 0.0, W, H)
    rects, labels = [], []
    for i, ((x0, y0, x1, y1), it) in enumerate(zip(boxes, items)):
        rects.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                      "fill": WASH.get(it.get("color",
                                              PALETTE_NAMES[i % len(PALETTE_NAMES)]),
                                       WASH["blue"])})
        bw, bh = x1 - x0, y1 - y0
        if bw > 80 and bh > 52:
            big = bw > 150 and bh > 86
            labels.append({"x": x0 + 11, "y": y0 + (18 if big else 14), "t": str(it["label"]),
                           "s": 26 if big else 18})
            labels.append({"x": x0 + 11, "y": y0 + (48 if big else 36),
                           "t": spec.get("fmt", "%g") % float(it["value"]),
                           "s": 22 if big else 16})
    return px.spec(spec.get("title", ""), [
        px.rect(rects, strokeWidth=2),
        {"data": {"values": labels}, "encoding": px.xy(
            text={"field": "t", "type": "nominal"},
            size={"field": "s", "type": "quantitative", "scale": None, "legend": None}),
         "mark": {"type": "text", "font": FONT, "color": "black", "fontWeight": "bold",
                  "align": "left", "baseline": "top"}}], cfg, schema)


def _venn_vl(spec, cfg, schema):
    """Two or three overlapping sets. Fixed positions and a fixed radius: a true area-proportional
    Venn is a solver, and at this size nobody reads the areas anyway -- they read the numbers."""
    sets = spec.get("sets") or []
    W, H = 900.0, 620.0
    px = _Px(W, H)
    R = 170.0
    if len(sets) == 2:
        cs = [(W / 2 - 100, H / 2), (W / 2 + 100, H / 2)]
        spots = {"a": (W / 2 - 165, H / 2), "b": (W / 2 + 165, H / 2), "ab": (W / 2, H / 2)}
        lab = {"a": (W / 2 - 200, H / 2 - 210), "b": (W / 2 + 200, H / 2 - 210)}
    else:
        cs = [(W / 2 - 105, H / 2 - 62), (W / 2 + 105, H / 2 - 62), (W / 2, H / 2 + 112)]
        spots = {"a": (W / 2 - 185, H / 2 - 110), "b": (W / 2 + 185, H / 2 - 110),
                 "c": (W / 2, H / 2 + 190), "ab": (W / 2, H / 2 - 105),
                 "ac": (W / 2 - 110, H / 2 + 56), "bc": (W / 2 + 110, H / 2 + 56),
                 "abc": (W / 2, H / 2 + 8)}
        lab = {"a": (W / 2 - 250, H / 2 - 250), "b": (W / 2 + 250, H / 2 - 250),
               "c": (W / 2, H / 2 + 280)}
    circles = [{"x": c[0], "y": c[1],
                "fill": WASH.get(s.get("color", PALETTE_NAMES[i]), PALETTE[i])}
               for i, (s, c) in enumerate(zip(sets, cs))]
    counts = [{"x": spots[k][0], "y": spots[k][1], "t": str(v)}
              for k, v in (spec.get("counts") or {}).items() if k in spots]
    names = [{"x": lab[k][0], "y": lab[k][1], "t": sets[i]["name"]}
             for i, k in enumerate("abc"[:len(sets)]) if k in lab]
    return px.spec(spec.get("title", ""), [
        {"data": {"values": circles},
         "mark": {"type": "point", "shape": "circle", "filled": True, "fillOpacity": 0.45,
                  "strokeOpacity": 1, "opacity": 1,
                  "size": 4 * 3.14159 * R * R / 4, "stroke": "black", "strokeWidth": 2.5},
         "encoding": px.xy(color={"field": "fill", "type": "nominal", "scale": None,
                                  "legend": None})},
        px.text(counts, 26, True),
        px.text(names, 24, True)], cfg, schema)


def _ridgeline_vl(spec, cfg, schema):
    """Stacked densities, overlapping slightly. Twelve of these fit where twelve histograms would
    need a whole page each."""
    groups = spec.get("groups") or []
    rows = [{"g": g["name"], "v": float(v)} for g in groups for v in g["values"]]
    names = [g["name"] for g in groups]
    lo, hi = min(r["v"] for r in rows), max(r["v"] for r in rows)
    pad = (hi - lo) * 0.04 or 1.0
    step = int(spec.get("step", 64))
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 260, "height": step, "data": {"values": rows},
            "transform": [{"density": "v", "groupby": ["g"], "as": ["value", "density"],
                           "steps": 96, "extent": [lo, hi]}],
            "mark": {"type": "area", "interpolate": "monotone", "stroke": "black",
                     "strokeWidth": 1.4, "fillOpacity": 0.86},
            "encoding": {
                "x": {"field": "value", "type": "quantitative", "title": spec.get("x_label"),
                      "scale": {"domain": [lo - pad, hi + pad], "nice": False}},
                "y": {"field": "density", "type": "quantitative", "title": None,
                      "scale": {"range": [step, -step * 1.1]},
                      "axis": None},
                "row": {"field": "g", "type": "nominal", "sort": names, "spacing": -step * 0.55,
                        "title": None,
                        "header": {"labelAngle": 0, "labelAlign": "right",
                                   "labelFontSize": 24, "labelFontWeight": "bold"}},
                "color": {"field": "g", "type": "nominal", "legend": None,
                          "scale": {"domain": names,
                                    "range": (PALETTE * 4)[:len(names)]}}},
            "config": dict(cfg, view={"stroke": None})}


def _polar_vl(spec, cfg, schema):
    """Bars bent round a circle -- for anything genuinely cyclical, where a straight axis lies
    about Sunday being next to Monday."""
    items = spec.get("items") or []
    n = len(items)
    top = max(float(i["value"]) for i in items) or 1.0
    import math as _m
    R0, R1, SZ = 70.0, 270.0, 22      # the wedges' inner and outer radius, the labels' size

    def lab(it):
        return "%s  %s" % (it["label"], spec.get("fmt", "%g") % float(it["value"]))

    def ring(i, it):
        """A label's radius in the scale's units: just clear of the outer edge at its own angle -- half its
        width out at the sides, half its height at the top and bottom."""
        th = 2 * _m.pi * (i + 0.5) / max(n, 1)
        w = EM * SZ * len(lab(it))
        r = R1 + 18 + (w / 2.0) * abs(_m.sin(th)) + (SZ * 0.6) * abs(_m.cos(th))
        return (r - R0) * top / (R1 - R0)
    side = max([R1 + 18 + EM * SZ * len(lab(it)) for it in items] or [R1])
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": max(760, int(2 * side + 20)), "height": 700,
            "data": {"values": [{"l": it["label"], "v": float(it["value"]), "i": i, "lr": ring(i, it),
                                 "lab": lab(it),
                                 "fill": WASH.get(it.get("color",
                                                         PALETTE_NAMES[i % len(PALETTE_NAMES)]),
                                                  WASH["blue"])}
                                for i, it in enumerate(items)]},
            "layer": [
                {"mark": {"type": "arc", "stroke": "black", "strokeWidth": 1.4,
                          "innerRadius": R0, "padAngle": 0.012},
                 "encoding": {"theta": {"field": "i", "type": "nominal",
                                        "scale": {"type": "band", "range": [0, 6.2832]},
                                        "sort": [i for i in range(n)]},
                              "radius": {"field": "v", "type": "quantitative",
                                         "scale": {"type": "linear", "zero": True,
                                                   "range": [R0, R1],
                                                   "domain": [0, top]}},
                              "color": {"field": "fill", "type": "nominal", "scale": None,
                                        "legend": None}}},
                # labels on a FIXED outer ring, not at each wedge's own radius -- otherwise the
                # short wedges' names crowd the middle and the ring is unreadable
                {"mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                          "color": "black"},
                 "encoding": {"theta": {"field": "i", "type": "nominal",
                                        "scale": {"type": "band", "range": [0, 6.2832]},
                                        "sort": [i for i in range(n)], "bandPosition": 0.5},
                              "radius": {"field": "lr", "type": "quantitative",
                                         "scale": {"type": "linear", "zero": True,
                                                   "range": [R0, R1], "domain": [0, top]}},
                              "text": {"field": "lab", "type": "nominal"}}}],
            "config": dict(cfg, view={"stroke": None})}


def _tree_vl(spec, cfg, schema):
    """An org chart / hierarchy, laid out tidily: leaves get equal slots, a parent sits over the
    middle of its children, and the elbows are drawn as three segments so they stay square."""
    nodes = spec.get("nodes") or []
    by_id = dict((str(nd["id"]), dict(nd, id=str(nd["id"]),
                                      parent=(None if nd.get("parent") in (None, "")
                                              else str(nd["parent"])), children=[]))
                 for nd in nodes)
    roots = []
    for nd in by_id.values():
        if nd["parent"] and nd["parent"] in by_id:
            by_id[nd["parent"]]["children"].append(nd)
        else:
            roots.append(nd)
    depth = {}
    def dep(nd, d):
        depth[nd["id"]] = d
        for k in nd["children"]:
            dep(k, d + 1)
    for r in roots:
        dep(r, 0)
    levels = max(depth.values()) + 1
    slot = [0]
    def place(nd):
        if not nd["children"]:
            nd["px"] = slot[0]
            slot[0] += 1
        else:
            for k in nd["children"]:
                place(k)
            nd["px"] = (nd["children"][0]["px"] + nd["children"][-1]["px"]) / 2.0
    for r in roots:
        place(r)
    leaves = max(slot[0], 1)
    BW, BH = 190.0, 62.0
    W = max(900.0, leaves * (BW + 26))
    H = (levels - 1) * 138.0 + 46 + BH / 2 + 26     # to the bottom row's edge, not a whole row on
    px = _Px(W, H)
    boxes, labels, links = [], [], []
    def xy_of(nd):
        return ((nd["px"] + 0.5) * (W / leaves), depth[nd["id"]] * 138.0 + 46)
    for nd in by_id.values():
        cx, cy = xy_of(nd)
        boxes.append({"x0": cx - BW / 2, "x1": cx + BW / 2, "y0": cy - BH / 2,
                      "y1": cy + BH / 2,
                      "fill": WASH.get(nd.get("color", "blue"), WASH["blue"])})
        a, b = _wrap2(str(nd.get("label", nd["id"])), 20)
        labels.append({"x": cx, "y": cy - (9 if b else 0), "t": a, "s": 16})
        if b:
            labels.append({"x": cx, "y": cy + 11, "t": b, "s": 16})
        for k in nd["children"]:
            kx, ky = xy_of(k)
            mid = cy + BH / 2 + 38
            for j, (x, y) in enumerate(((cx, cy + BH / 2), (cx, mid), (kx, mid),
                                        (kx, ky - BH / 2))):
                links.append({"k": nd["id"] + ">" + k["id"], "o": j, "x": x, "y": y})
    return px.spec(spec.get("title", ""), [
        px.line(links, strokeWidth=2, color=RULE),
        px.rect(boxes, strokeWidth=2, cornerRadius=6),
        {"data": {"values": labels},
         "mark": {"type": "text", "font": FONT, "color": "black", "fontSize": 22},
         "encoding": px.xy(text={"field": "t", "type": "nominal"})}], cfg, schema)


def _flow_vl(spec, cfg, schema):
    """A process: boxes left to right with arrows between them, wrapping onto a second line when
    it runs out of page."""
    steps = spec.get("steps") or []
    per = int(spec.get("per_row", 4))
    W = 1080.0
    rows_n = (len(steps) + per - 1) // per
    BW, BH, GAP = (W - 40) / per - 46, 96.0, 46.0
    H = rows_n * (BH + 58) + 20
    px = _Px(W, H)
    boxes, labels, arrows = [], [], []
    for i, st in enumerate(steps):
        r, c = i // per, i % per
        x0 = 20 + c * (BW + GAP)
        y0 = 20 + r * (BH + 58)
        boxes.append({"x0": x0, "x1": x0 + BW, "y0": y0, "y1": y0 + BH,
                      "fill": WASH.get(st.get("color", "blue"), WASH["blue"])})
        a, b = _wrap2(str(st.get("text", st) if not isinstance(st, dict) else st["text"]), 18)
        labels.append({"x": x0 + BW / 2, "y": y0 + BH / 2 - (11 if b else 0), "t": a})
        if b:
            labels.append({"x": x0 + BW / 2, "y": y0 + BH / 2 + 13, "t": b})
        if i < len(steps) - 1 and c < per - 1:
            ay = y0 + BH / 2
            tip = x0 + BW + GAP - 8
            # shaft and head as SEPARATE groups -- one polyline through all six points draws a
            # zigzag, because there is no way to lift the pen inside a single line mark.
            arrows += [{"k": "s%d" % i, "o": 0, "x": x0 + BW + 8, "y": ay},
                       {"k": "s%d" % i, "o": 1, "x": tip, "y": ay},
                       {"k": "h%d" % i, "o": 0, "x": tip - 13, "y": ay - 9},
                       {"k": "h%d" % i, "o": 1, "x": tip, "y": ay},
                       {"k": "h%d" % i, "o": 2, "x": tip - 13, "y": ay + 9}]
    return px.spec(spec.get("title", ""), [
        px.line(arrows, strokeWidth=2.6, color="#404040"),
        px.rect(boxes, strokeWidth=2, cornerRadius=8),
        {"data": {"values": labels},
         "mark": {"type": "text", "font": FONT, "color": "black", "fontSize": 24,
                  "fontWeight": "bold"},
         "encoding": px.xy(text={"field": "t", "type": "nominal"})}], cfg, schema)


def _kanban_vl(spec, cfg, schema):
    """Columns of cards. The board, on paper, which is where it started."""
    cols = spec.get("columns") or []
    W = 1080.0
    n = max(len(cols), 1)
    CW = (W - 20 * (n + 1)) / n
    tall = max([len(c.get("items") or []) for c in cols] or [1])
    H = 108 + tall * 76 + 30
    px = _Px(W, H)
    heads, cards, labels, counts, heads_t = [], [], [], [], []
    for ci, c in enumerate(cols):
        x0 = 20 + ci * (CW + 20)
        heads.append({"x0": x0, "x1": x0 + CW, "y0": 20, "y1": 74,
                      "fill": WASH.get(c.get("color", "gray"), WASH["gray"])})
        heads_t.append({"x": x0 + 16, "y": 47, "t": str(c["name"]), "al": "left"})
        counts.append({"x": x0 + CW - 16, "y": 47,
                       "t": str(len(c.get("items") or [])), "al": "right"})
        for j, cd in enumerate(c.get("items") or []):
            y0 = 92 + j * 76
            txt = cd if isinstance(cd, str) else cd.get("text", "")
            col = "white" if isinstance(cd, str) else cd.get("color", "white")
            cards.append({"x0": x0, "x1": x0 + CW, "y0": y0, "y1": y0 + 62,
                          "fill": WASH.get(col, "#FFFFFF")})
            a, b = _wrap2(str(txt), 24)
            labels.append({"x": x0 + 14, "y": y0 + (20 if b else 31), "t": a})
            if b:
                labels.append({"x": x0 + 14, "y": y0 + 42, "t": b})
    # Column names bold, card text regular: everything bold is the same as nothing bold.
    return px.spec(spec.get("title", ""), [
        px.rect(cards, strokeWidth=1.4, cornerRadius=5),
        px.rect(heads, strokeWidth=1.8, cornerRadius=5),
        px.text(heads_t, 24, True, align="left"),
        px.text(counts, 24, True, align="right"),
        px.text(labels, 22, False, align="left")], cfg, schema)


def _journey_vl(spec, cfg, schema):
    """Numbered milestones along a road: where we are, what is behind, what is left."""
    steps = spec.get("steps") or []
    W, H = 1080.0, 272.0
    px = _Px(W, H)
    n = len(steps)
    M = 110.0                      # the first and last labels were cut off at M = 60
    gap = (W - 2 * M) / max(n - 1, 1)
    road, dots, nums, labels = [], [], [], []
    road = [{"k": 0, "o": 0, "x": M, "y": 120}, {"k": 0, "o": 1, "x": W - M, "y": 120}]
    done_x = M + gap * max([i for i, s in enumerate(steps) if s.get("done")] or [-1])
    prog = [{"k": 1, "o": 0, "x": M, "y": 120},
            {"k": 1, "o": 1, "x": max(M, done_x), "y": 120}]
    for i, s in enumerate(steps):
        x = M + i * gap
        dots.append({"x": x, "y": 120,
                     "fill": (WASH["green"] if s.get("done") else
                              WASH.get(s.get("color", "white"), "#FFFFFF"))})
        nums.append({"x": x, "y": 120, "t": str(i + 1)})
        a, b = _wrap2(str(s.get("label", "")), 15)
        labels.append({"x": x, "y": 184, "t": a})
        if b:
            labels.append({"x": x, "y": 206, "t": b})
        if s.get("note"):
            labels.append({"x": x, "y": 62, "t": str(s["note"])})
    return px.spec(spec.get("title", ""), [
        px.line(road, strokeWidth=8, color="#D5D5D5"),
        px.line(prog, strokeWidth=8, color=INK["blue"]),
        {"data": {"values": dots},
         "mark": {"type": "point", "size": 1500, "filled": True, "opacity": 1,
                  "stroke": "black", "strokeWidth": 2.5},
         "encoding": px.xy(color={"field": "fill", "type": "nominal", "scale": None,
                                  "legend": None})},
        px.text(nums, 20, True),
        px.text(labels, 22, True)], cfg, schema)


def _clock_vl(spec, cfg, schema):
    """Twenty-four hours as a ring. A day is a circle, and a bar chart of hours pretends midnight
    is a cliff edge."""
    import math as _m
    blocks = spec.get("blocks") or []
    W, H = 760.0, 760.0
    px = _Px(W, H)
    CX, CY, R0, R1 = W / 2, H / 2, 150.0, 300.0
    wedges, ticks, labels = [], [], []
    for bi, b in enumerate(blocks):
        a0 = (float(b["start"]) / 24.0) * 2 * _m.pi - _m.pi / 2
        a1 = (float(b["end"]) / 24.0) * 2 * _m.pi - _m.pi / 2
        steps = max(3, int((a1 - a0) / 0.09))
        outer = [(CX + R1 * _m.cos(a0 + (a1 - a0) * i / steps),
                  CY + R1 * _m.sin(a0 + (a1 - a0) * i / steps)) for i in range(steps + 1)]
        inner = [(CX + R0 * _m.cos(a0 + (a1 - a0) * i / steps),
                  CY + R0 * _m.sin(a0 + (a1 - a0) * i / steps))
                 for i in range(steps, -1, -1)]
        fill = WASH.get(b.get("color", "blue"), WASH["blue"])
        for o, (x, y) in enumerate(outer + inner):
            wedges.append({"k": bi, "o": o, "x": x, "y": y, "fill": fill})
        am = (a0 + a1) / 2
        labels.append({"x": CX + (R0 + R1) / 2 * _m.cos(am),
                       "y": CY + (R0 + R1) / 2 * _m.sin(am), "t": str(b.get("label", ""))})
    for h in range(24):
        a = (h / 24.0) * 2 * _m.pi - _m.pi / 2
        ticks.append({"k": h, "o": 0, "x": CX + R1 * _m.cos(a), "y": CY + R1 * _m.sin(a)})
        ticks.append({"k": h, "o": 1, "x": CX + (R1 + (14 if h % 6 == 0 else 8)) * _m.cos(a),
                      "y": CY + (R1 + (14 if h % 6 == 0 else 8)) * _m.sin(a)})
        if h % 3 == 0:
            labels.append({"x": CX + (R1 + 40) * _m.cos(a), "y": CY + (R1 + 40) * _m.sin(a),
                           "t": "%02d" % h})
    return px.spec(spec.get("title", ""), [
        {"data": {"values": wedges},
         "mark": {"type": "line", "filled": True, "fillOpacity": 0.9, "strokeWidth": 1.4,
                  "stroke": "black"},
         "encoding": px.xy(detail={"field": "k", "type": "nominal"},
                           order={"field": "o", "type": "quantitative"},
                           color={"field": "fill", "type": "nominal", "scale": None,
                                  "legend": None})},
        px.line(ticks, strokeWidth=2, color="black"),
        px.text(labels, 22, True)], cfg, schema)
def _agenda_vl(spec, cfg, schema):
    """A classic paper day planner. The things that make that page what it is are structural, not
    decorative:

      * a HALF-HOUR ruled schedule running from early morning to night, every slot writable
        whether or not anything is booked -- the ruling is the point, because the page is a
        planning surface first and a record second;
      * hours labeled, half-hours ticked but unlabeled, so the eye lands on the hour;
      * a side column of standing lists -- people to see, and backup plans for when a booked
        appointment falls through;
      * a goal-versus-actual block at the foot, planned in the morning and filled in at night.

    So the schedule is ruled for the WHOLE day even where nothing is planned. An agenda that only
    draws the busy hours is a record of a day; this is a page you take into one.
    """
    items = sorted(_agenda_items(spec), key=lambda i: i["start"])
    lo = float(spec.get("start", 6))
    hi = float(spec.get("end", 22))
    if items:
        lo = min(lo, float(items[0]["start"]))
        hi = max(hi, max(float(i["end"]) for i in items))
    lo, hi = float(int(lo)), float(-(-hi // 1))
    slots = int((hi - lo) * 2)
    W, PH = _page(spec, float(WIDTH), None)
    TOP = 64.0
    ROW = ((PH - TOP - 16.0) / float(slots)) if PH else 33.0
    GUT, X0 = 86.0, 96.0
    X1 = W * 0.70                              # times | schedule | side column
    SX0, SX1 = X1 + 24.0, W - 8.0
    H = TOP + slots * ROW + 16
    px = _Px(W, H)

    def y_of(t):
        return TOP + (t - lo) * 2 * ROW

    rules, times, blocks, labels, heads, boxes = [], [], [], [], [], []
    # the day, and the date beside it
    heads.append({"x0": 0, "y0": 8, "x1": W, "y1": TOP - 12, "fill": WASH["gray"]})
    labels.append({"x": 14, "y": TOP / 2 - 2, "t": str(spec.get("day", spec.get("title", ""))),
                   "s": 22, "al": "left", "b": True})
    if spec.get("date"):
        labels.append({"x": W - 14, "y": TOP / 2 - 2, "t": str(spec["date"]),
                       "s": 17, "al": "right", "b": False})

    # the ruled schedule -- every half hour, hour lines darker
    for k in range(slots + 1):
        t = lo + k / 2.0
        y = y_of(t)
        whole = (k % 2 == 0)
        rules.append({"k": "r%d" % k, "o": 0, "x": GUT if whole else X0 - 14, "y": y})
        rules.append({"k": "r%d" % k, "o": 1, "x": X1, "y": y})
        if whole and k < slots:
            times.append({"x": GUT - 10, "y": y + 11, "t": _hhmm(t)})
    for x in (GUT, X1):
        rules.append({"k": "v%s" % x, "o": 0, "x": x, "y": TOP})
        rules.append({"k": "v%s" % x, "o": 1, "x": x, "y": y_of(hi)})

    for it in items:
        y0, y1 = y_of(float(it["start"])), y_of(float(it["end"]))
        blocks.append({"x0": GUT + 4, "y0": y0 + 2, "x1": X1 - 4, "y1": y1 - 2,
                       "fill": WASH.get(it.get("color", "blue"), WASH["blue"])})
        a2, b2 = _wrap2(str(it.get("text", "")), 46)
        labels.append({"x": GUT + 14, "y": (y0 + y1) / 2.0 - (14 if b2 else 0),
                       "t": a2, "s": 22, "al": "left", "b": True})
        if b2:
            labels.append({"x": GUT + 14, "y": (y0 + y1) / 2.0 + 16, "t": b2,
                           "s": 22, "al": "left", "b": True})
        labels.append({"x": X1 - 14, "y": (y0 + y1) / 2.0, "s": 18, "al": "right", "b": False,
                       "t": "%s-%s" % (_hhmm(it["start"]), _hhmm(it["end"]))})

    # side column: standing lists, then goals planned against actual
    def panel(title, y, h, rows_n, entries):
        boxes.append({"x0": SX0, "y0": y, "x1": SX1, "y1": y + h, "fill": "#FFFFFF"})
        boxes.append({"x0": SX0, "y0": y, "x1": SX1, "y1": y + 34, "fill": WASH["gray"]})
        labels.append({"x": SX0 + 12, "y": y + 17, "t": title, "s": 22, "al": "left", "b": True})
        step = (h - 40) / max(rows_n, 1)
        for r in range(rows_n):
            ly = y + 40 + step * (r + 1) - 6
            rules.append({"k": "%s%d" % (title, r), "o": 0, "x": SX0 + 10, "y": ly})
            rules.append({"k": "%s%d" % (title, r), "o": 1, "x": SX1 - 10, "y": ly})
            if r < len(entries):
                labels.append({"x": SX0 + 14, "y": ly - 11, "t": str(entries[r]),
                               "s": 20, "al": "left", "b": False})

    y = TOP
    avail = y_of(hi) - TOP
    people = list(spec.get("people") or [])
    backup = list(spec.get("backup") or [])
    goals = list(spec.get("goals") or [])
    ph = avail * (0.34 if goals else 0.5)
    panel(spec.get("people_title", "People to see"), y, ph,
          max(len(people), int(ph // 30) - 1), people)
    y += ph + 14
    bh = avail * (0.28 if goals else 0.46)
    panel(spec.get("backup_title", "Backup plans"), y, bh,
          max(len(backup), int(bh // 30) - 1), backup)
    y += bh + 14
    if goals:
        gh = y_of(hi) - y
        boxes.append({"x0": SX0, "y0": y, "x1": SX1, "y1": y + gh, "fill": "#FFFFFF"})
        boxes.append({"x0": SX0, "y0": y, "x1": SX1, "y1": y + 34, "fill": WASH["gray"]})
        labels.append({"x": SX0 + 12, "y": y + 17, "t": spec.get("goals_title", "Goals"),
                       "s": 22, "al": "left", "b": True})
        gx1, gx2 = SX1 - 120, SX1 - 58
        labels.append({"x": gx1, "y": y + 50, "t": "plan", "s": 18, "al": "center", "b": False})
        labels.append({"x": gx2, "y": y + 50, "t": "did", "s": 18, "al": "center", "b": False})
        step = (gh - 66) / max(len(goals), 1)
        for r, g in enumerate(goals):
            ly = y + 66 + step * (r + 0.5)
            labels.append({"x": SX0 + 14, "y": ly, "t": str(g["name"]), "s": 20,
                           "al": "left", "b": False})
            labels.append({"x": gx1, "y": ly, "t": str(g.get("goal", "")), "s": 22,
                           "al": "center", "b": True})
            labels.append({"x": gx2, "y": ly, "t": str(g.get("actual", "")), "s": 22,
                           "al": "center", "b": True})
            rules.append({"k": "g%d" % r, "o": 0, "x": SX0 + 10, "y": ly + step / 2 - 2})
            rules.append({"k": "g%d" % r, "o": 1, "x": SX1 - 10, "y": ly + step / 2 - 2})

    # the rules UNDER the events: drawn over them, a half-hour line ran through an event's words
    lay = [px.rect(boxes, strokeWidth=0),
           px.line(rules, strokeWidth=1, color=RULE),
           px.rect(blocks, strokeWidth=1.4, stroke=GRAY, cornerRadius=4),
           px.rect(heads, strokeWidth=0),
           px.text(times, 20, True, color=GRAY, align="right")]
    for al in ("left", "right", "center"):
        for bold in (True, False):
            for sz in sorted(set(l["s"] for l in labels)):
                sel = [l for l in labels
                       if l["al"] == al and l["b"] == bold and l["s"] == sz]
                if sel:
                    lay.append(px.text(sel, sz, bold,
                                       color="black" if bold else GRAY, align=al))
    return px.spec("" if spec.get("day") else spec.get("title", ""), lay, cfg, schema)


def _hours(v):
    """A time of day as hours: 9, 15.5, "09:00", "9:30", "9 am", "3:15 pm" -> 9.0, 15.5, 9.0, 9.5, 9.0, 15.25;
    None for anything else."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = re.match(r"\s*(\d{1,2})(?:[:.](\d{2}))?\s*([ap])?\.?m?\.?\s*$", str(v or ""), re.I)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3):
        h = h % 12 + (12 if m.group(3).lower() == "p" else 0)
    return h + mi / 60.0 if h <= 24 and mi < 60 else None


def _agenda_items(spec):
    """An agenda's items with start and end in hours, as the builder lays them out. The model is told
    {start, end, text}, times written as people write them; `time` ("09:00" or "09:00-10:30") is read too, and
    an item with no end lasts an hour. Raises SpecError naming an item with no time it can read."""
    out = []
    for i, it in enumerate(spec.get("items") or []):
        if not isinstance(it, dict):
            raise SpecError("agenda item %d must be {start, end, text}" % i)
        start, end = it.get("start"), it.get("end")
        if start is None and it.get("time") is not None:
            parts = re.split(r"\s*(?:-|–|to)\s*", str(it["time"]), maxsplit=1)
            start, end = parts[0], (parts[1] if len(parts) > 1 else end)
        a, b = _hours(start), _hours(end) if end is not None else None
        if a is None:
            raise SpecError("agenda item %d needs a start time like \"09:00\" (got %r)" % (i, start))
        out.append(dict(it, start=a, end=b if b is not None and b > a else a + 1.0))
    return out


def _hhmm(t):
    """8 -> 08:00, 15.5 -> 15:30. Half-hour starts are the whole reason an agenda is not a bar
    chart of integers."""
    t = float(t)
    return "%02d:%02d" % (int(t), int(round((t - int(t)) * 60)))


def _checklist_vl(spec, cfg, schema):
    """Boxes you can actually tick, on paper.

    A long item WRAPS onto a second line rather than being cut short: in a column beside its notes
    "Water bottles or hydration bladder" would otherwise come out "Water bottles or hydration bla...".
    Two lines fit the row; the ellipsis is the last resort after that."""
    items = spec.get("items") or []
    per_line = max(12, int((WIDTH - 180) / (0.45 * 17)))      # Remarkable Mono: 0.45 em a character
    wrap = lambda s: "\n".join(l for l in _wrap2(s, per_line) if l)
    rows = [{"i": i, "t": wrap(str(c.get("text", c) if isinstance(c, dict) else c)),
             "done": 1 if (isinstance(c, dict) and c.get("done")) else 0,
             "fill": WASH.get(c.get("color", "white"), "#FFFFFF") if isinstance(c, dict)
                     else "#FFFFFF"} for i, c in enumerate(items)]
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 90, "height": 54 * len(rows) + 40, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "rect", "stroke": "black", "strokeWidth": 1.2,
                          "height": {"band": 0.8}, "x": 4, "x2": 40, "cornerRadius": 3},
                 "encoding": {"color": {"field": "fill", "type": "nominal", "scale": None,
                                        "legend": None}}},
                {"mark": {"type": "point", "shape": ICONS["check"], "size": 620, "filled": False,
                          "strokeCap": "round", "strokeJoin": "round",
                          "stroke": INK["black"], "strokeWidth": 3, "x": 22},
                 "encoding": {"opacity": {"condition": {"test": "datum.done == 1", "value": 1},
                                          "value": 0}}},
                {"mark": {"type": "text", "fontSize": 30, "font": FONT, "color": "black",
                          "align": "left", "x": 58, "limit": WIDTH - 180, "lineBreak": "\n"},
                 "encoding": {"text": {"field": "t", "type": "nominal"},
                              "strikethrough": {"condition": {"test": "datum.done == 1",
                                                              "value": True}, "value": False}}}],
            "encoding": {"y": {"field": "i", "type": "ordinal", "axis": None,
                               "sort": list(range(len(rows)))}},
            "config": cfg}


def _habit_vl(spec, cfg, schema):
    """Habits down the side, days across the top, a filled square where it happened."""
    habits = spec.get("habits") or []
    days = spec.get("days") or [str(d) for d in range(1, 15)]
    rows = []
    for h in habits:
        done = set(str(d) for d in (h.get("done") or []))
        for d in days:
            rows.append({"h": h["name"], "d": str(d), "on": 1 if str(d) in done else 0,
                         "fill": WASH.get(h.get("color", "green"), WASH["green"])
                                 if str(d) in done else "#FFFFFF"})
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": WIDTH - 240, "height": 56 * max(1, len(habits)) + 50,
            "data": {"values": rows},
            "mark": {"type": "rect", "stroke": "black", "strokeWidth": 1.2,
                     "width": {"band": 0.84}, "height": {"band": 0.72}, "cornerRadius": 3},
            "encoding": {
                "x": {"field": "d", "type": "nominal", "sort": [str(d) for d in days],
                      "axis": {"orient": "top", "labelAngle": 0, "title": None,
                               "domain": False, "ticks": False, "labelFontSize": 20}},
                "y": {"field": "h", "type": "nominal", "sort": [h["name"] for h in habits],
                      "axis": {"title": None, "domain": False, "ticks": False,
                               "labelFontSize": 24}},
                "color": {"field": "fill", "type": "nominal", "scale": None, "legend": None}},
            "config": cfg}


def _yearmap_vl(spec, cfg, schema):
    """A year as 53 weeks of squares -- the shape that shows a streak at a glance."""
    import datetime as _dt
    y = spec.get("year", _dt.date.today().year)
    counts = dict((str(k), float(v)) for k, v in (spec.get("counts") or {}).items())
    hi = max(list(counts.values()) or [1])
    ramp = ["#FFFFFF", WASH["green"], "#7CE35A", "#46B82B", "#1E7A12"]
    d = _dt.date(y, 1, 1)
    rows = []
    while d.year == y:
        v = counts.get(d.isoformat(), 0)
        step = 0 if not v else min(len(ramp) - 1, 1 + int(3.0 * v / hi))
        rows.append({"wk": int(d.strftime("%W")), "dow": d.weekday(),
                     "fill": ramp[step], "date": d.isoformat()})
        d += _dt.timedelta(days=1)
    return {"$schema": schema, "title": spec.get("title", "%d" % y),
            "width": WIDTH - 90, "height": 220, "data": {"values": rows},
            "mark": {"type": "rect", "stroke": "#B8B8B8", "strokeWidth": 0.7,
                     "width": {"band": 0.86}, "height": {"band": 0.86}, "cornerRadius": 2},
            "encoding": {
                "x": {"field": "wk", "type": "ordinal", "axis": None},
                "y": {"field": "dow", "type": "ordinal", "axis": None},
                "color": {"field": "fill", "type": "nominal", "scale": None, "legend": None}},
            "config": cfg}

def _timeline_vl(spec, cfg, schema):
    """Events on one line, alternating above and below so labels never collide.

    Pixels again. The Vega-Lite version put a "side" axis on the page labeled -1.0 to 1.0, drew
    every stem upwards whatever side its label was on, and hung the last label off the right edge.
    """
    evs = sorted(spec.get("events") or [], key=lambda e: float(e["at"]))
    W, H = _page(spec, 1080.0, 340.0)
    H = H or 340.0
    M, MID = 110.0, H / 2 - 2
    px = _Px(W, H)
    lo = min(float(e["at"]) for e in evs)
    hi = max(float(e["at"]) for e in evs)
    span = (hi - lo) or 1.0
    def x_of(v):
        return M + (W - 2 * M) * (float(v) - lo) / span
    axis = [{"k": "ax", "o": 0, "x": 24, "y": MID}, {"k": "ax", "o": 1, "x": W - 24, "y": MID}]
    stems, dots, labels, ticks = [], [], [], []
    for i, e in enumerate(evs):
        x = x_of(e["at"])
        up = (i % 2 == 0)
        end = MID - 74 if up else MID + 74
        stems.append({"k": i, "o": 0, "x": x, "y": MID})
        stems.append({"k": i, "o": 1, "x": x, "y": end})
        dots.append({"x": x, "y": MID,
                     "fill": WASH.get(e.get("color", "blue"), WASH["blue"])})
        a2, b2 = _wrap2(str(e.get("text", "")), 20)
        ly = end - 30 if up else end + 8
        labels.append({"x": x, "y": ly, "t": a2})
        if b2:
            labels.append({"x": x, "y": ly + 21, "t": b2})
        ticks.append({"x": x, "y": MID + (26 if up else -26),
                      "t": str(e.get("label", e["at"]))})
    return px.spec(spec.get("title", ""), [
        px.line(axis, strokeWidth=3, color="black"),
        px.line(stems, strokeWidth=1.8, color=RULE),
        {"data": {"values": dots},
         "mark": {"type": "point", "size": 300, "filled": True, "stroke": "black",
                  "strokeWidth": 2, "opacity": 1},
         "encoding": px.xy(color={"field": "fill", "type": "nominal", "scale": None,
                                  "legend": None})},
        px.text(ticks, 20, True, color="#404040"),
        px.text(labels, 22, True)], cfg, schema)

def _waffle_vl(spec, cfg, schema):
    """A hundred squares. Proportion you can COUNT rather than estimate off an angle.

    With a KEY. Without one the chart is a hundred colored squares and no way to say what any of
    them is -- which is worse than a pie, not better.
    """
    parts = spec.get("parts") or []
    total = float(sum(p["value"] for p in parts)) or 1.0
    CELL, PAD = 58.0, 6.0
    GRID = 10 * CELL
    W = GRID                     # the key sits under the tiles, so it is exactly as wide
    KEY = 34.0 * len(parts) + 20
    px = _Px(W, GRID + KEY + 16)
    cells, i = [], 0
    # EACH PART ITS OWN COLOR, in palette order unless the spec names one (all blue, the parts could not be told apart)
    tone = dict((id(p), p.get("color") or PALETTE_NAMES[j % len(PALETTE_NAMES)]) for j, p in enumerate(parts))
    for p in parts:
        n = int(round(100.0 * p["value"] / total))
        for _ in range(n):
            if i >= 100:
                break
            cells.append({"x0": (i % 10) * CELL + PAD / 2, "y0": (i // 10) * CELL + PAD / 2,
                          "x1": (i % 10 + 1) * CELL - PAD / 2,
                          "y1": (i // 10 + 1) * CELL - PAD / 2,
                          "fill": WASH.get(tone[id(p)], WASH["blue"])})
            i += 1
    while i < 100:
        cells.append({"x0": (i % 10) * CELL + PAD / 2, "y0": (i // 10) * CELL + PAD / 2,
                      "x1": (i % 10 + 1) * CELL - PAD / 2,
                      "y1": (i // 10 + 1) * CELL - PAD / 2, "fill": "#FFFFFF"})
        i += 1
    sw, names, vals = [], [], []
    for j, p in enumerate(parts):
        y = GRID + 26 + j * 34
        sw.append({"x0": PAD / 2, "x1": PAD / 2 + 28, "y0": y - 12, "y1": y + 12,
                   "fill": WASH.get(tone[id(p)], WASH["blue"])})
        names.append({"x": PAD / 2 + 40, "y": y, "t": str(p["name"])})
        vals.append({"x": W - PAD / 2, "y": y,
                     "t": "%s  ·  %.0f%%" % (spec.get("fmt", "%g") % float(p["value"]),
                                                 100.0 * p["value"] / total)})
    return px.spec(spec.get("title", ""), [
        px.rect(cells, strokeWidth=1.2, cornerRadius=2),
        px.rect(sw, strokeWidth=1.4, cornerRadius=3),
        px.text(names, 24, False, align="left"),
        px.text(vals, 24, True, align="right")], cfg, schema)


def _funnel_vl(spec, cfg, schema):
    """Stages narrowing, with the drop-off named at each step.

    Labels live in their OWN COLUMN to the right, with a leader out to each bar. Centered inside
    the bar they were sliced in half by the bar's edges the moment a stage got narrow -- which is
    every funnel, by definition.
    """
    stages = spec.get("stages") or []
    top = float(stages[0]["value"]) if stages else 1.0
    W = 1080.0
    BAND, CX, HALF = 78.0, 330.0, 300.0
    LX = 700.0
    H = BAND * max(1, len(stages)) + 24
    px = _Px(W, H)
    bars, leaders, names, vals, drops = [], [], [], [], []
    prev = None
    for i, s in enumerate(stages):
        v = float(s["value"])
        w = HALF * v / (top or 1.0)
        cy = 12 + i * BAND + BAND / 2.0
        bars.append({"x0": CX - w, "x1": CX + w, "y0": cy - BAND * 0.38,
                     "y1": cy + BAND * 0.38,
                     "fill": WASH.get(s.get("color", PALETTE_NAMES[i % len(PALETTE_NAMES)]),
                                      WASH["blue"])})
        leaders.append({"k": i, "o": 0, "x": CX + w + 8, "y": cy})
        leaders.append({"k": i, "o": 1, "x": LX - 10, "y": cy})
        names.append({"x": LX, "y": cy, "t": str(s["name"])})
        vals.append({"x": W - 16, "y": cy - 10,
                     "t": "%s  ·  %.0f%%" % (spec.get("fmt", "%g") % v,
                                                   100.0 * v / top)})
        if prev is not None:
            d = v - prev
            drops.append({"x": W - 16, "y": cy + 12,
                          "t": ("%+.0f%%" % (100.0 * d / prev)) if prev else ""})
        prev = v
    return px.spec(spec.get("title", ""), [
        px.line(leaders, strokeWidth=1.2, color=RULE, strokeDash=[3, 3]),
        px.rect(bars, strokeWidth=2, cornerRadius=4),
        px.text(names, 24, True, align="left"),
        px.text(vals, 24, True, align="right"),
        px.text(drops, 20, False, color="#505050", align="right")], cfg, schema)


def _gauge_vl(spec, cfg, schema):
    """A half dial. One number, read without reading."""
    v = float(spec.get("value", 0))
    lo = float(spec.get("min", 0))
    hi = float(spec.get("max", 100))
    frac = 0.0 if hi == lo else max(0.0, min(1.0, (v - lo) / (hi - lo)))
    import math as _m
    rows = [{"k": "done", "t": frac, "o": 0, "fill": WASH.get(spec.get("color", "green"),
                                                              WASH["green"])},
            {"k": "rest", "t": 1.0 - frac, "o": 1, "fill": "#FFFFFF"}]
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": 620, "height": 400, "data": {"values": rows},
            "layer": [
                {"mark": {"type": "arc", "stroke": "black", "strokeWidth": 2.5,
                          "innerRadius": 110, "outerRadius": 190, "y": 300},
                 "encoding": {"theta": {"field": "t", "type": "quantitative", "stack": True,
                                        "scale": {"range": [-_m.pi / 2, _m.pi / 2]}},
                              "order": {"field": "o", "type": "quantitative"},
                              "color": {"field": "fill", "type": "nominal", "scale": None,
                                        "legend": None}}},
                {"mark": {"type": "text", "fontSize": 54, "fontWeight": "bold", "font": FONT,
                          "color": "black", "x": 310, "y": 268},
                 "encoding": {"text": {"value": spec.get("label", "%g" % v)}}},
                {"mark": {"type": "text", "fontSize": 24, "font": FONT, "color": GRAY,
                          "x": 310, "y": 300},
                 "encoding": {"text": {"value": spec.get("note", "%g of %g" % (v, hi))}}}],
            "config": cfg}


def _first_day(spec):
    """The calendar's first weekday (6 = Sunday, 0 = Monday, 5 = Saturday): the spec's, else the user's preference."""
    if spec.get("first_day") is not None:
        return int(spec["first_day"])
    from paperdaemon import paths
    return {"monday": 0, "saturday": 5}.get(paths.prefs()["week_start"], 6)



def _wet_spans(hours, threshold=30):
    """[(h0, h1, peak_pop, kind), ...]: the runs of hours with a real chance of precipitation."""
    out, run = [], None
    snow = set((71, 73, 75, 77, 85, 86))
    for hr in sorted(hours, key=lambda x: x["h"]):
        # by CHANCE alone: a forecast of half a millimeter at a 4% chance is not a rain window
        wet = (hr.get("pop") or 0) >= threshold
        if wet:
            kind = "snow" if hr.get("code") in snow else "rain"
            if run and run[1] == hr["h"]:
                run[1] = hr["h"] + 1
                run[2] = max(run[2], hr.get("pop") or 0)
                if kind == "snow":
                    run[3] = "snow"
            else:
                if run:
                    out.append(tuple(run))
                run = [hr["h"], hr["h"] + 1, hr.get("pop") or 0, kind]
        elif run:
            out.append(tuple(run))
            run = None
    if run:
        out.append(tuple(run))
    # a dry hour between two wet stretches is one stretch with a lull, not two forecasts
    merged = []
    for sp in out:
        if merged and sp[0] - merged[-1][1] <= 1:
            a = merged[-1]
            merged[-1] = (a[0], sp[1], max(a[2], sp[2]), "snow" if "snow" in (a[3], sp[3]) else "rain")
        else:
            merged.append(sp)
    return merged


def _compass(deg):
    if deg is None:
        return ""
    pts = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return pts[int((float(deg) + 22.5) // 45) % 8]


def _clock12(hhmm):
    """'06:58' -> '6:58'; the am/pm is obvious on a sunrise line."""
    if not hhmm or ":" not in hhmm:
        return ""
    h, m = hhmm.split(":")[:2]
    return "%d:%s" % ((int(h) % 12) or 12, m)


# ---------------------------------------------------------------- the day's weather figures
# TWO COLUMNS OF THREE, icons left-aligned in each. Rows centered at their own width make the
# block's outline swell and narrow row by row, so the columns are clearly two, with the icons
# left aligned within their column. The figures are set at the high/low's size, the icons a little
# bigger and heavier (sizes tuned on a monitor read small on the tablet), and every TIME is a clock
# face set to the minute, not digits. One layout, used by the week AND the month, so the two
# cannot drift apart.
WX_ROW = 1.42            # row pitch, in the figures' type size
WX_ICON = 1.22           # an icon's box, in the figures' type size
WX_GAP = 0.22            # icon to figure
ICON_STROKE = 2.3        # the weight of every icon's line on a calendar
RULE_STROKE = 2.2        # rules and frames
CURVE_STROKE = 3.0       # the day's temperature line


def _wind_arrow(deg):
    """An arrow pointing the way the label beside it names -- where the wind comes FROM, the bearing
    as reported -- in the icon box (-1..1), y down, drawn in the icons' monoline style. An arrow
    pointing where the wind is GOING would read "↑ S" for a south wind and "↓ N" for a north wind:
    against its own label, north at the bottom."""
    import math
    a = math.radians(float(deg) % 360.0)
    dx, dy = math.sin(a), -math.cos(a)
    tip, tail = (0.80 * dx, 0.80 * dy), (-0.80 * dx, -0.80 * dy)
    out = ["M %.3f %.3f L %.3f %.3f" % (tail[0], tail[1], tip[0], tip[1])]
    for t in (math.radians(34), math.radians(-34)):
        bx, by = -dx * 0.45, -dy * 0.45
        rx, ry = bx * math.cos(t) - by * math.sin(t), bx * math.sin(t) + by * math.cos(t)
        out.append("M %.3f %.3f L %.3f %.3f" % (tip[0], tip[1], tip[0] + rx, tip[1] + ry))
    return " ".join(out)


def wx_rows(wd):
    """The grid's rows for this day, [(left, right)], each cell (kind, value) or None. Only rows the
    forecast can fill: past its horizon a day may have humidity and nothing else."""
    rows = []
    uv = ("uv", "%d" % round(wd["uv"])) if wd.get("uv") is not None else None
    hu = ("humid", "%d%%" % round(wd["humidity"])) if wd.get("humidity") is not None else None
    if uv or hu:
        rows.append((uv, hu))
    sr, ss = wd.get("sunrise"), wd.get("sunset")
    if _clock12(sr) and _clock12(ss):
        rows.append((("sunrise", sr), ("sunset", ss)))
    if wd.get("wind") is not None:
        d_ = wd.get("wind_dir")
        rows.append((("wind", "%d" % round(wd["wind"])), ("dir", d_) if d_ is not None else None))
    return rows


def wx_grid(I, T, x0, cw, pad, y, wd, sz, max_rows=None):
    """Draw the day's figures from `y` (the grid's top) as two left-aligned columns; returns the y
    under the grid. I(x, y, size, path) and T(x, y, text, size, align) are the builder's own.
    `max_rows` drops rows from the end (a six-row month's cells cannot hold all three)."""
    from paperdaemon.pipeline.draw import glyphs as _GL
    rows = wx_rows(wd)[:max_rows] if max_rows is not None else wx_rows(wd)
    col_w = (cw - 2 * pad) / 2.0
    ipx = sz * WX_ICON
    for r_i, (left, right) in enumerate(rows):
        cy = y + sz * WX_ROW * (r_i + 0.5)
        for c_i, cell in enumerate((left, right)):
            if not cell:
                continue
            kind, val = cell
            xl = x0 + pad + c_i * col_w
            if kind == "uv":
                up = ipx * 1.25                         # the UV sun carries its letters: a touch bigger
                I(xl + up / 2.0, cy, up, uv_icon())
                T(xl + up + sz * WX_GAP, cy, val, sz, "left")
            elif kind in ("humid", "wind"):
                I(xl + ipx / 2.0, cy, ipx, icon_path(kind))
                xv = xl + ipx + sz * WX_GAP
                T(xv, cy, val, sz, "left")
                if kind == "wind":                      # the unit, small, after the figure
                    from paperdaemon.pipeline.charts import weather as _wxu
                    wind_unit = "mph" if _wxu.temperature_units() == "fahrenheit" else "km/h"
                    T(xv + EM * sz * len(val) + sz * 0.22, cy + sz * 0.10, wind_unit, sz * 0.55, "left")
            elif kind in ("sunrise", "sunset"):
                I(xl + ipx / 2.0, cy, ipx, icon_path(kind))
                hm = _GL.parse_time(val)
                if hm:                                  # the time as a dial, set to the minute
                    I(xl + ipx + sz * WX_GAP + ipx / 2.0, cy, ipx, _GL.clock_path(hm[0], hm[1], 2.0))
            elif kind == "dir":                         # set in a touch: "10 mph" fills its column
                xa = xl + sz * 0.2
                I(xa + ipx / 2.0, cy, ipx * 0.92, _wind_arrow(val))
                T(xa + ipx + sz * WX_GAP, cy, _compass(val), sz, "left")
    return y + sz * WX_ROW * len(rows)


WEEK_CARD_LINES = 6      # a haiku's three lines, each of which may run over once
WEEK_EVENTS = 4          # a week day's entries (the type and figures are sized for the tablet)


def _week_vl(spec, cfg, schema):
    """THE WEEK: seven day columns starting TODAY (today is the leftmost), each with its day number,
    the forecast in full, the day's entries, and -- at the foot -- an on-this-day card.

    Not an hour grid. An hour grid on a tablet page is forty rows of mostly-empty ruling; a day
    column with its actual entries uses the ink on the content. The forecast is always there,
    and with a whole column it says what a month cell cannot: sunrise and sunset, wind, the shape
    of the day's temperature as a small line, and WHEN it will rain. Under it the entries stack
    from the top in the order given, a clock face for each time. Five entries always fit; the
    card at the foot is capped so they do. Holidays arrive by rule, like the calendar.
    """
    import datetime as _dt
    from paperdaemon.pipeline.draw import glyphs as _GL
    first = _dt.date.fromisoformat(str(spec["start"])) if spec.get("start") else _dt.date.today()
    days = [first + _dt.timedelta(days=i) for i in range(7)]

    # entries and cards, keyed by ISO date or weekday name; a value is a list of entries or a
    # dict with "events" and "card"
    given = spec.get("days") or {}
    lookup = {}
    for k, v in given.items():
        key = str(k).strip().lower()
        lookup[key] = v
        lookup[key[:3]] = v
    per_day, per_card = [], []
    for d in days:
        v = (lookup.get(d.isoformat()) or lookup.get(d.strftime("%A").lower())
             or lookup.get(d.strftime("%a").lower()) or [])
        if isinstance(v, dict):
            per_day.append(_mark_events({"events": list(v.get("events") or [])}))
            per_card.append(v.get("card"))
        else:
            per_day.append(_mark_events({"events": list(v)}))
            per_card.append(None)

    # holidays, like the calendar; a week column has room for the observances too
    region = spec.get("holidays", "US")
    if region:
        from paperdaemon.pipeline.charts import holidays as _hol
        kinds = (("holiday", "national", "season") if spec.get("observances", True)
                 else ("holiday",))
        table = _hol.table(days[0].year, str(region))
        if days[-1].year != days[0].year:
            table.update(_hol.table(days[-1].year, str(region)))
        for i, d in enumerate(days):
            have = set(str(e.get("text", "")).lower() for e in per_day[i])
            for name, kind, icon in reversed(table.get(d, [])):
                if kind in kinds and name.lower() not in have:
                    per_day[i].insert(0, {"text": name, "kind": kind, "icon": icon})

    # the forecast: always. Given as rm_weather.week() returns it, or fetched.
    wx = dict(spec.get("weather") or {})
    if not wx and spec.get("lat") is not None and spec.get("lon") is not None:
        from paperdaemon.pipeline.charts import weather as _wxm
        wx = _wxm.week(float(spec["lat"]), float(spec["lon"]), days[0])

    # ---- geometry: the calendar's, at the calendar's cell width
    W, want_h = _page(spec, PAGES["tablet"][0], None)
    CW = W / 7.0
    HDR = max(40.0, min(64.0, CW * 0.25))
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    # SIZES FOR THE TABLET, not the monitor they were first tuned on: line weight, small icons and
    # text all read a bit too light and small there. The figures under the high/low are set AT the
    # high/low's size; entries are 26 (not 23) and the card 19 (not 13); a day holds four entries
    # instead of five to make the room.
    big = clamp(CW * 0.29, 22.0, 62.0)
    small = clamp(CW * 0.13, 12.0, 27.0)
    note_sz = clamp(CW * 0.122, 12.0, 26.0)
    pad = max(9.0, CW * 0.055)
    icon_px = big * 0.85
    line_h = note_sz * EV_LEAD
    mid = -note_sz * 0.05
    clock_px, ev_px, gap = note_sz * EV_CLOCK, note_sz * EV_ICON, note_sz * EV_GAP
    ins, rad = max(3.0, CW * 0.02), max(4.0, CW * 0.02)
    card_sz = CARD_SZ
    year_sz = card_sz * 1.15
    cpad = max(4.0, CW * 0.02)
    lead = card_sz * 1.22
    head = year_sz * 1.05
    ch_h = small * 2.3                     # the temperature line's height
    ck = small * 1.0                       # a clock face under the line, where the times were

    # TIGHT ON THE PAGE. The column is exactly as tall as its tallest content: the forecast
    # block of the fullest day, five entry lines, and the tallest card this week carries. The
    # arithmetic here mirrors the drawing below, step for step. `page`/`height` still win.
    def block_h(wd):
        h = pad + big
        if not wd:
            return h + note_sz * 0.9
        h += small * 1.15
        if wd.get("hi") is not None and wd.get("lo") is not None:
            h += small * 0.75
        h += small * WX_ROW * len(wx_rows(wd)) + small * 0.3
        if len([1 for x in wd.get("hours") or [] if x.get("temp") is not None]) >= 4:
            h += small * 0.3 + ch_h + small * 0.35 + ck * 1.2 + small * 0.2
        return h + note_sz * 0.9

    def card_h(card):
        if not card or not _haiku_lines(card):
            return 0.0
        hd = head if _card_head(card) else 0.0
        n = len(_card_lines(card, _units(CW - 2 * pad, card_sz), WEEK_CARD_LINES))
        return 2 * cpad + hd + n * lead

    tallest = max(block_h(wx.get(d.isoformat()) or {}) for d in days)
    card_max = max(card_h(c) for c in per_card)
    need = (tallest + note_sz * 0.45 + WEEK_EVENTS * line_h
            + (note_sz * 0.5 + card_max if card_max else 0.0) + pad)
    CH = (want_h - HDR) if want_h else need
    CH = max(CH, CW * 1.85)
    H = HDR + CH

    px = _Px(W, H)
    cells, heads, hdr_t, texts, icons, rules, tiles, cards, orns, curves, nights, hatch, haze, pills = \
        [], [], [], [], [], [], [], [], [], [], [], [], [], []

    def T(x, y, t, size, align="center", bold=False):
        texts.append({"x": x, "y": y, "t": t, "s": size, "al": align, "b": bold})

    def I(x, y, sz, path):
        icons.append({"x": x, "y": y, "sz": sz ** 2, "icon": path, "ink": "#000000"})

    def R(k, x0_, x1_, y_):
        rules.append({"x": x0_, "y": y_, "k": k, "o": 0})
        rules.append({"x": x1_, "y": y_, "k": k, "o": 1})

    weekend = set(("Sat", "Sun"))
    today = _dt.date.today()
    for i, d in enumerate(days):
        x0, y0 = i * CW, HDR
        name = d.strftime("%a")
        heads.append({"x0": x0, "y0": 0, "x1": x0 + CW, "y1": HDR,
                      "fill": "#DCDCDF" if name in weekend else "#EFEFF1"})
        hdr_t.append({"x": x0 + CW / 2.0, "y": HDR / 2.0, "t": name})
        evs = per_day[i]
        wd = wx.get(d.isoformat()) or {}
        base = "#FBFBFC" if name in weekend else "#FFFFFF"
        fill = weather_wash(wd)                     # the tile is laid once its bottom is known
        cells.append({"x0": x0, "y0": y0, "x1": x0 + CW, "y1": y0 + CH, "fill": base})
        R("v%d" % i, x0, x0, 0)
        rules[-2]["y"], rules[-1]["y"] = 0, H

        # the day number, the weather glyph across from it
        T(x0 + pad, y0 + pad + big * 0.5, str(d.day), big, "left")
        cx = x0 + CW / 2.0
        inner = CW - 2 * pad
        cur = y0 + pad + big
        if wd:
            wicon = wd.get("icon")
            precip = wicon in ("rain", "snow", "storm")
            rain = wd.get("pop") if (precip and wd.get("hi") is not None) else None
            if wicon:
                I(x0 + CW - pad - icon_px / 2.0, y0 + pad + icon_px / 2.0, icon_px,
                  weather_icon(wicon, rain))
            cur += small * 1.15
            if wd.get("hi") is not None and wd.get("lo") is not None:
                T(cx, cur, "%d\u00b0 / %d\u00b0" % (round(wd["hi"]), round(wd["lo"])), small)
                cur += small * 0.75
            # the six figures, two left-aligned columns (see wx_grid)
            cur = wx_grid(I, T, x0, CW, pad, cur, wd, small) + small * 0.3
            # THE DAY'S TEMPERATURE AS A LINE: time along the bottom, the temperature scaled
            # between the day's own low and high. Six figures said less in three times the room.
            hours = sorted((h for h in wd.get("hours") or [] if h.get("temp") is not None),
                           key=lambda h: h["h"])
            if len(hours) >= 4:
                lab = small * 0.8
                top = cur + small * 0.3
                lo = min(h["temp"] for h in hours)
                hi = max(h["temp"] for h in hours)
                span = (hi - lo) or 1.0
                # the curve takes the whole width; the high and low are printed two rows up
                gx0, gx1 = x0 + pad, x0 + CW - pad
                hw = (gx1 - gx0) / 23.0
                for h in hours:
                    curves.append({"x": gx0 + hw * h["h"],
                                   "y": top + ch_h * (1.0 - (h["temp"] - lo) / span),
                                   "k": "c%d" % i, "o": h["h"]})
                # NIGHT IS SHADED at both ends of the chart -- from the left edge to sunrise and
                # from sunset to the right edge -- so the line reads against the day.
                def _hour_of(hhmm):
                    try:
                        hh_, mm_ = str(hhmm).split(":")[:2]
                        return int(hh_) + int(mm_) / 60.0
                    except (ValueError, AttributeError):
                        return None
                rise, sett = _hour_of(wd.get("sunrise")), _hour_of(wd.get("sunset"))
                ny0, ny1 = top - lab * 0.35, top + ch_h + small * 0.25
                if rise is not None and rise > 0:
                    nights.append({"x0": gx0, "y0": ny0, "x1": gx0 + hw * min(23.0, rise),
                                   "y1": ny1, "fill": "#000000"})
                if sett is not None and sett < 23:
                    nights.append({"x0": gx0 + hw * max(0.0, sett), "y0": ny0, "x1": gx1,
                                   "y1": ny1, "fill": "#000000"})
                # THE WET HOURS ARE HATCHED behind the line, the same height as the night
                # shading: diagonal hairlines, the tablet's own idiom. No figures on them yet.
                for j, (h0, h1, peak, kind) in enumerate(_wet_spans(wd.get("hours") or [])[:3]):
                    bx0 = max(gx0, gx0 + hw * (h0 - 0.5))
                    bx1 = min(gx1, gx0 + hw * (h1 - 0.5))
                    hgt, step, n = ny1 - ny0, small * 0.34, 0
                    c = bx0 - hgt
                    while c < bx1:
                        t0 = max(0.0, (bx0 - c) / hgt)
                        t1 = min(1.0, (bx1 - c) / hgt)
                        if t0 < t1:
                            k = "h%d_%d_%d" % (i, j, n)
                            hatch.append({"x": c + t0 * hgt, "y": ny1 - t0 * hgt, "k": k, "o": 0})
                            hatch.append({"x": c + t1 * hgt, "y": ny1 - t1 * hgt, "k": k, "o": 1})
                            n += 1
                        c += step
                    # THE KIND OF PRECIPITATION stands in the hatching up near the top, and THE
                    # CHANCE at its foot, when the stretch is wide enough to hold them. Nothing
                    # is punched out: a white haze that FADES to nothing sits under each, so the
                    # hatch and the line gray off around the glyph and the figure and stay in
                    # view. This is the whole rain story, inside the chart the time axis already
                    # draws.
                    ipx3 = lab * 1.35
                    gcx = (bx0 + bx1) / 2.0
                    ptxt = "%d%%" % round(peak)
                    tw = _GL.measure(ptxt, TRACK) * lab * CAPF
                    hz = max(ipx3, tw) * 0.95          # ONE haze, the same under glyph and figure
                    if bx1 - bx0 >= ipx3 * 1.45:
                        gcy = ny0 + lab * 0.25 + ipx3 * 0.6
                        haze.append({"x0": gcx - hz, "y0": gcy - hz, "x1": gcx + hz, "y1": gcy + hz})
                        I(gcx, gcy, ipx3, icon_path(kind))
                    if bx1 - bx0 >= tw * 1.0:
                        pcy = ny1 - lab * 0.85
                        haze.append({"x0": gcx - hz, "y0": pcy - hz, "x1": gcx + hz, "y1": pcy + hz})
                        T(gcx, pcy, ptxt, lab)
                base_y = top + ch_h + small * 0.35
                # THE TIMES ARE CLOCK FACES: 6, noon and 6, where "6a 12p 6p" were. The night
                # shading says which six is which.
                for hh in (6, 12, 18):
                    I(gx0 + hw * hh, base_y + ck * 0.6, ck, _GL.clock_path(hh, 0, 2.0))
                cur = base_y + ck * 1.2 + small * 0.2    # the rule sits close under the clocks
            # WHEN it rains: the wet stretches of the day, with the peak chance (two at most)
            R("s%d" % i, x0 + pad, x0 + CW - pad, cur)
            # THE DAY'S COLOR ENDS JUST ABOVE THIS RULE: the sky is the weather's, the events
            # below sit on white, and a pill never has to fight its day for the eye.
            if fill:
                tiles.append({"x0": x0 + ins, "y0": y0 + ins, "x1": x0 + CW - ins,
                              "y1": cur - small * 0.15, "fill": fill, "r": rad})
            cur += note_sz * 0.9
        else:
            cur += note_sz * 0.9

        # THE CARD AT THE FOOT, capped so that five entries always fit above it
        floor = y0 + CH - pad
        card = per_card[i]
        ev_floor = floor
        if card and _haiku_lines(card):
            cyear = _card_head(card)
            hd = head if cyear else 0.0
            room_px = floor - (cur + note_sz * 0.45 + WEEK_EVENTS * line_h + note_sz * 0.5)
            # +0.5: in the fullest column the room is an exact multiple of the leading, and
            # floating point must not round three lines down to two
            room = int(min(WEEK_CARD_LINES, max(0.0, room_px - 2 * cpad - hd + 0.5) // lead))
            lines = _card_lines(card, _units(inner, card_sz), room)
            if lines:
                hgt = 2 * cpad + hd + len(lines) * lead
                c_top = floor - hgt
                cards.append({"x0": x0 + ins, "y0": c_top, "x1": x0 + CW - ins, "y1": floor,
                              "fill": CARD_FILL, "r": rad})
                yy = c_top + cpad
                if cyear:
                    T(cx, yy + year_sz * 0.62, cyear, year_sz)
                    orns.append({"x": cx, "y": yy + year_sz * 0.92 + 2.5,
                                 "sz": inner ** 2, "icon": ORNAMENT, "ink": "#000000"})
                    yy += hd
                for ln, runover in lines:
                    T(x0 + pad + (card_sz * RUNOVER if runover else 0), yy + card_sz * 0.6,
                      ln, card_sz, "left")
                    yy += lead
                ev_floor = c_top - note_sz * 0.5

        # entries, from the top, in the order given; never into the card
        ly = cur + note_sz * 0.45
        for e in evs[:WEEK_EVENTS]:
            if ly + note_sz * 0.45 > ev_floor:
                break
            ph = note_sz * PILL_H
            pills.append({"x0": x0 + ins, "y0": ly + mid - ph / 2.0,
                          "x1": x0 + CW - ins, "y1": ly + mid + ph / 2.0,
                          "fill": pill_fill(e.get("kind")), "r": rad})
            x = x0 + pad
            avail = CW - 2 * pad
            hhmm = _GL.parse_time(e.get("at")) if e.get("at") else None
            if hhmm:
                I(x + clock_px / 2.0, ly + mid, clock_px, _GL.clock_path(hhmm[0], hhmm[1], 2.0))
                x += clock_px + gap
                avail -= clock_px + gap
            ic = e.get("icon") or KIND_ICON.get(e.get("kind"))
            text = str(e.get("text", ""))
            if (ic and icon_path(ic, None)
                    and _GL.measure(text, TRACK) * note_sz * CAPF <= avail - (ev_px + gap)):
                I(x0 + CW - pad - ev_px / 2.0, ly + mid, ev_px, icon_path(ic))
                avail -= ev_px + gap
            T(x, ly, _GL.fit(text, _units(avail, note_sz), TRACK), note_sz, "left")
            ly += line_h

    # ---- title
    d1 = days[-1]
    if spec.get("title"):
        title_t = str(spec["title"])
    elif days[0].month == d1.month:
        title_t = "%s %d - %d, %d" % (days[0].strftime("%B"), days[0].day, d1.day, d1.year)
    else:
        title_t = "%s %d - %s %d, %d" % (days[0].strftime("%b"), days[0].day,
                                          d1.strftime("%b"), d1.day, d1.year)
    title = {"text": title_t, "fontSize": max(22.0, W / 40.0), "offset": max(12.0, W / 90.0)}
    if spec.get("place"):
        title["subtitle"] = str(spec["place"])
        title["subtitleFontSize"] = max(16.0, W / 64.0)
        title["subtitleColor"] = GRAY

    lay = [px.rect(cells, strokeWidth=0), px.rect(heads, strokeWidth=0)]
    if tiles:
        lay.append(px.rect(tiles, stroke=None, strokeWidth=0, cornerRadius=tiles[0]["r"]))
    if cards:
        lay.append(px.rect(cards, stroke=None, strokeWidth=0, cornerRadius=cards[0]["r"]))
    if pills:
        lay.append(px.rect(pills, stroke=None, strokeWidth=0, cornerRadius=pills[0]["r"]))
    frame = [{"x": 0, "y": HDR, "k": "h0", "o": 0}, {"x": W, "y": HDR, "k": "h0", "o": 1},
             {"x": 0, "y": H, "k": "h1", "o": 0}, {"x": W, "y": H, "k": "h1", "o": 1},
             {"x": 0, "y": 0, "k": "h2", "o": 0}, {"x": W, "y": 0, "k": "h2", "o": 1},
             {"x": W, "y": 0, "k": "v7", "o": 0}, {"x": W, "y": H, "k": "v7", "o": 1}]
    lay += [px.line(rules + frame, strokeWidth=RULE_STROKE, color=RULE),
            px.text(hdr_t, max(15.0, min(27.0, HDR * 0.46)), True)]
    if nights:
        lay.append(px.rect(nights, stroke=None, strokeWidth=0, opacity=0.10))
    if hatch:
        lay.append(px.line(hatch, strokeWidth=1.3, color=RULE))
    if curves:
        lay.append(px.line(curves, strokeWidth=CURVE_STROKE, color="black", interpolate="monotone"))
    if haze:
        # a radial fade, white at the center to nothing at the edge -- the haze has no edge
        lay.append(px.rect(haze, stroke=None, strokeWidth=0, color={
            "gradient": "radial", "x1": 0.5, "y1": 0.5, "r1": 0.0, "x2": 0.5, "y2": 0.5, "r2": 0.5,
            "stops": [{"offset": 0.0, "color": "rgba(255,255,255,0.88)"},
                      {"offset": 0.45, "color": "rgba(255,255,255,0.72)"},
                      {"offset": 1.0, "color": "rgba(255,255,255,0)"}]}))
    if icons:
        lay.append({"data": {"values": icons},
                    "mark": {"type": "point", "filled": False, "opacity": 1,
                             "strokeWidth": ICON_STROKE,
                             "strokeCap": "round", "strokeJoin": "round"},
                    "encoding": px.xy(shape={"field": "icon", "type": "nominal",
                                             "scale": None, "legend": None},
                                      size={"field": "sz", "type": "quantitative",
                                            "scale": None, "legend": None},
                                      stroke={"field": "ink", "type": "nominal",
                                              "scale": None, "legend": None})})
    if orns:
        lay.append({"data": {"values": orns},
                    "mark": {"type": "point", "filled": False, "opacity": 1,
                             "strokeWidth": 1.1,
                             "strokeCap": "round", "strokeJoin": "round"},
                    "encoding": px.xy(shape={"field": "icon", "type": "nominal",
                                             "scale": None, "legend": None},
                                      size={"field": "sz", "type": "quantitative",
                                            "scale": None, "legend": None},
                                      stroke={"field": "ink", "type": "nominal",
                                              "scale": None, "legend": None})})
    for sz in sorted(set(t["s"] for t in texts)):
        for al in ("left", "center", "right"):
            for bold in (False, True):
                sel = [t for t in texts if t["s"] == sz and t["al"] == al and t["b"] == bold]
                if sel:
                    lay.append(px.text(sel, sz, bold, color="black", align=al))
    return px.spec(title, lay, cfg, schema)


def _gantt_vl(spec, cfg, schema):
    """Tasks as bars along a shared scale -- a plan, which is what a tablet page is usually for."""
    tasks = spec.get("tasks") or []
    rows = [{"t": t["name"], "a": t["start"], "b": t["end"],
             "fill": WASH.get(t.get("color", "blue"), WASH["blue"]),
             "lab": str(t.get("label", ""))} for t in tasks]
    names = [t["name"] for t in tasks]
    pad = 8 + int(max([len(n) for n in names] or [4]) * 8.0)
    return {"$schema": schema, "title": spec.get("title", ""),
            "width": max(320, WIDTH - pad - 190), "height": 62 * len(rows) + 60,
            "data": {"values": rows},
            "layer": [
                {"mark": {"type": "bar", "stroke": "black", "strokeWidth": 2,
                          "height": {"band": 0.66}, "cornerRadius": 3},
                 "encoding": {"color": {"field": "fill", "type": "nominal", "scale": None,
                                        "legend": None}}},
                {"mark": {"type": "text", "align": "left", "dx": 7, "fontSize": 22,
                          "font": FONT, "color": "black"},
                 "encoding": {"text": {"field": "lab", "type": "nominal"},
                              "x": {"field": "b", "type": "quantitative"}}}],
            "encoding": {
                "y": {"field": "t", "type": "nominal", "sort": names, "title": None,
                      "axis": {"titlePadding": pad}},
                "x": {"field": "a", "type": "quantitative", "title": spec.get("x_label"),
                      "axis": dict(tickCount=8, **_GRID)},
                "x2": {"field": "b"}},
            "config": cfg}


def _grid_vl(spec):
    """table and calendar, both drawn as a rect grid with text in it.

    Vega-Lite rather than a second drawing library, so every chart in this system comes out of one
    renderer with one set of crispness settings -- the thing that decides whether it traces cleanly
    is the styling, and having two paths would mean tuning it twice.
    """
    cfg = _config()
    schema = "https://vega.github.io/schema/vega-lite/v5.json"
    blank = {"labelColor": "black", "domain": False, "ticks": False, "labelFontSize": 15,
             "labelLimit": 0, "grid": False, "title": None}
    if spec["type"] == "table":
        cols, rows = spec["columns"], spec["rows"]
        cells = []
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                cells.append({"col": cols[c], "row": r, "v": "" if val is None else str(val),
                              "head": 0})
        for c, name in enumerate(cols):                 # the header, as row -1
            cells.append({"col": name, "row": -1, "v": name, "head": 1})
        # THE TYPE FITS THE TABLE. At a fixed 16 px, a table of two columns of short words across
        # the whole width comes out smaller than the typed text above it. The widest entry sets
        # it (to 3/4 of its column), up to 28 px for a short table, back down to 16 as the rows
        # run past a dozen.
        longest = max([len(str(v)) for row in rows for v in row] + [len(str(c)) for c in cols] + [1])
        fs = 0.75 * (WIDTH - 90) / max(1, len(cols)) / (0.5 * longest)
        fs = max(16.0, min(fs, 28.0, 28.0 * 12.0 / max(12.0, len(rows) + 1.0)))
        h = 2.75 * fs * (len(rows) + 1) + 40
        return {"$schema": schema, "title": spec.get("title", ""),
                "width": WIDTH - 90, "height": h, "data": {"values": cells},
                "layer": [
                    {"mark": {"type": "rect", "stroke": "black", "strokeWidth": 1.5},
                     "encoding": {"color": {"field": "head", "type": "quantitative", "legend": None,
                                            "scale": {"domain": [0, 1],
                                                      "range": ["#FFFFFF", "#D9D9D9"]}}}},
                    {"transform": [{"filter": "datum.head == 0"}],
                     "mark": {"type": "text", "fontSize": round(fs), "font": FONT, "color": "black"},
                     "encoding": {"text": {"field": "v", "type": "nominal"}}},
                    {"transform": [{"filter": "datum.head == 1"}],
                     "mark": {"type": "text", "fontSize": round(fs), "font": FONT, "color": "black",
                              "fontWeight": "bold"},
                     "encoding": {"text": {"field": "v", "type": "nominal"}}}],
                "encoding": {
                    "x": {"field": "col", "type": "nominal", "sort": cols, "axis": None},
                    "y": {"field": "row", "type": "ordinal",
                          "sort": list(range(-1, len(rows))), "axis": None}},
                "config": cfg}
    # ---- calendar: a real month, drawn in pixels
    #
    # SUNDAY FIRST by default. Monday-first is the ISO convention and it is what the Python
    # calendar module hands you, which is the only reason this ever started the week on a Monday;
    # it is not what the wall calendar in the room does.
    #
    # The cell carries the weather when the spec gives it: high and low, the UV index and the
    # humidity, each behind its own icon. "UV 7 . 49%" was the first attempt and the 49 could have
    # been anything -- rain, cloud, battery. A sun in front of one number and a droplet in front of
    # the other says which is which without a word.
    #
    # Cell height is CAPPED against cell width. Stretching five rows to fill a 1960-tall page gave
    # 207x385 cells: everything bunched into the top fifth with a letterbox of nothing under it.
    import calendar as _cal
    y, mo = spec["year"], spec["month"]
    marks = {}
    for k, v in (spec.get("marks") or {}).items():
        marks[int(k)] = v if isinstance(v, dict) else {"note": str(v)}
    for m in marks.values():
        m["events"] = _mark_events(m)
    wx = dict((int(k), v) for k, v in (spec.get("weather") or {}).items())
    if not wx and spec.get("lat") is not None and spec.get("lon") is not None:
        from paperdaemon.pipeline.charts import weather as _wxm
        wx = _wxm.month(float(spec["lat"]), float(spec["lon"]), y, mo)
    # ONE MONTH. Every day carries its forecast icon and all seven weather figures when there is
    # a forecast, its events, and its card when it has one and the events leave room. Color
    # follows the forecast when there is one -- the SKY -- and what the day HAS when there is
    # not; or say `color_by` yourself.
    color_by = str(spec.get("color_by") or ("weather" if wx else "kind")).lower()
    cards, orns, tiles, pills, seps = [], [], [], [], []
    # BUILT-IN HOLIDAYS. `holidays` is a region ("US", "US-MA") or False. The big ones go on
    # every calendar; the observances and the year's turning points go on a what's-on calendar
    # by default and on a weather calendar only when `observances` is set -- a weather cell
    # has five lines and the forecast is what it is for.
    region = spec.get("holidays", "US")
    if region:
        from paperdaemon.pipeline.charts import holidays as _hol
        kinds = (("holiday", "national", "season") if spec.get("observances", True)
                 else ("holiday",))
        for d, items in _hol.month(y, mo, str(region), kinds).items():
            evs = marks.setdefault(d, {}).setdefault("events", [])
            have = set(str(e.get("text", "")).lower() for e in evs)
            for name, kind, icon in items:
                if name.lower() not in have:
                    evs.insert(0, {"text": name, "kind": kind, "icon": icon})
    first_dow = _first_day(spec)            # 6 = Sunday, 0 = Monday
    weeks = _cal.Calendar(firstweekday=first_dow).monthdayscalendar(y, mo)
    allnames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dows = [allnames[(first_dow + i) % 7][:3] for i in range(7)]
    weekend = set(("Sat", "Sun"))

    # THE PORTRAIT SAFE AREA IS THE FORM THIS IS BUILT FOR. Other sizes still draw,
    # but every measurement below -- type sizes, how many events fit, how many
    # characters fit on a line -- is chosen against 1450 x 1960.
    W, want_h = _page(spec, *PAGES["tablet"])
    CW = W / 7.0
    HDR = max(34.0, min(56.0, CW * 0.22))
    # A page has a height; use it. Capping the cell aspect left a third of a tablet sheet
    # empty, and filling the gap with a ruled band was answering a question nobody asked.
    CH_ = ((want_h - HDR) / len(weeks)) if want_h else CW * 1.15
    if spec.get("cell_aspect"):
        CH_ = min(CH_, CW * float(spec["cell_aspect"]))
    CH_ = max(CH_, CW)                     # square is the floor, enforced in validate() too
    ins, rad = max(3.0, CW * 0.02), max(4.0, CW * 0.02)       # a day's color tile: inset, corner
    H = HDR + CH_ * len(weeks)
    px = _Px(W, max(H, want_h or 0))

    def clamp(v, a2, b2):
        return max(a2, min(b2, v))

    pad = max(9.0, CW * 0.055)
    # The day number and the weather icon are drawn the same VISUAL height. A digit stands CAP
    # (0.66) of its font size; a Lucide glyph fills about 0.83 of its box. Matching cap height to
    # BOX height was the last mistake -- it made the icon two thirds the size it looked, and the
    # inscribed percentage six pixels tall. Match what the eye sees, and size both off the cell so
    # there is room for a figure inside the icon.
    # Driven off cell WIDTH. Height was the tighter of the two on anything that is not
    # a tall portrait page, and it throttled the square to two thirds the type size
    # for no reason -- the content is a narrow column, so width is what binds.
    big = clamp(min(CH_ * 0.22, CW * 0.29), 22.0, 62.0)   # the day number
    # A digit stands 0.66 of its font size; a Lucide glyph draws about 0.83 of its box. 0.85
    # puts the two within a few per cent of each other, which is what "the same height" means
    # to the eye, and leaves a cloud interior wide enough for a figure.
    icon_px = big * 0.85                                 # the weather icon, same apparent height
    small = clamp(CH_ * 0.125, 12.0, 27.0)               # high / low, and the figures under it
    tiny = clamp(CH_ * 0.100, 10.0, 22.0)
    note_sz = clamp(CH_ * 0.115, 12.0, 26.0)             # entries
    ev_block_m = note_sz * (0.35 + 0.40 + EV_LEAD * (MONTH_EVENTS - 1)) + note_sz * 0.30
    # THE RULE UNDER THE WEATHER. One height for the whole month: under the temperatures and as
    # many rows of the two-column grid (wx_grid) as fit over the entries -- all three in a five-row
    # month, fewer in a six-row one. The day's color ends just above it, and the entries list
    # top-down beneath it -- so a pill never sits on the sky.
    sep_off = None
    grid_rows = 0
    if wx:
        _top = pad + big + small * 1.0 + small * 0.75    # the grid's top, from the cell's
        _avail = CH_ - pad - ev_block_m - _top
        _vals = [v for v in wx.values() if v.get("hi") is not None]
        grid_rows = max([len(wx_rows(v)) for v in _vals] or [0])
        while grid_rows and small * WX_ROW * grid_rows > _avail:
            grid_rows -= 1
        sep_off = _top + small * WX_ROW * grid_rows + small * 0.3
    badge = clamp(tiny * 0.78, 9.0, 16.0)                # the "UV" / "RH" lettering
    top_off = pad + big * 0.52

    cells, heads, hdr_t, nums, notes, stats, icons, rules, rings = \
        [], [], [], [], [], [], [], [], []
    today = spec.get("today")
    for d, name in enumerate(dows):
        x0 = d * CW
        heads.append({"x0": x0, "x1": x0 + CW, "y0": 0, "y1": HDR,
                      "fill": "#DCDCDF" if name in weekend else "#EFEFF1"})
        hdr_t.append({"x": x0 + CW / 2.0, "y": HDR / 2.0, "t": name})
    for w, week in enumerate(weeks):
        for d, day in enumerate(week):
            x0, y0 = d * CW, HDR + w * CH_
            m = marks.get(day) or {}
            fill = "#FFFFFF"
            wd = wx.get(day) or {}
            kinds_here = [e.get("kind") for e in (m.get("events") or [])
                          if e.get("kind") in KIND_COLOR]
            if m.get("card"):
                kinds_here.append("history")
            if day and m.get("color"):
                fill = WASH.get(m["color"], WASH["yellow"])
            elif day and color_by == "weather" and weather_wash(wd):
                fill = weather_wash(wd)
            elif day and color_by != "weather" and kinds_here:
                fill = WASH[KIND_COLOR[min(kinds_here, key=KINDS.index)]]
            elif not day:
                fill = "#F4F4F5"
            elif dows[d] in weekend:
                fill = "#FBFBFC"
            # A DAY'S COLOR IS A TILE, not the cell: a rounded wash set in from the rules, so the
            # grid stays a grid and the color reads as something ON the day.
            base = "#F4F4F5" if not day else ("#FBFBFC" if dows[d] in weekend else "#FFFFFF")
            if day and fill not in (base, "#FFFFFF"):
                tiles.append({"x0": x0 + ins, "y0": y0 + ins, "x1": x0 + CW - ins,
                              "y1": (y0 + sep_off - small * 0.15) if sep_off else (y0 + CH_ - ins),
                              "fill": fill, "r": rad})
                fill = base
            cells.append({"x0": x0, "y0": y0, "x1": x0 + CW, "y1": y0 + CH_, "fill": fill})
            if not day:
                continue
            wd = wx.get(day) or {}
            top = y0 + top_off

            # FIXED ROWS. Centering the block meant a day with no rain line sat its numbers
            # half a line higher than its neighbor, and the whole grid read as crooked. Every
            # row is at a fixed offset from the top of the cell now, so the temperatures line up
            # across the month whether or not the day below them has anything to say.
            #
            # The weather icon lives top-right beside the day number; the EVENT icon lives at the
            # bottom beside its note. They were both being drawn into the same corner.
            cx = x0 + CW / 2.0
            # The percentage goes INSIDE the icon, and ONLY when the icon is precipitation. A
            # chance of rain printed across a sun is a number about weather that is not going to
            # happen, and it covered the only part of the icon that says anything.
            wicon = wd.get("icon")
            precip = wicon in ("rain", "snow", "storm")
            rain = wd.get("pop") if (precip and wd.get("hi") is not None) else None
            wpx = icon_px                                # constant, so the rows never shift
            head_h = max(big, wpx)
            # the icon is inset the SAME from the top as it is from the right
            head_y = y0 + pad + wpx / 2.0
            shape = weather_icon(wicon, rain) if wicon else None
            if shape:
                icons.append({"x": x0 + CW - pad - wpx / 2.0, "y": head_y, "sz": wpx ** 2,
                              "icon": shape, "ink": "#000000"})
            nums.append({"x": x0 + pad, "y": y0 + pad + big * 0.5, "t": str(day), "s": big})

            # THE WEATHER ROWS ARE THE WEEK'S ROWS: temperatures, UV and humidity, sunrise and
            # sunset, wind -- in that order, because that is the order they matter in. Each has
            # a pitch; as many as fit between the day number and what is reserved below -- five
            # event lines, and the day's card when it has one -- are drawn, the rest dropped
            # from the end. A day without a card holds all four; a card day the basics.
            #
            # Past the sixteen-day horizon the API still returns an hourly humidity but no
            # temperature, and a lone droplet on an otherwise empty day is a number about
            # nothing. No temperature, no weather rows.
            from paperdaemon.pipeline.draw import glyphs as _GL
            have_t = bool(wx) and wd.get("hi") is not None
            temps = ("%d\u00b0 / %d\u00b0" % (round(wd["hi"]), round(wd["lo"]))) if have_t \
                else str(m.get("temp") or "")
            # THE WEEK'S LAYOUT (wx_grid): the temperatures centered, then the six figures in two
            # left-aligned columns, as many rows as the month's rule allows (grid_rows).
            floor = y0 + CH_ - pad
            line_h = note_sz * EV_LEAD
            t_c = y0 + pad + big + small * 1.0            # the temperatures' center
            if temps:
                stats.append({"x": cx, "y": t_c, "s": small, "b": False,
                              "t": temps, "c": True, "k": "temp"})
            # THE CARD SITS AT THE FOOT, and only when the day has THREE EVENTS OR FEWER and the
            # whole haiku fits between them and the weather. A busier day is about its events;
            # the card is not cut down to make room, it is left off.
            evs = list(m.get("events") or [])[:MONTH_EVENTS]
            card = m.get("card") if day else None
            c_top0, c_bot0, card_sz, year_sz, cpad, lead, head = _card_geom(CW, CH_, pad, big,
                                                                           note_sz)
            chead = _card_head(card) if card else ""
            head = head if chead else 0.0
            cinner = CW - 2 * pad
            clines = _card_lines(card, _units(cinner, card_sz), 6) if card else []
            card_h = (2 * cpad + head + len(clines) * lead) if clines else 0.0
            card_top = floor - card_h

            grid_top = t_c + small * 0.75
            rows_here = grid_rows if (have_t and grid_rows) else 0
            # A DAY THAT CARRIES A CARD GIVES IT ROOM. The figures and the card are sized for the
            # tablet, and under a full three-row grid a four- or five-line haiku no longer fits a
            # month cell -- so on a card day the grid drops rows from the end (wind first) until
            # the card and the day's events fit. Every other day keeps all three.
            if clines and len(evs) <= 3 and rows_here:
                need = card_h + len(evs) * line_h + note_sz * (0.85 if evs else 0.3) + note_sz * 0.2
                while rows_here > 1 and floor - (grid_top + small * WX_ROW * rows_here
                                                 + small * 0.3) < need:
                    rows_here -= 1
            rows_bottom = grid_top
            if rows_here:
                def _I(x_, y_, sz_, path_):
                    icons.append({"x": x_, "y": y_, "sz": sz_ ** 2, "icon": path_, "ink": "#000000"})

                def _T(x_, y_, t_, s_, al_="left"):
                    stats.append({"x": x_, "y": y_, "s": s_, "b": False, "t": t_, "al": al_})
                rows_bottom = wx_grid(_I, _T, x0, CW, pad, grid_top, wd, small,
                                      max_rows=rows_here) + small * 0.3
            if sep_off:
                # the month's one rule height -- except on a card day that gave up a row, whose
                # rule (and color tile) closes under the rows it kept
                # (a day past the forecast has no figures above its rule at all; when it carries a
                # card the rule comes up under the day number and the card has the cell)
                if have_t:
                    ry = y0 + sep_off if rows_here == grid_rows else rows_bottom
                else:
                    ry = grid_top if clines else y0 + sep_off
                seps.append({"k": "sep%d" % day, "x0": x0 + pad, "x1": x0 + CW - pad, "y": ry})
                if tiles and tiles[-1]["x0"] == x0 + ins and tiles[-1]["y0"] == y0 + ins:
                    tiles[-1]["y1"] = ry - small * 0.15      # the day's color ends at its rule
                rows_bottom = ry
            # EVENTS LIST TOP-DOWN under the rule that closes the weather block. The card keeps
            # the foot, and shows only when the day has three events or fewer and the whole haiku
            # fits under the last of them; otherwise it is left off, never cut.
            ev_top = rows_bottom + note_sz * 0.85
            if clines and len(evs) <= 3:
                n = len(evs)
                bottom_of_events = (ev_top + (n - 1) * line_h + note_sz * 0.45) if n \
                    else (ev_top - note_sz * 0.4)
                if bottom_of_events > card_top - note_sz * 0.2:
                    clines = []
            ev_limit = (card_top - note_sz * 0.2) if clines else floor
            # UP TO FIVE EVENTS, and NOT ONE OF THEM WRAPS. A time is drawn as a CLOCK SET TO IT
            # rather than typed. A line that would run into the card (or off the cell) is left off.
            mid = -note_sz * 0.05
            clock_px, ev_px, gap = note_sz * EV_CLOCK, note_sz * EV_ICON, note_sz * EV_GAP
            for i, e in enumerate(evs):
                ly = ev_top + i * line_h
                if ly + note_sz * 0.45 > ev_limit:
                    break
                ph = note_sz * PILL_H
                pills.append({"x0": x0 + ins, "y0": ly + mid - ph / 2.0,
                              "x1": x0 + CW - ins, "y1": ly + mid + ph / 2.0,
                              "fill": pill_fill(e.get("kind")), "r": rad})
                x = x0 + pad
                avail = CW - 2 * pad
                hhmm = _GL.parse_time(e.get("at")) if e.get("at") else None
                if hhmm:
                    icons.append({"x": x + clock_px / 2.0, "y": ly + mid,
                                  "sz": clock_px ** 2, "ink": "#000000",
                                  "icon": _GL.clock_path(hhmm[0], hhmm[1], 2.0)})
                    x += clock_px + gap
                    avail -= clock_px + gap
                ic = e.get("icon") or KIND_ICON.get(e.get("kind"))
                text = str(e.get("text", ""))
                # THE ICON GIVES WAY, NOT THE WORDS. If the line only fits without its icon the
                # icon goes: a cut word is a lost meaning, a missing flag is not.
                if (ic and icon_path(ic, None)
                        and _GL.measure(text, TRACK) * note_sz * CAPF <= avail - (ev_px + gap)):
                    icons.append({"x": x0 + CW - pad - ev_px / 2.0, "y": ly + mid,
                                  "sz": ev_px ** 2, "icon": icon_path(ic), "ink": "#000000"})
                    avail -= ev_px + gap
                notes.append({"x": x, "y": ly, "s": note_sz,
                              "t": _GL.fit(text, _units(avail, note_sz), TRACK)})

            # THE CARD: a haiku under its head ("1846 - Neptune"), on a gray rounded slip with no
            # border, at the foot of the cell.
            if clines:
                cards.append({"x0": x0 + ins, "y0": card_top, "x1": x0 + CW - ins,
                              "y1": floor, "fill": CARD_FILL, "r": rad})
                yy = card_top + cpad
                if chead:
                    stats.append({"x": cx, "y": yy + year_sz * 0.62, "s": year_sz,
                                  "b": False, "t": chead, "c": True})
                    orns.append({"x": cx, "y": yy + year_sz * 0.92 + 2.5, "sz": cinner ** 2,
                                 "icon": ORNAMENT, "ink": "#000000"})
                    yy += head
                for ln, runover in clines:
                    stats.append({"x": x0 + pad + (card_sz * RUNOVER if runover else 0),
                                  "y": yy + card_sz * 0.6, "s": card_sz, "b": False,
                                  "t": ln, "c": False, "al": "left"})
                    yy += lead

    panel = []
    grid = []
    for d in range(8):
        grid.append({"k": "v%d" % d, "o": 0, "x": d * CW, "y": 0})
        grid.append({"k": "v%d" % d, "o": 1, "x": d * CW, "y": HDR + CH_ * len(weeks)})
    for w in range(len(weeks) + 1):
        grid.append({"k": "h%d" % w, "o": 0, "x": 0, "y": HDR + w * CH_})
        grid.append({"k": "h%d" % w, "o": 1, "x": W, "y": HDR + w * CH_})
    for r in [q for q in panel if q.get("rule")]:
        grid.append({"k": r["k"], "o": 0, "x": pad, "y": r["y"]})
        grid.append({"k": r["k"], "o": 1, "x": W - pad, "y": r["y"]})
    for r in seps:
        grid.append({"k": r["k"], "o": 0, "x": r["x0"], "y": r["y"]})
        grid.append({"k": r["k"], "o": 1, "x": r["x1"], "y": r["y"]})

    panel = [q for q in panel if not q.get("rule")]

    # a weather calendar has to say WHERE the weather is; a forecast with no place on it is a
    # set of numbers about nowhere
    place = spec.get("place")
    head = spec.get("title") or "%s %d" % (_cal.month_name[mo], y)
    title = {"text": head, "fontSize": max(22.0, W / 40.0), "offset": max(12.0, W / 90.0)}
    if place and wx:
        title["subtitle"] = str(place)
        title["subtitleFontSize"] = max(14.0, W / 78.0)
        title["subtitleColor"] = GRAY
        title["subtitlePadding"] = 5
    elif place:
        title["subtitle"] = str(place)
        title["subtitleFontSize"] = max(14.0, W / 78.0)
        title["subtitleColor"] = GRAY

    lay = [px.rect(cells, strokeWidth=0),
           px.rect(heads + panel, strokeWidth=0),]
    if tiles:
        lay.append(px.rect(tiles, stroke=None, strokeWidth=0, cornerRadius=tiles[0]["r"]))
    if cards:
        lay.append(px.rect(cards, stroke=None, strokeWidth=0, cornerRadius=cards[0]["r"]))
    if pills:
        lay.append(px.rect(pills, stroke=None, strokeWidth=0, cornerRadius=pills[0]["r"]))
    if orns:
        # a hairline, thinner than the icons -- it is a rule, not a drawing
        lay.append({"data": {"values": orns},
                    "mark": {"type": "point", "filled": False, "opacity": 1,
                             "strokeWidth": 1.1,
                             "strokeCap": "round", "strokeJoin": "round"},
                    "encoding": px.xy(shape={"field": "icon", "type": "nominal",
                                             "scale": None, "legend": None},
                                      size={"field": "sz", "type": "quantitative",
                                            "scale": None, "legend": None},
                                      stroke={"field": "ink", "type": "nominal",
                                              "scale": None, "legend": None})})
    lay += [
           px.line(grid, strokeWidth=RULE_STROKE, color=RULE),
           # the weekday names fill their band (at 0.46 of it they were too small to read on the tablet)
           px.text([t for t in hdr_t if not t.get("al")],
                   max(15.0, min(32.0, HDR * 0.62)), True)]
    if [t for t in hdr_t if t.get("al")]:
        lay.append(px.text([t for t in hdr_t if t.get("al")],
                           max(15.0, min(32.0, HDR * 0.62)), True, align="left"))

    if icons:
        lay.append({"data": {"values": icons},
                    "mark": {"type": "point", "filled": False, "opacity": 1,
                             "strokeWidth": ICON_STROKE,
                             "strokeCap": "round", "strokeJoin": "round"},
                    "encoding": px.xy(shape={"field": "icon", "type": "nominal",
                                             "scale": None, "legend": None},
                                      size={"field": "sz", "type": "quantitative",
                                            "scale": None, "legend": None},
                                      stroke={"field": "ink", "type": "nominal",
                                              "scale": None, "legend": None})})
    if rings:
        # after the icons, before the text: this knocks the sun's inner ring out so "UV" has
        # clean ground. Drawn before the icons it simply vanished underneath them.
        lay.append(px.rect(rings, stroke=None, strokeWidth=0,
                           cornerRadius=rings[0]["r"]))
    # not bold: a month of bold day numbers is a month of shouting. And ALL of them black --
    # graying the days that had nothing on them read as "grayed out", not as quiet.
    if nums:
        lay.append(px.text(nums, big, False, color="black", align="left"))
    for bold in (True, False):
        for sz in sorted(set(t["s"] for t in stats)):
            for al in ("center", "left", "right"):
                for kind in (None, "temp", "uv", "pct"):
                    sel = [t for t in stats if t["b"] == bold and t["s"] == sz
                           and t.get("k") == kind
                           and t.get("al", "center" if t.get("c") else "right") == al]
                    if not sel:
                        continue
                    extra = {}
                    lay.append(px.text(sel, sz, bold, color="black", align=al, **extra))
    if notes:
        lay.append(px.text(notes, note_sz, False, align="left"))
    return px.spec(title, lay, cfg, schema)


# THE FONT HAS 98 GLYPHS: printable ASCII, the degree sign, the middle dot and the minus. Text
# that reaches for anything else -- a curly quote, an en dash, an ellipsis, an arrow -- would be
# set in whatever face the renderer falls back to, and one wrong glyph on a page reads as a
# mistake. So every string in a spec is mapped to what the font has before anything is drawn.
_ASCII = {"\u2013": "-", "\u2014": "-", "\u2010": "-", "\u2011": "-", "\u2018": "'", "\u2019": "'",
          "\u201c": '"', "\u201d": '"', "\u2026": "..", "\u00d7": "x", "\u2192": "->",
          "\u2190": "<-", "\u00a0": " ", "\u2022": "\u00b7", "\u2713": "v", "\u2714": "v",
          "\u00e9": "e", "\u00e8": "e", "\u00e1": "a", "\u00e0": "a", "\u00f3": "o", "\u00fa": "u",
          "\u00ed": "i", "\u00f1": "n", "\u00fc": "u", "\u00f6": "o", "\u00e4": "a", "\u00e7": "c"}


def _in_font(text):
    try:
        from paperdaemon.pipeline.draw import lettering as _T
        have = _T.G
    except Exception:
        return "".join(_ASCII.get(ch, ch) for ch in str(text))
    out = "".join(ch if (ch in have or ch == "\n") else _ASCII.get(ch, ch) for ch in str(text))
    return "".join(ch if (ch in have or ch == "\n") else (_T.fold(ch) or "-") for ch in out)


def _fontsafe(obj):
    """The spec with every string mapped into the font. Keys are left alone."""
    if isinstance(obj, str):
        return _in_font(obj)
    if isinstance(obj, dict):
        return dict((k, _fontsafe(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return [_fontsafe(v) for v in obj]
    return obj


# ONE CHART AT A TIME: `page` rebinds the module's WIDTH while a chart is built (below), so two charts built at once on
# two threads would lay themselves out against each other's width
_BUILDING = threading.RLock()


def to_vegalite(spec):
    with _BUILDING:
        return _to_vegalite_sized(spec)


def _to_vegalite_sized(spec):
    if isinstance(spec, dict) and spec.get("type") in TABLETOP_TYPES:
        # Do not font-normalize identifiers, state, or commands. Only displayed
        # text is normalized by the tabletop canvas, after strict validation.
        from paperdaemon.pipeline.charts import tabletop as rm_tabletop
        return rm_tabletop.to_vegalite(spec)
    spec = _fontsafe(spec)
    spec = validate(spec)
    if spec.get("page") or spec.get("width"):
        # WIDTH is what all sixty builders lay themselves out against, so rebinding it for the
        # duration is what makes `page` work everywhere instead of only in the few charts that
        # were rewritten to take a size. Restored in the finally, because a chart that silently
        # resized every chart after it would be a nasty thing to debug.
        global WIDTH
        keep = WIDTH
        try:
            WIDTH = int(_page(spec)[0])
            return _to_vegalite(spec)
        finally:
            WIDTH = keep
    return _to_vegalite(spec)


def _to_vegalite(spec):
    if spec["type"] in GRIDLIKE:
        cfg = _config()
        schema = "https://vega.github.io/schema/vega-lite/v5.json"
        special = {"week": _week_vl, "gantt": _gantt_vl,
                   "cards": _cards_vl, "posts": _posts_vl, "progress": _progress_vl, "agenda": _agenda_vl,
                   "checklist": _checklist_vl, "habit": _habit_vl, "yearmap": _yearmap_vl,
                   "timeline": _timeline_vl, "waffle": _waffle_vl, "funnel": _funnel_vl,
                   "gauge": _gauge_vl, "candle": _candle_vl, "radar": _radar_vl,
                   "dist": _dist_vl, "violin": _dist_vl, "sankey": _sankey_vl,
                   "pictograph": _pictograph_vl, "map": _map_vl, "stock": _stock_vl,
                   "bullet": _bullet_vl, "slope": _slope_vl, "dumbbell": _dumbbell_vl,
                   "bump": _bump_vl, "matrix": _matrix_vl, "sparkbars": _sparkbars_vl,
                   "quadrant": _quadrant_vl, "waterfall": _waterfall_vl,
                   "histogram": _histogram_vl, "bubble": _bubble_vl, "lollipop": _lollipop_vl,
                   "diverging": _diverging_vl, "pyramid": _pyramid_vl,
                   "marimekko": _marimekko_vl, "treemap": _treemap_vl, "venn": _venn_vl,
                   "ridgeline": _ridgeline_vl, "polar": _polar_vl, "tree": _tree_vl,
                   "flow": _flow_vl, "kanban": _kanban_vl, "journey": _journey_vl,
                   "clock": _clock_vl}
        if spec["type"] == "violin":
            spec = dict(spec, violin=True)
        fn = special.get(spec["type"])
        return fn(spec, cfg, schema) if fn else _grid_vl(spec)
    t, cats, series = spec["type"], spec["categories"], spec["series"]
    title = spec.get("title", "")
    xl, yl = spec.get("x_label"), spec.get("y_label")
    cfg = _config()
    n = len(series)
    colors = PALETTE[:n]
    schema = "https://vega.github.io/schema/vega-lite/v5.json"

    if t == "bar":
        rows = [{"c": c, "s": d["name"], "v": d["values"][i]}
                for d in series for i, c in enumerate(cats)]
        vl = {"$schema": schema, "title": title, "width": WIDTH - 80, "height": 560,
              "data": {"values": rows},
              "mark": {"type": "bar", "stroke": "black", "strokeWidth": 2.6},
              "encoding": {
                  # sort=cats or Vega-Lite orders them alphabetically: Jan, Feb, Mar, Apr
                  # renders as Apr, Feb, Jan, Mar.
                  "x": {"field": "c", "type": "nominal", "title": xl, "sort": cats,
                        "axis": {"labelAngle": 0}},
                  "y": {"field": "v", "type": "quantitative", "title": yl},
                  "color": {"field": "s", "type": "nominal", "title": None,
                            "scale": {"domain": [d["name"] for d in series], "range": colors},
                            "legend": {"symbolType": "square"}}},
              "config": cfg}
        if n > 1:
            vl["encoding"]["xOffset"] = {"field": "s", "type": "nominal",
                                         "sort": [d["name"] for d in series]}
        else:
            vl["encoding"]["color"]["legend"] = None
        return vl

    if t == "area":
        rows = [{"x": c, "s": d["name"], "v": d["values"][i]}
                for d in series for i, c in enumerate(cats)]
        return {"$schema": schema, "title": title, "width": WIDTH - 100, "height": 560,
                "data": {"values": rows},
                "mark": {"type": "area", "line": {"color": "black", "strokeWidth": 3},
                         "opacity": 1, "stroke": "black", "strokeWidth": 2},
                "encoding": {
                    "x": {"field": "x", "type": "nominal", "title": xl, "sort": cats,
                          "axis": {"labelAngle": 0}},
                    "y": {"field": "v", "type": "quantitative", "title": yl, "stack": "zero"},
                    "color": {"field": "s", "type": "nominal", "title": None,
                              "scale": {"domain": [d["name"] for d in series], "range": colors},
                              "legend": {"symbolType": "square"}}},
                "config": cfg}

    if t == "scatter":
        # categories are the x VALUES here, read as numbers; each series is a cloud of points.
        rows = [{"x": float(c), "s": d["name"], "v": d["values"][i]}
                for d in series for i, c in enumerate(cats)]
        return {"$schema": schema, "title": title, "width": WIDTH - 100, "height": 560,
                "data": {"values": rows},
                "mark": {"type": "point", "filled": True, "size": 300, "opacity": 1,
                         "stroke": "black", "strokeWidth": 2},
                "encoding": {
                    "x": {"field": "x", "type": "quantitative", "title": xl,
                          "axis": dict(**_GRID)},
                    "y": {"field": "v", "type": "quantitative", "title": yl,
                          "axis": dict(**_GRID)},
                    "shape": {"field": "s", "type": "nominal", "title": None,
                              "scale": {"range": SHAPES[:n]}},
                    "color": {"field": "s", "type": "nominal", "title": None,
                              "scale": {"domain": [d["name"] for d in series],
                                        "range": LINE_INK[:n]}}},
                "config": cfg}

    if t in ("line", "step"):
        # `step` is a line that holds its value until the next reading -- which is the truth for
        # anything that changes in jumps: a setting, a price band, a headcount, a version.
        rows = [{"x": c, "s": d["name"], "v": d["values"][i]}
                for d in series for i, c in enumerate(cats)]
        interp = {"interpolate": "step-after"} if t == "step" else {}
        return {"$schema": schema, "title": title, "width": WIDTH - 100, "height": 560,
                "data": {"values": rows},
                "encoding": {
                    "x": {"field": "x", "type": "nominal", "title": xl, "sort": cats,
                          "axis": dict(labelAngle=0, **_GRID)},
                    "y": {"field": "v", "type": "quantitative", "title": yl,
                          "axis": dict(**_GRID)}},
                "layer": [
                    # color AND dash, not color alone: the dash is what survives if a line is
                    # traced thin, and it is what makes two series readable in a photocopy.
                    {"mark": dict({"type": "line", "strokeWidth": 4}, **interp),
                     "encoding": {
                         "color": {"field": "s", "type": "nominal", "title": None,
                                   "scale": {"domain": [d["name"] for d in series],
                                             "range": LINE_INK[:n]},
                                   "legend": {"symbolType": "stroke", "symbolStrokeWidth": 4}},
                         "strokeDash": {"field": "s", "type": "nominal", "title": None,
                                        "scale": {"range": DASHES[:n]},
                                        "legend": None},
                         "detail": {"field": "s", "type": "nominal"}}},
                    # any extra channel spawns ANOTHER legend box -> legend: None
                    {"mark": {"type": "point", "filled": True, "size": 160, "opacity": 1,
                              "strokeWidth": 2, "stroke": "black"},
                     "encoding": {
                         "shape": {"field": "s", "type": "nominal", "legend": None,
                                   "scale": {"range": SHAPES[:n]}},
                         "fill": {"field": "s", "type": "nominal", "legend": None,
                                  "scale": {"range": MARKER_FILL[:n]}}}}],
                "config": cfg}

    if t in ("pie", "donut"):
        # DEVICE WASHES, not a grayscale ramp. The tablet has six highlighter washes, and a
        # light-gray slice with a light-gray label beside it (which is what a ramp produces) is
        # unreadable twice over.
        #
        # Labels sit OUTSIDE the arc in black, with a leader, and every slice gets one -- a label
        # tinted in its slice's own color, or the biggest slice left unlabeled, reads badly.
        import math as _m
        vals = [float(v) for v in series[0]["values"]]
        total = float(sum(vals)) or 1.0
        W, H = 1000.0, 660.0
        CX, CY, R = W / 2.0, H / 2.0 + 10, 216.0
        inner = 0.46 * R if t == "donut" else 0.0
        px = _Px(W, H)
        wedges, leaders, labels, holes = [], [], [], []
        ang = -_m.pi / 2
        for i, (c, v) in enumerate(zip(cats, vals)):
            sweep = 2 * _m.pi * v / total
            fill = PALETTE[i % len(PALETTE)]
            steps = max(4, int(sweep / 0.08))
            pts = [(CX + R * _m.cos(ang + sweep * k / steps),
                    CY + R * _m.sin(ang + sweep * k / steps)) for k in range(steps + 1)]
            if inner:
                pts += [(CX + inner * _m.cos(ang + sweep * k / steps),
                         CY + inner * _m.sin(ang + sweep * k / steps))
                        for k in range(steps, -1, -1)]
            else:
                pts.append((CX, CY))
            for o, (x, y) in enumerate(pts):
                wedges.append({"k": i, "o": o, "x": x, "y": y, "fill": fill})
            mid = ang + sweep / 2.0
            right = _m.cos(mid) >= 0
            lx = CX + (R + 26) * _m.cos(mid)
            ly = CY + (R + 26) * _m.sin(mid)
            tx = CX + (R + 58) * (1 if right else -1) + (24 if right else -24)
            leaders.append({"k": i, "o": 0, "x": CX + (R - 6) * _m.cos(mid),
                            "y": CY + (R - 6) * _m.sin(mid)})
            leaders.append({"k": i, "o": 1, "x": lx, "y": ly})
            leaders.append({"k": i, "o": 2, "x": tx + (-10 if right else 10), "y": ly})
            labels.append({"x": tx, "y": ly, "al": "left" if right else "right", "k": i,
                           "t": "%s  ·  %s  ·  %.0f%%"
                                % (c, spec.get("fmt", "%g") % v,
                                   100.0 * v / total)})
            ang += sweep
        lay = [
            {"data": {"values": wedges},
             "mark": {"type": "line", "filled": True, "fillOpacity": 1, "stroke": "black",
                      "strokeWidth": 2},
             "encoding": px.xy(detail={"field": "k", "type": "nominal"},
                               order={"field": "o", "type": "quantitative"},
                               color={"field": "fill", "type": "nominal", "scale": None,
                                      "legend": None})},
            px.line(leaders, strokeWidth=1.2, color="#808080")]
        # LABELS NEVER SIT ON EACH OTHER: on each side, top to bottom, a label is at least a line below the one
        # above it (two thin slices side by side put theirs at the same height), and its leader bends to it
        LABEL_SZ = 22
        for side in ("left", "right"):
            prev = None
            for l in sorted([l for l in labels if l["al"] == side], key=lambda l: l["y"]):
                if prev is not None and l["y"] < prev + LABEL_SZ * 1.25:
                    l["y"] = prev + LABEL_SZ * 1.25
                    for q in leaders:
                        if q["k"] == l["k"] and q["o"] == 2:
                            q["y"] = l["y"]
                prev = l["y"]
        for side in ("left", "right"):
            sel = [l for l in labels if l["al"] == side]
            if sel:
                lay.append(px.text(sel, LABEL_SZ, True, align=side))
        return px.spec(title, lay, cfg, schema)

    if t == "stacked":
        rows = [{"c": c, "s": d["name"], "v": d["values"][i]}
                for d in series for i, c in enumerate(cats)]
        return {"$schema": schema, "title": title, "width": WIDTH - 80, "height": 560,
                "data": {"values": rows},
                "mark": {"type": "bar", "stroke": "black", "strokeWidth": 2},
                "encoding": {
                    "x": {"field": "c", "type": "nominal", "title": xl, "sort": cats,
                          "axis": {"labelAngle": 0}},
                    "y": {"field": "v", "type": "quantitative", "title": yl, "stack": "zero"},
                    "color": {"field": "s", "type": "nominal", "title": None,
                              "scale": {"domain": [d["name"] for d in series], "range": colors},
                              "legend": {"symbolType": "square"}},
                    "order": {"field": "s", "type": "nominal"}},
                "config": cfg}

    if t == "heatmap":
        # series are ROWS, categories are COLUMNS, and the number is printed in every cell so the
        # shade never has to be decoded by eye.
        #
        # The ramp is white -> yellow -> orange -> magenta: four DEVICE washes, all of them light.
        # The old grayscale ran to near-black, which meant white text on the hot half and a page
        # the decomposer's UI mode read as a dark theme and inverted.
        rows, lo, hi = [], None, None
        for d in series:
            for i, c in enumerate(cats):
                v = d["values"][i]
                rows.append({"r": d["name"], "c": c, "v": v})
                lo = v if lo is None else min(lo, v)
                hi = v if hi is None else max(hi, v)
        return {"$schema": schema, "title": title,
                "width": WIDTH - 260, "height": 90 * len(series) + 40,
                "data": {"values": rows},
                "layer": [
                    {"mark": {"type": "rect", "stroke": "black", "strokeWidth": 1.5},
                     "encoding": {"color": {"field": "v", "type": "quantitative", "legend": None,
                                            "scale": {"range": ["#FFFFFF", WASH["yellow"],
                                                                WASH["orange"],
                                                                WASH["magenta"]]}}}},
                    {"mark": {"type": "text", "fontSize": 22, "fontWeight": "bold", "font": FONT,
                              "color": "black"},
                     "encoding": {"text": {"field": "v", "type": "quantitative",
                                           "format": ","}}}],
                "encoding": {
                    "x": {"field": "c", "type": "nominal", "title": xl, "sort": cats,
                          "axis": {"labelAngle": 0, "domain": False, "ticks": False}},
                    "y": {"field": "r", "type": "nominal", "title": yl,
                          "sort": [d["name"] for d in series],
                          "axis": {"domain": False, "ticks": False}}},
                "config": cfg}

    # ---- hbar
    vals = series[0]["values"]
    rows = [{"c": c, "v": v} for c, v in zip(cats, vals)]
    # the axis title does NOT reflow around labelLimit:0 labels -> pad by hand
    pad = 8 + int(max(len(c) for c in cats) * 8.0)
    layers = [{"mark": {"type": "bar", "fill": "white", "stroke": "black",
                        "strokeWidth": 2, "height": {"band": 0.62}}}]
    if spec.get("value_labels", True):
        layers.append({"mark": {"type": "text", "align": "left", "dx": 7, "fontSize": 22,
                                "fontWeight": "bold", "color": "black", "font": FONT},
                       "encoding": {"text": {"field": "v", "type": "quantitative",
                                             "format": ","}}})
    return {"$schema": schema, "title": title,
            "width": max(320, WIDTH - pad - 190), "height": 560,
            "data": {"values": rows},
            "encoding": {
                # "-x" here would re-rank by value. The model decides the order; this draws it.
                "y": {"field": "c", "type": "nominal", "title": yl, "sort": cats,
                      "axis": {"titlePadding": pad}},
                "x": {"field": "v", "type": "quantitative", "title": xl,
                      "axis": {"tickCount": 6},
                      "scale": {"domain": [0, max(vals) * 1.14], "nice": False}}},
            "layer": layers, "config": cfg}


# ---------------------------------------------------------------- rendering
def check_font(font=FONT):
    """resvg SILENTLY drops ALL text for an unknown font. Verify once at startup."""
    probe = {"$schema": "https://vega.github.io/schema/vega-lite/v5.json",
             "data": {"values": [{"a": "WWWWWWWW", "b": 1}]}, "mark": "bar",
             "encoding": {"x": {"field": "a", "type": "nominal",
                                "axis": {"labelFontSize": 40, "labelColor": "black"}},
                          "y": {"field": "b", "type": "quantitative", "axis": None}},
             "config": {"background": "white", "font": font, "view": {"stroke": None}}}
    with_label = len(_vlc().vegalite_to_png(vl_spec=probe, scale=1))
    probe["encoding"]["x"]["axis"] = None
    return with_label != len(_vlc().vegalite_to_png(vl_spec=probe, scale=1))

def render(spec, png_path=None, svg_path=None, scale=1.0, crisp=True):
    """House spec -> crisp PNG (and optional SVG). Returns the PNG bytes."""
    svg = _vlc().vegalite_to_svg(vl_spec=to_vegalite(spec))
    if svg_path:
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
    if crisp:
        svg = re.sub(r"<svg ", "<svg " + _CRISP, svg, count=1)
    png = _vlc().svg_to_png(svg, scale=scale)
    if png_path:
        with open(png_path, "wb") as f:
            f.write(png)
    return png
