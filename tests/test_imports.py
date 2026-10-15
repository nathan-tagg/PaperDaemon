"""Every pipeline module imports in a fresh interpreter, the way the daemon and the host load them."""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "paperdaemon", "pipeline")


def modules():
    out = []
    for cur, dirs, files in os.walk(PIPE):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "fastdecomp")]
        for f in files:
            if not f.endswith(".py") or f == "__main__.py":
                continue
            rel = os.path.relpath(os.path.join(cur, f), ROOT)[:-3].replace(os.sep, ".")
            out.append(rel[:-len(".__init__")] if rel.endswith(".__init__") else rel)
    return sorted(out)


@pytest.mark.parametrize("module", modules())
def test_module_imports(module, tmp_path):
    env = dict(os.environ, RM_STATE=str(tmp_path), RM_MIRROR=str(tmp_path), RM_CACHE=str(tmp_path),
               PAPERDAEMON_HOME=str(tmp_path), PYTHONIOENCODING="utf-8")
    code = "import importlib, sys; sys.path.insert(0, %r); import paperdaemon.pipeline; importlib.import_module(%r)" % (ROOT, module)
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert p.returncode == 0, p.stderr[-1500:]
