r"""Symbols built from the installed face: fractions (½ ¾ ⅛ ...), superscript and subscript digits, and the signs an
answer reaches for (≈ ± × ÷ √ ∞ π µ). The same unit grid as lettering: baseline y=0, cap height 1.0, x-height 0.60,
descender -0.28, y UP.

A FRACTION IS ONE GLYPH: a small numerator up, a slash, a small denominator down, drawn with the face's own digits.
Folded to ASCII, "6½–7" was lettered "61/2-7" -- sixty-one halves -- and "¾" came out "34", its fraction slash
dropped. "≈" had neither a glyph nor a fold, so it vanished, and the meaning with it ("≈ 40 minutes").

    install()        # after serif.install() and accents.install(); lettering does all three on import
"""
import math
import unicodedata

from paperdaemon.pipeline.draw import lettering as T

SMALL = 0.56          # a fraction's, a superscript's and a subscript's digits, of the face's own size
UP = 0.44             # a numerator's and a superscript's baseline: their tops reach the cap line
DOWN = -0.12          # a subscript's baseline

FRACTIONS = "½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅐⅛⅜⅝⅞⅑⅒"
SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾"
SUBSCRIPTS = "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎"


def _ink(polys):
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)


def _shift(polys, dx=0.0, dy=0.0):
    return [[(x + dx, y + dy) for x, y in p] for p in polys]


def _small(G, text, x, base):
    """`text` in the face's own glyphs at SMALL size, from x on `base` -> (strokes, the x after it)."""
    out = []
    for c in text:
        adv, polys = G[c]
        out += [[(x + px * SMALL, base + py * SMALL) for px, py in p] for p in polys]
        x += adv * SMALL
    return out, x


def fraction(G, num, den):
    """A fraction as one glyph -> (advance, strokes), or None when the face lacks one of its digits."""
    if not num or not den or any(c not in G for c in num + den):
        return None
    top, x = _small(G, num, 0.02, UP)
    slash = [[(x - 0.10, 0.0), (x + 0.22, 1.0)]]
    bottom, end = _small(G, den, x + 0.10, 0.0)
    return (end + 0.04, top + slash + bottom)


def _placed(G, text, base):
    if not text or any(c not in G for c in text):
        return None
    polys, end = _small(G, text, 0.02, base)
    return (end + 0.04, polys)


def _signs(G):
    out = {}
    if "~" in G:                                         # two of the face's waves, as "=" stacks two lines
        adv, wave = G["~"]
        mid = (_ink(wave)[1] + _ink(wave)[3]) / 2.0
        out["≈"] = (adv, _shift(wave, dy=0.46 - mid) + _shift(wave, dy=0.25 - mid))
    if "+" in G:                                         # the face's plus, raised, over a bar its width
        adv, plus = G["+"]
        x0, y0, x1, _y1 = _ink(plus)
        out["±"] = (adv, _shift(plus, dy=0.20 - y0) + [[(x0, 0.06), (x1, 0.06)]])
    out["×"] = (0.54, [[(0.08, 0.14), (0.46, 0.56)], [(0.08, 0.56), (0.46, 0.14)]])
    out["÷"] = (0.56, [[(0.06, 0.35), (0.50, 0.35)], T._dot(0.28, 0.55), T._dot(0.28, 0.10)])
    out["√"] = (0.84, [[(0.02, 0.42), (0.13, 0.50), (0.30, -0.02), (0.50, 1.04), (0.82, 1.04)]])
    loop = []
    for k in range(33):                                  # a lemniscate, two loops on the x-height's middle
        t = 2.0 * math.pi * k / 32.0
        d = 1.0 + math.sin(t) ** 2
        loop.append((0.45 + 0.42 * math.cos(t) / d, 0.32 + 0.42 * math.sin(t) * math.cos(t) / d))
    out["∞"] = (0.90, [loop])
    out["π"] = (0.68, [[(0.02, 0.54), (0.12, 0.60), (0.64, 0.60)], [(0.20, 0.60), (0.17, 0.0)],
                       [(0.48, 0.60), (0.48, 0.08), (0.57, 0.0)]])
    if "u" in G:                                         # the face's u with a descender at its left stem
        adv, u = G["u"]
        x0 = _ink(u)[0]
        out["µ"] = (adv, u + [[(x0, 0.30), (x0, -0.28)]])
        out["μ"] = out["µ"]
    return out


def install():
    """Add the symbols to the installed face. -> how many."""
    G = T.G
    made = _signs(G)
    for ch in FRACTIONS:
        num, _, den = unicodedata.normalize("NFKD", ch).partition("⁄")
        g = fraction(G, num, den)
        if g:
            made[ch] = g
    for chars, base in ((SUPERSCRIPTS, UP), (SUBSCRIPTS, DOWN)):
        for ch in chars:
            g = _placed(G, unicodedata.normalize("NFKD", ch), base)
            if g:
                made[ch] = g
    made = {ch: g for ch, g in made.items() if ch not in G}
    G.update(made)
    T.TALL.update(made)                                  # a line without them keeps its baseline exactly
    return len(made)
