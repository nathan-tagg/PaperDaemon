"""The arrow detector's farthest ends (page/marks._ends): found among the convex hull's corners, the same pair as
comparing every two ends, so a traced picture of thousands of strokes is read in moments rather than minutes."""
import math
import random
from types import SimpleNamespace as NS

from paperdaemon.pipeline.page import marks as M


def _every_pair(lines, idxs):
    ends = []
    for i in idxs:
        p = lines[i].points
        ends += [(p[0].x, p[0].y), (p[-1].x, p[-1].y)]
    best, far = None, -1.0
    for a in ends:
        for b in ends:
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if d > far:
                far, best = d, (a, b)
    return best, far


def _stroke(rnd, grid=None):
    pts = [(rnd.uniform(-800, 800), rnd.uniform(0, 2000)) for _ in range(rnd.randint(2, 6))]
    if grid:                                          # ties and ends in a line along the hull
        pts = [(round(x / grid) * grid, round(y / grid) * grid) for x, y in pts]
    return NS(points=[NS(x=x, y=y) for x, y in pts])


def test_the_farthest_ends_are_the_same_pair_as_every_pair_compared():
    rnd = random.Random(7)
    for t in range(300):
        lines = [_stroke(rnd, 200 if t % 3 == 0 else None) for _ in range(rnd.randint(1, 60))]
        idxs = list(range(len(lines)))
        assert M._ends(lines, idxs) == _every_pair(lines, idxs)


def test_a_traced_picture_is_read_for_its_ends():
    rnd = random.Random(3)
    lines = [_stroke(rnd) for _ in range(13000)]       # every pair: 676 million distances, about 96 s
    (a, b), span = M._ends(lines, list(range(len(lines))))
    assert span == math.hypot(a[0] - b[0], a[1] - b[1]) > 0
