"""The tablet's own typefaces, taken from the reMarkable desktop app installed on this computer.

Typed text on a page is set in reMarkable Sans and reMarkable Serif Small. Those faces belong to reMarkable and
PaperDaemon does not ship them; the desktop app (which every PaperDaemon user has, since the login comes from it)
carries them inside its program file. `extract()` finds each embedded TrueType file there and copies it, unchanged,
into PaperDaemon's content folder (rm-fonts), named by the face's own PostScript name. They never leave the
computer. Without the desktop app the pages are drawn with the older lettering model, as before.
"""

import os
import re
import struct

from .. import paths

_TAG = re.compile(rb"[A-Za-z0-9/ ]{4}")


def app_programs():
    """Where the desktop app's program file may be, most likely first."""
    out = []
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles(x86)")):
        if root:
            out.append(os.path.join(root, "reMarkable", "reMarkable.exe"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        out.append(os.path.join(local, "Programs", "reMarkable", "reMarkable.exe"))
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


def extract(dest=None, programs=None):
    """Copy the faces out of the first desktop app found into `dest` (default: the content folder's rm-fonts).
    Faces already there are left alone. -> the number of faces written (0 when there is no app)."""
    import mmap
    dest = dest or paths.fonts_dir()
    for exe in programs or app_programs():
        if not os.path.isfile(exe):
            continue
        with open(exe, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
            found = _fonts_in(data)
            if not found:
                continue
            os.makedirs(dest, exist_ok=True)
            wrote = 0
            for off, ln in found:
                blob = bytes(data[off:off + ln])
                name = _ps_name(blob)
                if not name or not name.startswith("reMarkable"):
                    continue
                path = os.path.join(dest, name + ".ttf")
                if os.path.isfile(path):
                    continue
                tmp = path + ".part"
                with open(tmp, "wb") as out:
                    out.write(blob)
                os.replace(tmp, path)
                wrote += 1
            return wrote
    return 0
