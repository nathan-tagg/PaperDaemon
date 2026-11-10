"""A text slot served by a COMMAND-LINE PROGRAM on this computer.

The slot's source is a command: the program's name or path, with any arguments of the user's own after it.
PaperDaemon runs it once for each turn of a job, hands it the request and reads what it prints. Nothing here knows
any one program. What is particular to a program is DATA, the `cli` field of the slot's harness:

    program, places   the program's usual name, and where its installers put it (tried when the command is not on
                      the PATH); a harness whose `program` is the command's is the one that speaks for it
    args              added to the command for every request: text with {placeholders}. A LIST inside the list is left
                      out whole when a placeholder in it has nothing to give, and when it begins with an argument
                      the user's own command already gives (`program --effort high` keeps the user's effort);
                      {"each_picture": [...]} is repeated for every picture of the request
    input             what goes on the program's input: text with placeholders, or {"json": a JSON value written on
                      one line, "text": how a turn's words are written in it, "picture": how a picture is} -- the
                      value "{parts}" in `json` becomes the list of them
    output            where the answer is in what the program prints: {"format": "text" | "json" | "json-lines",
                      "where": {field: value} (json-lines: the last line with these), "text": the answer's words,
                      "answer": a structured answer the program checked against {schema}, "error": true when the run
                      failed, "error_text": what it said, "usage": {"input", "output", "cached"}} -- each a dotted
                      path, a usage count a path or a list of paths added up
    ready             {"args": [...], "json": a dotted path that is true when the program is ready, "else": what to
                      tell the user when it is not} -- without it, a program that is found is ready
    sends_to          the host the program sends a page to, for the notices; without it the page stays here
    answer_rule       one sentence on how this program wants a structured answer given
    models            the names the program takes for its models, offered where a model is picked

    {model}                       the slot's model
    {system}  {system_file}       the system text, or a file holding it
    {prompt}  {prompt_file}       the conversation as plain text, or a file holding it
    {schema}  {schema_file}       the host's tools as one JSON schema for the answer, or a file holding it
    {picture_file}                a picture's file (in "each_picture" and in `input`'s "picture")
    {base64}  {media_type}        a picture's bytes and type (in `input`'s "picture")
    {text}                        a turn's words (in `input`'s "text")
    {request.a.b}                 a field of the request as the harness tuned it (its `request` field): an effort,
                                  a temperature, anything the program has an argument for

Without a `cli` field the program is spoken to the plainest way: the system text and the conversation on its input,
its answer what it prints. Every file a request needs is made in a folder of its own and removed after the run. The
program is run as it is installed, signed in by whoever signed it in: PaperDaemon reads, keeps and sends nothing of
that.
"""
import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid

from .. import paths
from .adapters import Adapter, AdapterError, _b64

ARGV_ROOM = 30000                          # a Windows command line holds 32,767 characters in all, quoted
PLAIN = {"args": [], "input": "{system}\n\n{prompt}", "output": {"format": "text"}}
HOLE = re.compile(r"\{([a-z_][a-z0-9_]*(?:\.[A-Za-z0-9_.\-]+)?)\}")
FILES = {"system_file": ("system", ".txt"), "prompt_file": ("prompt", ".txt"), "schema_file": ("schema", ".json")}
RULES = ("\n\nHOW TO ANSWER: with one JSON object and nothing else, {\"text\": ..., \"tool_calls\": [{\"name\": ..., "
         "\"arguments\": {...}}]}. Every tool you use goes in tool_calls, in order: its name exactly as listed, and its "
         "arguments as that tool's own schema says. Put in text only what you would say besides the calls; leave it "
         "empty otherwise.%s The tools:\n")


# ------------------------------------------------------------------------------ the command and its harness
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


def cli_of(harness, command):
    """How the command's program is spoken to: the harness's own `cli`, else that of the harness made for the
    program (by its `program`), else the plainest way."""
    own = getattr(harness, "cli", None) if harness is not None else None
    if own:
        return own
    from .. import harnesses
    name = name_of(command)
    for h in harnesses.for_kind("text"):
        c = getattr(h, "cli", None) or {}
        if name and str(c.get("program") or "").lower() == name:
            return c
    return PLAIN


