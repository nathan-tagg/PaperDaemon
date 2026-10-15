r"""Individually drawn portraits, one folder of SVG masters per portrait set.

A look that names a `portrait_set` is drawn from <content>/games/portraits/<set>/<emotion>.svg instead of
from the generic face kit (games/faces). The masters are frozen drawings, 600 x 600 units; this module only
rescales them and lays a character's tell marks over them. A set is installed content (see paperdaemon/paths.py):
without it, face_svg raises FileNotFoundError and the caller falls back to the kit.

The `glance` and `blink` marks move or replace the eyes of a master; they find the eyes as the two
groups translated to the standard eye positions, and are skipped for a set whose masters differ.
"""
import re
from paperdaemon import paths

SET_NAME = re.compile(r"[\w.-]+")


def set_dir(name):
    if not SET_NAME.fullmatch(str(name)):
        raise ValueError("bad portrait set name %r" % (name,))
    return paths.content_path("games", "portraits", name)


def available(name):
    try:
        return paths.installed("games", "portraits", name)
    except Exception:
        return False


def face_svg(look, emotion, size=200, marks=()):
    from paperdaemon.pipeline.games import faces as F
    root = set_dir(look["portrait_set"])
    with open(root + "/" + emotion + ".svg", encoding="utf-8") as f:
        svg = f.read()
    svg = re.sub(r'width="600" height="600"', f'width="{int(size)}" height="{int(size)}"', svg, count=1)
    if not marks:
        return svg

    # Groups are local to the master's own transform, not the generic kit's anchors.
    def eyes(m):
        x, y = float(m[1]), float(m[2])
        inner = m[3]
        if 'blink' in marks:
            side = -1 if x < 100 else 1
            inner = (f'<path d="M -8 0 Q 0 5 8 0 M {side*8} 0 L {side*12} 0" '
                     'fill="none" stroke="#2B2E33" stroke-width="4" stroke-linecap="round"/>')
        if 'glance' in marks:
            x -= 2
            y += 1
        return f'<g transform="translate({x:g} {y:g})">{inner}</g>'
    svg, n = re.subn(r'<g transform="translate\((7[5-9]|12[1-5]) (101)\)">(.*?)</g>', eyes, svg)
    if n != 2 and ('blink' in marks or 'glance' in marks):
        marks = [m for m in marks if m not in ('glance', 'blink')]
    anchors = dict(lx=77, rx=123, ey=101, temple=(149, 99), ears=(49, 151, 119),
                   cheeks=((64, 126), (136, 126)), my=144, nx=100, ny=120,
                   top=40, chin=169)
    head = 'M 49 78 Q 45 142 67 155 Q 100 181 133 155 Q 155 142 151 78Z'
    overlay = F._marks([m for m in marks if m not in ('glance', 'blink')], anchors,
                       dict(look, skin='#EFD0BA', face=[]), head)
    if overlay:
        svg = svg.replace('</svg>', '<g transform="translate(12 -1) scale(.88)">' + overlay + '</g></svg>')
    return svg
