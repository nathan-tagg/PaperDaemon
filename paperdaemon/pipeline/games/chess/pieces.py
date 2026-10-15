"""PaperDaemon's chess pieces, drawn here as vector shapes, and rendered to pictures at first use.

Each piece is a few filled outlines on a 100 x 100 grid: a plinth, a body, and the piece's own top. White
pieces are near-white with a black outline, so they read on the board's near-white squares; black pieces are
near-black, with their details drawn in near-white, and stand out on its green ones. The pictures are cached in the data folder, by the drawing's version.
"""
import os

VERSION = 2
INK = "#111111"
STROKE = 3.6

_PLINTH = ("M 23 91 L 77 91 Q 80 91 80 88 L 80 85 Q 80 81 76 81 L 24 81 Q 20 81 20 85 L 20 88 "
           "Q 20 91 23 91 Z")
_SHAPES = {
    "P": [("path", "M 31 81 C 35 68 42 60 44 53 L 56 53 C 58 60 65 68 69 81 Z"),
          ("path", "M 38 52 Q 38 47 43 47 L 57 47 Q 62 47 62 52 Q 62 55 59 55 L 41 55 Q 38 55 38 52 Z"),
          ("circle", (50, 33, 13))],
    "R": [("path", "M 30 81 L 34 47 L 66 47 L 70 81 Z"),
          ("path", "M 27 47 L 27 19 L 36 19 L 36 27 L 45 27 L 45 19 L 55 19 L 55 27 L 64 27 L 64 19 "
                   "L 73 19 L 73 47 Z"),
          ("detail", "M 31 39 L 69 39")],
    "B": [("path", "M 32 81 C 36 70 40 63 42 58 L 58 58 C 60 63 64 70 68 81 Z"),
          ("path", "M 37 57 Q 37 52 42 52 L 58 52 Q 63 52 63 57 Q 63 60 60 60 L 40 60 Q 37 60 37 57 Z"),
          ("path", "M 50 15 C 35 26 33 41 40 52 L 60 52 C 67 41 65 26 50 15 Z"),
          ("circle", (50, 11, 4.6)),
          ("detail", "M 55 25 L 46 37")],
    "N": [("path", "M 31 81 L 73 81 C 75 61 71 42 63 27 L 66 13 L 57 20 L 52 10 L 47 20 "
                   "C 38 23 31 32 25 44 L 20 53 C 18 58 21 62 26 61 L 36 58 C 40 57 44 55 47 53 "
                   "C 43 61 34 69 31 81 Z"),
          ("dot", (43, 32, 2.8)),
          ("dot", (25, 54, 1.8)),
          ("detail", "M 63 29 C 68 42 70 58 69 76")],
    "Q": [("path", "M 31 81 C 35 69 38 60 40 54 L 60 54 C 62 60 65 69 69 81 Z"),
          ("path", "M 31 54 L 21 25 L 35 41 L 38 18 L 46 39 L 50 14 L 54 39 L 62 18 L 65 41 L 79 25 "
                   "L 69 54 Z"),
          ("circle", (21, 22, 4.2)), ("circle", (38, 15, 4.2)), ("circle", (50, 11, 4.2)),
          ("circle", (62, 15, 4.2)), ("circle", (79, 22, 4.2)),
          ("detail", "M 33 49 L 67 49")],
    "K": [("path", "M 31 81 C 35 69 38 60 40 55 L 60 55 C 62 60 65 69 69 81 Z"),
          ("path", "M 33 55 C 25 44 27 31 38 31 C 44 31 48 36 50 41 C 52 36 56 31 62 31 C 73 31 75 44 67 55 Z"),
          ("path", "M 47 8 L 53 8 L 53 15 L 59 15 L 59 21 L 53 21 L 53 33 L 47 33 L 47 21 L 41 21 L 41 15 "
                   "L 47 15 Z"),
          ("detail", "M 34 50 L 66 50")],
}


def svg(color, kind, size=100):
    """The piece as an SVG document `size` pixels square; color 'w' or 'b', kind one of KQRBNP."""
    fill, detail = ("#F7F7F2", INK) if color == "w" else ("#1C1C1C", "#F4F4EC")
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 100 100">' % (size, size),
           '<g stroke="%s" stroke-width="%.1f" stroke-linejoin="round" stroke-linecap="round" fill="%s">'
           % (INK, STROKE, fill),
           '<path d="%s"/>' % _PLINTH]
    for what, shape in _SHAPES[kind.upper()]:
        if what == "path":
            out.append('<path d="%s"/>' % shape)
        elif what == "circle":
            out.append('<circle cx="%s" cy="%s" r="%s"/>' % shape)
        elif what == "dot":
            out.append('<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="none"/>' % (shape + (detail,)))
        elif what == "detail":
            out.append('<path d="%s" fill="none" stroke="%s" stroke-width="%.1f"/>' % (shape, detail, STROKE * 0.8))
    out.append("</g></svg>")
    return "".join(out)


def png_path(color, kind, size):
    """The piece's picture at `size` pixels, transparent around it; drawn the first time it is asked for."""
    from paperdaemon import paths
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
