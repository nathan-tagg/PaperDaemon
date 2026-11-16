"""A text slot served by a COMMAND-LINE PROGRAM on this computer.

The slot's source is a command, WHOLE, as the user types it: the program's name or path, then the user's own
arguments. PaperDaemon runs it EXACTLY as typed, once for each turn of a job, and adds nothing to it: no argument, no
setting, nothing particular to any program. It is spoken to the plainest way there is:

    its input       the system text, then the conversation, as plain text
    a picture       a file in the run's own folder (the program's working folder), named in the words where the
                    picture is; the program opens it itself, as its command allows
    its answer      what it prints; with tools, the JSON object in what it prints ({"text", "tool_calls"})

Whatever else the program needs -- printing an answer and stopping, which model, how much effort, which of its own
tools it may use -- the user's command says. The program is run as it is installed and signed in by the user on this
computer; PaperDaemon reads, keeps and sends nothing of that (the maintainer, 11-15: no program-specific harness).
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid

from .. import paths
from .adapters import Adapter, AdapterError

RULES = ("\n\nHOW TO ANSWER: with one JSON object and nothing else, {\"text\": ..., \"tool_calls\": [{\"name\": ..., "
         "\"arguments\": {...}}]}. Every tool you use goes in tool_calls, in order: its name exactly as listed, and its "
         "arguments as that tool's own schema says. Put in text only what you would say besides the calls; leave it "
         "empty otherwise. The tools:\n")


# ------------------------------------------------------------------------------ the command
def split(command):
    """The command as typed -> [program, its own arguments...]."""
    try:
        parts = shlex.split(str(command or ""), posix=(os.name != "nt"))
    except ValueError:
        parts = str(command or "").split()
    return [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]


def name_of(command):
    """The program's plain name: `C:\\tools\\Thing.exe --fast` -> thing."""
    parts = split(command)
    return os.path.splitext(os.path.basename(parts[0]))[0].lower() if parts else ""


# THE ARGUMENT A COMMAND NAMED ITS MODEL WITH in the versions that kept a model beside the command (0.2.42 to 0.2.47).
# Read only to bring such a slot into today's shape; nothing running does.
_OLD_MODEL_ARG = "--model"


def model_of(command, legacy=False):
    """UPGRADES ONLY (`legacy`): the model a command of an earlier version names (`prog --model x`, `prog --model=x`),
    else "". PaperDaemon does not otherwise look for a model in a command: the command is the user's."""
    arg = _OLD_MODEL_ARG if legacy else ""
    own = split(command)[1:]
    for i, a in enumerate(own):
        if arg and a == arg and i + 1 < len(own):
            return own[i + 1]
        if arg and a.startswith(arg + "="):
            return a[len(arg) + 1:]
    return ""


def with_model(command, model):
    """A command and a model name an earlier version kept beside it -> the command as it is: the command is whole, and
    PaperDaemon knows no program's way of naming a model to add it."""
    return str(command or "").strip()


def find(command):
    """-> (the program's file or None, the user's own arguments): the command as a file, else on the PATH -- this
    process's, else the system's as it is NOW: a program installed after PaperDaemon started is on the latter only
    (11-15: a program installed while PaperDaemon ran, and its lineup's test said no answer)."""
    parts = split(command)
    if not parts:
        return None, []
    prog = os.path.expandvars(os.path.expanduser(parts[0]))
    hit = prog if os.path.isfile(prog) else (shutil.which(prog) or shutil.which(prog, path=_path_now()))
    return hit, parts[1:]


def _path_now():
    """The PATH as Windows holds it now (the user's, then the machine's), its %NAMES% filled in; elsewhere, this
    process's."""
    if os.name != "nt":
        return os.environ.get("PATH", "")
    import winreg
    out = []
    for root, key in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                out.append(os.path.expandvars(str(winreg.QueryValueEx(k, "Path")[0] or "")))
        except OSError:
            pass
    return os.pathsep.join(x for x in out if x) or os.environ.get("PATH", "")


