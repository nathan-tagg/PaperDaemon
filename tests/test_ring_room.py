"""A ring round words keeps to the free paper round them (DF115: round "Thursday, November / 19 at 3 pm." the ring cut
the "y" of the "by" before it, and its top edge ran through "All baked" on the line above, reading as a strike-through),
and on open paper it is the ring it always was."""
from paperdaemon.pipeline.host.features import markup as M

INF = float("inf")
OPEN = {"up": INF, "down": INF, "left": INF, "right": INF}


def _inside(pt, poly):
    x, y, n, hit = pt[0], pt[1], len(poly), False
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            hit = not hit
    return hit


def test_on_open_paper_the_ring_is_the_one_it_always_was():
    for box in ((0.0, 0.0, 300.0, 40.0), (0.0, 0.0, 60.0, 40.0), (-200.0, 300.0, 200.0, 460.0)):
        assert M._ring(*box, room=OPEN) == M._ring(*box)


def test_in_a_paragraph_the_ring_stays_off_the_words_round_it_and_still_holds_its_own():
    box = (222.0, 452.0, 552.0, 492.0)                    # "Thursday, November" at the end of a line
    room = {"up": 5.0, "down": 30.0, "left": 9.0, "right": INF}
    ring = M._ring(*box, room=room)
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    assert min(xs) >= box[0] - (room["left"] - M.CLEAR_H) - 1e-6        # the "by" before it is not touched
    assert min(ys) >= box[1] - max(3.0, room["up"] - M.CLEAR_V) - 1e-6   # nor the line above
    for corner in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
        assert _inside(corner, ring)                                     # the words are all inside it


def test_the_room_is_the_nearest_thing_on_each_side_and_the_marked_words_are_not_in_the_way():
    box = (100.0, 100.0, 300.0, 140.0)
    others = [(110.0, 105.0, 180.0, 138.0),               # one of the marked words itself
              (0.0, 50.0, 400.0, 95.0),                   # the line above
              (0.0, 190.0, 400.0, 230.0),                 # a line further down
              (40.0, 100.0, 91.0, 140.0),                 # the word before it
              (600.0, 100.0, 700.0, 140.0)]               # far off to the right
    room = M._room(box, others)
    assert room == {"up": 5.0, "down": 50.0, "left": 9.0, "right": 300.0}
