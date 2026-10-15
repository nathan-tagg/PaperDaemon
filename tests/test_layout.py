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

