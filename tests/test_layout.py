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
