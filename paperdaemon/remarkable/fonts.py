"""The tablet's own typefaces, taken from the reMarkable desktop app installed on this computer.

Typed text on a page is set in reMarkable Sans and reMarkable Serif Small, and a book that names no face is set in
the app's EB Garamond. Those faces are not PaperDaemon's to ship; the desktop app (which every PaperDaemon user has,
since the login comes from it) carries them inside its program file. `extract()` finds each embedded TrueType file
there and copies it, unchanged, into PaperDaemon's content folder (rm-fonts), named by the face's own PostScript name.
They never leave the computer. Without the desktop app typed text is drawn with the older lettering model, and books
are set in the published EB Garamond (books.py says so).
"""

import os
import re
import struct
import sys

from .. import paths

_TAG = re.compile(rb"[A-Za-z0-9/ ]{4}")


def _installed_at():
    """THE APP WHEREVER IT WAS INSTALLED: the folders Windows records for its uninstaller (every user and this one,
    both registry views), and the program of an app that is running now."""
    out = []
    if sys.platform != "win32":
        return out
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                try:
                    root = winreg.OpenKey(hive, sub)
                except OSError:
                    continue
                with root:
                    for i in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                                name = str(winreg.QueryValueEx(k, "DisplayName")[0])
                                if not name.lower().startswith("remarkable"):
                                    continue
                                for v in ("InstallLocation", "DisplayIcon"):
                                    try:
                                        p = str(winreg.QueryValueEx(k, v)[0]).split(",")[0].strip('"')
                                    except OSError:
                                        continue
                                    # the folder, or a program in it (the icon may be its maintenance tool's)
                                    folder = os.path.dirname(p) if p.lower().endswith(".exe") else p
                                    out.append(os.path.join(folder, "reMarkable.exe"))
                        except OSError:
                            continue
    except ImportError:
        pass
    try:
        import subprocess
        got = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-Process reMarkable -ErrorAction SilentlyContinue | Select-Object -First 1).Path"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        if got:
            out.append(got)
    except (OSError, subprocess.SubprocessError):
        pass
    return out


def app_programs():
    """Where the desktop app's program file may be, most likely first: the usual folders, then wherever Windows says
    it was installed or it is running from."""
    out = []
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles(x86)")):
        if root:
            out.append(os.path.join(root, "reMarkable", "reMarkable.exe"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        out.append(os.path.join(local, "Programs", "reMarkable", "reMarkable.exe"))
    if not any(os.path.isfile(p) for p in out):
        out += _installed_at()
    seen, uniq = set(), []
    for p in out:
        if p.lower() not in seen:
            seen.add(p.lower())
            uniq.append(p)
    return uniq


def _fonts_in(data):
    """Every complete TrueType/OpenType file inside `data` -> [(offset, length)]: a font header (version 1.0 or
    OTTO) followed by a table directory whose records are all real tags, with cmap and outlines among them."""
    out = []
    for sig in (b"\x00\x01\x00\x00", b"OTTO"):
        i = data.find(sig)
        while i >= 0:
            n = struct.unpack(">H", data[i + 4:i + 6])[0] if i + 6 <= len(data) else 0
            if 4 <= n <= 64 and i + 12 + 16 * n <= len(data):
                tags, end = [], 0
                for k in range(n):
                    tag, _cs, off, ln = struct.unpack(">4sIII", data[i + 12 + 16 * k:i + 28 + 16 * k])
                    if not _TAG.fullmatch(tag):
                        tags = None
                        break
                    tags.append(tag)
                    end = max(end, off + ln)
                if tags and b"cmap" in tags and b"name" in tags and (b"glyf" in tags or b"CFF " in tags) \
                        and 0 < end <= 50_000_000 and i + end <= len(data):
                    out.append((i, end))
            i = data.find(sig, i + 1)
    return out


def _ps_name(font_bytes):
    """The face's PostScript name (name id 6), or None."""
    import io
    from fontTools.ttLib import TTFont
    try:
        with TTFont(io.BytesIO(font_bytes), lazy=True) as f:
            n = f["name"].getDebugName(6) or f["name"].getDebugName(4)
    except Exception:
        return None
    n = re.sub(r"[^A-Za-z0-9_-]", "", str(n or ""))
    return n or None


# The faces taken: reMarkable's own, and the app's EB Garamond, the face a book is set in when it names none. The app
# keeps EB Garamond packed among its Qt resources (variable fonts: EBGaramond-Regular and EBGaramond-Italic); it is the
# app's own build, which no published EB Garamond matches table for table, so books are laid out exactly only with it.
WANTED = ("reMarkable", "EBGaramond")


def extract(dest=None, programs=None):
    """Copy the faces out of the first desktop app found into `dest` (default: the content folder's rm-fonts), from
    the program file and the Qt resources packed in it. Faces already there are left alone. -> the number of faces
    written (0 when there is no app)."""
    from .templates import _blobs
    dest = dest or paths.fonts_dir()
    for exe in programs or app_programs():
        if not os.path.isfile(exe):
            continue
        with open(exe, "rb") as fh:
            data = fh.read()
        found = [(blob, off, ln) for blob in _blobs(data) for off, ln in _fonts_in(blob)]
        if not found:
            continue
        os.makedirs(dest, exist_ok=True)
        wrote = 0
        for blob, off, ln in found:
            face = bytes(blob[off:off + ln])
            name = _ps_name(face)
            if not name or not name.startswith(WANTED):
                continue
            path = os.path.join(dest, name + ".ttf")
            if os.path.isfile(path):
                continue
            tmp = path + ".part"
            with open(tmp, "wb") as out:
                out.write(face)
            os.replace(tmp, path)
            wrote += 1
        return wrote
    return 0
