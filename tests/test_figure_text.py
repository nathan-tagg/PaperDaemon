"""A figure can carry words: a "labeled diagram of the water cycle" came out as a blob, a tank and two arrows with no
word on it, because draw_figure had no part that could hold text. A text part is lettered on the figure's grid like
every other part."""
from paperdaemon.pipeline import host as H
from paperdaemon.pipeline.draw import lettering as LT


def _extent(paths):
    xs = [p[0] for pth in paths for p in pth]
    ys = [p[1] for pth in paths for p in pth]
    return min(xs), min(ys), max(xs), max(ys)


def test_a_text_part_is_lettered_at_its_baseline():
    paths = H._part_paths({"kind": "text", "text": "Evaporation", "x": 100, "y": 500, "size": 28})
    assert len(paths) > 10 and all(len(p) >= 2 for p in paths)
    x0, y0, x1, y1 = _extent(paths)
    assert 95 <= x0 <= 110 and x1 - x0 > 150              # starts at x, runs right
    assert 460 <= y0 and y1 <= 512                          # capitals above the baseline, nothing far below it


def test_anchors_put_the_middle_or_the_right_end_at_x():
    left = _extent(H._part_paths({"kind": "text", "text": "Collection", "x": 0, "y": 100}))
    mid = _extent(H._part_paths({"kind": "text", "text": "Collection", "x": 0, "y": 100, "anchor": "center"}))
    right = _extent(H._part_paths({"kind": "text", "text": "Collection", "x": 0, "y": 100, "anchor": "right"}))
    w = left[2] - left[0]
    assert abs((mid[0] + mid[2]) / 2) < w * 0.1 and abs(right[2]) < w * 0.1 and left[0] > -w * 0.1


def test_text_is_a_known_part_kind_and_needs_words():
    assert "text" in H.PART_SCHEMA["items"]["properties"]["kind"]["enum"]
    try:
        H._part_paths({"kind": "text", "x": 0, "y": 0})
        raise AssertionError("a text part with no text drew something")
    except ValueError:
        pass
    assert LT.measure("Precipitation", 28) > 0

def test_a_leader_that_ends_in_its_label_stops_short_of_the_words():
    # round 17, DF211: "Chloroplast" was struck through by the line that pointed at it
    from paperdaemon.pipeline.host.features import draw as D
    label = H._part_paths({"kind": "text", "text": "Chloroplast", "x": 430, "y": 170, "size": 28})
    x0, y0, x1, y1 = _extent(label)
    box = D._word_box(label, 28.0)
    assert box[0] < x0 and box[2] > x1 and box[1] < y0 and box[3] > y1
    leader = [(345.0, 180.0), (x0 + 40.0, y0 + 10.0)]            # from the shape into the middle of the word
    out = D._off_the_words([list(leader), list(label[0])], ["line", "text"], [box])
    end = out[0][-1]
    assert out[0][0] == leader[0] and end[0] < x0 and abs(end[0] - box[0]) < 1e-6   # cut at the label's left edge
    assert out[1] == list(label[0])                                              # the words are left alone
    # a line that only passes by, or ends well clear of the words, is unchanged
    clear = [(0.0, 0.0), (100.0, 100.0)]
    assert D._off_the_words([clear], ["line"], [box])[0] == clear
    assert D._off_the_words([clear], ["line"], [])[0] == clear

