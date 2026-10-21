"""The one renderer (fastdecomp/render.c through pipeline/page/paint.py): a pixel is inked when its center is inside the
stroke's exact shape; pens are opaque with round ends; the highlighter has flat ends and darkens without stacking;
the shader washes once per stroke; ss > 1 averages down to smooth edges."""
import numpy as np
from PIL import Image

from paperdaemon.pipeline.page.paint import paint


def canvas(w=40, h=20):
    return Image.new("RGB", (w, h), "white")


def ink(img):
    return np.asarray(img, np.int16).sum(axis=2) < 765


def test_a_pen_inks_exactly_the_pixels_whose_centers_are_inside():
    img = paint(canvas(), [([(5.0, 10.0), (30.0, 10.0)], [4.0, 4.0], "pen", (0, 0, 0))])
    a = ink(img)
    # radius 2 around y = 10: pixel centers at 8.5, 9.5, 10.5, 11.5 are inside; 7.5 and 12.5 are not
    assert a[8:12, 15].all() and not a[7, 15] and not a[12, 15]
    # round ends: the end's center row reaches past x = 30 by the radius; the corner rows do not
    assert a[10, 31] and not a[8, 32]


def test_the_highlighter_has_flat_ends_and_darkens_without_stacking():
    pts = [(5.0, 10.0), (30.0, 10.0)]
    img = paint(canvas(), [(pts, [6.0, 6.0], "highlighter", (200, 220, 100))])
    px = np.asarray(img)
    assert tuple(px[10, 15]) == (200, 220, 100)
    assert tuple(px[10, 31]) == (255, 255, 255)            # flat: nothing past the end point
    twice = paint(canvas(), [(pts, [6.0, 6.0], "highlighter", (200, 220, 100))] * 2)
    assert np.array_equal(np.asarray(twice), px)           # the same color again changes nothing
    over = paint(canvas(), [(pts, [6.0, 6.0], "pen", (100, 100, 100)), (pts, [6.0, 6.0], "highlighter", (200, 220, 100))])
    assert tuple(np.asarray(over)[10, 15]) == (100, 100, 100)    # darken: the darker of the two per channel


def test_the_shader_washes_once_per_stroke_and_deepens_under_another():
    zig = [(5.0, 10.0), (20.0, 10.0), (5.0, 10.5)]         # the stroke runs back over itself
    one = np.asarray(paint(canvas(), [(zig, [6.0] * 3, "shader", (0, 0, 0, 128))]))
    assert tuple(one[10, 10]) == (127, 127, 127)            # once, though two segments cover it
    two = np.asarray(paint(canvas(), [(zig, [6.0] * 3, "shader", (0, 0, 0, 128))] * 2))
    assert two[10, 10, 0] < one[10, 10, 0]                  # a second stroke deepens it


def test_supersampling_smooths_edges_and_keeps_the_shape():
    sharp = np.asarray(paint(canvas(), [([(5.0, 10.0), (30.0, 10.0)], [3.0, 3.0], "pen", (0, 0, 0))]), np.int16)
    soft = np.asarray(paint(canvas(), [([(5.0, 10.0), (30.0, 10.0)], [3.0, 3.0], "pen", (0, 0, 0))], ss=4), np.int16)
    assert set(np.unique(sharp)) <= {0, 255}
    assert ((soft > 0) & (soft < 255)).any()                # partly covered pixels are gray
    assert abs(int(sharp[:, 15, 0].sum()) - int(soft[:, 15, 0].sum())) < 255 * 2


def test_what_is_under_the_strokes_stays():
    img = Image.new("RGB", (40, 20), (10, 200, 30))
    out = np.asarray(paint(img, [([(5.0, 5.0), (6.0, 5.0)], [2.0, 2.0], "pen", (0, 0, 0))], ss=2))
    assert tuple(out[15, 30]) == (10, 200, 30)


def test_a_picture_is_the_whole_page_and_everything_past_it(tmp_path, monkeypatch):
    """Every picture holds the whole page and anything past its edges (here a picture out past the right side and
    above the top), and says where its top-left corner is, so a pixel maps back to the page whatever the frame."""
    from paperdaemon.pipeline.page import images, render as R, typed
    pic = tmp_path / "p.png"
    Image.new("RGB", (10, 10), "black").save(pic)
    monkeypatch.setattr(R, "strokes", lambda doc, page, arrays=False: [])
    monkeypatch.setattr(R, "page_frame", lambda doc, page: (1404, 1872))
    monkeypatch.setattr(R, "_paste_source", lambda *a: "")
    monkeypatch.setattr(typed, "paragraphs", lambda doc, page: (_ for _ in ()).throw(ValueError()))
    monkeypatch.setattr(images, "items", lambda doc, page: [{"path": str(pic), "box": (700.0, -100.0, 800.0, 200.0)}])
    out = tmp_path / "o.png"
    ox, oy = R.render("d", 1, str(out), blank_ok=True)[4]
    im = Image.open(out)
    assert (ox, oy) == (-702, -160)                          # the page's left edge; 60 above the picture's top
    assert im.size == (800 + 60 + 702, 1872 + 160)           # the page, and the picture past it with its margin
    assert ink(im.convert("RGB"))[int(150 - oy), int(790 - ox)]        # the picture is drawn where it lies on the page