def find(command, cli=None):
    """-> (the program's file or None, the user's own arguments). The command as a file, else on the PATH, else in
    the places the harness names for the program it is made for."""
    parts = split(command)
    if not parts:
        return None, []
    prog = os.path.expandvars(os.path.expanduser(parts[0]))
    hit = prog if os.path.isfile(prog) else shutil.which(prog)
    if not hit and cli and str(cli.get("program") or "").lower() == name_of(command):
        hit = next((p for p in (os.path.expandvars(os.path.expanduser(x)) for x in cli.get("places") or ())
                    if os.path.isfile(p)), None)
    return hit, parts[1:]


def _run(exe, args, stdin=None, folder=None):
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000   # no console window
    try:
        return subprocess.run([exe] + list(args), input=stdin, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", cwd=folder or paths.sub("cache", "cli"), **kw)
    except OSError as ex:
        raise AdapterError("%s could not be started (%s)" % (os.path.basename(exe), ex))


def _at(d, path):
    """A dotted path into what a program printed or into a request: `usage.output_tokens`."""
    for k in str(path or "").split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def ready(command, cli):
    """-> (True, "") when the program is found and says it is ready, else (False, why)."""
    exe, own = find(command, cli)
    if not exe:
        return False, "the program `%s` was not found on this computer" % (split(command) or ["?"])[0]
    chk = cli.get("ready") or {}
    if not chk.get("args"):
        return True, ""
    try:
        p = _run(exe, list(chk["args"]))
    except AdapterError as ex:
        return False, str(ex)
    try:
        d = json.loads(p.stdout or "{}")
    except ValueError:
        d = {}
    if chk.get("json"):
        ok = bool(_at(d, chk["json"]))
    else:
        ok = p.returncode == 0
    return (True, "") if ok else (False, str(chk.get("else") or "%s is not ready" % os.path.basename(exe)))


# ------------------------------------------------------------------------------ a request
def schema_of(tools, force, loose=False):
    """The host's tools as one schema for a structured answer. `loose`: each call's arguments only an object (a
    schema too long for a command line; the tools' own schemas then go in the system text)."""
    calls = []
    for t in tools:
        params = t.get("parameters") or {"type": "object", "properties": {}}
        calls.append({"type": "object", "description": (t.get("description") or "")[:1000 if not loose else 200],
                      "properties": {"name": {"const": t["name"]}, "arguments": {"type": "object"} if loose else params},
                      "required": ["name", "arguments"]})
    arr = {"type": "array", "items": {"anyOf": calls} if len(calls) > 1 else calls[0]}
    if force:
        arr["minItems"] = 1
    return {"type": "object", "properties": {"text": {"type": "string"}, "tool_calls": arr}, "required": ["tool_calls"]}


def turns_of(messages, vision):
    """The conversation as turns, each its pictures and its words; an earlier turn is headed by whose it was, so a
    later request begins with the same turns. -> ([(pictures, words)], pictures dropped)."""
    out, dropped = [], 0
    alone = len(messages) == 1 and messages[0]["role"] == "user"
    for m in messages:
        role = m["role"]
        if role == "user":
            imgs = list(m.get("images") or [])
            if imgs and not vision:
                dropped, imgs = dropped + len(imgs), []
            out.append((imgs, (m.get("text") or "") if alone else "[THE USER'S SIDE]\n" + (m.get("text") or "")))
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


def _fill(text, values):
    """Text with its {placeholders} filled -> (text, False when one it uses has nothing to give). A name that is no
    placeholder stays as written."""
    whole = [True]

    def put(m):
        k = m.group(1)
        if k not in values:
            return m.group(0)
        v = values[k]() if callable(values[k]) else values[k]
        if v in (None, ""):
            whole[0] = False
            return ""
        return str(v)
    return HOLE.sub(put, str(text)), whole[0]


def _fill_json(v, values, parts):
    if isinstance(v, str):
        return parts if v == "{parts}" else _fill(v, values)[0]
    if isinstance(v, list):
        return [_fill_json(x, values, parts) for x in v]
    if isinstance(v, dict):
        return {k: _fill_json(x, values, parts) for k, x in v.items()}
    return v


class CommandLine(Adapter):
    """A command-line program on this computer, run once a call."""
    family = "cli"

    def __init__(self, url=None, key=None, model="", harness=None):
        self.command = str(url or "").strip()
        self.base = self.api = self.command
        self.key, self.model, self.harness = None, model or "", harness

    def cli(self, harness=None):
        return cli_of(harness if harness is not None else self.harness, self.command)

    def models(self):
        cli = self.cli()
        if not find(self.command, cli)[0]:
            raise AdapterError("the program `%s` was not found on this computer" % (split(self.command) or ["?"])[0])
        return list(cli.get("models") or [])

    def health(self):
        return ready(self.command, self.cli())[0]

    def request(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
                temperature=None, max_tokens=None, folder=None):
        """-> (the program's arguments after the user's own, what goes on its input, the system text, pictures
        dropped). `folder`: where the request's files are made; without one a file's placeholder gives nothing."""
        caps = caps or {}
        own = set(split(self.command)[1:])                        # what the user typed after the program's name
        cli = self.cli(harness)
        body = {"model": self.model}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if harness is not None:
            body = harness.tune(body, caps)
        args_spec = list(cli.get("args") or [])
        inp = cli.get("input", PLAIN["input"])
        used = set(HOLE.findall(json.dumps([args_spec, inp])))
        takes_pictures = (isinstance(inp, dict) and bool(inp.get("picture"))) or any(isinstance(a, dict) for a in args_spec)
        turns, dropped = turns_of(messages, bool(caps.get("vision")) and takes_pictures)
        system = system or "You are a helpful assistant."
        schema = ""
        if tools:
            listed = "\n".join("- %s: %s" % (t["name"], (t.get("description") or "").strip()) for t in tools)
            detailed = "\n".join("- %s: %s\n  arguments (JSON schema): %s" % (
                t["name"], (t.get("description") or "").strip(),
                json.dumps(t.get("parameters") or {}, ensure_ascii=False)) for t in tools)
            checked = bool(used & {"schema", "schema_file"})        # the program checks the answer against the schema
            schema = json.dumps(schema_of(tools, force_tool), ensure_ascii=True, separators=(",", ":"))
            if "schema" in used and "schema_file" not in used and len(subprocess.list2cmdline([schema])) + 2000 > ARGV_ROOM:
                # too long for a command line: the calls' arguments unchecked by the program, each tool's schema said
                schema = json.dumps(schema_of(tools, force_tool, loose=True), ensure_ascii=True, separators=(",", ":"))
                checked = False
            rule = (" " + str(cli["answer_rule"]).strip()) if cli.get("answer_rule") else ""
            system += (RULES % rule) + (listed if checked else detailed)
            if force_tool and not checked:
                system += "\nAt least one call is required."
        prompt = "\n\n".join(words for _pics, words in turns)
        made = {}

        def file_of(key):
            def give():
                what, ext = FILES[key]
                content = {"system": system, "prompt": prompt, "schema": schema}[what]
                if folder is None or not content:
                    return ""
                if key not in made:
                    made[key] = os.path.join(folder, what + ext)
                    with open(made[key], "w", encoding="utf-8") as f:
                        f.write(content)
                return made[key]
            return give
        values = {"model": self.model, "system": system, "prompt": prompt, "schema": schema}
        values.update({k: file_of(k) for k in FILES})
        for k in used:
            if k.startswith("request."):
                v = _at(body, k[len("request."):])
                values[k] = "" if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else str(v).lower()
                                                  if isinstance(v, bool) else v)
        pictures = []                                             # (file or "", bytes), in the order of the turns

        def picture_file(png):
            if folder is None:
                return ""
            p = os.path.join(folder, "picture-%d.png" % (len([x for x in pictures if x[0]]) + 1))
            with open(p, "wb") as f:
                f.write(png)
            return p
        wants_files = "picture_file" in used
        for pics, _words in turns:
            for png in pics:
                pictures.append((picture_file(png) if wants_files else "", png))
        args = []
        for a in args_spec:
            if isinstance(a, dict):
                for path, _png in pictures:
                    args += [_fill(x, dict(values, picture_file=path))[0] for x in a.get("each_picture") or []]
            elif isinstance(a, list):
                if a and a[0] in own:
                    continue                                      # the user's own argument stands; the harness's is left out
                filled = [_fill(x, values) for x in a]
                if all(ok for _t, ok in filled):
                    args += [t for t, _ok in filled]
            else:
                args.append(_fill(a, values)[0])
        if isinstance(inp, dict):
            parts, k = [], 0
            for pics, words in turns:
                for png in pics:
                    path = pictures[k][0]
                    k += 1
                    parts.append(_fill_json(copy.deepcopy(inp.get("picture")), dict(
                        values, base64=_b64(png), media_type="image/png", picture_file=path), None))
                parts.append(_fill_json(copy.deepcopy(inp.get("text", "{text}")), dict(values, text=words), None))
            stdin = json.dumps(_fill_json(copy.deepcopy(inp.get("json", "{parts}")), values, parts), ensure_ascii=False) + "\n"
        else:
            stdin = _fill(inp, values)[0] if inp else None
        return args, stdin, system, dropped

    @staticmethod
    def parse(out, tools, cli=None, name="the program"):
        """What the program printed -> the neutral reply."""
        spec = (cli or PLAIN).get("output") or {"format": "text"}
        fmt = spec.get("format") or "text"
        d = None
        if fmt == "json":
            try:
                d = json.loads(out or "")
            except ValueError:
                d = None
        elif fmt == "json-lines":
            where = spec.get("where") or {}
            for line in (out or "").splitlines():
                try:
                    x = json.loads(line)
                except ValueError:
                    continue
                if isinstance(x, dict) and all(x.get(k) == v for k, v in where.items()):
                    d = x
        if fmt != "text" and not isinstance(d, dict):
            raise AdapterError("%s gave no answer" % name, body=(out or "")[-600:])
        if d is not None and spec.get("error") and _at(d, spec["error"]):
            raise AdapterError("%s: %s" % (name, str(_at(d, spec.get("error_text") or spec.get("text") or "") or "an error")[:300]),
                               body=json.dumps(d)[:600])
        text = (out or "").strip() if d is None else str(_at(d, spec.get("text") or "") or "")
        usage = {}
        for k, path in (spec.get("usage") or {}).items():
            vals = [_at(d, p) for p in (path if isinstance(path, list) else [path])] if d is not None else []
            usage[k] = sum(int(v or 0) for v in vals) if any(v is not None for v in vals) else None
        if not tools:
            return {"text": text, "tool_calls": [], "stop": "end_turn", "usage": usage}
        so = _at(d, spec.get("answer")) if d is not None and spec.get("answer") else None
        if not isinstance(so, dict):
            so = _json_in(text)
        names = {t["name"] for t in tools}
        calls = [{"id": "call_" + uuid.uuid4().hex[:12], "name": c.get("name"), "arguments": c.get("arguments") or {}}
                 for c in (so.get("tool_calls") or []) if isinstance(c, dict) and c.get("name") in names]
        said = so.get("text") if so else text
        return {"text": str(said or ""), "tool_calls": calls, "stop": "tool_use" if calls else "end_turn", "usage": usage}

    def chat(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
             temperature=None, max_tokens=None):
        cli = self.cli(harness)
        exe, own = find(self.command, cli)
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
        try:
            r = self.parse(p.stdout, tools, cli, name)
        except AdapterError as ex:
            if "gave no answer" not in str(ex):
                raise                                 # the program said what went wrong (a limit reached, a refusal)
            ok, why = ready(self.command, cli)
            raise AdapterError(why if not ok else "%s stopped (%d): %s" % (
                name, p.returncode, ((p.stderr or "") + (p.stdout or ""))[-300:].strip()), body=(p.stderr or "")[-600:])
        if (cli.get("output") or {}).get("format", "text") == "text" and p.returncode != 0 and not r["text"]:
            raise AdapterError("%s stopped (%d): %s" % (name, p.returncode, (p.stderr or "")[-300:].strip()))
        r["dropped_images"], r["forced_refused"] = dropped, False
        return r


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


__all__ = ["CommandLine", "cli_of", "find", "ready", "split", "name_of", "schema_of", "turns_of", "PLAIN"]
