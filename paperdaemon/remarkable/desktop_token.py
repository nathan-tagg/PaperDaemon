"""The reMarkable desktop app's login on this computer: PaperDaemon's only way to get a device token.

reMarkable offers no way to register a device or get a code from its website, so PaperDaemon takes the
login of the reMarkable desktop app the user has signed in to. The app keeps it with Qt's QSettings, on
Windows in the registry under HKEY_CURRENT_USER\\Software\\reMarkable\\desktop:

- `devicetoken`: the device token, wrapped as @ByteArray(...) (auth.set_device_token unwraps it);
- `UserToken`: the short-lived session token the app made from it.

Two ways to take it:

- borrow: copy the device token into PaperDaemon's credential entry. Both then share one device, and the
  cloud keeps one notification channel per device, so the two cannot work at the same time.
- steal: copy it, then remove both values from the app's settings. The app is signed out; logging in to it
  again makes it a device of its own. Nothing else the app keeps is touched, and nothing on the tablet or in
  the cloud changes.

The token goes straight to the credential store; it is never written to a file or a log. Every registry
access goes through `_registry()`, so a test can put a stand-in in its place.
"""
import subprocess
import sys

KEYS = (r"Software\reMarkable\desktop", r"Software\reMarkable\reMarkable")
NAMES = ("devicetoken", "deviceToken", "DeviceToken")
LOGIN_VALUES = ("devicetoken", "UserToken")          # what steal removes, and nothing else
APP_EXE = "reMarkable.exe"


def _registry():
    """The registry module (winreg), or None off Windows."""
    if sys.platform != "win32":
        return None
    import winreg
    return winreg


def _clean(v):
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    v = str(v or "").strip()
    return v or None


def _locate():
    """(key path, value name, token) of the app's device token, or None."""
    reg = _registry()
    if reg is None:
        return None
    for path in KEYS:
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, path) as k:
                for n in NAMES:
                    try:
                        v, _kind = reg.QueryValueEx(k, n)
                    except OSError:
                        continue
                    if _clean(v):
                        return path, n, _clean(v)
        except OSError:
            continue
    return None


def find():
    """The desktop app's device token, or None when the app is not installed or not signed in."""
    hit = _locate()
    return hit[2] if hit else None


def app_running():
    """True while the reMarkable desktop app runs (it would write its login back when it quits)."""
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % APP_EXE, "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except OSError:
        return False
    return APP_EXE.lower() in out.lower()


def remove_login():
    """Remove the app's login (LOGIN_VALUES) from the key that holds its device token. -> the names removed."""
    hit = _locate()
    reg = _registry()
    if not hit or reg is None:
        return []
    removed = []
    with reg.OpenKey(reg.HKEY_CURRENT_USER, hit[0], 0, reg.KEY_SET_VALUE | reg.KEY_QUERY_VALUE) as k:
        for name in (hit[1],) + tuple(n for n in LOGIN_VALUES if n != hit[1]):
            try:
                reg.DeleteValue(k, name)
                removed.append(name)
            except OSError:
                pass
    return removed
