import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from paperdaemon import server
from paperdaemon.pipeline.decompose.fastdecomp import rmfast
from paperdaemon.pipeline.decompose.reference import rm_paint


def client():
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    return c


def ellipse(w=200, h=150):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).ellipse((10, 10, w - 10, h - 10), fill=255)
    return m


def test_the_page_editor_fill_is_the_decomposers_own():
    m = ellipse()
    bits = np.packbits((np.asarray(m) > 0).astype(np.uint8).ravel()).tobytes()
    for flat in (0, 1):
        r = client().post("/api/v1/fill?w=200&h=150&ppg=2&flat=%d" % flat, content=bits)
        assert r.status_code == 200
        got = r.json()["strokes"]
        want = rmfast.fill(m, (0, 0, 0, 255), 2.0, (0, 0, 200, 150), (0, 0), (200, 150), flat, rm_paint)
        assert len(got) == len(want) > 3                         # rings, not one sweep
        for g, (pts, field, pen, *_) in zip(got, want):
            assert g["field"] == field[0] and g["pen"] == int(pen)
            assert np.allclose(g["pts"], np.asarray(pts, np.float64))
        # every ring is inside the area: the fill keeps to it
        xs = [p[0] for s in got for p in s["pts"]]
        ys = [p[1] for s in got for p in s["pts"]]
        assert min(xs) >= 9 and max(xs) <= 191 and min(ys) >= 9 and max(ys) <= 141


def test_a_fill_whose_area_does_not_fit_its_size_is_refused():
    r = client().post("/api/v1/fill?w=200&h=150&ppg=2", content=b"\x00" * 10)
    assert r.status_code == 400
