"""Start scripts: how a model server is started on this computer. The script is PaperDaemon's extension
point -- whatever it does is the user's choice, and PaperDaemon does not second-guess it.

THE START-SCRIPT CONTRACT

When it runs. Before a model call, when PaperDaemon's own server for that model is not running (the
processes the script started have all ended, or the script never ran). Never while a model call is in
progress: a script waits until the calls in flight have finished. One script at a time.

What it gets. The script runs with its own folder as the working directory and these variables:
    PAPERDAEMON_ROLE            text or image
    PAPERDAEMON_LOCATION        the slot's location, e.g. http://127.0.0.1:8790
    PAPERDAEMON_HOST            the location's host name, e.g. 127.0.0.1
    PAPERDAEMON_PORT            the location's port, e.g. 8790
    PAPERDAEMON_OTHER_LOCATION  the other slot's location (empty when it has none), so a script can
                                wait for the other model to go idle, or stop it
    PAPERDAEMON_LINEUP          the name of the lineup the slot belongs to
    PAPERDAEMON_DATA            PaperDaemon's data folder

What PaperDaemon waits for. Either the location answers while something the script started is still
running (the usual case: the script runs its server in the foreground), or the script exits with code
0 and the location answers (a script that hands its server to something outside PaperDaemon, such as a
service or a container; it should check first and exit fast, because it runs before every call). There
is no time limit: the wait lasts as long as the script, or something it started, is alive.

What a failure shows. The script's last lines of output, with its exit code.

When it ends. PaperDaemon ends what the script started when PaperDaemon quits or is paused, and at no other time
(on Windows the processes run in a kill-on-close job object). Stopping another program's server, to
make room on the graphics card, is the script's own business: the text script can stop the image
server and the image script the text server.

PaperDaemon ships no start scripts: the user writes their own in <data>/start-scripts/.
"""
import os
import sys

from . import paths

def folder():
    return paths.sub("start-scripts")


def path_of(m):
    """The file a slot's `script` names (a name in the start-scripts folder, or a full path), or None."""
    name = str(m.get("script") or "").strip().strip('"')
    if not name:
        return None
    return name if os.path.isabs(name) else os.path.join(folder(), name)


def text_of(m):
    """The text of a slot's start script: its file's, else its inline text, else ""."""
    p = path_of(m)
    if p:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    return str(m.get("script_text") or "")


def has_script(m):
    return bool(str(m.get("script") or "").strip() or str(m.get("script_text") or "").strip())


def identity(m):
    """What a slot's start script IS, to tell whether the one running is the one a job needs: its file (by
    path) or its inline text (by content), with the location it serves. "" when the slot has none."""
    import hashlib
    p = path_of(m)
    if p:
        what = "file:" + os.path.normcase(os.path.abspath(p))
    else:
        text = str(m.get("script_text") or "")
        if not text.strip():
            return ""
        what = "text:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    return what + "@" + str(m.get("location") or "").strip()


def runnable(role, m):
    """The path of the script to run for a slot: its file, or its inline text written to
    <data>/launch/<role>.cmd (or .sh). None when the slot has no start script."""
    p = path_of(m)
    if p:
        if not os.path.isfile(p):
            raise FileNotFoundError("the start script %s does not exist" % p)
        return p
    text = str(m.get("script_text") or "")
    if not text.strip():
        return None
    win = sys.platform == "win32"
    path = os.path.join(paths.sub("launch"), "%s.%s" % (role, "cmd" if win else "sh"))
    with open(path, "w", encoding="utf-8", newline="\r\n" if win else "\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    return path
