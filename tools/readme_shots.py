"""The README's pictures, made again from nothing, in a throwaway engine on a test port.

THE PAGES: each a test notebook's page with a request typed on it, worked by the real host and drawn in a Paper Pro's
frame: a month and a week with their weather, a conversation, a drawing, a coloring page, pictures generated and
decomposed into pen strokes, the newest posts of a subreddit (fetched from Reddit), a game of chess (Stockfish), and
paintings found on the web and decomposed. With --live LINEUP the models are the user's own lineup (from their
settings: the README's pages were made with Qwen 3.8 27B and FLUX.2 Klein), run by the throwaway engine on this
tool's ports; without it the model's replies are scripted (tools/replay.py) and the generated pictures are ones
FLUX.2 Klein made for the decomposer's torture test. A web search is answered by Wikimedia Commons' own search, so the
paintings are found and fetched for real. Paintings decomposed on the Decompose screen are sent to notebooks as well.

THE SCREENS: PaperDaemon's own (the editor and its pens, Decompose, the library, the Daemon, the Lineup's tabs,
Settings), the whole window each time, photographed by headless Microsoft Edge at twice the screen's pixels
(tools/readme_editor.mjs).

    uv run python tools/readme_shots.py [--live LINEUP [--context N]] [--only month,chess] [--no-screens] [--keep]
    uv run python tools/readme_shots.py --resume WORK ...     # go on in a work folder a stopped run left
    uv run python tools/readme_shots.py --from WORK           # the screens only, from a work folder --keep kept

Nothing reaches the user's settings or library. The weather, Reddit and Wikimedia Commons are fetched, so the pages
show the week they were made. The tablet's faces come from the content folder when it has them.
PAPERDAEMON_SHOT_ADAPTER (a card's LUID, "high,low") picks the card the editor, the engine and the pages are drawn on.
"""
import argparse
import base64
import datetime
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import replay as RP  # noqa: E402
import ui_shot as US  # noqa: E402

PAINTINGS = os.path.join(ROOT, "tests", "decompose", "pictures")     # Hokusai, Van Gogh, Vermeer: public domain
DECOMPOSED = (("great-wave.jpg", "The Great Wave"), ("starry-night.jpg", "The Starry Night"),
              ("pearl-earring.jpg", "Girl with a Pearl Earring"))
_TODAY = datetime.date.today()
_PLACE = {"network": {"allowed": True},
          "location": {"name": "Denver, Colorado, United States", "lat": 39.7392, "lon": -104.9903, "holidays": "US"}}

# THE HOUSE the drawing request gets: a figure of plain parts, as the model builds one (the host fits it to its box)
_RAYS = [(175 + 13 * c, 12 + 13 * s, 175 + 19 * c, 12 + 19 * s)
         for c, s in ((1, 0), (0.707, 0.707), (0, 1), (-0.707, 0.707), (-1, 0), (-0.707, -0.707), (0, -1),
                      (0.707, -0.707))]
_HOUSE = ([{"kind": "line", "x1": 0, "y1": 100, "x2": 200, "y2": 100},
           {"kind": "rect", "x1": 30, "y1": 55, "x2": 110, "y2": 100},
           {"kind": "polyline", "points": [[22, 55], [70, 18], [118, 55]]},
           {"kind": "rect", "x1": 60, "y1": 72, "x2": 80, "y2": 100},
           {"kind": "rect", "x1": 38, "y1": 62, "x2": 54, "y2": 76},
           {"kind": "rect", "x1": 86, "y1": 62, "x2": 102, "y2": 76},
           {"kind": "rect", "x1": 146, "y1": 77, "x2": 156, "y2": 100},
           {"kind": "circle", "cx": 151, "cy": 55, "r": 22},
           {"kind": "circle", "cx": 175, "cy": 12, "r": 9}] +
          [{"kind": "line", "x1": round(a, 1), "y1": round(b, 1), "x2": round(c, 1), "y2": round(d, 1)}
           for a, b, c, d in _RAYS])


# PICTURES FLUX.2 KLEIN MADE for the decomposer's torture test (tests/decompose/pictures), with the prompts that made
# them: what the picture model hands back when a page asks for one of them
KLEIN = {"koi-pond.jpg": "a koi pond seen from above, many orange and white koi, lily pads and pink water lilies, "
                         "highly detailed illustration",
         "autumn-path.jpg": "a forest path in autumn with thousands of falling leaves in red, orange and gold, "
                            "highly detailed illustration"}


def _plan(*steps, rule="erase", what_is="request"):
    """The model's plan: its steps, the first answering the request, and what to do with the request."""
    return ("plan", {"steps": [dict(s, answers=RP.NEW if i == 0 else []) for i, s in enumerate(steps)],
                     "rulings": RP.RULE(what_is, rule)})