def _run(exe, args, stdin=None, folder=None):
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000   # no console window
    try:
        return subprocess.run([exe] + list(args), input=stdin, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", cwd=folder or paths.sub("cache", "cli"), **kw)
    except OSError as ex:
        raise AdapterError("%s could not be started (%s)" % (os.path.basename(exe), ex))


def ready(command):
    """-> (True, "") when the program is found, else (False, why)."""
    if not find(command)[0]:
        return False, "the program `%s` was not found on this computer" % (split(command) or ["?"])[0]
    return True, ""


# ------------------------------------------------------------------------------ a request
def turns_of(messages, vision):
    """The conversation as turns, each its pictures and its words, every turn headed by whose it is. A turn is written
    the same way in every call of a job, so a later call begins exactly as the one before did and the provider reads
    that part from its cache. -> ([(pictures, words)], pictures dropped)."""
    out, dropped = [], 0
    alone = len(messages) == 1 and messages[0]["role"] == "user"
    for m in messages:
        role = m["role"]
        if role == "user":
            imgs = list(m.get("images") or [])
            if imgs and not vision:
                dropped, imgs = dropped + len(imgs), []
            out.append((imgs, "[THE USER'S SIDE]\n" + (m.get("text") or "")))
        elif role == "assistant":
            said = [m["text"]] if m.get("text") else []
            said += ["called %s(%s)" % (c["name"], json.dumps(c.get("arguments") or {}, ensure_ascii=False))
                     for c in m.get("tool_calls") or []]
            out.append(([], "[YOUR EARLIER TURN]\n" + "\n".join(said)))
        elif role == "tool":
            out.append(([], "[RESULT OF %s]\n%s" % (m.get("name") or "the call", m.get("text") or "")))
    if not alone:
        out.append(([], "[NOW] Take your next turn."))
    return out, dropped


class CommandLine(Adapter):
    """A command-line program on this computer, run once a call, exactly as the user typed it."""
    family = "cli"

    def __init__(self, url=None, key=None, harness=None):
        self.command = str(url or "").strip()
        self.base = self.api = self.command
        self.key, self.model, self.harness = None, "", harness    # (no model is kept: the command says its own)

    def models(self):
        if not find(self.command)[0]:
            raise AdapterError("the program `%s` was not found on this computer" % (split(self.command) or ["?"])[0])
        return []

    def health(self):
        return ready(self.command)[0]

    def request(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
                temperature=None, max_tokens=None, folder=None):
        """-> (arguments added to the command: none, what goes on its input, the system text, pictures dropped).
        `folder`: the run's folder, where its pictures are saved; without one no picture is sent."""
        caps = caps or {}
        turns, dropped = turns_of(messages, bool(caps.get("vision")) and folder is not None)
        system = system or "You are a helpful assistant."
        if tools:
            system += RULES + "\n".join("- %s: %s\n  arguments (JSON schema): %s" % (
                t["name"], (t.get("description") or "").strip(),
                json.dumps(t.get("parameters") or {}, ensure_ascii=False)) for t in tools)
            if force_tool:
                system += "\nAt least one call is required."
        # A PICTURE IS A FILE, named in the words where it is: the one way any program can be shown one
        words, k = [], 0
        for pics, said in turns:
            lines = []
            for png in pics:
                k += 1
                with open(os.path.join(folder, "picture-%d.png" % k), "wb") as f:
                    f.write(png)
                lines.append("[PICTURE: picture-%d.png, a file in the current folder; open it to see it]" % k)
            words.append("\n".join(lines + [said]))
        return [], system + "\n\n" + "\n\n".join(words), system, dropped

    @staticmethod
    def parse(out, tools, name="the program"):
        """What the program printed -> the neutral reply."""
        text = (out or "").strip()
        if not tools:
            return {"text": text, "tool_calls": [], "stop": "end_turn", "usage": {}}
        so = _json_in(text)
        if not (so.get("tool_calls") if isinstance(so, dict) else None):
            so = _invokes_in(text) or so
        names = {t["name"] for t in tools}
        calls = [{"id": "call_" + uuid.uuid4().hex[:12], "name": c.get("name"), "arguments": c.get("arguments") or {}}
                 for c in (so.get("tool_calls") or []) if isinstance(c, dict) and c.get("name") in names]
        said = so.get("text") if so else text
        return {"text": str(said or ""), "tool_calls": calls, "stop": "tool_use" if calls else "end_turn", "usage": {}}

    def chat(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
             temperature=None, max_tokens=None):
        exe, own = find(self.command)
        name = os.path.basename(exe) if exe else (split(self.command) or ["the program"])[0]
        if not exe:
            raise AdapterError("the program `%s` was not found on this computer" % name)
        folder = tempfile.mkdtemp(prefix="run-", dir=paths.sub("cache", "cli"))    # empty: nobody's project files
        try:
            args, stdin, system, dropped = self.request(system, messages, tools, force_tool, caps, harness,
                                                        temperature, max_tokens, folder=folder)
            p = _run(exe, own + args, stdin, folder)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        r = self.parse(p.stdout, tools, name)
        if p.returncode != 0 and not r["text"] and not r["tool_calls"]:
            raise AdapterError("%s stopped (%d): %s" % (name, p.returncode, ((p.stderr or "") + (p.stdout or ""))[-300:].strip()),
                               body=(p.stderr or "")[-600:])
        r["dropped_images"], r["forced_refused"] = dropped, False
        return r


def _invokes_in(text):
    """Calls a model wrote in the tool-call markup it was trained on instead of the JSON it was asked for:
    <invoke name="answer"><parameter name="lines">["..."]</parameter></invoke>. Each parameter's value is read as
    JSON when it is JSON, else as the text it is. -> {"text": "", "tool_calls": [...]}, or {} when there are none."""
    calls = []
    for m in re.finditer(r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>', str(text or ""), re.S):
        args = {}
        for pm in re.finditer(r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>', m.group(2), re.S):
            raw = pm.group(2).strip()
            try:
                args[pm.group(1)] = json.loads(raw)
            except ValueError:
                args[pm.group(1)] = raw
        calls.append({"name": m.group(1), "arguments": args})
    return {"text": "", "tool_calls": calls} if calls else {}


def _json_in(text):
    """The JSON object in a model's words: the words themselves, a fenced block, or the outermost braces."""
    t = str(text or "").strip()
    for cand in (t, re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t), t[t.find("{"):t.rfind("}") + 1] if "{" in t and "}" in t else ""):
        try:
            d = json.loads(cand)
        except ValueError:
            continue
        if isinstance(d, dict):
            return d
    return {}


__all__ = ["CommandLine", "find", "ready", "split", "name_of", "model_of", "with_model", "turns_of"]
