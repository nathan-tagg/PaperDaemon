"""The decomposer gives exactly the strokes it gave when the record was made: every picture in
tests/decompose/pictures (three public-domain paintings and two generated pages), in a full-page box and a
half-width box through decompose_into, and at a width through decompose, compared by a digest of the strokes' exact values and types.

    uv run python tests/test_decompose_identity.py --record     (only when a change to the strokes is intended)
"""
import hashlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PICTURES = os.path.join(HERE, "decompose", "pictures")
EXPECTED = os.path.join(HERE, "decompose", "expected.json")
BOXES = {"page": (1560, 2080, (-780.0, 40.0)), "half": (780, 1040, (-390.0, 300.0)), "width": (1400, None, None)}


def _decompose():
    sys.path.insert(0, os.path.dirname(HERE))
    try:
        from paperdaemon.pipeline import decompose
        return decompose
    except ImportError:
        import paperdaemon.pipeline  # noqa: F401
        from paperdaemon.pipeline import decompose as rm_model
        return rm_model


def digest(picture, box):
    """decompose_into for a box; for "width", the model's own call, decompose, at that width."""
    w, h, origin = BOXES[box]
    src = os.path.join(PICTURES, picture)
    if h is None:
        got = _decompose().decompose(src, w)
        strokes = got[0] if isinstance(got, tuple) else got
    else:
        strokes, _params, _secs = _decompose().decompose_into(src, w, h, origin=origin)
    return {"strokes": len(strokes), "sha256": hashlib.sha256(repr(strokes).encode()).hexdigest()}


def cases():
    return [(p, b) for p in sorted(os.listdir(PICTURES)) for b in BOXES]


@pytest.mark.parametrize("picture,box", cases())
def test_the_decomposer_gives_the_recorded_strokes(picture, box):
    with open(EXPECTED, encoding="utf-8") as f:
        want = json.load(f)["%s@%s" % (picture, box)]
    assert digest(picture, box) == want


if __name__ == "__main__" and "--record" in sys.argv:
    out = {"%s@%s" % (p, b): digest(p, b) for p, b in cases()}
    with open(EXPECTED, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print(json.dumps(out, indent=1))