# THE PAGES. Each: its id (the picture is tablet-<id>.png), the notebook's name, the request typed on its page, the
# model's replies for the job, and any later turns (a request typed under what is there, and the replies). `erase`:
# the job takes the request off the page, so the README shows its words above the picture.
DEMOS = [
    {"id": "month", "name": _TODAY.strftime("%B"), "request": "This month, with the holidays.", "erase": True,
     "replies": [_plan({"do": "calendar", "what": _TODAY.strftime("%Y-%m")}),
                 ("chart", {"spec": {"type": "calendar", "year": _TODAY.year, "month": _TODAY.month}})]},
    {"id": "week", "name": "This week", "request": "Plan my week, with the weather.", "erase": True,
     "replies": [_plan({"do": "calendar", "what": "week"}), ("chart", {"spec": {"type": "week", "days": {}}})]},
    {"id": "talk", "name": "Mars", "request": "How many moons does Mars have, and what are they called?",
     "replies": [("answer", {"answers": RP.NEW, "lines": ["Two: Phobos and Deimos."],
                             "rulings": RP.RULE("question", "keep")})],
     "then": [("Which one is bigger?",
               [("answer", {"answers": RP.NEW, "lines": ["Phobos, about 22 km across.", "Deimos is about 12 km."],
                            "rulings": RP.RULE("question", "keep")})]),
              ("Could I see Phobos from the surface of Mars?",
               [("answer", {"answers": RP.NEW, "lines": ["Yes: it crosses the sky twice a day, rising in the west,",
                                                          "about a third the width of our full Moon."],
                            "rulings": RP.RULE("question", "keep")})])]},
    {"id": "draw", "name": "Drawing", "request": "Draw a house with a tree and the sun.",
     "replies": [_plan({"do": "draw", "what": "a house with a tree and the sun"}, rule="keep"),
                 ("draw_figure", {"parts": _HOUSE})]},
    {"id": "coloring", "name": "Coloring", "request": "Make a children's coloring page of a friendly dragon.",
     "live": True},
    {"id": "koi", "name": "Koi pond", "request": "Draw a koi pond, seen from above.", "picture": "koi-pond.jpg",
     "replies": [_plan({"do": "image", "what": KLEIN["koi-pond.jpg"]}, rule="keep"),
                 ("image", {"prompt": KLEIN["koi-pond.jpg"]})]},
    {"id": "autumn", "name": "Autumn", "request": "Draw a forest path in autumn.", "picture": "autumn-path.jpg",
     "replies": [_plan({"do": "image", "what": KLEIN["autumn-path.jpg"]}, rule="keep"),
                 ("image", {"prompt": KLEIN["autumn-path.jpg"]})]},
    {"id": "posts", "name": "Cozy places", "request": "The latest posts from r/comfyPlaces.",
     "replies": [_plan({"do": "posts", "what": "the latest posts from r/comfyPlaces", "source": "r/comfyPlaces",
                        "sort": "new", "count": 4, "pictures": True}, rule="keep")]},
    {"id": "chess", "name": "Chess", "request": "Let's play chess, Rocco. I'll be black.", "erase": True,
     "replies": [_plan({"do": "chess", "what": "a game of chess; the user plays black", "color": "black"})]},
    {"id": "mona", "name": "Mona Lisa", "request": "Paste an image of the Mona Lisa.",
     "replies": [_plan({"do": "web_picture", "what": "Mona Lisa by Leonardo da Vinci"}, rule="keep")]},
    {"id": "gallery", "name": "Van Gogh", "request": "Decompose a gallery of Van Gogh's paintings.",
     "replies": [_plan(*[{"do": "web_picture", "what": w, "near": side} for w, side in (     # two rows of two
         ("The Starry Night by Vincent van Gogh", "left"), ("Sunflowers by Vincent van Gogh", "right"),
         ("Irises by Vincent van Gogh", "left"), ("Cafe Terrace at Night by Vincent van Gogh", "right"))],
         rule="keep")]},
]

# A LINEUP FILLED IN, for the Lineup's tabs: models on this computer, each with the start script that runs it
TEXT_BAT = "\n".join([
    "@echo off",
    "rem Qwen 3.8 27B with vision, on llama.cpp's server, all of it on the graphics card",
    'if "%PAPERDAEMON_PORT%"=="" set PAPERDAEMON_PORT=8790',
    '"C:\\llama\\llama-server.exe" ^',
    '  -m "C:\\models\\Qwen3.8-27B-Q4_K_M.gguf" ^',
    '  --mmproj "C:\\models\\Qwen3.8-27B-mmproj-Q8_0.gguf" ^',
    "  -ngl 99 -fa on -ctk q8_0 -ctv q8_0 -c 32768 ^",
    "  --host 127.0.0.1 --port %PAPERDAEMON_PORT%"])
