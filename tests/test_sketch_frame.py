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


def _onto_job(mark_box):
    """A draw step ON a snowman already on the page (mark 1), laid out as the plan lays it out."""
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline import host as H
    from paperdaemon.pipeline.host import job as J
    from paperdaemon.pipeline.host import layout as PL
    J.begin(doc="nodoc", page=1, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
    specs = [{"id": "p1", "kind": "drawing", "size": "small", "near": "mark:1", "side": "on"}]
    boxes = PL.solve([dict(p) for p in specs], first_free_y=1500, marks={1: mark_box}, obstacles=[mark_box])
    H.JOB.plan = {"places": boxes, "reflow": {"specs": specs, "first_free_y": 1500, "marks": {1: mark_box},
                                               "obstacles": [mark_box], "text_col": None}}
    H.JOB.steps = [{"id": 1, "do": "draw", "what": "a top hat on the snowman", "place": "p1", "status": "doing",
                    "near": "mark:1", "side": "on"}]
    H.JOB.mark_index = [{"id": 1, "bbox": mark_box, "parts": [[-60, 600, 60, 720], [-100, 720, 100, 950],
                                                              [-140, 950, 140, 1250]], "count": 3}]
    return H


def test_a_hat_drawn_above_the_head_stays_there_unscaled():
    # the hat sits ABOVE the snowman's box: fitted into that box it was scaled 2x and moved onto the body
    H = _onto_job([-140, 600, 140, 1250])
    hat = [{"kind": "rect", "x1": -45, "y1": 480, "x2": 45, "y2": 590},
           {"kind": "polyline", "points": [[-75, 595], [75, 595]]}]
    assert H._draw_figure(hat, "p1").get("ok")
    x0, y0, x1, y1 = _extent(H.JOB.draw.strokes)
    assert abs(x0 - (-75)) < 12 and abs(x1 - 75) < 12 and abs(y0 - 480) < 12 and abs(y1 - 595) < 12
    from paperdaemon.pipeline.host import decision as D
    told = D.step_message(H.JOB.steps[0])
    assert "ON mark:1" in told and "x -60..60, y 600..720" in told and "nothing is moved or scaled" in told


def test_an_addition_drawn_on_a_grid_of_its_own_is_still_fitted():
    H = _onto_job([-140, 600, 140, 1250])
    far = [{"kind": "rect", "x1": -700, "y1": 1950, "x2": -640, "y2": 2000}]     # farther than its own size away
    assert H._draw_figure(far, "p1").get("ok")
    x0, y0, x1, y1 = _extent(H.JOB.draw.strokes)
    assert -160 <= x0 and x1 <= 160 and 580 <= y0 and y1 <= 1270                  # fitted into the drawing's box


def test_a_part_drawn_in_a_color_keeps_it():
    # "add red apples": the apples were drawn in black
    from paperdaemon.pipeline.draw import PenColor
    H = _onto_job([-140, 600, 140, 1250])
    apples = [{"kind": "circle", "cx": -40, "cy": 700, "r": 14, "color": "red"},
              {"kind": "circle", "cx": 40, "cy": 720, "r": 14, "color": "Red"},
              {"kind": "line", "x1": -40, "y1": 686, "x2": -36, "y2": 676}]
    assert H._draw_figure(apples, "p1").get("ok")
    inks = [s[3] for s in H.JOB.draw.strokes]
    assert inks.count(PenColor.RED) >= 2 and inks[-1] == PenColor.BLACK
