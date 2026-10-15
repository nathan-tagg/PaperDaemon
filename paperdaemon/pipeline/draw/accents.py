r"""The accented and extended Latin letters (Latin-1 and Latin Extended-A), built from the installed face.

An accented letter is its base letter as the face draws it, plus a mark: `é` is this face's `e` and an acute, so
when the face changes (serif.install) the accented letters follow. The few letters that are not a base and a mark
(ß æ œ ø ð þ ł đ ħ ı ŋ ĳ ſ ĸ ...) are drawn here in the same unit grid: baseline y=0, cap height 1.0, x-height
0.60, descender -0.28, y UP.

THE MARKS SIT ABOVE THE CAP LINE on a capital, which is where they belong and is taller than anything the ASCII
face reaches. So these letters are kept out of lettering.ascent()'s base measure (TALL): a line of plain text keeps
exactly the first baseline it always had, and only a line that has an accented capital in it is set lower.

    install()        # after serif.install(); lettering does both on import
"""
import unicodedata

from paperdaemon.pipeline.draw import lettering as T

GAP = 0.09            # between the letter's top and its mark
MARK = 0.15           # a mark's height
DOT = 0.035           # a dot's radius, as lettering._dot draws one

# Latvian and Romanian write a comma below where Unicode decomposes to a cedilla; `ģ` takes it turned, above
_COMMA_BELOW = set("ĢĶķĻļŅņŖŗ")
# Czech and Slovak write the caron of a tall lowercase letter (and of Slovak L) as an apostrophe beside it
_APOSTROPHE = set("ďľťĽ")


def _ink(strokes):
    xs = [x for p in strokes for x, _ in p]
    ys = [y for p in strokes for _, y in p]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)


def _shift(strokes, dx=0.0, dy=0.0):
    return [[(x + dx, y + dy) for x, y in p] for p in strokes]


def _dot(x, y):
    return T._dot(x, y)


def _mark(name, cx, top, right=None):
    """The strokes of one mark centered on `cx`, sitting above `top` (below the baseline for the hooks)."""
    b = top + GAP
    h = MARK
    if name == "grave":
        return [[(cx - 0.08, b + h), (cx + 0.05, b + 0.02)]]
    if name == "acute":
        return [[(cx - 0.05, b + 0.02), (cx + 0.08, b + h)]]
    if name == "circumflex":
        return [[(cx - 0.12, b + 0.01), (cx, b + h), (cx + 0.12, b + 0.01)]]
    if name == "caron":
        return [[(cx - 0.12, b + h), (cx, b + 0.01), (cx + 0.12, b + h)]]
    if name == "tilde":
        return [[(cx - 0.15, b + 0.03), (cx - 0.09, b + 0.10), (cx - 0.03, b + 0.09), (cx + 0.03, b + 0.05),
                 (cx + 0.09, b + 0.04), (cx + 0.15, b + 0.11)]]
    if name == "macron":
        return [[(cx - 0.14, b + 0.07), (cx + 0.14, b + 0.07)]]
    if name == "breve":
        return [T._arc(cx, b + 0.12, 0.12, 0.10, 180, 360, 12)]
    if name == "dot":
        return [_dot(cx, b + 0.06)]
    if name == "diaeresis":
        return [_dot(cx - 0.11, b + 0.06), _dot(cx + 0.11, b + 0.06)]
    if name == "ring":
        return [T._arc(cx, b + 0.08, 0.075, 0.075, 0, 360, 16)]
    if name == "double_acute":
        return [[(cx - 0.12, b + 0.02), (cx - 0.03, b + h)], [(cx + 0.03, b + 0.02), (cx + 0.12, b + h)]]
    if name == "cedilla":
        return [[(cx, 0.0), (cx, -0.07), (cx + 0.07, -0.11), (cx + 0.06, -0.19), (cx - 0.05, -0.21)]]
    if name == "ogonek":
        rx = cx if right is None else right
        return [[(rx, 0.0), (rx - 0.08, -0.09), (rx - 0.05, -0.19), (rx + 0.05, -0.19)]]
    if name == "comma_below":
        return [[(cx + 0.02, -0.07), (cx - 0.04, -0.22)]]
    if name == "comma_above":
        return [[(cx + 0.03, b + h), (cx - 0.02, b + 0.03)]]
    raise KeyError(name)


_MARKS = {"̀": "grave", "́": "acute", "̂": "circumflex", "̌": "caron", "̃": "tilde",
          "̄": "macron", "̆": "breve", "̇": "dot", "̈": "diaeresis", "̊": "ring",
          "̋": "double_acute", "̧": "cedilla", "̨": "ogonek"}


