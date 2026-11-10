"""A text slot served by Claude Code, the command-line program installed on this computer.

PaperDaemon starts the program as it is published (`claude -p`, its own non-interactive mode), hands it one request
and reads what it prints. It never reads, stores or sends the program's sign-in: Claude Code signs in by itself, as
the person who signed it in, and the use is theirs under their own agreement with Anthropic. Nothing of the program
is changed or bundled.

One call of the adapter is one run of the program, with nothing kept between runs:

    its tools      none (--tools ""), no MCP servers (--strict-mcp-config), no settings files or hooks of the
                   user's (--setting-sources ""), no session saved (--no-session-persistence)
    the system     the host's own, in place of Claude Code's (--system-prompt-file; the file is removed after)
    the request    the conversation as one user message on the program's input (stream-json), each earlier turn a
                   block of its own, so a later turn's request begins with the same blocks; pictures as pictures
    a tool call    the host's tools become one JSON schema (--json-schema): the model answers with
                   {"text", "tool_calls": [{"name", "arguments"}]}, each call checked against its tool's own schema
    model, effort  --model and --effort; the effort is the harness's to set, as `output_config.effort` in its
                   `request` -- the field the Messages API itself takes, so one harness serves both
"""
import json
import os
import shutil
import subprocess
import tempfile
import uuid

from .. import paths
from .adapters import Adapter, AdapterError, _b64

WHERE = "https://api.anthropic.com/claude-code"       # the slot's location: where its pages go, for every notice
ARGV_ROOM = 30000                                     # a Windows command line holds 32,767 characters in all, quoted
EFFORTS = ("low", "medium", "high", "xhigh", "max")
RULES = ("\n\nHOW TO ANSWER: answer only through StructuredOutput. Every tool you use goes in tool_calls, in order: its "
         "name exactly as listed, and its arguments as that tool's own schema says. Put in text only what you would "
         "say besides the calls; leave it empty otherwise. The tools:\n")


def program():
    """The Claude Code program on this computer, or None: on the PATH, else where its installers put it."""
    home = os.path.expanduser("~")
    places = [shutil.which("claude"),
              os.path.join(home, ".local", "bin", "claude.exe"), os.path.join(home, ".local", "bin", "claude"),
              os.path.join(os.environ.get("APPDATA") or "", "npm", "claude.cmd"),
              "/usr/local/bin/claude", "/opt/homebrew/bin/claude"]
    return next((p for p in places if p and os.path.isfile(p)), None)


def _run(args, stdin=None):
    exe = program()
    if not exe:
        raise AdapterError("Claude Code is not installed on this computer (no `claude` program was found)")
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000              # no console window
    folder = paths.sub("cache", "claude-cli")         # an empty folder: no project instructions of anyone's
    try:
        return subprocess.run([exe] + args, input=stdin, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", cwd=folder, **kw)
    except OSError as ex:
        raise AdapterError("Claude Code could not be started (%s)" % ex)


def signed_in():
    """-> (True, "") when the program says it is signed in, else (False, why)."""
    try:
        p = _run(["auth", "status"])
    except AdapterError as ex:
        return False, str(ex)
    try:
        d = json.loads(p.stdout or "{}")
    except ValueError:
        d = {}
    if d.get("loggedIn"):
        return True, ""
    return False, "Claude Code is not signed in on this computer: run `claude` once and sign in"


def schema_of(tools, force, loose=False):
    """The host's tools as one schema for the program's structured output. `loose`: each call's arguments only an
    object (a schema too long for a command line; the tools' own schemas then go in the system text)."""
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


def blocks_of(messages, vision):
    """The conversation as the content of one user message: each turn a block of its own (a later request begins
    with the same blocks), pictures as pictures. -> (blocks, pictures dropped)."""
    out, dropped = [], 0
    alone = len(messages) == 1 and messages[0]["role"] == "user"
    for m in messages:
        role = m["role"]
        if role == "user":
            imgs = list(m.get("images") or [])
            if imgs and not vision:
                dropped, imgs = dropped + len(imgs), []
            out += [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(i)}}
                    for i in imgs]
            out.append({"type": "text", "text": (m.get("text") or "") if alone else "[THE USER'S SIDE]\n" + (m.get("text") or "")})
        elif role == "assistant":
            said = [m["text"]] if m.get("text") else []
            said += ["called %s(%s)" % (c["name"], json.dumps(c.get("arguments") or {}, ensure_ascii=False))
                     for c in m.get("tool_calls") or []]
            out.append({"type": "text", "text": "[YOUR EARLIER TURN]\n" + "\n".join(said)})
        elif role == "tool":
            out.append({"type": "text", "text": "[RESULT OF %s]\n%s" % (m.get("name") or "the call", m.get("text") or "")})
    if not alone:
        out.append({"type": "text", "text": "[NOW] Take your next turn."})
    return out, dropped


