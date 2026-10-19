"""The tablet's page templates, borrowed from the user's own reMarkable desktop app and library (never shipped).

WHAT THERE IS (read 2026-10-18 from the desktop app 3.x and the user's library):
  * the app's program file carries, among its Qt resources (some packed: a 4-byte big-endian length, then zlib):
    - templates.json, the index: every template's name, its file name ("P ..." portrait, "LS ..." landscape), its
      categories and an `iconCode`;
    - the definitions: JSON, vector and parametric -- constants (numbers, or formulas over templateWidth and
      templateHeight, with ?:, comparisons and && ||) and items: groups (a bounding box, repeated in rows and columns:
      a count, "down", "up", "right", "infinite"), paths (M, L, C, Z with numbers or formulas over parentWidth and
      parentHeight; strokeWidth, strokeColor, fillColor) and text (fontSize, position);
    - the picker's icons: glyphs of an icon font ("icomoon"), one per `iconCode`;
  * five templates have no definition: Calligraphy large and medium, Hexagon large, medium and small are drawn by the
    app's own code; and Blank is blank;
  * the rM Methods templates are documents of the user's library (type TemplateType) whose .template file is a
    definition in the same format, with its icon as SVG (iconData).
PaperDaemon is portrait only: the landscape templates are left out.

extract() reads the app into the content folder (rm-page-templates: the index with each template's icon as an SVG
path, and the definitions); catalog() lists every template there is, defaults and rM Methods together; svg() draws one
template at a page's size."""
import io
import math
import json
import os
import re
import zlib

from .. import paths
from . import fonts

DIR = "rm-page-templates"
# the index's names whose definitions are named otherwise
ALIAS = {"Grid margin": "Grid margin medium", "Lined medium": "Lines medium", "Lined small": "Lines small",
         "Week planner 1": "Weekplanner 1", "Week planner 2": "Weekplanner 2", "Week planner US": "Weekplanner US",
         "Bass tabs": "Bass tab", "Guitar tabs": "Guitar tab"}
DRAWN_BY_THE_APP = ("Calligraphy large", "Calligraphy medium", "Hexagon large", "Hexagon medium", "Hexagon small")


def folder():
    return paths.content_path(DIR)


# ---------------------------------------------------------------- reading the app

def _blobs(data):
    """The program file and every Qt resource packed in it (a 4-byte length, then zlib)."""
    yield data
    for m in re.finditer(rb"\x78[\x01\x5e\x9c\xda]", data):
        i = m.start()
        n = int.from_bytes(data[i - 4:i], "big") if i >= 4 else 0
        if 32 <= n <= 4_000_000:
            try:
                out = zlib.decompressobj().decompress(data[i:i + n + 4096], n + 1)
            except zlib.error:
                continue
            if len(out) == n:
                yield out


def _json_at(buf, start):
    """The balanced {...} beginning at `start`, or None."""
    depth, i, instr, esc = 0, start, False, False
    while i < len(buf) and i - start < 2_000_000:
        c = buf[i]
        if instr:
            if esc:
                esc = False
            elif c == 0x5C:
                esc = True
            elif c == 0x22:
                instr = False
        elif c == 0x22:
            instr = True
        elif c == 0x7B:
            depth += 1
        elif c == 0x7D:
            depth -= 1
            if depth == 0:
                return buf[start:i + 1]
        i += 1
    return None


