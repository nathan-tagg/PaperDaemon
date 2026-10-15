"""Refactoring guards: record, or compare against the record, what a structure-only change must not alter.

    uv run python tools/baseline.py record [prefix] [charts] [faces]
    uv run python tools/baseline.py check  [prefix] [charts] [faces]

- prefix: the host's brief and tool schema, as the model is given them, for a lineup with an image model
  and for one without (tests/baseline/prefix-*.txt, prefix-*.json);
- charts: the PNG of every sample chart spec below, by its SHA-256 (tests/baseline/charts.json);
- faces: the SVG of every emotion of every face in the shipped cast, by its SHA-256
  (tests/baseline/faces.json).

Each part runs in a process of its own, with its own data folder in the system's temporary folder.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "baseline")

HARNESS_IMAGE = {
    "id": "qwen3.8-27b", "name": "Qwen 3.8 27B", "lineup": "Qwen 3.8 + Klein",
    "capabilities": {"vision": True, "forced_tool": True, "context": 65536, "thinking": "off"},
    "brief_additions": "",
    "image": {"name": "FLUX.2 Klein 9B", "abilities": ["generate", "edit_reference"],
              "workflows": {"childrensColoringBook": {"about": "a children's coloring book page"}},
              "steps": 4, "steps_range": [4, 12]},
}
HARNESS_NO_IMAGE = dict(HARNESS_IMAGE, lineup="text only", image=None)

_BARS = {"title": "Rain", "x_label": "Month", "y_label": "mm", "categories": ["Jan", "Feb", "Mar", "Apr"],
         "series": [{"name": "North", "values": [30, 42, 18, 25]}, {"name": "South", "values": [12, 20, 33, 9]}]}
_ONE = {"title": "Share", "categories": ["Red", "Green", "Blue"], "series": [{"name": "votes", "values": [5, 3, 2]}]}
_ITEMS = {"title": "Scores", "items": [{"label": "Ann", "value": 12}, {"label": "Bo", "value": -4},
                                       {"label": "Cy", "value": 7}]}
_POS = {"title": "Sizes", "items": [{"label": "Ann", "value": 12}, {"label": "Bo", "value": 4},
                                    {"label": "Cy", "value": 7}]}
_GROUPS = {"title": "Spread", "groups": [{"name": "A", "values": [1, 2, 3, 4, 5, 3]},
                                         {"name": "B", "values": [2, 3, 5, 6, 4, 4]}]}

CHARTS = {
    **{t: dict(_BARS, type=t) for t in ("bar", "stacked", "line", "area", "step", "heatmap")},
    "scatter": dict(_BARS, type="scatter", categories=[1, 2, 3, 4]),
    "hbar": dict(_ONE, type="hbar"), "pie": dict(_ONE, type="pie"), "donut": dict(_ONE, type="donut"),
    **{t: dict(_ITEMS, type=t) for t in ("lollipop", "diverging", "waterfall")},
    **{t: dict(_POS, type=t) for t in ("polar", "treemap", "progress")},
    **{t: dict(_GROUPS, type=t) for t in ("dist", "violin", "ridgeline")},
    "histogram": {"type": "histogram", "title": "Ages", "values": [3, 5, 7, 7, 8, 9, 12, 14, 15], "bins": 4},
    "bubble": {"type": "bubble", "title": "B", "items": [{"label": "a", "x": 1, "y": 2, "size": 3},
                                                       {"label": "b", "x": 3, "y": 1, "size": 6}]},
    "bullet": {"type": "bullet", "title": "Goals", "items": [{"label": "Read", "value": 7, "target": 10}]},
    "slope": {"type": "slope", "title": "Then and now", "items": [{"label": "A", "before": 3, "after": 6},
                                                                  {"label": "B", "before": 5, "after": 2}]},
    "dumbbell": {"type": "dumbbell", "title": "Gap", "items": [{"label": "A", "a": 3, "b": 6},
                                                               {"label": "B", "a": 5, "b": 2}]},
    "bump": {"type": "bump", "title": "Ranks", "categories": ["W1", "W2", "W3"],
             "series": [{"name": "A", "values": [1, 2, 1]}, {"name": "B", "values": [2, 1, 2]}]},
    "pyramid": {"type": "pyramid", "title": "Ages", "bands": [{"band": "0-9", "a": 5, "b": 4},
                                                             {"band": "10-19", "a": 6, "b": 7}]},
    "marimekko": {"type": "marimekko", "title": "Mix", "columns": [
        {"name": "X", "value": 10, "parts": [{"name": "a", "value": 6}, {"name": "b", "value": 4}]},
        {"name": "Y", "value": 5, "parts": [{"name": "a", "value": 2}, {"name": "b", "value": 3}]}]},
    "waffle": {"type": "waffle", "title": "Done", "parts": [{"name": "done", "value": 62},
                                                          {"name": "left", "value": 38}]},
    "funnel": {"type": "funnel", "title": "Steps", "stages": [{"name": "Seen", "value": 100},
                                                             {"name": "Read", "value": 40}]},
    "gauge": {"type": "gauge", "value": 64, "min": 0, "max": 100, "label": "Battery"},
    "radar": {"type": "radar", "title": "Skills", "axes": ["Speed", "Power", "Wit"],
              "series": [{"name": "A", "values": [3, 4, 5]}]},
    "sparkbars": {"type": "sparkbars", "title": "Week", "rows": [{"label": "Steps", "values": [3, 5, 2, 6]}]},
    "matrix": {"type": "matrix", "title": "Map", "items": [{"label": "a", "x": 1, "y": 2}, {"label": "b", "x": 3, "y": 1}]},
    "quadrant": {"type": "quadrant", "title": "Effort", "items": [{"label": "a", "x": 1, "y": 2},
                                                                  {"label": "b", "x": 3, "y": 1}]},
    "pictograph": {"type": "pictograph", "title": "Pets", "rows": [{"label": "Cats", "value": 4, "icon": "star"}]},
    "candle": {"type": "candle", "title": "Price", "bars": [{"t": "Mon", "open": 3, "high": 5, "low": 2, "close": 4},
                                                          {"t": "Tue", "open": 4, "high": 6, "low": 3, "close": 5}]},
    "stock": {"type": "stock", "title": "Price", "bars": [{"t": "Mon", "close": 4}, {"t": "Tue", "close": 5},
                                                        {"t": "Wed", "close": 3}]},
    "sankey": {"type": "sankey", "title": "Flow", "links": [{"from": "a", "to": "b", "value": 3},
                                                           {"from": "a", "to": "c", "value": 2}]},
    "venn": {"type": "venn", "title": "Both", "sets": [{"name": "Cats"}, {"name": "Dogs"}]},
    "table": {"type": "table", "title": "Moons", "columns": ["Planet", "Moons"], "rows": [["Mars", "2"], ["Earth", "1"]]},
    "checklist": {"type": "checklist", "title": "Today", "items": ["Water the plants", "Read"]},
    "kanban": {"type": "kanban", "title": "Work", "columns": [{"name": "To do", "items": ["Paint"]},
                                                            {"name": "Done", "items": ["Sand"]}]},
    "timeline": {"type": "timeline", "title": "Trips", "events": [{"at": "1990", "text": "Moon"},
                                                                {"at": "2000", "text": "Mars"}]},
    "gantt": {"type": "gantt", "title": "Build", "tasks": [{"name": "Plan", "start": "2026-01-01", "end": "2026-01-05"}]},
    "clock": {"type": "clock", "title": "Day", "blocks": [{"start": 8, "end": 12, "label": "Work"}]},
    "agenda": {"type": "agenda", "title": "Monday", "items": [{"start": "09:00", "text": "Walk"}]},
    "habit": {"type": "habit", "title": "Habits", "habits": [{"name": "Read"}, {"name": "Walk"}]},
    "flow": {"type": "flow", "title": "Bake", "steps": [{"text": "Mix"}, {"text": "Bake"}]},
    "journey": {"type": "journey", "title": "Trip", "steps": [{"label": "Pack"}, {"label": "Go"}]},
    "tree": {"type": "tree", "title": "Family", "nodes": [{"id": "a", "label": "Root"},
                                                         {"id": "b", "parent": "a", "label": "Leaf"}]},
    "cards": {"type": "cards", "title": "Tips", "items": [{"head": "One", "lines": ["first"]}]},
    "calendar": {"type": "calendar", "year": 2026, "month": 2,
                 "marks": {"14": {"events": [{"text": "Party", "at": "18:00", "kind": "personal"}]}}},
}

_PREFIX = r"""
import json, os, sys
sys.path.insert(0, %(root)r)
import paperdaemon.pipeline
from paperdaemon.pipeline import host as H
print(json.dumps({"brief": H.system_brief(), "tools": H.tool_schema()}))
"""

_CHARTS = r"""
import hashlib, json, sys
sys.path.insert(0, %(root)r)
import paperdaemon.pipeline
from paperdaemon.pipeline import charts as CH
out = {}
for name, spec in json.loads(sys.stdin.read()).items():
    try:
        out[name] = hashlib.sha256(CH.render(spec)).hexdigest()
    except Exception as ex:
        out[name] = "error: %%s: %%s" %% (type(ex).__name__, str(ex)[:160])
