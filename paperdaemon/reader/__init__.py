"""The handwriting reader: a page's ink in, lines of words with page-coordinate boxes out.

One interface, several engines. Each engine declares what it can do (platforms, download size, what
kind of word boxes it gives, whether it gives confidences) and whether it can run here, and says why
not when it cannot. Every engine reads on this computer; no ink or page image leaves it.

Typed text never comes through here: the host takes it from the page file, character for character.
"""
import sys
from dataclasses import dataclass, field

from . import render


@dataclass
class Word:
    text: str
    box: tuple                  # (x0, y0, x1, y1) in page coordinates
    confidence: float = None    # None when the engine gives none


@dataclass
class Line:
    words: list = field(default_factory=list)

    @property
    def text(self):
        return " ".join(w.text for w in self.words)

    @property
    def box(self):
        xs0, ys0, xs1, ys1 = zip(*(w.box for w in self.words))
        return (min(xs0), min(ys0), max(xs1), max(ys1))


class Engine:
    id = ""
    name = ""
    platforms = ()              # sys.platform values it runs on; empty means any
    download_mb = 0             # what it adds to an install
    word_boxes = "native"       # "native" | "derived" | "generated"
    confidences = False

    def available(self):
        """-> (True, "") or (False, why not)."""
        if self.platforms and sys.platform not in self.platforms:
            return False, "%s runs only on %s" % (self.name, ", ".join(self.platforms))
        return True, ""

    def read_image(self, image):
        """A PIL image of ink -> [Line] with boxes in IMAGE pixels."""
        raise NotImplementedError


def engines():
    from .winocr import WindowsOCR
    return [WindowsOCR()]


def pick(engine_id=None):
    """The engine to use: the one asked for if it can run here, else the first available. -> Engine or None."""
    usable = [e for e in engines() if e.available()[0]]
    for e in usable:
        if e.id == engine_id:
            return e
    return usable[0] if usable else None


def read(strokes, engine=None):
    """Read a page's ink. `strokes` is [{"points": [(x, y), ...], "width": w}] in page coordinates.
    -> [Line] in page coordinates, top to bottom and left to right; [] when there is no ink.
    Raises LookupError when no engine can run here, so the host can record that handwriting was not read."""
    engine = engine or pick()
    if engine is None:
        raise LookupError("no handwriting reader can run on this computer")
    image, tf = render.ink_image(strokes)
    if image is None:
        return []
    lines = []
    for line in engine.read_image(image):
        words = [Word(w.text, tf.to_page(w.box), w.confidence) for w in line.words if w.text.strip()]
        if words:
            lines.append(Line(sorted(words, key=lambda w: w.box[0])))
    lines.sort(key=lambda ln: (ln.box[1], ln.box[0]))
    return lines


def read_picture(image, scale=2, engine=None):
    """Words in a picture of a page (a render of it, or a crop): a PIL image or a file path ->
    [{"text", "x", "y", "w", "h", "line"}] in the picture's own pixels, line by line in reading order.
    The picture is read at `scale` times its size: small lettering reads as nothing at 1x."""
    from PIL import Image
    engine = engine or pick()
    if engine is None:
        raise LookupError("no handwriting reader can run on this computer")
    im = Image.open(image) if isinstance(image, str) else image
    im = im.convert("RGB")
    if scale and scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    s = float(scale or 1)
    out = []
    for n, line in enumerate(engine.read_image(im)):
        for w in line.words:
            if w.text.strip():
                x0, y0, x1, y1 = w.box
                out.append({"text": w.text, "x": x0 / s, "y": y0 / s, "w": (x1 - x0) / s, "h": (y1 - y0) / s, "line": n})
    return out


def lines_of(words):
    """Words from read_picture grouped by line -> [{"text", "x", "y", "w", "h", "words"}] in reading order."""
    out = {}
    for w in words:
        out.setdefault(w["line"], []).append(w)
    res = []
    for n in sorted(out):
        ws = sorted(out[n], key=lambda w: w["x"])
        x0, y0 = min(w["x"] for w in ws), min(w["y"] for w in ws)
        x1, y1 = max(w["x"] + w["w"] for w in ws), max(w["y"] + w["h"] for w in ws)
        res.append({"text": " ".join(w["text"] for w in ws), "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "words": ws})
    return res


__all__ = ["Word", "Line", "Engine", "engines", "pick", "read", "read_picture", "lines_of"]
