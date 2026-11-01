"""A sketch is drawn on ONE grid. The host fits a figure into its box as a whole; an icon the model drew with it, in the
same reply or while the figure is shown back for a fix, joins the figure and is fitted with it, so it lands where the
model put it beside the other parts (a sun meant for the sky had landed on the house's window). A sketch step makes no
picture: a picture that must look real is an image step of the plan."""


def _job():
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline import host as H
    from paperdaemon.pipeline.host import job as J
    from paperdaemon.pipeline.host import layout as PL
    J.begin(doc="nodoc", page=1, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
    specs = [{"id": "p1", "kind": "drawing", "size": "medium", "near": "stack"}]
    boxes = PL.solve([dict(p) for p in specs], first_free_y=300)
    H.JOB.plan = {"places": boxes, "reflow": {"specs": specs, "first_free_y": 300, "marks": None, "obstacles": None,
                                               "text_col": None}}
    H.JOB.steps = [{"id": 1, "do": "draw", "what": "a house with the sun", "place": "p1", "status": "doing"}]
    return H, boxes["p1"]


def _extent(strokes):
    xs = [p[0] for s in strokes for p in s[0]]
    ys = [p[1] for s in strokes for p in s[0]]
    return min(xs), min(ys), max(xs), max(ys)


HOUSE = [{"kind": "rect", "x1": 0, "y1": 100, "x2": 80, "y2": 200},
         {"kind": "polyline", "points": [[0, 100], [40, 60], [80, 100]]}]


def test_an_icon_is_a_part_of_a_figure_on_its_grid():
    from paperdaemon.pipeline import host as H
    paths = H._part_paths({"kind": "icon", "name": "sun", "cx": 100, "cy": 50, "r": 30})
    assert paths and all(len(p) >= 2 for p in paths)
    x0, y0, x1, y1 = _extent([(p,) for p in paths])
    assert 60 <= x0 and x1 <= 140 and 10 <= y0 and y1 <= 90
    try:
        H._part_paths({"kind": "icon", "name": "zzqx", "cx": 0, "cy": 0, "r": 10})
        raise AssertionError("an unknown icon drew something")
    except ValueError as ex:
        assert "no icon named" in str(ex)


def test_an_icon_drawn_with_the_figure_joins_it_and_lands_beside_it():
    H, box = _job()
    assert H.t_draw_figure(HOUSE)["ok"]
    house = len(H.JOB.draw.strokes)
    res = H.t_element("sun", 180, 20, 15)                      # the same reply: the figure's grid, up and right
    assert res.get("ok") and H.JOB.figure["parts"][-1]["kind"] == "icon"
    strokes = H.JOB.draw.strokes
    hx0, hy0, hx1, hy1 = _extent(strokes[:house])
    sx0, sy0, sx1, sy1 = _extent(strokes[house:])
    assert sx0 > hx1 and sy1 < hy1 and sy0 < hy0                 # still up and to the right of the house
    x0, y0, x1, y1 = _extent(strokes)
    assert box["x0"] - 1 <= x0 and x1 <= box["x1"] + 1 and box["y0"] - 1 <= y0 and y1 <= box["y1"] + 1
    assert len(H.JOB.ops) == 1                                   # one figure, not a figure and an icon


def test_an_icon_in_a_later_reply_is_drawn_on_its_own():
    H, box = _job()
    assert H.t_draw_figure(HOUSE)["ok"]
    H.JOB.turns += 1                                             # another reply, the figure not shown back
    assert H.t_element("star", box["cx"], box["cy"], 20).get("ok")
    assert all(p["kind"] != "icon" for p in H.JOB.figure["parts"]) and len(H.JOB.ops) == 2


def test_shown_back_for_a_fix_the_figure_stays_in_its_own_box():
    from paperdaemon.pipeline.host import layout as PL
    H, box = _job()
    assert H.t_draw_figure(HOUSE)["ok"]
    # the step closed; the host is on another step with a box of its own
    specs = [{"id": "p1", "kind": "drawing", "size": "medium", "near": "stack"},
             {"id": "p2", "kind": "text", "size": "small", "near": "stack"}]
    H.JOB.plan["places"] = dict(PL.solve([dict(p) for p in specs], first_free_y=300), p1=box)
    H.JOB.steps = [{"id": 1, "do": "draw", "what": "a house", "place": "p1", "status": "done"},
                   {"id": 2, "do": "write", "what": "a caption", "place": "p2", "status": "todo"}]
    H.JOB.turns += 1
    H.JOB.looking = True
    try:
        assert H.t_element("sun", 180, 20, 15).get("ok")          # joins the figure while it is looked at
        assert H.t_draw_figure(HOUSE + [{"kind": "circle", "cx": 150, "cy": 30, "r": 12}])["ok"]
    finally:
        H.JOB.looking = False
    assert H.JOB.figure["place"] == "p1"
    x0, y0, x1, y1 = _extent(H.JOB.draw.strokes)
    assert box["x0"] - 1 <= x0 and x1 <= box["x1"] + 1 and box["y0"] - 1 <= y0 and y1 <= box["y1"] + 1


def test_a_sketch_step_makes_no_picture():
    from paperdaemon.pipeline.host import decision as D
    from paperdaemon.pipeline.host import jobs as JB
    p = JB.PROTOCOLS["draw"]
    assert "image" not in p.allowed and "image" not in p.closes
    assert "image" not in [t["function"]["name"] if "function" in t else t.get("name") for t in D.tool_schema()]
