"""G4, the replay: scripted model replies run through the real host on the benchmark's fixture pages, and what the
jobs write recorded, so a change meant to alter only the host's structure can be shown to commit the same pages.

    uv run python tools/replay.py record      # write tests/baseline/replay.json
    uv run python tools/replay.py check       # replay and compare

Each case runs the host in its own process on a fresh copy of one fixture notebook, with a stub engine on a
local port answering the host's model calls from a script (streamed, as the engine does) and its other calls
(memories, status) with nothing. Nothing reaches a model, the network or the user's library. This guards
refactoring only: a script is not a model, and a replay says nothing about how well a lineup works.
"""
import hashlib
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CASES_DIR = os.path.join(ROOT, "tests", "benchmark", "cases")
OUT = os.path.join(ROOT, "tests", "baseline", "replay.json")


def _call(name, args):
    return {"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


# A ruling policy stands in for the model's reading of the page, so a script needs no fixture's ids: every id the
# listing marks NEW gets the policy's (is, then). "answers": NEW stands for those ids.
NEW = "<the new ids>"


def RULE(is_, then):
    return {"<policy>": [is_, then]}


# case -> the fixture it runs on, and the replies, in order: a reply is (tool, arguments) for a turn that offers
# that tool, or ("text", "...") for a plain call
SCRIPTS = {
    "answer": {"fixture": "typed-question", "replies": [
        ("answer", {"answers": NEW, "lines": ["Mars has two moons: Phobos and Deimos."],
                    "rulings": RULE("question", "keep")})]},
    "write-and-erase": {"fixture": "typed-question", "replies": [
        ("plan", {"steps": [{"do": "write", "what": "the moons of Mars", "answers": NEW}],
                  "rulings": RULE("request", "erase")}),
        ("write_paragraph", {"lines": ["Phobos is the larger and closer moon.", "Deimos is small and far out."]})]},
    "chart": {"fixture": "chart", "replies": [
        ("plan", {"steps": [{"do": "chart", "what": "diameters of the inner planets", "answers": NEW}],
                  "rulings": RULE("request", "erase")}),
        ("chart", {"spec": {"type": "bar", "title": "Inner planets (km)",
                            "categories": ["Mercury", "Venus", "Earth", "Mars"],
                            "series": [{"name": "Diameter", "values": [4879, 12104, 12742, 6779]}]}})]},
    "ink": {"fixture": "ink-question", "replies": [
        ("answer", {"answers": NEW, "lines": ["A spider has eight legs."], "rulings": RULE("question", "keep")})]},
    "ask": {"fixture": "typed-question", "replies": [
        ("ask", {"lines": ["Do you mean Mars's natural moons, or its moons and spacecraft too?"]})]},
    "skip": {"fixture": "draw", "replies": [("skip", {"note": "nothing here asks for work"})]},
    "remember": {"fixture": "typed-question", "replies": [
        ("answer", {"answers": NEW, "lines": ["Two: Phobos and Deimos."], "rulings": RULE("question", "keep"),
                    "remember": "Keep answers short."})]},
    "highlight": {"fixture": "typed-question", "replies": [
        ("plan", {"steps": [{"do": "highlight", "what": "the planet", "target": "para:1", "words": "Mars",
                             "answers": []}], "rulings": RULE("question", "keep")})]},
    "refused-then-fixed": {"fixture": "chart", "replies": [
        ("plan", {"steps": [{"do": "chart", "what": "diameters", "answers": NEW}], "rulings": []}),
        ("plan", {"steps": [{"do": "chart", "what": "diameters", "answers": NEW}], "rulings": RULE("request", "erase")}),
        ("chart", {"spec": {"type": "bar", "title": "Inner planets (km)", "categories": ["Mercury", "Venus"],
                            "series": [{"name": "Diameter", "values": [4879, 12104]}]}})]},
}


def _fill(args, new):
    """The script's stand-ins replaced: NEW by the new ids, a ruling policy by one ruling per new id."""
    if isinstance(args, dict):
        if "<policy>" in args:
            is_, then = args["<policy>"]
            return [{"id": i, "is": is_, "then": then} for i in new]
        return {k: _fill(v, new) for k, v in args.items()}
    if isinstance(args, list):
        return [_fill(v, new) for v in args]
    return list(new) if args == NEW else args


def _new_ids(req):
    """The ids the listing marked NEW, read from the conversation the host sent."""
    for m in req.get("messages") or []:
        c = m.get("content")
        parts = c if isinstance(c, list) else [{"type": "text", "text": c or ""}]
        for p in parts:
            hit = re.search(r"NEW[^\n]*?:\s*((?:(?:para|line|mark|picture):\d+(?:, )?)+)", str(p.get("text") or ""))
            if hit:
                return [x.strip() for x in hit.group(1).split(",") if x.strip()]
    return []


class _Stub(http.server.BaseHTTPRequestHandler):
    script, used, seen = [], [], []

    def log_message(self, *a):
        pass

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._json({"memories": [], "max": 30} if "/memories" in self.path else {})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if not self.path.endswith("/v1/chat/completions"):
            return self._json({"memories": [], "max": 30} if "/memories" in self.path else {})
        req = json.loads(body or b"{}")
        offered = [t["function"]["name"] for t in req.get("tools") or []]
        _Stub.seen.append(offered)
        reply = None
        for i, (name, args) in enumerate(_Stub.script):
            if i in _Stub.used:
                continue
            if (name == "text" and not offered) or name in offered:
                _Stub.used.append(i)
                reply = {"content": args} if name == "text" else _call(name, _fill(args, _new_ids(req)))
                break
        if reply is None:          # nothing scripted fits: end the job the quiet way
            reply = _call("skip", {"note": "nothing scripted"}) if "skip" in offered else {"content": "ok"}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        delta = dict(reply, role="assistant")
        if "tool_calls" in delta:
            delta["tool_calls"] = [dict(c, index=0) for c in delta["tool_calls"]]
        for chunk in ({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                      {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if "tool_calls" in reply else "stop"}]},
                      {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}):
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