print(json.dumps(out))
"""

_FACES = r"""
import hashlib, json, os, sys
sys.path.insert(0, %(root)r)
import paperdaemon.pipeline
from paperdaemon.pipeline.games import characters as RC
from paperdaemon.pipeline.games import faces as F
out = {}
EMOTIONS = ("neutral", "happy", "sad", "angry", "surprised", "thinking")
for cid in sorted(RC.roster()):
    look = RC.look_of(cid)
    for e in EMOTIONS:
        out["%%s/%%s" %% (hashlib.sha256(cid.encode()).hexdigest()[:10], e)] = \
            hashlib.sha256(F.face_svg(look, e).encode()).hexdigest()
print(json.dumps(out))
"""


def _run(code, stdin=None, harness=None):
    home = tempfile.mkdtemp(prefix="pd-baseline-")
    env = dict(os.environ, PAPERDAEMON_HOME=home, RM_STATE=home, RM_MIRROR=os.path.join(home, "mirror"),
               RM_CACHE=os.path.join(home, "mirror"), PYTHONIOENCODING="utf-8",
               PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    os.makedirs(env["RM_MIRROR"], exist_ok=True)
    os.makedirs(os.path.join(home, "fonts"), exist_ok=True)      # the lettering font is built here
    env["PAPERDAEMON_CONTENT"] = os.path.join(home, "content")     # the shipped content only
    env.pop("RM_RUN", None)
    if harness is not None:
        path = os.path.join(home, "harness.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(harness, f)
        env["RM_RUN"] = path
    p = subprocess.run([sys.executable, "-c", code % {"root": ROOT}], input=stdin, capture_output=True,
                       text=True, encoding="utf-8", env=env, cwd=home)
    if p.returncode != 0:
        raise SystemExit("baseline: the child failed:\n" + p.stderr[-3000:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def prefix():
    out = {}
    for name, h in (("image", HARNESS_IMAGE), ("no-image", HARNESS_NO_IMAGE)):
        got = _run(_PREFIX, harness=h)
        out["prefix-%s-brief.txt" % name] = got["brief"]
        out["prefix-%s-tools.json" % name] = json.dumps(got["tools"], indent=1, ensure_ascii=False) + "\n"
    return out


def charts():
    return {"charts.json": json.dumps(_run(_CHARTS, stdin=json.dumps(CHARTS)), indent=1, sort_keys=True) + "\n"}


def faces():
    return {"faces.json": json.dumps(_run(_FACES), indent=1, sort_keys=True) + "\n"}


PARTS = {"prefix": prefix, "charts": charts, "faces": faces}


def main(argv):
    if not argv or argv[0] not in ("record", "check"):
        print(__doc__)
        return 2
    parts = argv[1:] or list(PARTS)
    bad = 0
    os.makedirs(OUT, exist_ok=True)
    for part in parts:
        for name, text in PARTS[part]().items():
            path = os.path.join(OUT, name)
            if argv[0] == "record":
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                print("recorded", name)
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    old = f.read()
            except OSError:
                print("MISSING", name)
                bad += 1
                continue
            if old == text:
                print("same", name)
                continue
            bad += 1
            if name.endswith(".json") and part in ("charts", "faces"):
                a, b = json.loads(old), json.loads(text)
                diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
                print("DIFFERENT", name, len(diff), "entries:", ", ".join(diff[:20]))
            else:
                print("DIFFERENT", name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
