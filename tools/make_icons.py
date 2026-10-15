"""Draw PaperDaemon's application icon, the daemon's face, into shell/icons (build_app.py runs this first).

    uv run python tools/make_icons.py [--sheet PATH]

The face is the devil head the daemon signs its notes with (paperdaemon/pipeline/draw/signature.py,
devil_head: the face, two horns, two eyes and a grin), drawn in the interface's ink on its dark ground in a
rounded square. Each size is drawn on its own, with a stroke weight chosen for it, so the face still reads
at 16 px. Writes icon.ico (16 to 256 px), icon.png (512 px) and 32x32.png / 128x128.png for the Tauri shell;
--sheet also writes every size side by side, enlarged, for looking at.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "shell", "icons")

GROUND = (0x24, 0x21, 0x24, 255)     # --paper in ui/style.css
INK = (0xBD, 0xB6, 0xAA, 255)        # --ink
SS = 8                               # supersampling
# per size: the stroke weight in output pixels, the face's height as a share of the square, whether the grin
# is drawn, and whether the face is a solid silhouette with its features cut out. At 16 and 24 px an outlined
# face's brow, eyes and grin merge into stripes; a solid horned head with the eyes cut out still reads.
LOOK = {16: (1.6, 0.94, False, True), 24: (1.8, 0.90, True, True), 32: (2.0, 0.86, True, True),
        48: (2.6, 0.80, True, False), 64: (3.3, 0.78, True, False), 128: (6.0, 0.76, True, False),
        256: (10.5, 0.74, True, False), 512: (19.0, 0.74, True, False)}


def head():
    sys.path.insert(0, ROOT)
    from paperdaemon.pipeline.draw.signature import devil_head
    polys = devil_head()
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    return polys, (min(xs), min(ys), max(xs), max(ys))


def draw(size, polys, box):
    s = size * SS
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(0.22 * s), fill=GROUND)
    x0, y0, x1, y1 = box
    w, fill, grin, solid = LOOK[size]
    k = fill * s / max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    width = max(1, int(round(w * SS)))

    def stroke(p, color, wd):
        pts = [(s / 2.0 + (x - cx) * k, s / 2.0 - (y - cy) * k) for x, y in p]      # pen space is y-up
        d.line(pts, fill=color, width=wd, joint="curve")
        r = wd / 2.0
        for x, y in (pts[0], pts[-1]):                                             # round the open ends
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)
        return pts

    face, horns, eyes, mouth = polys[0], polys[1:3], polys[3:5], polys[5]
    if solid:
        d.polygon(stroke(face, INK, width), fill=INK)
        for p in horns:
            stroke(p, INK, width)
        for p in eyes + ([mouth] if grin else []):
            stroke(p, GROUND, max(1, int(round(1.0 * SS))))
    else:
        for p in [face] + horns + eyes + ([mouth] if grin else []):
            stroke(p, INK, width)
    return im.resize((size, size), Image.LANCZOS)


def write_ico(path, images):
    """An .ico holding each image as its own PNG entry, so every size keeps the drawing made for it."""
    import io
    import struct
    blobs = []
    for im in images:
        buf = io.BytesIO()
        im.save(buf, "PNG")
        blobs.append((im.width, im.height, buf.getvalue()))
    out = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    for w, h, data in blobs:
        out += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(out + b"".join(d for _w, _h, d in blobs))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sheet", help="also write every size side by side, enlarged 8x, to this PNG")
    a = ap.parse_args(argv)
    polys, box = head()
    os.makedirs(OUT, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = {n: draw(n, polys, box) for n in sizes + [512]}
    images[512].save(os.path.join(OUT, "icon.png"))
    images[32].save(os.path.join(OUT, "32x32.png"))
    images[128].save(os.path.join(OUT, "128x128.png"))
    write_ico(os.path.join(OUT, "icon.ico"), [images[n] for n in sizes])
    if a.sheet:
        big = [images[n].resize((n * 4, n * 4), Image.NEAREST) for n in (16, 24, 32, 48)]
        whole = [images[n] for n in sizes]
        w = sum(i.width for i in big) + sum(i.width for i in whole) + 20 * 12
        sheet = Image.new("RGBA", (w, max(256, 48 * 4) + 40), (128, 128, 128, 255))
        x = 10
        for im in whole + big:
            sheet.alpha_composite(im, (x, 20))
            x += im.width + 20
        sheet.save(a.sheet)
    print("icons written to %s" % os.path.normpath(OUT))


if __name__ == "__main__":
    main()
