"""The app never loads the libraries only the decomposer's Python reference runs on (they are left out of the build).

Run in a fresh process, so nothing another test imported counts: the engine, the daemon, the host and the studio
are imported, the host's brief is built, and a picture is decomposed. None of OpenCV, numba, llvmlite, SciPy,
scikit-image or Shapely may be loaded by then.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = r"""
import base64, io, sys
sys.path.insert(0, ROOT)
from PIL import Image, ImageDraw
import paperdaemon.server, paperdaemon.studio, paperdaemon.pipeline.daemon
import paperdaemon.pipeline.host as H
H.system_brief()
from paperdaemon import studio
im = Image.new("RGB", (400, 300), "white")
d = ImageDraw.Draw(im)
d.ellipse((40, 40, 360, 260), outline="black", width=8)
d.rectangle((150, 100, 250, 200), fill=(200, 60, 60))
buf = io.BytesIO()
im.save(buf, "PNG")
out, _ = studio.decompose("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), 600)
assert out["strokes"] > 0
heavy = ("cv2", "numba", "llvmlite", "scipy", "skimage", "shapely")
print(" ".join(sorted({m.split(".")[0] for m in sys.modules if m.split(".")[0] in heavy})))
"""


def test_the_engine_loads_none_of_the_reference_libraries(tmp_path):
    from paperdaemon.pipeline import decompose as M
    if M.fast() is None:
        pytest.skip("the C decomposer is not built here")
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    r = subprocess.run([sys.executable, "-c", "ROOT = %r\n" % ROOT + PROBE], capture_output=True, text=True, env=env,
                       cwd=str(tmp_path), timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.strip().splitlines()[-1:] in ([], [""]), "loaded: " + r.stdout.strip().splitlines()[-1]
