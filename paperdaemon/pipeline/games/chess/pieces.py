"""PaperDaemon's chess pieces: the "cburnett" set by Colin M.L. Burnett (CC BY-SA 3.0), recolored to the board and
rendered to pictures at first use.

The drawings are in paperdaemon/content/games/pieces/cburnett, unchanged, with their license (LICENSE.md there).
They are recolored as they are drawn: white pieces near-white with a near-black outline, so they read on the board's
near-white squares; black pieces near-black with their details in near-white, so they stand out on its green ones.
The pictures are cached in the data folder, by the drawing's version.
"""
import os

from paperdaemon import paths

VERSION = 3
FOLDER = os.path.join(paths.BUNDLED, "games", "pieces", "cburnett")
INK = "#111111"                     # every outline
FILL = {"w": "#F7F7F2", "b": "#1C1C1C"}
DETAIL = "#F4F4EC"                  # a black piece's light details


def svg(color, kind, size=100):
    """The piece as an SVG document `size` pixels square; color 'w' or 'b', kind one of KQRBNP."""
    with open(os.path.join(FOLDER, "%s%s.svg" % (color, kind.upper())), encoding="utf-8") as f:
        src = f.read()
    # the set's own colors -> the board's: an outline is black, a body white or black, a black piece's detail #ececec
    src = src.replace('stroke="#000"', 'stroke="%s"' % INK).replace('#ececec', DETAIL)
    if color == "w":
        src = src.replace('fill="#fff"', 'fill="%s"' % FILL["w"]).replace('fill="#000"', 'fill="%s"' % INK)
    else:
        src = src.replace('fill="#000"', 'fill="%s"' % FILL["b"])
    # A SHAPE WITH NO FILL OF ITS OWN is black by SVG's default (a black pawn, queen and rook name none): the root
    # gives it the piece's own fill instead. Some of the set carry a size and some do not; the root sets it.
    head = src[:src.index(">")]
    rest = src[src.index(">"):]
    for attr in (" width=", " height="):
        if attr in head:
            i = head.index(attr) + len(attr) + 1
            head = head[:head.index(attr)] + head[head.index('"', i) + 1:]
    head += ' width="%d" height="%d" fill="%s"' % (size, size, FILL[color] if color == "b" else INK)
    return head + rest


def png_path(color, kind, size):
    """The piece's picture at `size` pixels, transparent around it; drawn the first time it is asked for."""
    folder = paths.cache_dir("chess", "pieces-v%d-%d" % (VERSION, size))
    out = os.path.join(folder, "%s%s.png" % (color, kind.upper()))
    if not os.path.isfile(out):
        import vl_convert
        data = vl_convert.svg_to_png(svg(color, kind, size), scale=1.0)
        tmp = out + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, out)
    return out
