"""The layout solver never overlaps two places and keeps every one inside the safe area's sides and below its top
(a page scrolls, so the stack may run past the first screen) on randomized plans."""
import random

from paperdaemon.pipeline.host import layout as LY


def _box(b):
    return (b["x0"], b["y0"], b["x1"], b["y1"]) if isinstance(b, dict) else tuple(b)


def test_random_plans_never_overlap_and_stay_in_the_safe_area():
    rng = random.Random(7)
    solved = 0
    for _ in range(300):
        n = rng.randint(1, 4)
        places = [{"id": "p%d" % i, "kind": rng.choice([k for k in LY.KINDS if k not in ("calendar", "coloring")]),
                   "size": rng.choice(["small", "medium", "large"]),
                   "near": rng.choice(["stack", "stack", "left", "right"] + list(LY.CORNERS[:4]))} for i in range(n)]
        first = rng.choice([None, 300.0, 900.0])
        try:
            out = LY.solve(places, first_free_y=first)
        except LY.PlanError:
            continue                                     # a plan that cannot fit is refused, never squeezed
        solved += 1
        boxes = [_box(out[p["id"]]) for p in places]
        s = LY.SAFE
        for x0, y0, x1, y1 in boxes:
            # inside the sides and below the top; the bottom may run past the first screen (a page scrolls)
            assert s[0] - 1e-6 <= x0 < x1 <= s[2] + 1e-6 and s[1] - 1e-6 <= y0 < y1
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                assert a[2] <= b[0] + 1e-6 or b[2] <= a[0] + 1e-6 or a[3] <= b[1] + 1e-6 or b[3] <= a[1] + 1e-6
    assert solved > 150



def test_a_full_coloring_page_alone_takes_the_whole_screen():
    # the screen the tablet shows without scrolling, measured on the device: x -810..810, y 0..2160. A full coloring
    # page alone in the plan takes all of it, whatever is written above; with other places it is laid out as before
    from paperdaemon.pipeline.host import layout as PL
    from paperdaemon.pipeline.host.features import pictures as PX
    screen, safe = (-810.0, 0.0, 810.0, 2160.0), (-800.0, 115.0, 800.0, 2150.0)
    b = PL.solve([{"id": "c", "kind": "coloring", "size": "full", "near": "stack"}], first_free_y=902, safe=safe,
                 screen=screen)["c"]
    assert (b["x0"], b["y0"], b["x1"], b["y1"]) == screen
    assert PX._dims_for(b) == (768, 1024)                                   # exactly 3:4, so no white bands
    both = PL.solve([{"id": "c", "kind": "coloring", "size": "full", "near": "stack"},
                     {"id": "t", "kind": "text", "size": "small", "near": "stack"}], first_free_y=300, safe=safe,
                    screen=screen)
    assert both["c"]["y0"] >= 300 and both["t"]["y0"] > both["c"]["y1"]


def test_a_picture_is_the_pages_width_under_the_words_and_never_shrinks():
    """A stacked picture has its own size, not a share of the room left: the safe area's width (half when small), as
    tall as its square source, centered, below the reply's words, the page extending below it when it must."""
    from paperdaemon.pipeline.host import layout as PL
    for free in (300, 1500):
        b = PL.solve([{"id": "pic", "kind": "image", "size": "medium"},
                      {"id": "reply", "kind": "text", "size": "medium"}], first_free_y=free)
        pic, reply = b["pic"], b["reply"]
        assert (pic["x0"], pic["x1"], pic["w"], pic["h"]) == (-800.0, 800.0, 1600.0, 1600.0)
        assert pic["y0"] >= reply["y1"] + PL.GAP
    small = PL.solve([{"id": "pic", "kind": "image", "size": "small"}], first_free_y=300)["pic"]
    assert (small["w"], small["h"], small["cx"]) == (800.0, 800.0, 0.0)


def test_additions_drawn_onto_one_drawing_never_crowd_each_other():
    # "add a top hat, a scarf and buttons to the snowman": every addition goes ON mark 1. Each one's place is the
    # drawing itself, not new room, so they may share it -- while a new place beside it still keeps clear.
    snowman = {"x0": -200.0, "y0": 600.0, "x1": 200.0, "y1": 1300.0}
    places = [{"id": "s%d" % i, "kind": "drawing", "size": "small", "near": "mark:1", "side": "on"} for i in range(3)]
    out = LY.solve(places, first_free_y=1350.0, marks={1: snowman}, obstacles=[snowman])
    for p in places:
        b = out[p["id"]]
        assert snowman["x0"] <= b["x0"] < b["x1"] <= snowman["x1"] and snowman["y0"] <= b["y0"] < b["y1"] <= snowman["y1"]
    beside = places[:2] + [{"id": "t", "kind": "text", "size": "small", "near": "mark:1", "side": "right"}]
    out = LY.solve(beside, first_free_y=1350.0, marks={1: snowman}, obstacles=[snowman])
    assert out["t"]["x0"] >= out["s0"]["x1"] - 1e-6


def test_text_placed_by_a_mark_or_in_a_corner_keeps_to_the_typed_column():
    # 11-18, Blue Origin ("Okay, This is NOT how you place strokes"): a reply placed below a mark took the safe area's
    # full width, x -800..800, into the margins
    mark = {"x0": -600.0, "y0": 300.0, "x1": 600.0, "y1": 400.0}
    out = LY.solve([{"id": "t", "kind": "text", "size": "medium", "near": "mark:1", "side": "below"},
                    {"id": "c", "kind": "text", "size": "small", "near": "bottom-left"}],
                   first_free_y=450.0, marks={1: mark}, obstacles=[mark])
    for k in ("t", "c"):
        assert out[k]["x0"] >= LY.TEXT_COL[0] - 1e-6 and out[k]["x1"] <= LY.TEXT_COL[1] + 1e-6, (k, out[k])


def test_a_page_used_past_its_first_screen_gets_a_screen_below_for_what_is_stacked():
    # 11-22, Opus 5.5 p1: the free page began at y 7958, the stacked band ended at the first screen's 2150, and a large
    # drawing got a 240-unit box (then every part of it was refused). With less than a quarter screen left there, the
    # band is a screen's height below what is on the page
    out = LY.solve([{"id": "d", "kind": "drawing", "size": "large", "near": "stack"}], first_free_y=7958.0)
    assert out["d"]["y0"] >= 7958.0 and out["d"]["h"] >= 600, out["d"]
    room = LY.solve([{"id": "d", "kind": "drawing", "size": "large", "near": "stack"}], first_free_y=600.0)
    assert room["d"]["y1"] <= LY.SAFE[3] + 1e-6                 # with room on the first screen, as before
