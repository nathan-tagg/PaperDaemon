r"""Does the text server keep a tool call's nested keys and values intact?

llama-server turns each tool's JSON schema into a grammar, and that grammar holds an object's declared
properties to the order the schema declares them: once the model has written a key, no key declared
before it can follow. An out-of-order key is then dropped without a word, or -- where extra keys are
allowed -- forced into a near-miss spelling. The host's tools therefore declare only the keys a nested
object requires, in the order a model writes them (paperdaemon.pipeline.host TOOLS; tests/test_erase_ids.py checks the
schema offline). This asks a running server to copy calls verbatim, including the forced-choice erase
lists of plan and answer, and reports what arrived: lost keys, respelled keys, and changed values.

It sends requests to the server you name and nothing else; run it only against a text server you
started for it, when no job is using that server. The host's tools are read with PaperDaemon's data
folder (PAPERDAEMON_HOME, as for the engine).

    uv run python tools/check_schema_order.py --url http://127.0.0.1:8790 [--model PaperDaemon]
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROBES = [
    ("plan", {"steps": [{"do": "image", "what": "a sailboat on a calm lake at dawn"}],
              "erase": [{"id": "para:1", "because": "request"}]}),
    ("plan", {"steps": [{"do": "calendar", "what": "this week", "size": "full"}],
              "erase": [{"id": "line:2", "because": "request"}, {"id": "mark:7", "because": "stale"},
                        {"id": "picture:1", "because": "asked"}]}),
    ("plan", {"steps": [{"do": "erase", "what": "the words 'circle this' and the arrow", "because": "request",
                         "at": "the words 'circle this' and the arrow drawn from them"}]}),
    ("plan", {"steps": [{"do": "game", "what": "chess: a steady club player; the user plays white",
                         "moves": ["e4"]}],
              "erase": [{"id": "para:1", "because": "request"}]}),
    ("plan", {"steps": [{"do": "coloring", "what": "an owl on a branch", "workflow": "childrensColoringBook"}]}),
    ("plan", {"steps": [{"do": "write", "what": "a tip", "near": "right", "size": "small"}]}),
    ("answer", {"task": "List three facts about octopuses.", "lines": ["1. Three hearts."],
                "erase": [{"id": "line:1", "because": "request"}]}),
    ("chart", {"spec": {"type": "table", "columns": ["Planet", "Moons"], "rows": [["Mars", "2"]],
                        "title": "Moons"}}),
]


def tool_schema():
    """The host's tools, as it renders them, from a process of its own (the pipeline reads where its files
    are when imported)."""
    code = ("import json, sys; sys.path.insert(0, %r)\n"
            "import paperdaemon.pipeline\n"
            "from paperdaemon.pipeline import host as H; print(json.dumps(H.tool_schema()))" % ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        sys.exit("could not read the host's tools:\n" + out.stderr[-2000:])
    return json.loads(out.stdout.strip().splitlines()[-1])


def call(url, model, tools, fn, args):
    body = {"model": model, "max_tokens": 600, "temperature": 0,
            "tools": [t for t in tools if t["function"]["name"] == fn], "tool_choice": "required",
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": "Call %s with EXACTLY these arguments -- same keys, same "
                                                     "order, same values:\n%s" % (fn, json.dumps(args))}]}
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    m = json.loads(urllib.request.urlopen(req, timeout=600).read())["choices"][0]["message"]
    c = (m.get("tool_calls") or [{}])[0].get("function") or {}
    try:
        return json.loads(c.get("arguments") or "{}")
    except ValueError:
        return {"(not json)": c.get("arguments")}


def leaves(o, path=""):
    """Every key path with its value, so a dropped, respelled or changed one shows."""
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(leaves(v, path + "." + k if path else k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out.update(leaves(v, "%s[%d]" % (path, i)))
    else:
        out[path] = o
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True, help="the text server, e.g. http://127.0.0.1:8790")
    ap.add_argument("--model", default="PaperDaemon", help="the model name the server answers to")
    a = ap.parse_args(argv)
    tools = tool_schema()
    bad = 0
    for fn, args in PROBES:
        got = call(a.url, a.model, tools, fn, args)
        want, have = leaves(args), leaves(got)
        lost = [k for k in want if k not in have]
        extra = [k for k in have if k not in want]
        changed = [k for k in want if k in have and have[k] != want[k]]
        ok = not (lost or extra or changed)
        bad += not ok
        print("%s %-7s %s" % ("PASS" if ok else "FAIL", fn, json.dumps(got)[:160]))
        for label, keys in (("lost", lost), ("respelled or extra", extra), ("changed", changed)):
            if keys:
                print("       %s: %s" % (label, ", ".join(keys)))
    print("ALL PASS" if not bad else "%d of %d probes changed on the way" % (bad, len(PROBES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