class ClaudeCLI(Adapter):
    """Claude Code on this computer, run once a call."""
    family = "claude-cli"

    def __init__(self, url=None, key=None, model=""):
        super().__init__(url or WHERE, None, model)

    def models(self):
        if not program():
            raise AdapterError("Claude Code is not installed on this computer (no `claude` program was found)")
        return ["opus", "sonnet", "haiku"]            # the program's own names for the newest of each

    def health(self):
        return bool(program()) and signed_in()[0]

    def request(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
                temperature=None, max_tokens=None):
        """-> (arguments for the program, what goes on its input, the system text, pictures dropped)."""
        caps = caps or {}
        body = {"model": self.model}
        if harness is not None:
            body = harness.tune(body, caps)
        effort = str((body.get("output_config") or {}).get("effort") or body.get("effort") or "").lower()
        blocks, dropped = blocks_of(messages, bool(caps.get("vision")))
        args = ["-p", "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
                "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
        if body.get("model"):
            args += ["--model", str(body["model"])]
        if effort in EFFORTS:
            args += ["--effort", effort]
        system = system or "You are a helpful assistant."
        if tools:
            schema = json.dumps(schema_of(tools, force_tool), ensure_ascii=True, separators=(",", ":"))
            listed = "\n".join("- %s: %s" % (t["name"], (t.get("description") or "").strip()) for t in tools)
            if len(subprocess.list2cmdline(args + ["--json-schema", schema])) > ARGV_ROOM:
                # too long for a command line: the calls' arguments unchecked by the program, each tool's schema said
                schema = json.dumps(schema_of(tools, force_tool, loose=True), ensure_ascii=True, separators=(",", ":"))
                listed = "\n".join("- %s: %s\n  arguments (JSON schema): %s" % (
                    t["name"], (t.get("description") or "").strip(),
                    json.dumps(t.get("parameters") or {}, ensure_ascii=False)) for t in tools)
            system += RULES + listed
            args += ["--json-schema", schema]
        stdin = json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}, ensure_ascii=False) + "\n"
        return args, stdin, system, dropped

    @staticmethod
    def parse(out, tools):
        """What the program printed (one JSON object a line) -> the neutral reply."""
        result = None
        for line in (out or "").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("type") == "result":
                result = d
        if result is None:
            raise AdapterError("Claude Code gave no result", body=(out or "")[-600:])
        if result.get("is_error") or result.get("subtype") not in (None, "success"):
            raise AdapterError("Claude Code: %s" % str(result.get("result") or result.get("subtype") or "an error")[:300],
                               status=result.get("api_error_status"), body=json.dumps(result)[:600])
        u = result.get("usage") or {}
        usage = {"input": sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                             "cache_read_input_tokens")),
                 "output": u.get("output_tokens"), "cached": u.get("cache_read_input_tokens")}
        if not tools:
            return {"text": result.get("result") or "", "tool_calls": [], "stop": "end_turn", "usage": usage}
        so = result.get("structured_output")
        if not isinstance(so, dict):
            try:
                so = json.loads(result.get("result") or "")
            except ValueError:
                so = {}
        names = {t["name"] for t in tools}
        calls = [{"id": "call_" + uuid.uuid4().hex[:12], "name": c.get("name"), "arguments": c.get("arguments") or {}}
                 for c in (so.get("tool_calls") or []) if isinstance(c, dict) and c.get("name") in names]
        return {"text": str(so.get("text") or ""), "tool_calls": calls, "stop": "tool_use" if calls else "end_turn",
                "usage": usage}

    def chat(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
             temperature=None, max_tokens=None):
        args, stdin, system, dropped = self.request(system, messages, tools, force_tool, caps, harness,
                                                    temperature, max_tokens)
        fd, path = tempfile.mkstemp(prefix="system-", suffix=".txt", dir=paths.sub("cache", "claude-cli"))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(system)
            p = _run(args + ["--system-prompt-file", path], stdin)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            r = self.parse(p.stdout, tools)
        except AdapterError as ex:
            if "gave no result" not in str(ex):
                raise                                 # the program said what went wrong (a limit reached, a refusal)
            ok, why = signed_in()
            raise AdapterError(why if not ok else "Claude Code stopped (%d): %s" % (
                p.returncode, ((p.stderr or "") + (p.stdout or ""))[-300:].strip()), body=(p.stderr or "")[-600:])
        r["dropped_images"], r["forced_refused"] = dropped, False
        return r
