"""A checklist reads as lines of the page's text: trimmed to its boxes and words, its left edge on the text column's,
never wider than the column (DF106: drawn as wide as the page, its boxes sat at the page's far left, left of the typed
lines above it, its words larger than theirs)."""
from paperdaemon.pipeline import draw as A
from paperdaemon.pipeline import host as H
from paperdaemon.pipeline.host import job as J
from paperdaemon.pipeline.host import layout as PL


def test_a_checklist_sits_on_the_text_column_at_the_texts_size():
    import os
    os.makedirs(H.QUEUE, exist_ok=True)
    J.begin(doc="nodoc", page=1, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
    specs = [{"id": "s1", "kind": "chart", "size": "medium", "near": "stack"}]
    boxes = PL.solve([dict(p) for p in specs], first_free_y=760)
    H.JOB.plan = {"places": boxes, "reflow": {"specs": specs, "first_free_y": 760, "marks": None, "obstacles": None,
                                               "text_col": None}}
    H.JOB.steps = [{"id": 1, "do": "chart", "what": "a checklist", "place": "s1", "status": "doing"}]
    H.JOB.images = []
    r = H.t_chart({"type": "checklist", "items": ["Book the lodge", "Order lunch", "Send the agenda"]}, place="s1")
    assert r.get("ok"), r
    x0, y0, x1, y1 = H.JOB.images[-1]["box"]
    col = H._text_col()
    assert abs(x0 - col[0]) < 1e-6 and x1 < col[1] and x1 - x0 < 0.6 * (col[1] - col[0])
    assert 150 < y1 - y0 < 260                                      # three rows of typed-size lines, not a poster
