"""Windows OCR (`Windows.Media.Ocr`), called in process through the WinRT projection for Python.

It needs no download (the engine ships with Windows; each language needs its OCR pack), returns a box
per word and no confidences, and caps images at 10,000 px a side. Microsoft documents it for printed
text; on handwriting it is the bar PaperDaemon's other engines are measured against.
"""
import math
import sys

from . import Engine, Line, Word


class WindowsOCR(Engine):
    id = "windows-ocr"
    name = "Windows OCR"
    platforms = ("win32",)
    download_mb = 1
    word_boxes = "native"
    confidences = False

    def _engine(self):
        from winrt.windows.media.ocr import OcrEngine
        return OcrEngine.try_create_from_user_profile_languages()

    def available(self):
        ok, why = super().available()
        if not ok:
            return ok, why
        try:
            engine = self._engine()
        except ImportError:
            return False, "the WinRT packages for Windows OCR are not installed"
        except OSError as ex:
            return False, "Windows OCR could not start (%s)" % ex
        if engine is None:
            return False, "no Windows OCR language pack is installed for your languages"
        return True, ""

    def read_image(self, image):
        """A TALLER PICTURE THAN THE ENGINE TAKES is read in bands (Windows refuses either side past MAX_SIDE: a long
        page's render failed whole, 11-12): each band overlaps the next, and a line is kept from the band whose own
        part holds its middle, moved back to the picture's place."""
        from .render import MAX_SIDE
        if image.height <= MAX_SIDE - 1 and image.width <= MAX_SIDE - 1:
            return self._read_one(image)
        if image.width > MAX_SIDE - 1:                    # (a page is never that wide: scaled to fit across)
            from PIL import Image
            k = (MAX_SIDE - 1) / float(image.width)
            small = image.resize((MAX_SIDE - 1, max(1, int(image.height * k))), Image.LANCZOS)
            return [Line([Word(w.text, tuple(v / k for v in w.box), w.confidence) for w in ln.words])
                    for ln in self.read_image(small)]
        band, over = MAX_SIDE - 1, 600
        step = band - over
        lines, top = [], 0
        while True:
            bottom = min(image.height, top + band)
            own0 = 0 if top == 0 else top + over / 2.0
            own1 = image.height if bottom == image.height else bottom - over / 2.0
            for ln in self._read_one(image.crop((0, top, image.width, bottom))):
                words = [Word(w.text, (w.box[0], w.box[1] + top, w.box[2], w.box[3] + top), w.confidence)
                         for w in ln.words]
                if not words:
                    continue
                mid = (min(w.box[1] for w in words) + max(w.box[3] for w in words)) / 2.0
                if own0 <= mid < own1:
                    lines.append(Line(words))
            if bottom == image.height:
                break
            top += step
        return lines

    def _read_one(self, image):
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        rgba = image.convert("RGBA")
        bmp = SoftwareBitmap.create_copy_from_buffer(rgba.tobytes(), BitmapPixelFormat.RGBA8, rgba.width, rgba.height)
        result = self._engine().recognize_async(bmp).get()
        # Text found at an angle is read from a straightened copy, and every word box is in that copy: each
        # box is turned back about the image's center, and the box around it kept.
        angle = float(result.text_angle or 0.0) if result.text_angle is not None else 0.0
        cx, cy = rgba.width / 2.0, rgba.height / 2.0
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        lines = []
        for ln in result.lines:
            words = []
            for w in ln.words:
                r = w.bounding_rect
                box = (r.x, r.y, r.x + r.width, r.y + r.height)
                if abs(angle) > 0.01:
                    pts = [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c)
                           for x, y in ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3]))]
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    box = (min(xs), min(ys), max(xs), max(ys))
                words.append(Word(w.text, box))
            lines.append(Line(words))
        return lines


if sys.platform != "win32":
    WindowsOCR.__doc__ += "\n(Not available on this platform.)"
