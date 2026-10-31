"""A PICTURE LAID OUT IN PAGE UNITS, DRAWN AT TWICE THE TABLET'S RESOLUTION.

A picture PaperDaemon sends to the tablet is made at `images.PICTURE_K` pixels a page unit. The game pages, the chat
and the rest were laid out in pixels, one a unit: rather than every place and size in them changing, they draw
through `Draw` -- every place, length, width and face given in page units as before, drawn `k` pixels a unit -- and
measure through it in page units (`textlength`, `textbbox`: the same numbers the layout always had). `canvas` makes
the picture, `paste` puts a picture into a box given in page units.
"""
from PIL import Image, ImageDraw, ImageFont

_faces = {}


def face(font, k):
    """The same face at k times its size (one made once)."""
    if k == 1 or not isinstance(font, ImageFont.FreeTypeFont):
        return font
    key = (font.path, font.size, getattr(font, "index", 0), k)
    if key not in _faces:
        _faces[key] = font.font_variant(size=int(round(font.size * k)))
    return _faces[key]


def _xy(v, k):
    if isinstance(v, (int, float)):
        return v * k
    return type(v)(_xy(x, k) for x in v) if isinstance(v, tuple) else [_xy(x, k) for x in v]


def canvas(w, h, bg="white", mode="RGB", k=None):
    """A picture w x h page units, k pixels a unit (PICTURE_K) -> (image, Draw)."""
    if k is None:
        from paperdaemon.pipeline.page.images import PICTURE_K as k
    im = Image.new(mode, (int(round(w * k)), int(round(h * k))), bg)
    return im, Draw(im, k)


def paste(im, pic, xy, size=None, k=None, mask=None):
    """`pic` into `im` at xy (page units), `size` page units (default: its own pixels, one a unit) -> None. A picture
    with transparency is laid over (mask it itself, as PIL's paste does)."""
    if k is None:
        from paperdaemon.pipeline.page.images import PICTURE_K as k
    w, h = size if size is not None else pic.size
    w, h = int(round(w * k)), int(round(h * k))
    if pic.size != (w, h):
        pic = pic.resize((w, h), Image.LANCZOS)
    at = (int(round(xy[0] * k)), int(round(xy[1] * k)))
    if mask is True:
        im.paste(pic, at, pic)
    else:
        im.paste(pic, at)


class Draw:
    """ImageDraw on a picture k pixels a page unit, spoken to in page units."""

    def __init__(self, im, k):
        self.im, self.k, self._d = im, k, ImageDraw.Draw(im)

    @property
    def width(self):                       # the picture's size in page units
        return self.im.width / self.k

    @property
    def height(self):
        return self.im.height / self.k

    def _w(self, width):
        return max(1, int(round(width * self.k))) if width else width

    # measured in page units: the face as laid out
    def textlength(self, text, font=None, **kw):
        return self._d.textlength(text, font=font, **kw)

    def textbbox(self, xy, text, font=None, **kw):
        return self._d.textbbox(xy, text, font=font, **kw)

    def multiline_textbbox(self, xy, text, font=None, spacing=4, **kw):
        return self._d.multiline_textbbox(xy, text, font=font, spacing=spacing, **kw)

    # drawn k pixels a unit
    def text(self, xy, text, fill=None, font=None, stroke_width=0, **kw):
        self._d.text(_xy(xy, self.k), text, fill=fill, font=face(font, self.k), stroke_width=int(round(stroke_width * self.k)), **kw)

    def multiline_text(self, xy, text, fill=None, font=None, spacing=4, stroke_width=0, **kw):
        self._d.multiline_text(_xy(xy, self.k), text, fill=fill, font=face(font, self.k), spacing=spacing * self.k,
                               stroke_width=int(round(stroke_width * self.k)), **kw)

    def line(self, xy, fill=None, width=0, joint=None):
        self._d.line(_xy(xy, self.k), fill=fill, width=self._w(width), joint=joint)

    def rectangle(self, xy, fill=None, outline=None, width=1):
        self._d.rectangle(_xy(xy, self.k), fill=fill, outline=outline, width=self._w(width))

    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, **kw):
        self._d.rounded_rectangle(_xy(xy, self.k), radius * self.k, fill=fill, outline=outline, width=self._w(width), **kw)

    def ellipse(self, xy, fill=None, outline=None, width=1):
        self._d.ellipse(_xy(xy, self.k), fill=fill, outline=outline, width=self._w(width))

    def polygon(self, xy, fill=None, outline=None, width=1):
        self._d.polygon(_xy(xy, self.k), fill=fill, outline=outline, width=self._w(width))

    def arc(self, xy, start, end, fill=None, width=1):
        self._d.arc(_xy(xy, self.k), start, end, fill=fill, width=self._w(width))

    def pieslice(self, xy, start, end, fill=None, outline=None, width=1):
        self._d.pieslice(_xy(xy, self.k), start, end, fill=fill, outline=outline, width=self._w(width))
