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
