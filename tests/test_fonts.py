"""The tablet's typefaces are taken from the desktop app's program file, never shipped."""
import io
import os

from paperdaemon.remarkable import fonts


def _face(name):
    """A small real TrueType face carrying `name` as its PostScript name."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({65: "A"})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((500, 0))
    pen.lineTo((250, 700))
    pen.closePath()
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": name.split("-")[0], "styleName": "Regular", "psName": name})
    fb.setupOS2()
    fb.setupPost()
    buf = io.BytesIO()
    fb.save(buf)
    return buf.getvalue()


def test_extracts_embedded_faces_by_their_own_names(tmp_path):
    a, b, other = _face("reMarkableSans-Regular"), _face("reMarkableSerifSmall-Bold"), _face("SomeoneElse-Regular")
    zero = bytes(1)
    exe = tmp_path / "reMarkable.exe"
    exe.write_bytes(b"MZ" + zero * 1000 + a + (zero + b"junk") * 50 + b + b"pad" * 10 + other + zero * 64)
    dest = tmp_path / "rm-fonts"
    assert fonts.extract(str(dest), programs=[str(exe)]) == 2
    for name, src in (("reMarkableSans-Regular", a), ("reMarkableSerifSmall-Bold", b)):
        got = (dest / (name + ".ttf")).read_bytes()
        # the face's own bytes, up to the end of its last table (only the file's zero padding may be left out)
        assert src.startswith(got) and not src[len(got):].strip(zero)
    assert not (dest / "SomeoneElse-Regular.ttf").exists()          # only the tablet's faces
    assert fonts.extract(str(dest), programs=[str(exe)]) == 0         # never rewritten


def test_no_app_writes_nothing(tmp_path):
    assert fonts.extract(str(tmp_path / "rm-fonts"), programs=[str(tmp_path / "missing.exe")]) == 0
    assert not os.path.exists(tmp_path / "rm-fonts")
