"""Ink rendered for a recognizer, not for the eye: black on white, at twice the page's scale (recognizers
miss small writing), every stroke drawn at one normalized width (accuracy depends on stroke weight more
than on looks), and a transform that maps the recognizer's boxes back onto the page."""
from dataclasses import dataclass

from PIL import Image, ImageDraw

SCALE = 2.0
PAD = 24                # page units of white around the ink
STROKE_PX = 4           # the drawn width of every stroke, in image pixels
MAX_SIDE = 10000        # Windows OCR's limit on either side of an image


@dataclass
class Transform:
    x0: float           # the page coordinate at image x = 0
    y0: float
    scale: float

    def to_page(self, box):
        """(x0, y0, x1, y1) in image pixels -> page coordinates."""
        a, b, c, d = box
        s = self.scale
        return (self.x0 + a / s, self.y0 + b / s, self.x0 + c / s, self.y0 + d / s)

    def to_image(self, x, y):
        return ((x - self.x0) * self.scale, (y - self.y0) * self.scale)


def ink_image(strokes, scale=SCALE):
    """-> (PIL image, Transform) for the ink's extent, or (None, None) when there is no ink."""
    pts = [p for s in strokes for p in s.get("points") or ()]
    if not pts:
        return None, None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0 = min(xs) - PAD, min(ys) - PAD
    w, h = (max(xs) + PAD - x0), (max(ys) + PAD - y0)
    scale = min(scale, (MAX_SIDE - 1) / max(w, h))
    tf = Transform(x0, y0, scale)
    img = Image.new("L", (max(1, int(w * scale) + 1), max(1, int(h * scale) + 1)), 255)
    draw = ImageDraw.Draw(img)
    for s in strokes:
        line = [tf.to_image(p[0], p[1]) for p in s.get("points") or ()]
        if len(line) == 1:
            x, y = line[0]
            r = STROKE_PX / 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=0)
        elif line:
            draw.line(line, fill=0, width=STROKE_PX, joint="curve")
    return img, tf