_JOB = r"""
import json, random, sys, uuid
_rng = random.Random(0)                     # the ids a job makes (pictures, pages) the same on every run
uuid.uuid4 = lambda: uuid.UUID(int=_rng.getrandbits(128), version=4)
from paperdaemon import ledger as S
led = S.load(); led.setdefault("watching_since", 0)   # watching since before the fixture was tagged
S.classify(S.scan(), led); S.save(led)
keys = [k for k, e in S.load()["entries"].items() if e.get("status") == "pending"]
S.claim(keys[0], "replay")
import paperdaemon.pipeline.host as H
H.run_job({"keys": keys[:1]})
print(json.dumps({"key": keys[0], "entry": S.load()["entries"][keys[0]]}))
"""


def run_case(name, spec, work=None):
    """One scripted job -> {file: sha256 of what it wrote, ..., "note": the ledger's note, "offered": [...]}.

    With `work` (a folder of the caller's) the job runs there and the folder is kept: the first job copies the
    fixture into it, and a later job continues on the same mirror and ledger, so a test can look at what a job
    wrote, or change the page and run another job on it."""
    from paperdaemon.benchmark import fixtures as FX
    keep = work is not None
    work = work or tempfile.mkdtemp(prefix="pd-replay-")
    try:
        mirror, state = os.path.join(work, "mirror"), os.path.join(work, "state")
        if not os.path.isdir(mirror):
            shutil.copytree(os.path.join(CASES_DIR, spec["fixture"], "mirror"), mirror)
            os.makedirs(os.path.join(state, "rm-queue"))
        before = {os.path.relpath(os.path.join(d, f), mirror): open(os.path.join(d, f), "rb").read()
                  for d, _, fs in os.walk(mirror) for f in fs}
        port = _free_port()
        _Stub.script, _Stub.used, _Stub.seen = list(spec["replies"]), [], []
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Stub)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        run = {"lineup": "Replay", "model": "replay-model", "capabilities": {"max_output": 2000, "vision": True},
               "tag_lineup": {FX.TAG.lower(): "Replay"},
               "lineups": {"Replay": {"lineup": "Replay", "model": "replay-model", "tags": [{"name": FX.TAG, "prompt": ""}],
                                      "capabilities": {"max_output": 2000, "vision": True}}},
               "settings": {"tags": {"ignore": "ignore", "sprompt": "sprompt"}, "location": {"holidays": "US"},
                            "prefs": {"temperature": "fahrenheit", "clock": "12", "week_start": "sunday"},
                            "network": {"allowed": False}}}
        for k, v in (spec.get("settings") or {}).items():      # a case's own settings (network, home place)
            run["settings"][k] = v
        runfile = os.path.join(state, "lineup.json")
        with open(runfile, "w", encoding="utf-8") as f:
            json.dump(run, f)
        engine = "http://127.0.0.1:%d" % port
        env = dict(os.environ, RM_MIRROR=mirror, RM_CACHE=mirror, RM_STATE=state, RM_RUN=runfile,
                   RM_TRIGGERS=json.dumps([FX.TAG]), RM_LLM=engine + "/host/llm/-", RM_STUDIO=engine + "/host",
                   RM_STUDIO_TOKEN="-", RM_HOST_DRY_DOCS="1", PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
                   PAPERDAEMON_HOME=os.path.join(work, "home"), PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0")
        p = subprocess.run([sys.executable, "-c", _JOB], cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        srv.shutdown()
        try:
            res = json.loads(p.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise RuntimeError("%s: the host did not finish:\n%s" % (name, (p.stderr or p.stdout)[-2000:]))
        out = {"note": res["entry"].get("note"), "status": res["entry"].get("status"), "offered": _Stub.seen,
               "unused_replies": [i for i in range(len(spec["replies"])) if i not in _Stub.used]}
        changed = []
        for d, _, fs in os.walk(mirror):
            for f in fs:
                rel = os.path.relpath(os.path.join(d, f), mirror)
                data = open(os.path.join(d, f), "rb").read()
                if before.get(rel) != data and f.endswith((".rm", ".png")):
                    changed.append((rel, data))
        # labeled by kind and order, not by the fixture's ids
        for kind in ("rm", "png"):
            for i, (rel, data) in enumerate(sorted(c for c in changed if c[0].endswith("." + kind))):
                out["%s %d" % (kind, i + 1)] = hashlib.sha256(data).hexdigest()
        return out
    finally:
        if os.environ.get("REPLAY_KEEP") and not keep:
            print("kept:", work)
        elif not keep:
            shutil.rmtree(work, ignore_errors=True)


def main(argv):
    if not argv or argv[0] not in ("record", "check"):
        print(__doc__)
        return 2
    got = {name: run_case(name, spec) for name, spec in SCRIPTS.items()}
    if argv[0] == "record":
        again = {name: run_case(name, spec) for name, spec in SCRIPTS.items()}
        if again != got:
            for n in got:
                if got[n] != again[n]:
                    print("NOT REPEATABLE", n)
            return 1
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            json.dump(got, f, indent=1, sort_keys=True)
            f.write("\n")
        for n, r in got.items():
            print("recorded %s: %s, %d file(s) written" % (n, r["status"], sum(1 for k in r if k[:3] in ("rm ", "png"))))
        return 0
    with open(OUT, encoding="utf-8") as f:
        old = json.load(f)
    bad = 0
    for n in SCRIPTS:
        if got.get(n) == old.get(n):
            print("same", n)
        else:
            bad += 1
            print("DIFFERENT", n, sorted(k for k in set(got.get(n, {})) | set(old.get(n, {}))
                                         if got.get(n, {}).get(k) != old.get(n, {}).get(k)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