IMAGE_BAT = "\n".join([
    "@echo off",
    "rem Z-Image Turbo on stable-diffusion.cpp's server",
    'if "%PAPERDAEMON_PORT%"=="" set PAPERDAEMON_PORT=8791',
    '"C:\\sd\\sd-server.exe" ^',
    '  --diffusion-model "C:\\models\\sd\\z_image_turbo_bf16.safetensors" ^',
    '  --vae "C:\\models\\sd\\ae.safetensors" ^',
    '  --llm "C:\\models\\sd\\Qwen3-4B-Q8_0.gguf" ^',
    "  --diffusion-fa --vae-tiling ^",
    "  --listen-port %PAPERDAEMON_PORT%"])
SEARCH_BAT = "\n".join([
    "@echo off",
    "rem SearXNG in Docker, its settings (with JSON results on) in C:\\searxng",
    "docker rm -f searxng >nul 2>&1",
    "docker run --rm --name searxng -p 8888:8080 -v C:\\searxng:/etc/searxng searxng/searxng"])
LINEUP = {"name": "Daemon", "tags": [{"name": "Daemon", "prompt": ""}],
          "text": {"location": "http://127.0.0.1:8790", "api": "openai", "harness": "qwen3.8-27b",
                   "script_text": TEXT_BAT},
          "image": {"location": "http://127.0.0.1:8791", "api": "sdapi", "harness": "z-image-turbo",
                    "script_text": IMAGE_BAT},
          "search": {"kind": "local", "url": "http://127.0.0.1:8888", "script_text": SEARCH_BAT}}

# A TEST NOTEBOOK with the request typed on its tagged page, made the way the benchmark's fixtures are
_FIXTURE_JOB = r"""
import os, sys
from paperdaemon.benchmark import fixtures as FX
sys.path.insert(0, FX.PIPELINE)
case = {"id": sys.argv[1], "title": sys.argv[1], "kind": "typed", "request": sys.argv[2]}
doc, _ = FX._notebook(os.environ["RM_MIRROR"], case)
FX._write_request(doc, case)
"""

# A LATER TURN: the next request typed under everything on the page, as the user would after pressing Enter a few times
_TYPE_JOB = r"""
import os, sys
from paperdaemon.benchmark import fixtures as FX
sys.path.insert(0, FX.PIPELINE)
from paperdaemon.pipeline.page import render as R, typed as TY
doc = next(f[:-8] for f in os.listdir(os.environ["RM_MIRROR"]) if f.endswith(".content"))
text = sys.argv[1]
ink = max(p.y for v in R.strokes(doc, 1) for p in v.points)
src = R.page_file(doc, R.live_pages(doc)[0]["id"])
before = open(src, "rb").read()
for k in range(1, 120):
    with open(src, "wb") as f:
        f.write(before)
    for c in (TY._RECORDS, TY._LAYOUTS, TY._RENDERS):
        c.clear()
    TY.insert(doc, 1, "\n" * k + text)
    for c in (TY._RECORDS, TY._LAYOUTS, TY._RENDERS):
        c.clear()
    y = [p["y"] for p in TY.paragraphs(doc, 1)[1] if str(p.get("text", "")).strip() == text][-1]
    if y >= ink + 60:
        break
print(k, round(y), round(ink))
"""

# A PAINTING, AS SEND TO TABLET LAYS IT ON A PAGE: decomposed, on a new notebook's first page
_PICTURE_JOB = r"""
import base64, os, sys, time
from paperdaemon import studio
from paperdaemon.pipeline import TEMPLATES, draw as A
from paperdaemon.pipeline.page import render as R
doc, name, src = sys.argv[1], sys.argv[2], sys.argv[3]
now = int(time.time() * 1000)
studio._new_notebook(R.RM, os.path.dirname(TEMPLATES), doc, name, "", now)
[(page_no, pid)] = studio._inbox_pages(doc, 1, now)
_, strokes = studio.decompose(base64.b64encode(open(src, "rb").read()).decode(), 1400, preview=False)
d = A.Drawing(1620, 2160)
d.strokes = list(strokes)
print(d.write_rm(doc, page_no))
"""