def test_a_page_with_nothing_past_it_is_the_page_exactly(tmp_path, monkeypatch):
    from paperdaemon.pipeline.page import images, render as R, typed
    monkeypatch.setattr(R, "strokes", lambda doc, page, arrays=False: [])
    monkeypatch.setattr(R, "page_frame", lambda doc, page: (1620, 2160))
    monkeypatch.setattr(R, "_paste_source", lambda *a: "")
    monkeypatch.setattr(typed, "paragraphs", lambda doc, page: (_ for _ in ()).throw(ValueError()))
    monkeypatch.setattr(images, "items", lambda doc, page: [])
    out = tmp_path / "o.png"
    got = R.render("d", 1, str(out), blank_ok=True)
    assert got[1] == (1620, 2160) and got[4] == (-810, 0)


def test_a_stroke_anchored_to_the_typed_text_is_read_where_the_tablet_draws_it(tmp_path, monkeypatch):
    # the tablet files ink written near typed text into a group anchored to it, stored offset from the page: read
    # at its stored place it was ruled on, pointed at and collided with somewhere it is not. It is read where the
    # tablet draws it, and keeps the identity of its stored self, which is what erasing matches in the file.
    from rmscene import scene_stream as ss
    from rmscene.crdt_sequence import CrdtSequenceItem
    from rmscene.scene_items import Line, Point, Pen, PenColor
    from rmscene.tagged_block_common import CrdtId
    from paperdaemon.pipeline import page as P
    from paperdaemon.pipeline.page import render as R
    stored = Line(color=PenColor.BLACK, tool=Pen.FINELINER_2,
                  points=[Point(100.0, 80.0, 2, 10, 0, 100), Point(140.0, 90.0, 2, 10, 0, 100)],
                  thickness_scale=1.0, starting_length=0.0)
    block = ss.SceneLineItemBlock(parent_id=CrdtId(1, 66), item=CrdtSequenceItem(
        item_id=CrdtId(1, 70), left_id=CrdtId(0, 0), right_id=CrdtId(0, 0), deleted_length=0, value=stored))
    page = tmp_path / "page.rm"
    page.write_bytes(b"x")
    monkeypatch.setattr(R, "live_pages", lambda doc: [{"id": "p"}])
    monkeypatch.setattr(R, "page_file", lambda doc, pid: str(page))
    monkeypatch.setattr(R, "blocks_of", lambda path, arrays=False: [block])
    monkeypatch.setattr(R, "_anchor_offsets", lambda doc, page_no, blocks: {CrdtId(1, 66): (-330.0, 234.0)})
    (line,) = R.strokes("doc", 1)
    assert (line.points[0].x, line.points[0].y) == (-230.0, 314.0)     # where the tablet draws it
    assert P.skey(line) == P.skey(stored)                               # erasing still finds it in the file
    assert (stored.points[0].x, stored.points[0].y) == (100.0, 80.0)   # the stored stroke is untouched


def test_a_highlighter_with_no_rgba_takes_its_color_from_the_enum(tmp_path, monkeypatch):
    # the user's pink highlighter stroke carried PenColor.PINK and no color_rgba, and was drawn yellow
    from rmscene.scene_items import Line, Point, Pen, PenColor
    from paperdaemon.pipeline.page import images, render as R, typed
    pink = Line(color=PenColor.PINK, tool=Pen.HIGHLIGHTER_2, thickness_scale=1.0, starting_length=0.0,
                points=[Point(-300.0, 130.0, 0, 120, 0, 100), Point(300.0, 130.0, 0, 120, 0, 100)])
    monkeypatch.setattr(R, "strokes", lambda doc, page, arrays=False: [pink])
    monkeypatch.setattr(R, "page_frame", lambda doc, page: (1620, 2160))
    monkeypatch.setattr(R, "_paste_source", lambda *a: "")
    monkeypatch.setattr(typed, "paragraphs", lambda doc, page: (_ for _ in ()).throw(ValueError()))
    monkeypatch.setattr(images, "items", lambda doc, page: [])
    out = tmp_path / "o.png"
    R.render("d", 1, str(out), blank_ok=True)
    r, g, b = Image.open(out).convert("RGB").getpixel((810, 130))
    assert b == 255 and g < 230 and r > g                       # the pink wash, not the yellow one (b would be low)


def test_a_grain_stroke_inks_its_density_and_each_pixel_once():
    from paperdaemon.pipeline.page.paint import response
    pts = [(x, 50.0) for x in np.arange(10.0, 390.0, 3.0)]
    solid = ink(paint(canvas(400, 100), [(pts, [8.0] * len(pts), "pen", (0, 0, 0))]))
    for d in (0.2, 0.5, 0.8):
        a = ink(paint(canvas(400, 100), [(pts, [8.0] * len(pts), "pen", (0, 0, 0), [d] * len(pts))]))
        assert not (a & ~solid).any()                         # only inside the stroke's shape
        assert abs(a.sum() / solid.sum() - d) < 0.06          # its share, however densely the points sit
    # density 1 is the solid stroke, pixel for pixel
    assert np.array_equal(ink(paint(canvas(400, 100), [(pts, [8.0] * len(pts), "pen", (0, 0, 0), [1.0] * len(pts))])), solid)
    # the pencils grain with pressure, the fineliner never
    assert response("PENCIL", [40])[1][0] < 0.1 < response("PENCIL", [255])[1][0]
    assert response("FINELINER", [10])[1][0] == 1.0 and response("FINELINER", [10])[0][0] == 1.0
    assert response("PAINTBRUSH", [30])[0][0] == 0             # the lightest paintbrush leaves nothing