def _compose(ch, G):
    """`ch` as its base letter plus its mark, or None when it does not decompose into ones we have."""
    parts = unicodedata.normalize("NFD", ch)
    base, marks = parts[0], parts[1:]
    if len(marks) != 1 or marks not in _MARKS:
        return None
    name = _MARKS[marks]
    if base == "i" and name not in ("ogonek",):
        base = "ı"                                  # ì í î ï ĩ ī ĭ: the dotless i under the mark
    if base == "j":
        base = "ȷ"
    if base not in G:
        return None
    adv, strokes = G[base]
    x0, _y0, x1, top = _ink(strokes)
    cx = (x0 + x1) / 2.0
    if ch in _APOSTROPHE:                                # ď ľ ť: an apostrophe after the stem, at its top
        stem = max(x for p in strokes for x, y in p if y >= top - 0.05)
        extra = [[(stem + 0.10, top), (stem + 0.07, top - 0.16)]]
        return (adv + 0.08, strokes + extra)
    if ch in _COMMA_BELOW:
        extra = _mark("comma_below", cx, top)
    elif ch in ("ģ",):
        extra = _mark("comma_above", cx, top)
    elif name == "ogonek":
        extra = _mark("ogonek", cx, top, right=x1 - 0.06 if base not in "iI" else cx + 0.04)
    else:
        extra = _mark(name, cx, top)
    return (adv, [list(p) for p in strokes] + extra)


def _without_dot(glyph):
    """`i` or `j` with its dot taken off: the polylines that come down to the x-height or below."""
    adv, strokes = glyph
    return (adv, [p for p in strokes if min(y for _, y in p) < 0.5])


def _slash(strokes, a, b):
    return [list(p) for p in strokes] + [[a, b]]


