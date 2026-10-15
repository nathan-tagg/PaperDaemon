"""Screenshots of PaperDaemon's screens, taken headless, for checking the UI without opening a window.

    uv run python tools/ui_shot.py [--port 8799] [--out FOLDER] [pane ...]

Starts the engine in this process on a test port with a throwaway data folder (never port 8770, never
the user's settings), renders each pane with Microsoft Edge in headless mode under a throwaway browser
profile, and stops. Panes: tablet, search, models, network (default: all). Prints the image paths.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
PANES = ("tablet", "search", "models", "network")


def _throwaway_keyring():
    """Secrets for this run live in memory, so the screenshots never touch the real credential store."""
    import keyring
    import keyring.backend
    import keyring.errors

    class Memory(keyring.backend.KeyringBackend):
        priority = 1
        store = {}

        def get_password(self, service, name):
            return self.store.get((service, name))

        def set_password(self, service, name, value):
            self.store[(service, name)] = value

        def delete_password(self, service, name):
            if self.store.pop((service, name), None) is None:
                raise keyring.errors.PasswordDeleteError("not set")
    keyring.set_keyring(Memory())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--out", help="where the screenshots go (default: a new temporary folder)")
    ap.add_argument("--settings", help="a JSON file merged over the defaults, to show a configured state")
    ap.add_argument("--signed-in", action="store_true", help="a stand-in login in the throwaway store, so the "
                    "screens show instead of the first-run setup")
    ap.add_argument("--console", action="store_true", help="print each page's console messages")
    ap.add_argument("--mirror-building", type=int, metavar="PERCENT", help="show the Mirror as building, this far along")
    ap.add_argument("--pull-error", metavar="TEXT", help="show the last Mirror download as failed with this error")
    ap.add_argument("panes", nargs="*", default=list(PANES))
    a = ap.parse_args()
    if a.port == 8770:
        sys.exit("8770 is PaperDaemon's own port; use a test port")
    edge = next((p for p in EDGE if os.path.exists(p)), None)
    if not edge:
        sys.exit("Microsoft Edge was not found")

    home = tempfile.mkdtemp(prefix="paperdaemon-shot-home-")
    os.environ["PAPERDAEMON_HOME"] = home
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _throwaway_keyring()
    from paperdaemon import server, settings
    s = settings.load()
    if a.settings:
        with open(a.settings, encoding="utf-8") as f:
            s = settings._merge(s, json.load(f))
    s["server"]["port"] = a.port
    settings.save(s)
    if a.signed_in:
        from paperdaemon import vault
        from paperdaemon.remarkable import auth
        vault.put(auth.DEVICE_KEY, "header.e30.signature")
    if a.mirror_building is not None:                # a stand-in pull, never started: the screens' building state
        server._pull.update(running=True, documents=a.mirror_building, documents_total=100, files=a.mirror_building * 3,
                            bytes=a.mirror_building * 80_000_000, bytes_total=8_000_000_000)
    if a.pull_error:
        server._pull.update(running=False, error=a.pull_error)
    servers = server.serve(a.port, ["127.0.0.1"])
    if not server.wait_up(a.port):
        sys.exit("the engine did not start on port %d" % a.port)
    profile = tempfile.mkdtemp(prefix="paperdaemon-shot-edge-")
    a.out = a.out or tempfile.mkdtemp(prefix="paperdaemon-shots-")
    os.makedirs(a.out, exist_ok=True)
    try:
        for pane in a.panes:
            shot = os.path.join(a.out, "%s.png" % pane)
            url = "http://127.0.0.1:%d/#pair=%s&pane=%s" % (a.port, server.pairing_token(), pane)
            r = subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                                "--user-data-dir=" + profile, "--window-size=1160,1400",
                                "--virtual-time-budget=4000", "--screenshot=" + shot]
                               + (["--enable-logging=stderr", "--v=0"] if a.console else []) + [url],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE if a.console else subprocess.DEVNULL,
                               timeout=120)
            if a.console:                            # the page's console messages: errors in the screens
                for ln in (r.stderr or b"").decode("utf-8", "replace").splitlines():
                    if "CONSOLE" in ln:
                        print("  " + ln.split("] ", 1)[-1][:300])
            print(shot)
    finally:
        for srv in servers:
            srv.should_exit = True
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