# EACH PAGE DRAWN BY THE ENGINE, and its cover kept as the window would keep it (thumbs.put): the library shows them at
# once
_DRAW_JOB = r"""
import json, sys
from paperdaemon import thumbs
from paperdaemon.pipeline.page import render as R
for doc, out in json.loads(sys.argv[1]):
    R.render(doc, 1, out, blank_ok=True)
    with open(thumbs.draw(doc, 1, thumbs.COVER, top=True), "rb") as f:
        thumbs.put(doc, 1, thumbs.COVER, f.read())
print("drawn")
"""


def _env(home, mirror, **more):
    return dict(os.environ, PAPERDAEMON_HOME=home, RM_MIRROR=mirror, RM_CACHE=mirror, PYTHONIOENCODING="utf-8",
                PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring", **more)


def _python(code, env, *args):
    p = subprocess.run([sys.executable, "-c", code] + list(args), cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-2000:])
    return p.stdout


# ---------------------------------------------------------------- what the pages need from outside

def _card():
    """The card PAPERDAEMON_SHOT_ADAPTER names, as Settings names it ("" without one): everything is drawn there."""
    want = os.environ.get("PAPERDAEMON_SHOT_ADAPTER", "")
    if not want:
        return ""
    from paperdaemon import gpus
    luid = [int(x) for x in want.split(",")]
    return next((c["id"] for c in gpus.cards() if c["luid"] == luid), "")


def _pin(home, card):
    """A home whose pages are drawn on `card` (its settings, written before anything is drawn)."""
    os.makedirs(home, exist_ok=True)
    if card:
        with open(os.path.join(home, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"render": {"card": card}}, f)


def _commons(query, images):
    """A web search answered by Wikimedia Commons' own search, in SearXNG's shape: real pictures, found for real."""
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
           "&gsrlimit=12&prop=imageinfo&iiprop=url|mime&iiurlwidth=1600&gsrsearch=" + urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": "PaperDaemon-readme-shots/1.0 (README pictures)"})
    pages = json.loads(urllib.request.urlopen(req, timeout=30).read()).get("query", {}).get("pages", {})
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") in ("image/jpeg", "image/png"):
            out.append({"title": p["title"].split(":", 1)[-1], "img_src": ii.get("thumburl") or ii.get("url"),
                        "url": ii.get("descriptionurl"), "content": "", "engine": "wikimedia commons"})
    return {"results": out if images else out[:5]}


def _search_by_commons():
    """The replay's engine stand-in answers the host's web searches (GET .../search) from Wikimedia Commons."""
    plain = RP._Stub.do_GET

    def do_get(self):
        if "/search?" not in self.path:
            return plain(self)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return self._json(_commons(q.get("q", [""])[0], q.get("images", ["0"])[0] == "1"))
    RP._Stub.do_GET = do_get


class _Painter:
    """The picture model as the replay's engine stand-in plays it: the one loaded, and the picture the page being made
    asks for (a file of KLEIN's)."""
    key, picture = "text", None


def _paint_from_klein():
    """The replay's engine stand-in plays the picture studio (load, status, generate, image), handing back the picture
    FLUX.2 Klein made for the page's prompt."""
    get, post = RP._Stub.do_GET, RP._Stub.do_POST

    def do_get(self):
        if self.path.endswith("/status"):
            return self._json({"key": _Painter.key, "phase": "ready", "tablet": {"image": "image"}})
        if "/image/" in self.path and _Painter.picture:
            with open(os.path.join(PAINTINGS, _Painter.picture), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None
        return get(self)

    def do_post(self):
        if self.path.endswith(("/load", "/generate")):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path.endswith("/load"):
                _Painter.key = body.get("key") or _Painter.key
                return self._json({"loading": True})
            return self._json({"kind": "image", "name": _Painter.picture, "steps": 4, "seed": 1})
        return post(self)
    RP._Stub.do_GET, RP._Stub.do_POST = do_get, do_post


def _stockfish(work):
    """Stockfish for the chess page, unpacked from the release build's checked download (tools/build_app.py)."""
    import build_app
    build_app.add_stockfish(work)
    return os.path.join(work, "stockfish", "stockfish.exe")


# ---------------------------------------------------------------- notebooks

def _take(case, mirror, name, notes):
    """The one notebook of a replay (its work folder) into `mirror` under a new id and `name`, and its notepad into
    `notes` -> its id."""
    src_mirror = os.path.join(case, "mirror")
    old = next(f[:-8] for f in os.listdir(src_mirror) if f.endswith(".content"))
    doc = str(uuid.uuid4())
    pad = os.path.join(case, "state", "rm-notepad", old + ".md")
    if os.path.isfile(pad):
        os.makedirs(notes, exist_ok=True)
        shutil.copyfile(pad, os.path.join(notes, doc + ".md"))
    for f in os.listdir(src_mirror):
        if f == old or f.startswith(old + "."):
            src = os.path.join(src_mirror, f)
            (shutil.copytree if os.path.isdir(src) else shutil.copyfile)(src, os.path.join(mirror, doc + f[len(old):]))
    _meta(mirror, doc, visibleName=name, parent="")
    return doc


def _meta(mirror, doc, **change):
    path = os.path.join(mirror, doc + ".metadata")
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    m.update(change)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=4)


