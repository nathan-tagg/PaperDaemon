"""`paperdaemon --headless` serves paired requests on its port and opens no window."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_headless_serves_paired_requests_and_opens_no_window(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({"server": {"port": 8796}}))
    env = dict(os.environ, PAPERDAEMON_HOME=str(home), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    p = subprocess.Popen([sys.executable, "-m", "paperdaemon", "--headless", "--announce"], cwd=ROOT, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        tok = None
        for line in p.stdout:
            if line.startswith("PAPERDAEMON_READY "):
                ready = json.loads(line.split(" ", 1)[1])
                tok = ready["token"]
                break
        assert tok
        assert isinstance(ready["webview"], list)             # the window's web view arguments (gpus.window_args)
        req = urllib.request.Request("http://127.0.0.1:8796/api/v1/status", headers={"Authorization": "Bearer " + tok})
        assert json.load(urllib.request.urlopen(req, timeout=30))["version"]
        try:
            urllib.request.urlopen("http://127.0.0.1:8796/api/v1/status", timeout=30)
            raise AssertionError("an unpaired request was answered")
        except urllib.error.HTTPError as ex:
            assert ex.code == 401
        assert "webview" not in sys.modules                   # this process never loaded a window either
        time.sleep(0.5)
        assert p.poll() is None
    finally:
        if sys.platform == "win32":                       # the venv's python.exe starts the interpreter as its child
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        else:
            p.kill()
        p.wait(timeout=30)