def _icon_paths(font_bytes, codes):
    """Each icon code's glyph as an SVG path, in a 0..1000 box, y down -> {code: (d, viewBox)}."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    f = TTFont(io.BytesIO(font_bytes))
    cmap, gs = f.getBestCmap(), f.getGlyphSet()
    asc, upm = f["hhea"].ascent, f["head"].unitsPerEm
    out = {}
    for code in codes:
        g = cmap.get(ord(code))
        if not g:
            continue
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (1, 0, 0, -1, 0, asc)))          # y down, top at 0
        out[code] = (pen.getCommands(), "0 0 %d %d" % (gs[g].width or upm, upm))
    return out


def extract(dest=None, programs=None):
    """Read the templates out of the first desktop app found into `dest` (the content folder's rm-page-templates).
    -> the number of portrait templates written (0 when there is no app, or it holds none)."""
    import mmap
    from fontTools.ttLib import TTFont
    dest = dest or folder()
    for exe in programs or fonts.app_programs():
        if not os.path.isfile(exe):
            continue
        with open(exe, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            data = bytes(mm)
        index, defs, icon_font = None, {}, None
        for b in _blobs(data):
            if index is None and b.lstrip()[:1] == b"{" and b'"templates"' in b[:300]:
                try:
                    index = json.loads(b)["templates"]
                except (ValueError, KeyError):
                    pass
            for m in re.finditer(rb'\{\s*"name"\s*:', b):
                j = _json_at(b, m.start())
                if not j or b'"items"' not in j:
                    continue
                try:
                    t = json.loads(j)
                except ValueError:
                    continue
                if t.get("orientation", "portrait") == "portrait":
                    defs.setdefault(t["name"], t)
            if icon_font is None and b[:4] == b"\x00\x01\x00\x00" and len(b) < 2_000_000:
                try:
                    f = TTFont(io.BytesIO(b), lazy=True)
                    if (f["name"].getDebugName(1) or "").lower() == "icomoon" and 0xE9FE in f.getBestCmap():
                        icon_font = b
                except Exception:
                    pass
        if not index:
            continue
        entries = [t for t in index if not t.get("landscape")]
        icons = _icon_paths(icon_font, [t.get("iconCode") for t in entries if t.get("iconCode")]) if icon_font else {}
        os.makedirs(os.path.join(dest, "defs"), exist_ok=True)
        out = []
        for t in entries:
            d = defs.get(ALIAS.get(t["name"], t["name"]))
            if d is not None:
                paths.write_json_atomic(os.path.join(dest, "defs", t["filename"] + ".json"), d)
            icon = icons.get(t.get("iconCode"))
            out.append({"name": t["name"], "file": t["filename"], "categories": t.get("categories") or [],
                        "icon": {"d": icon[0], "viewBox": icon[1]} if icon else None,
                        "drawn": "blank" if t["name"] == "Blank" else ("definition" if d is not None else "app")})
        paths.write_json_atomic(os.path.join(dest, "index.json"), {"templates": out})
        return len(out)
    return 0


# ---------------------------------------------------------------- every template there is

def catalog(mirror=None):
    """Every portrait template: the app's (read by extract) and the library's rM Methods, in one list by name with
    Blank first, as the tablet's picker lists them -> [{name, file, source: default|methods, icon, drawn}]."""
    out = []
    try:
        with open(os.path.join(folder(), "index.json"), encoding="utf-8") as f:
            out = [dict(t, source="default") for t in json.load(f)["templates"]]
    except (OSError, ValueError, KeyError):
        pass
    import glob
    mirror = mirror or paths.mirror_dir()
    for p in glob.glob(os.path.join(mirror, "*.template")):
        try:
            with open(p, encoding="utf-8") as f:
                t = json.load(f)
        except (OSError, ValueError):
            continue
        if t.get("orientation", "portrait") != "portrait":
            continue
        out.append({"name": t.get("name") or "Template", "file": os.path.basename(p)[:-9], "categories": t.get("categories") or [],
                    "source": "methods", "icon": {"svg": t.get("iconData")} if t.get("iconData") else None, "drawn": "definition"})
    out.sort(key=lambda t: (t["name"] != "Blank", t["name"].lower()))
    return out


def definition(entry, mirror=None):
    """A catalog entry's definition, or None (Blank, and those the app draws in its own code)."""
    try:
        if entry.get("source") == "methods":
            with open(os.path.join(mirror or paths.mirror_dir(), entry["file"] + ".template"), encoding="utf-8") as f:
                return json.load(f)
        with open(os.path.join(folder(), "defs", entry["file"] + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, KeyError):
        return None


# ---------------------------------------------------------------- the definitions' formulas

_TOK = re.compile(r"\s*(?:(\d+\.\d*|\.\d+|\d+)|([A-Za-z_][A-Za-z0-9_]*)|(<=|>=|==|!=|&&|\|\||[-+*/%()?:<>!]))")


class Formula(object):
    """A definition's formula: numbers, names, + - * / %, comparisons, && || !, ?:, parentheses."""

    def __init__(self, text):
        self.toks, pos = [], 0
        text = str(text)
        while pos < len(text):
            m = _TOK.match(text, pos)
            if not m or m.end() == pos:
                if text[pos:].strip():
                    raise ValueError("cannot read %r" % text)
                break
            num, name, op = m.groups()
            self.toks.append(("n", float(num)) if num else ("v", name) if name else ("o", op))
            pos = m.end()

    def value(self, env):
        self.i, self.env = 0, env
        v = self._ternary()
        return v

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else ("e", None)

    def _take(self, op=None):
        t = self._peek()
        if op is not None and t != ("o", op):
            raise ValueError("expected %s" % op)
        self.i += 1
        return t

    def _ternary(self):
        c = self._or()
        if self._peek() == ("o", "?"):
            self._take("?")
            a = self._ternary()
            self._take(":")
            b = self._ternary()
            return a if c else b
        return c

    def _or(self):
        v = self._and()
        while self._peek() == ("o", "||"):
            self._take()
            r = self._and()
            v = 1.0 if (v or r) else 0.0
        return v

    def _and(self):
        v = self._cmp()
        while self._peek() == ("o", "&&"):
            self._take()
            r = self._cmp()
            v = 1.0 if (v and r) else 0.0
        return v

    def _cmp(self):
        v = self._add()
        while self._peek()[0] == "o" and self._peek()[1] in ("<", ">", "<=", ">=", "==", "!="):
            op = self._take()[1]
            r = self._add()
            v = 1.0 if {"<": v < r, ">": v > r, "<=": v <= r, ">=": v >= r, "==": v == r, "!=": v != r}[op] else 0.0
        return v

    def _add(self):
        v = self._mul()
        while self._peek() in (("o", "+"), ("o", "-")):
            op = self._take()[1]
            r = self._mul()
            v = v + r if op == "+" else v - r
        return v

    def _mul(self):
        v = self._unary()
        while self._peek() in (("o", "*"), ("o", "/"), ("o", "%")):
            op = self._take()[1]
            r = self._unary()
            # the remainder as the app computes it (C and JavaScript: the sign of the dividend), not Python's floored one
            v = v * r if op == "*" else (v / r if r else 0.0) if op == "/" else (math.fmod(v, r) if r else 0.0)
        return v

    def _unary(self):
        t = self._peek()
        if t == ("o", "-"):
            self._take()
            return -self._unary()
        if t == ("o", "!"):
            self._take()
            return 0.0 if self._unary() else 1.0
        if t == ("o", "("):
            self._take()
            v = self._ternary()
            self._take(")")
            return v
        self._take()
        if t[0] == "n":
            return t[1]
        if t[0] == "v":
            if t[1] not in self.env:
                raise ValueError("unknown name %r" % t[1])
            return float(self.env[t[1]])
        raise ValueError("unexpected %r" % (t,))


def _num(v, env):
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return Formula(v).value(env)


# ---------------------------------------------------------------- drawing a definition

def svg(defn, width, height, font="sans-serif"):
    """The template drawn on a `width` x `height` page, in page units, as SVG: black lines on nothing, for under a
    page's ink. Blank or None -> an empty drawing."""
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (width, height, width, height)]
    if defn:
        # the names the app supplies: the page's size, and its origin (x 0 is the page's middle in its own units)
        env = {"templateWidth": float(width), "templateHeight": float(height), "paperOriginX": width / 2.0, "paperOriginY": 0.0}
        for c in defn.get("constants") or []:
            for k, v in c.items():
                try:
                    env[k] = _num(v, env)
                except ValueError:
                    pass
        _items(defn.get("items") or [], 0.0, 0.0, float(width), float(height), env, out, font, width, height)
    out.append("</svg>")
    return "".join(out)


def _repeat(spec, start, size, limit, env):
    """Where a group's copies begin along one axis: a count, "down"/"right" to the page's end, "up"/"left" to its
    start, "infinite" both ways, covering the page."""
    if size <= 0.5:
        return [start]
    if spec is None:
        return [start]
    if isinstance(spec, str) and spec in ("down", "right"):
        n = int(max(0.0, limit - start) // size) + 1
        return [start + k * size for k in range(min(n, 4000))]
    if isinstance(spec, str) and spec in ("up", "left"):
        n = int(max(0.0, start) // size) + 1
        return [start - k * size for k in range(min(n, 4000))]
    if spec == "infinite":
        first = start - (int(start // size) + 1) * size
        n = int((limit - first) // size) + 2
        return [first + k * size for k in range(min(n, 4000))]
    try:
        n = int(round(_num(spec, env)))
    except ValueError:
        n = 1
    return [start + k * size for k in range(max(0, min(n, 4000)))]


def _items(items, ox, oy, pw, ph, env, out, font, W, H):
    for it in items:
        kind = it.get("type")
        local = dict(env, parentWidth=pw, parentHeight=ph)
        try:
            if kind == "group":
                bb = it.get("boundingBox") or {}
                x = ox + _num(bb.get("x", 0), local)
                y = oy + _num(bb.get("y", 0), local)
                w = _num(bb.get("width", pw), local)
                h = _num(bb.get("height", ph), local)
                rep = it.get("repeat") or {}
                for gy in _repeat(rep.get("rows"), y, h, H, local):
                    for gx in _repeat(rep.get("columns"), x, w, W, local):
                        _items(it.get("children") or [], gx, gy, w, h, env, out, font, W, H)
            elif kind == "path":
                d, data, k = [], it.get("data") or [], 0
                arity = {"M": 2, "L": 2, "C": 6, "Q": 4, "Z": 0}
                while k < len(data):
                    cmd = data[k]
                    k += 1
                    n = arity.get(cmd, 0)
                    vals = [_num(v, local) for v in data[k:k + n]]
                    k += n
                    pts = ["%.2f %.2f" % (ox + vals[j], oy + vals[j + 1]) for j in range(0, n, 2)]
                    d.append(cmd + " ".join(pts))
                sw = float(it.get("strokeWidth", 1) or 0)
                fill = it.get("fillColor")
                out.append('<path d="%s" fill="%s" stroke="%s" stroke-width="%.2f"/>' % (
                    " ".join(d), _color(fill) if fill else "none", _color(it.get("strokeColor") or "#000000") if sw else "none", sw))
            elif kind == "text":
                pos = it.get("position") or {}
                size = _num(it.get("fontSize", 32), local)
                raw = str(it.get("text") or "")
                local["textWidth"] = _text_width(raw, size)       # a name the app supplies: this text's own width
                x, y = ox + _num(pos.get("x", 0), local), oy + _num(pos.get("y", 0), local)
                text = raw.replace("&", "&amp;").replace("<", "&lt;")
                out.append('<text x="%.2f" y="%.2f" font-size="%.2f" font-family="%s" dominant-baseline="hanging">%s</text>'
                           % (x, y, size, font, text))
        except ValueError:
            continue


def _text_width(text, size):
    """A text's width at `size`: measured in the tablet's own sans when it is installed, else about half an em a
    letter."""
    p = paths.font_file("reMarkableSans-Regular")
    if p:
        try:
            from PIL import ImageFont
            return float(ImageFont.truetype(p, max(1, int(round(size)))).getlength(text))
        except OSError:
            pass
    return 0.55 * size * len(text)


def _color(c):
    c = str(c)
    if re.fullmatch(r"#?[0-9A-Fa-f]{8}", c):              # #AARRGGBB, as Qt writes it
        h = c.lstrip("#")
        return "#" + h[2:] + h[:2]
    return c if c.startswith("#") or c.isalpha() else "#000000"