def _folder(mirror, name, when):
    """A folder in the library, as the tablet keeps one."""
    fid = str(uuid.uuid4())
    with open(os.path.join(mirror, fid + ".metadata"), "w", encoding="utf-8") as f:
        json.dump({"createdTime": str(when), "lastModified": str(when), "lastOpened": "", "lastOpenedPage": 0,
                   "parent": "", "pinned": False, "type": "CollectionType", "visibleName": name}, f, indent=4)
    with open(os.path.join(mirror, fid + ".content"), "w", encoding="utf-8") as f:
        json.dump({"tags": []}, f)
    return fid


def _made(mirror):
    """The notebooks and folders already in a work folder's library, by name -> id. One a stopped run was still taking
    in (its test notebook's name still on it) is removed: it is made again."""
    have = {}
    for f in os.listdir(mirror):
        if not f.endswith(".metadata"):
            continue
        doc = f[:-len(".metadata")]
        with open(os.path.join(mirror, f), encoding="utf-8") as fh:
            name = json.load(fh).get("visibleName") or ""
        if name.startswith("Benchmark - "):
            for g in os.listdir(mirror):
                if g == doc or g.startswith(doc + "."):
                    p = os.path.join(mirror, g)
                    shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
            continue
        have[name] = doc
    return have


def _wrap_up(state):
    """What the daemon does as a job is wrapped up: the ledger's "checked" flag taken off, so a later change to the page
    is seen as one (ledger.classify)."""
    path = os.path.join(state, "rm-ledger.json")
    with open(path, encoding="utf-8") as f:
        led = json.load(f)
    for e in led.get("entries", {}).values():
        e.pop("checked", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(led, f)


def _demo(demo, work, home, mirror, notes):
    """One page: its test notebook, the job (and any later turns) run by the real host -> the notebook's id."""
    cw = os.path.join(work, demo["id"])                        # the replay continues on this mirror
    os.makedirs(os.path.join(cw, "mirror"))
    os.makedirs(os.path.join(cw, "state", "rm-queue"))
    _pin(os.path.join(cw, "home"), CARD)
    env = _env(home, os.path.join(cw, "mirror"), RM_STATE=os.path.join(cw, "state"))
    _python(_FIXTURE_JOB, env, demo["id"], demo["request"])
    _Painter.key, _Painter.picture = "text", demo.get("picture")
    turns = [(None, demo.get("replies"))] + list(demo.get("then") or [])
    for i, (typed, replies) in enumerate(turns):
        if typed:
            _wrap_up(os.path.join(cw, "state"))
            _python(_TYPE_JOB, env, typed)
        if LIVE:
            got = _live_turn(cw)
        else:
            got = RP.run_case("%s %d" % (demo["id"], i + 1), {"settings": _PLACE, "replies": replies}, work=cw)
        if got.get("status") != "done":
            raise RuntimeError("%s, turn %d: the job did not finish: %s" % (demo["id"], i + 1, got.get("note")))
    return _take(cw, mirror, demo["name"], notes)


# ---------------------------------------------------------------- the models, for real (--live)

LIVE = None                 # the engine the pages are made through, when they are made by the real models
LIVE_PORTS = {"text": 8890, "image": 8891}


def _live_lineup(path, name):
    """The user's own lineup `name` (their settings file at `path`): its text and image slots on this tool's ports.
    Its start scripts make room on the card by ending the other model's server by name (taskkill /IM), which would end
    the user's own servers too: each such line ends instead whatever listens on this tool's port for that server."""
    with open(path, encoding="utf-8") as f:
        real = json.load(f)
    lu = next((x for x in real.get("lineups") or [] if x.get("name") == name), None)
    if lu is None:
        sys.exit("no lineup named %r in %s" % (name, path))
    exe = {"llama-server": LIVE_PORTS["text"], "sd-server": LIVE_PORTS["image"]}
    out = {}
    for role in ("text", "image"):
        lines = []
        for line in str(lu[role].get("script_text") or "").splitlines():
            m = re.match(r"(?i)\s*taskkill\s+/IM\s+([\w.-]+?)(?:\.exe)?\s", line + " ")
            if m:
                port = exe.get(m.group(1).lower())
                if port:
                    lines.append('for /f "tokens=5" %%%%p in (\'netstat -ano ^| findstr /R /C:":%d .*LISTENING"\') do '
                                 "taskkill /PID %%%%p /F >nul 2>&1" % port)
                continue
            lines.append(line)
        out[role] = dict(lu[role], location="http://127.0.0.1:%d" % LIVE_PORTS[role], script="",
                         script_text="\n".join(lines))
    return out


class _CommonsSearch(http.server.BaseHTTPRequestHandler):
    """A search server in SearXNG's shape whose answers come from Wikimedia Commons' own search: the lineup's web
    search, so a picture a page asks for is found and fetched for real."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        got = _commons(q.get("q", [""])[0], q.get("categories", [""])[0] == "images")
        for r in got["results"]:
            r["url"] = str(r.get("url") or r.get("img_src") or "")
        data = json.dumps(got).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _live_engine(a, lineup):
    """The throwaway engine the pages are made through: the user's lineup (on this tool's ports) watching the test
    notebooks' tag, the Commons search as its web search -> its servers (stop them with _live_stop)."""
    US._throwaway_keyring()
    from paperdaemon import server, settings
    from paperdaemon.benchmark import fixtures as FX
    search = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CommonsSearch)
    threading.Thread(target=search.serve_forever, daemon=True).start()
    s = settings.load()
    s["server"]["port"] = a.port
    s["risks"]["acknowledged"] = True
    s["network"]["allowed"] = True
    s["location"] = dict(s.get("location") or {}, **_PLACE["location"])
    if CARD:
        s["render"]["card"] = CARD
    lu = dict(s["lineups"][0], name="README", tags=[{"name": FX.TAG, "prompt": ""}])
    for role in ("text", "image"):
        lu[role] = dict(lu.get(role) or settings.slot_defaults(role), **lineup[role])
    lu["search"] = dict(settings.search_defaults(), kind="local", url="http://127.0.0.1:%d" % search.server_port)
    s["lineups"], s["lineup"] = [lu], "README"
    settings.save(s)
    servers = server.serve(a.port, ["127.0.0.1"])
    if not server.wait_up(a.port):
        sys.exit("the engine did not start on port %d" % a.port)
    return servers + [search]