def _specials(G):
    """The letters that are not a base and a mark, drawn in this face's grid."""
    out = {}
    out["ı"] = _without_dot(G["i"])                                      # ı
    out["ȷ"] = _without_dot(G["j"])                                      # ȷ
    a, e, o, O, E = G["a"], G["e"], G["o"], G["O"], G["E"]
    out["æ"] = (a[0] + e[0] - 0.10, [list(p) for p in a[1]] + _shift(e[1], a[0] - 0.10))
    out["œ"] = (o[0] + e[0] - 0.10, [list(p) for p in o[1]] + _shift(e[1], o[0] - 0.10))
    out["Œ"] = (O[0] + E[0] - 0.16, [list(p) for p in O[1]] + _shift(E[1], O[0] - 0.16))
    out["Æ"] = (1.00, [[(0, 0), (0.44, 1.0), (1.00, 1.0)], [(0.44, 1.0), (0.44, 0), (1.00, 0)],
                       [(0.44, 0.52), (0.90, 0.52)], [(0.16, 0.37), (0.44, 0.37)]])
    ox0, oy0, ox1, oy1 = _ink(o[1])
    out["ø"] = (o[0], _slash(o[1], (ox0 - 0.02, oy0 - 0.06), (ox1 + 0.02, oy1 + 0.06)))
    Ox0, Oy0, Ox1, Oy1 = _ink(O[1])
    out["Ø"] = (O[0], _slash(O[1], (Ox0 - 0.02, Oy0 - 0.06), (Ox1 + 0.02, Oy1 + 0.06)))
    # ß: a tall stem that turns over the top into two stacked bowls on the right
    out["ß"] = (0.60, [T._cat([(0.0, 0.0), (0.0, 0.76)], T._arc(0.22, 0.76, 0.22, 0.24, 180, 0),
                              [(0.44, 0.76)], T._arc(0.30, 0.76, 0.14, 0.14, 0, -90), [(0.24, 0.62)],
                              T._arc(0.30, 0.30, 0.26, 0.32, 90, -110), [(0.14, 0.03)])])
    D = G["D"]
    out["Ð"] = (D[0] + 0.10, _shift(D[1], 0.10) + [[(0.0, 0.50), (0.32, 0.50)]])
    out["Đ"] = out["Ð"]
    d = G["d"]
    dx0, _, dx1, dtop = _ink(d[1])
    out["đ"] = (d[0] + 0.06, [list(p) for p in d[1]] + [[(dx1 - 0.18, dtop - 0.14), (dx1 + 0.10, dtop - 0.14)]])
    # ð: a round bowl whose back rises and leans over, crossed near the top
    out["ð"] = (0.60, [T._arc(0.30, 0.30, 0.30, 0.30, 0, 360),
                       T._cat([(0.60, 0.30), (0.58, 0.58), (0.48, 0.80), (0.30, 0.98)]),
                       [(0.22, 0.78), (0.56, 0.94)]])
    out["þ"] = (0.60, [[(0, 1.0), (0, -0.28)], T._arc(0.30, 0.30, 0.30, 0.30, 0, 360)])
    out["Þ"] = (0.60, [[(0, 0), (0, 1.0)], T._cat([(0, 0.80), (0.34, 0.80)],
                                                  T._arc(0.34, 0.51, 0.22, 0.29, 90, -90), [(0, 0.22)])])
    h = G["h"]
    hx0, _, _, htop = _ink(h[1])
    out["ħ"] = (h[0] + 0.08, _shift(h[1], 0.08) + [[(hx0, htop - 0.16), (hx0 + 0.30, htop - 0.16)]])
    H = G["H"]
    out["Ħ"] = (H[0] + 0.12, _shift(H[1], 0.06) + [[(0.0, 0.76), (H[0] + 0.12, 0.76)]])
    l, L = G["l"], G["L"]
    lx0, _, lx1, _ = _ink(l[1])
    lc = (lx0 + lx1) / 2.0 + 0.06
    out["ł"] = (l[0] + 0.12, _shift(l[1], 0.06) + [[(lc - 0.14, 0.40), (lc + 0.14, 0.62)]])
    out["Ł"] = (L[0] + 0.06, _shift(L[1], 0.06) + [[(0.0, 0.38), (0.30, 0.60)]])
    out["Ŀ"] = (L[0], [list(p) for p in L[1]] + [_dot(0.36, 0.50)])
    out["ŀ"] = (l[0] + 0.16, [list(p) for p in l[1]] + [_dot(lx1 + 0.14, 0.42)])
    n = G["n"]
    nx0, _, nx1, _ = _ink(n[1])
    out["ŋ"] = (n[0], [list(p) for p in n[1]] + [[(nx1, 0.0), (nx1, -0.14), (nx1 - 0.10, -0.26), (nx1 - 0.24, -0.25)]])
    N = G["N"]
    out["Ŋ"] = (N[0], [list(p) for p in N[1]] + [[(N[0], 0.0), (N[0], -0.12), (N[0] - 0.10, -0.24),
                                                    (N[0] - 0.26, -0.22)]])
    i, j, I, J = G["i"], G["j"], G["I"], G["J"]
    out["ĳ"] = (i[0] + j[0] - 0.04, [list(p) for p in i[1]] + _shift(j[1], i[0] - 0.04))
    out["Ĳ"] = (I[0] + J[0] + 0.02, [list(p) for p in I[1]] + _shift(J[1], I[0] + 0.02))
    out["ĸ"] = (0.52, [[(0, 0), (0, 0.60)], [(0.50, 0.60), (0.04, 0.24)], [(0.17, 0.34), (0.52, 0)]])
    Tt, t = G["T"], G["t"]
    out["Ŧ"] = (Tt[0], [list(p) for p in Tt[1]] + [[(Tt[0] / 2.0 - 0.14, 0.50), (Tt[0] / 2.0 + 0.14, 0.50)]])
    tx0, _, _, _ = _ink(t[1])
    stem = min(x for p in t[1] for x, y in p if y > 0.70)
    out["ŧ"] = (t[0], [list(p) for p in t[1]] + [[(stem - 0.11, 0.34), (stem + 0.11, 0.34)]])
    out["ſ"] = (0.40,[T._cat([(0.10, 0.0), (0.10, 0.80)], T._arc(0.26, 0.80, 0.16, 0.18, 180, 30))])
    apostrophe = G.get("'") or (0.18, [[(0.09, 1.0), (0.07, 0.78)]])
    out["ŉ"] = (apostrophe[0] + n[0], [list(p) for p in apostrophe[1]] + _shift(n[1], apostrophe[0]))
    out["×"] = (0.56, [[(0.08, 0.14), (0.48, 0.54)], [(0.08, 0.54), (0.48, 0.14)]])
    out["÷"] = (0.56, [[(0.04, 0.34), (0.52, 0.34)], _dot(0.28, 0.58), _dot(0.28, 0.10)])
    for upright, turned in (("!", "¡"), ("?", "¿")):
        if upright in G:
            adv, strokes = G[upright]
            out[turned] = (adv, T._rot180(strokes, adv / 2.0, 0.5 - 0.14))
    return out


def install():
    """Add the extended letters to the installed face. -> how many."""
    G = T.G
    made = _specials(G)
    G.update(made)
    for code in list(range(0xC0, 0x180)):
        ch = chr(code)
        if ch in G or not unicodedata.category(ch).startswith("L"):
            continue
        g = _compose(ch, G)
        if g:
            G[ch] = g
            made[ch] = g
    T.TALL.update(made)
    return len(made)
