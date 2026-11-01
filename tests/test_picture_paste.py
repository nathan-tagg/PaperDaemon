"""A picture asked to be pasted goes on the page as itself (add-picture-paste): an image block fitted to its box, never
strokes drawn from it. The model says so with paste: true on an image or web_picture step; the host matches no words."""
import os

from PIL import Image


def _job(tmp_path, kind):
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline import host as H
    from paperdaemon.pipeline.host import job as J
    from paperdaemon.pipeline.host import layout as PL
    os.makedirs(H.QUEUE, exist_ok=True)
    J.begin(doc="nodoc", page=1, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
    specs = [{"id": "p1", "kind": "image", "size": "medium", "near": "stack"}]
    boxes = PL.solve([dict(p) for p in specs], first_free_y=300)
    H.JOB.plan = {"places": boxes, "reflow": {"specs": specs, "first_free_y": 300, "marks": None, "obstacles": None,
                                               "text_col": None}}
    png = str(tmp_path / ("%s.png" % kind))
    Image.new("RGB", (600, 400), (180, 40, 40)).save(png)
    return H, boxes["p1"], png


def test_the_paste_field_is_declared_and_only_a_plain_true_sets_it():
    from paperdaemon.pipeline.host import steps as ST
    assert "paste" in ST.fields_of("image") and "paste" in ST.fields_of("web_picture")
    assert "paste" not in ST.fields_of("draw") and "paste" not in ST.fields_of("coloring")
    built = ST.build([{"do": "web_picture", "what": "the Mona Lisa", "answers": [], "paste": True},
                      {"do": "image", "what": "a fox in the snow at dawn", "answers": [], "paste": "false"},
                      {"do": "image", "what": "an owl on a branch at night", "answers": []}])
    assert [s.get("paste") for s in built] == [True, None, None]


def test_a_web_picture_asked_pasted_goes_on_as_a_picture_with_no_strokes(tmp_path):
    H, box, png = _job(tmp_path, "web")
    real = H._fetch_png
    H._fetch_png = lambda what, site=None: (png, {"title": "Mona Lisa", "engine": "test"})
    try:
        H.JOB.steps = [{"id": 1, "do": "web_picture", "what": "the Mona Lisa", "place": "p1", "status": "todo",
                        "paste": True}]
        H._drain_host_steps()
    finally:
        H._fetch_png = real
    assert H.JOB.steps[0]["status"] == "done"
    assert not H.JOB.draw.strokes                                  # nothing drawn from it
    [im] = H.JOB.images
    assert im["type"] == "image" and im["place"] == "p1" and os.path.isfile(im["png"])
    x0, y0, x1, y1 = im["box"]                                     # inside its box, its aspect kept
    assert box["x0"] - 0.5 <= x0 and x1 <= box["x0"] + box["w"] + 0.5 and box["y0"] - 0.5 <= y0
    assert y1 <= box["y0"] + box["h"] + 0.5 and abs((x1 - x0) / (y1 - y0) - 1.5) < 0.01
    assert not os.path.exists(png)                                 # the download is gone once placed
    os.remove(im["png"])


def test_a_web_picture_not_asked_pasted_is_still_drawn_in_strokes(tmp_path):
    H, box, png = _job(tmp_path, "traced")
    real_fetch, real_trace = H._fetch_png, H._trace_into
    traced = []
    H._fetch_png = lambda what, site=None: (png, {"title": "a fox", "engine": "test"})
    H._trace_into = lambda png_, box_, place, what, **kw: traced.append(place) or 7
    try:
        H.JOB.steps = [{"id": 1, "do": "web_picture", "what": "a red fox", "place": "p1", "status": "todo"}]
        H._drain_host_steps()
    finally:
        H._fetch_png, H._trace_into = real_fetch, real_trace
    assert traced == ["p1"] and not H.JOB.images


def test_a_generated_picture_asked_pasted_goes_on_as_a_picture(tmp_path):
    H, box, png = _job(tmp_path, "made")
    saved = {k: getattr(H, k) for k in ("_picture_model", "_generate_png", "_image_offer")}
    H._picture_model = lambda fn: fn()
    H._generate_png = lambda prompt, side, height=None, seed=None, steps=None, workflow=None: png
    H._image_offer = lambda: {}
    try:
        q = {"id": 1, "do": "image", "what": "a lighthouse in a storm, oil painting", "place": "p1", "status": "todo",
             "paste": True}
        H.JOB.steps = [q]
        H._run_images([q])
    finally:
        for k, v in saved.items():
            setattr(H, k, v)
    assert q["status"] == "done" and not H.JOB.draw.strokes
    [im] = H.JOB.images
    assert im["type"] == "image" and os.path.isfile(im["png"]) and not os.path.exists(png)
    os.remove(im["png"])