def _live_stop(servers):
    """The model servers the engine started (each in its job object), then the engine and the search."""
    from paperdaemon.models import hotswap
    hotswap.stop_all()
    for srv in servers:
        if hasattr(srv, "should_exit"):
            srv.should_exit = True
        else:
            srv.shutdown()


def _live_turn(cw):
    """One job on a test notebook's page, run by the real host as the daemon runs it, through the live engine ->
    its ledger entry ({status, note, ...})."""
    from paperdaemon import loop, server, settings
    env = loop.environment(settings.load(), port=LIVE, token=server.host_token(), state=os.path.join(cw, "state"),
                           mirror=os.path.join(cw, "mirror"))
    env.update(PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring", PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", RP._JOB], cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])["entry"]
    except (ValueError, IndexError, KeyError):
        raise RuntimeError("the host did not finish:\n%s" % (p.stderr or p.stdout)[-2000:])


# ---------------------------------------------------------------- pictures

def _tablet(page, dst, width=900):
    """A page as the tablet shows it, drawn as a reMarkable Paper Pro: one screen of it, scrolled down as far as its
    content needs when that runs past the first screen (content up to a quarter-screen taller is shown whole, a
    little smaller, centered), set in the device's front: 196.6 x 274.1 mm around an 11.8-inch 3:4 display, the top
    and sides even, the bottom deeper, two grooves running round the edge, the white of the display a touch warm and
    its colors a touch quieter, as color e-ink shows them."""
    from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter
    pg = Image.open(page).convert("RGB")
    first = round(pg.width * 4 / 3)                            # the screen is 3:4; a longer page scrolls
    box = ImageChops.difference(pg, Image.new("RGB", pg.size, "white")).getbbox() or (0, 0, 0, 0)
    pad = round(pg.width * 0.04)
    canvas = Image.new("RGB", (pg.width, first), "white")
    tall = box[3] - box[1] + 2 * pad
    if tall > first * 1.25:                                    # pages of content: the first screen of it
        canvas.paste(pg.crop((0, max(0, box[1] - pad), pg.width, min(pg.height, max(0, box[1] - pad) + first))), (0, 0))
    elif tall > first:
        part = pg.crop((0, max(0, box[1] - pad), pg.width, min(pg.height, box[3] + pad)))
        part = part.resize((round(part.width * first / part.height), first), Image.LANCZOS)
        canvas.paste(part, ((pg.width - part.width) // 2, 0))
    else:
        top = max(0, min(box[1] - pad, box[3] + pad - first))
        canvas.paste(pg.crop((0, top, pg.width, min(pg.height, top + first))), (0, 0))
    pg = canvas.resize((width, round(first * width / pg.width)), Image.LANCZOS)
    pg = ImageChops.multiply(ImageEnhance.Color(pg).enhance(0.88), Image.new("RGB", pg.size, (247, 246, 242)))
    mm = width / 179.8                                         # the display is 179.8 x 239.8 mm
    side, chin, radius = 8.4 * mm, 25.9 * mm, 7.5 * mm
    w, h = round(width + 2 * side), round(pg.height + side + chin)
    k = 3                                                      # drawn three times larger, for smooth curves
    big = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=radius * k, fill=(220, 219, 215, 255))
    for inset, shade in ((0.0, (168, 166, 161)), (0.9, (196, 194, 189)), (1.7, (196, 194, 189))):
        e = inset * mm * k
        d.rounded_rectangle((e, e, w * k - 1 - e, h * k - 1 - e), radius=max(1.0, radius * k - e),
                            outline=shade + (255,), width=max(1, round(0.22 * mm * k)))
    body = big.resize((w, h), Image.LANCZOS)
    margin = round(7 * mm)                                     # room for the shadow it casts
    out = Image.new("RGBA", (w + 2 * margin, h + 2 * margin), (0, 0, 0, 0))
    shade = Image.new("L", out.size, 0)
    ImageDraw.Draw(shade).rounded_rectangle((margin, margin + round(2 * mm), margin + w, margin + h + round(2 * mm)),
                                            radius=round(radius), fill=70)
    out.paste(Image.new("RGBA", out.size, (0, 0, 0, 255)), (0, 0), shade.filter(ImageFilter.GaussianBlur(3 * mm)))
    out.alpha_composite(body, (margin, margin))
    x, y = margin + round(side), margin + round(side)
    out.paste(pg, (x, y))
    ImageDraw.Draw(out).rectangle((x - 1, y - 1, x + pg.width, y + pg.height), outline=(190, 188, 183, 255))
    out.save(dst, optimize=True)


CARD = ""


def main():
    global CARD, LIVE
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "images"))
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--only", default="", help="these pages only (ids, comma separated), and no screens")
    ap.add_argument("--no-screens", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the work folder, and say where it is")
    ap.add_argument("--from", dest="reuse", default="", help="the screens only, from a work folder kept by --keep")
    ap.add_argument("--context", type=int, default=0,
                    help="with --live: the text model's context, in tokens, in place of its script's own "
                         "(room on the card)")
    ap.add_argument("--live", default="", metavar="LINEUP",
                    help="the pages made by the real models: the user's lineup LINEUP (from their settings), run by a "
                         "throwaway engine on this tool's ports")
    ap.add_argument("--resume", default="", help="go on in a work folder an earlier run kept (or left when it was "
                                                  "stopped): the notebooks made there are used, the rest are made")
    a = ap.parse_args()
    if a.port == 8770:
        sys.exit("8770 is PaperDaemon's own port; use a test port")
    only = [x for x in a.only.split(",") if x]
    from paperdaemon import paths
    content = paths.content_dir()                              # the user's own, before the throwaway home: the faces
    lineup = _live_lineup(paths.settings_file(), a.live) if a.live else None
    if lineup and a.context:                                   # llama.cpp's context (-c) in the text model's script
        lineup["text"]["script_text"] = re.sub(r"(?<=\s)-c\s+\d+", "-c %d" % a.context, lineup["text"]["script_text"])
    CARD = _card()
    if a.reuse:
        home = os.path.join(a.reuse, "home")
        os.environ.update(PAPERDAEMON_HOME=home, RM_MIRROR=os.path.join(home, "mirror"),
                          RM_CACHE=os.path.join(home, "mirror"))
        with open(os.path.join(a.reuse, "made.json"), encoding="utf-8") as f:
            _screens(home, json.load(f)["wave"], a)
        if not a.keep:
            shutil.rmtree(a.reuse, ignore_errors=True)
        return
    work = a.resume or tempfile.mkdtemp(prefix="pd-readme-")
    try:
        home = os.path.join(work, "home")
        mirror = os.path.join(home, "mirror")
        os.makedirs(mirror, exist_ok=True)
        _pin(home, CARD)
        have = _made(mirror)
        # THIS PROCESS'S PAPERDAEMON is the throwaway one from the start: its modules read where the library is when
        # they are first imported
        os.environ.update(PAPERDAEMON_HOME=home, RM_MIRROR=mirror, RM_CACHE=mirror)
        if os.path.isdir(content):
            os.environ["PAPERDAEMON_CONTENT"] = content
        os.environ["PAPERDAEMON_STOCKFISH"] = _stockfish(work)
        _search_by_commons()
        _paint_from_klein()
        notes = os.path.join(home, "rm-notepad")                  # each notebook's notes, for the Daemon's Notes
        os.makedirs(a.out, exist_ok=True)
        made = []                                                 # (notebook, page picture), the newest last
        engine = _live_engine(a, lineup) if lineup else None
        LIVE = a.port if lineup else None
        try:
            for demo in DEMOS:
                if (only and demo["id"] not in only) or (demo.get("live") and not lineup):
                    continue
                if demo["name"] not in have:
                    shutil.rmtree(os.path.join(work, demo["id"]), ignore_errors=True)    # a turn a stopped run left
                    have[demo["name"]] = _demo(demo, work, home, mirror, notes)
                made.append((have[demo["name"]], os.path.join(work, demo["id"] + ".png"), demo["id"]))
        finally:
            if engine:
                _live_stop(engine)
        paintings = []
        if not only:
            for src, name in DECOMPOSED:
                if name not in have:
                    have[name] = str(uuid.uuid4())
                    _python(_PICTURE_JOB, _env(home, mirror), have[name], name, os.path.join(PAINTINGS, src))
                paintings.append((have[name], os.path.join(work, src + ".png"), src))
        _python(_DRAW_JOB, _env(home, mirror), json.dumps([[d, p] for d, p, _ in made + paintings]))
        for doc, png, did in made:
            _tablet(png, os.path.join(a.out, "tablet-%s.png" % did))
            print(os.path.join(a.out, "tablet-%s.png" % did))
        if only:
            return
        # THE LIBRARY'S ORDER: last touched first, the paintings among the pages; two folders above them
        order = [paintings[0][0], made[0][0], paintings[1][0], made[1][0], made[2][0], paintings[2][0]] + \
            [d for d, _, _ in made[3:]]
        now = int(datetime.datetime.now().timestamp() * 1000)
        for i, doc in enumerate(order):
            _meta(mirror, doc, lastModified=str(now - i * 3600000), lastOpened=str(now - i * 3600000))
        for name in ("Journal", "Work"):
            if name not in have:
                _folder(mirror, name, now)
        with open(os.path.join(work, "made.json"), "w", encoding="utf-8") as f:     # for --from
            json.dump({"wave": paintings[0][0]}, f)
        if not a.no_screens:
            _screens(home, paintings[0][0], a)
    finally:
        if a.keep:
            print("kept:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


def _screens(home, wave, a):
    """The window's screens, from a throwaway engine over the notebooks just made (tools/readme_editor.mjs)."""
    US._throwaway_keyring()
    from paperdaemon import server, settings, studio, vault
    from paperdaemon.remarkable import auth
    s = settings.load()
    s["server"]["port"] = a.port
    s["mirror"]["edit"] = True                                     # the editor's tools on a Mirror page
    s["risks"]["acknowledged"] = True                              # the screens, not the first open
    s["render"]["processor"] = False
    if CARD:
        s["render"]["card"] = CARD
    s["location"] = dict(s.get("location") or {}, **_PLACE["location"])   # the place the pages were made for
    s["network"]["allowed"] = True
    lu = dict(s["lineups"][0], name=LINEUP["name"], tags=LINEUP["tags"])
    for role in ("text", "image"):
        lu[role] = dict(lu.get(role) or settings.slot_defaults(role), **LINEUP[role])
    lu["search"] = dict(lu.get("search") or settings.search_defaults(), **LINEUP["search"])
    s["lineups"], s["lineup"] = [lu], LINEUP["name"]
    settings.save(s)
    vault.put(auth.DEVICE_KEY, "header.e30.signature")            # a stand-in login: the screens, not the first run
    for src, _ in reversed(DECOMPOSED):                            # the paintings kept on the Decompose screen
        with open(os.path.join(PAINTINGS, src), "rb") as f:
            studio.decompose(base64.b64encode(f.read()).decode(), 1400, keep=src)
    servers = server.serve(a.port, ["127.0.0.1"])
    if not server.wait_up(a.port):
        sys.exit("the engine did not start on port %d" % a.port)
    try:
        subprocess.run(["node", os.path.join(ROOT, "tools", "readme_editor.mjs"), str(a.port), server.pairing_token(),
                        a.out, wave], check=True, timeout=300)
    finally:
        for srv in servers:
            srv.should_exit = True


if __name__ == "__main__":
    main()
