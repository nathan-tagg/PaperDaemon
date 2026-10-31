"""PaperDaemon's local API: the one surface for the desktop window now, and for other devices over a
WireGuard tunnel later. Every route lives under /api/v1; a change that would break one adds /api/v2.

EVERY /api request must carry the pairing token (Authorization: Bearer <token>), from localhost too:
this API can write to the tablet and drive the graphics card. The desktop window is handed the token at
start; another device gets it by pairing (Settings > Network shows it). A shell that supervises the
engine may set PAPERDAEMON_PAIRING_TOKEN for it; that token is used as given and never stored. Bodies
and answers are JSON; an error answers {"error": "<what went wrong>"} with a 4xx status.

THE CONTRACT (all under /api/v1)

Engine and settings
  GET    /status                 {version, tablet, pull, secrets, loop, lineup, first_run}
                                 first_run: no settings saved yet, or no device token set
  GET    /settings               {settings, secrets}       PUT /settings  (the whole settings) -> same
  PUT    /secret/{name} {value}  DELETE /secret/{name}     names: device_token
  PUT    /keys/{role} {where, value}   an API key for one server or search service (role text, image or search)
  GET    /pairing                {token}                   POST /pairing/rotate -> {token}

Tablet
  POST   /tablet/check           {ok, generation?, tablet?, error?}   sign in and read the library's root
  POST   /tablet/pull            {started, pull}                       bring the mirror up to date
  POST   /tablet/desktop-token   {mode: borrow|steal} -> {found, set, removed?}   take the reMarkable desktop app's login on this
                                                computer (stored in the credential store, never a file)

Lineups (a lineup = {name, text: slot, image: slot}; a slot = {location, script, harness, ...})
  Every lineup is live: a page's tag picks the lineup that works it. `in_use` is the lineup of the job
  running now (or the last one), null before the first.
  GET    /lineups                {in_use, lineups: [lineup]}
  PUT    /lineups/{name}         body: a lineup (a "name" in the body renames it, its memories kept) -> {in_use, lineups}
  DELETE /lineups/{name}         -> {in_use, lineups}       (its memories deleted with it)
  GET    /lineups/{name}/memories          {memories: [{id, text, saved}], max}   what its model has learned
  PUT    /lineups/{name}/memories/{id} {text} -> {memories, max}          the user's edit
  DELETE /lineups/{name}/memories/{id}      -> {memories, max}

Start scripts (files in <data>/start-scripts/)
  GET    /scripts                [{name, path, text}]
  PUT    /scripts/{name} {text}  -> {name, path, text}
  GET    /scripts/templates      [{name, text}]            the templates PaperDaemon ships
  GET    /scripts/contract       {text}                    what a start script is given and must do

Harnesses
  GET    /harnesses              [{id, name, kind, extends, source, fields}], plus {file, error} entries
                                 for user harness files that did not load (they carry "error"); an image
                                 harness's fields include its prompt styles and its abilities

Models (the active lineup's two slots)
  GET    /models                 {text: slot view, image: slot view, lineup}
  POST   /models/{role}/start    start the slot's server now (by the engine rule): {started, work}
  POST   /models/{role}/stop     end PaperDaemon's own server for the slot: {stopped}

Tablet loop and jobs
  POST   /loop/start             loop status (below)       POST /loop/stop -> loop status
  GET    /loop                   {running, msg, lineup (in use), restart_pending, busy, card, halves}
  GET    /jobs?limit=50          [{key, notebook, doc_id, page, status, note, started, finished}], newest first
  GET    /queue                  [{key, notebook, doc_id, page, status, why, queued}], in the order they will be worked
  POST   /queue/order            {keys: [...]} -> the queue: the user's order for the waiting jobs
  POST   /queue/drop             {key} -> the queue: a waiting job taken out (its page settled until it changes)
  POST   /queue/abandon          {key} -> the queue: the job being worked stopped at once and thrown away (what it
                                 had written to its notebook put back from the cloud)

Notepads
  GET    /notepads               [{doc, notebook, entries, chars}]
  GET    /notepads/{doc}         {doc, notebook, text}
  POST   /notepads/{doc}/wipe    {wiped: entries removed}   (refused while a job is working)

Places (the Location control)
  GET    /places?q=              [{label, lat, lon, holidays}], best first

Decompose and send
  POST   /decompose {image (data URL or link), width, job?, keep?, name?}  {preview (PNG data URL), strokes, points, seconds, box, width, height}
  GET    /decompose/progress?job=                   {state: waiting | running, done: 0..1}
  POST   /decompose/send {id} or {image, width}     {sent, doc, page, created, strokes}
  POST   /decompose/save {id} or {image, name}      {path, name}: the decomp's picture in the user's Downloads
  GET    /decomps?offset=&limit=                    {total, items}: the kept decomps, newest first
  GET    /decomps/{id}/preview.png                  a kept decomp's preview, at the tablet's own scale
  DELETE /decomps/{id}                              {deleted}
  POST   /logs/send                                 {sent, doc, pages, first}: the logs as pages in the inbox

Benchmark
  GET    /tests?lineup=          {result: {finished, rows, passed, total} or null, changed, plan: [row]}: the
                                 lineup's latest test, gone once the lineup changes (no history)
  POST   /tests/run {lineup?}    starts a run: the run's status
  GET    /tests/status           {id, running, lineup, msg, started, finished, passed, failed,
                                  cases: [{id, title, result (queued|working|pass|fail|canceled), seconds, notes}]}
  POST   /tests/cancel           {canceled}

THE HOST'S SURFACE (/host, for the pipeline's host, with the host token: a token made fresh at every
start, handed to the host through its environment, and good for /host only)
  POST /host/load {key}    GET /host/status    POST /host/generate    POST /host/edit    GET /host/image/{name}
  POST /host/lineup {name}  the lineup the next job runs on (the one owning the job's tag)
  GET /host/memories?lineup=    POST /host/memories {lineup, changes}   the lineup's memories, and the model's changes
  /host/llm/<token>/...    the text slot, reached through the engine: /health, and every /v1 route (the
                           host sends no headers of its own, so the token is part of the address)
"""
import json
import re
import os
import secrets
import sys
import threading
import time

import uvicorn
from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from . import __version__, card, harnesses, ledger, loop, notepad, paths, scripts, settings, vault
from .models import adapters, checks, hotswap, slots
from .remarkable import auth

UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
API = "/api/v1"
PAIRING = "pairing-token"
# the secrets the settings page may set, by the name the page uses -> the credential store name
SECRETS = {f["path"].split(".", 1)[1]: f["store"] for f in settings.SCHEMA if f["type"] == "secret"}

_pair = {"token": None}
_engine = {"port": settings.API_PORT}
_pull = {"running": False, "started": None, "files": 0, "bytes": 0, "documents": 0, "documents_total": 0,
         "bytes_total": 0, "result": None, "error": None, "error_code": None}
# background work on the model slots: a check, or a server start, per slot
_work = {role: {"kind": None, "running": False, "since": None, "waited": 0, "report": None, "error": None}
         for role in slots.ROLES}


def pairing_token():
    if not _pair["token"]:
        # a supervising shell may hand the engine its token; it is then used as given and never stored
        t = os.environ.get("PAPERDAEMON_PAIRING_TOKEN", "").strip()
        if t:
            _pair["token"] = t
            return t
        t = vault.get(PAIRING)
        if not t:
            t = secrets.token_urlsafe(32)
            try:
                vault.put(PAIRING, t)
            except Exception:
                pass                              # no credential store: the token lives for this session
        _pair["token"] = t
    return _pair["token"]


def rotate_pairing():
    t = secrets.token_urlsafe(32)
    try:
        vault.put(PAIRING, t)
    except Exception:
        pass
    _pair["token"] = t
    return t


app = FastAPI(title="PaperDaemon", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)


LLM_PREFIX = "/host/llm/"
# the host's own token: made fresh at every start and good only for /host, so a copy of it in a pipeline
# log opens nothing once PaperDaemon has restarted, and never the API
_host = {"token": secrets.token_urlsafe(24)}


def host_token():
    return _host["token"]


@app.middleware("http")
async def require_pairing(request: Request, call_next):
    path = request.url.path
    if path.startswith(LLM_PREFIX):
        # the host speaks to the text model as to any OpenAI-compatible server, without headers of its
        # own, so its address carries the host token: /host/llm/<token>/v1/...
        got = path[len(LLM_PREFIX):].split("/", 1)[0]
        if not secrets.compare_digest(got.encode(), host_token().encode()):
            return JSONResponse({"error": "not paired"}, status_code=401)
    elif path.startswith("/host/"):
        got = request.headers.get("authorization", "")
        if not secrets.compare_digest(got.encode(), ("Bearer " + host_token()).encode()):
            return JSONResponse({"error": "not paired"}, status_code=401)
    elif path.startswith("/api/"):
        got = request.headers.get("authorization", "")
        if not secrets.compare_digest(got.encode(), ("Bearer " + pairing_token()).encode()):
            return JSONResponse({"error": "not paired"}, status_code=401)
    return await call_next(request)


def _secret_flags():
    """Which secrets are set (never their values), and the names of the API keys kept (key:<role>:<where>)."""
    return dict({k: vault.has(v) for k, v in SECRETS.items()}, keys=vault.keys())


def _bad(msg, code=400):
    return JSONResponse({"error": msg}, status_code=code)


def _first_run():
    if not settings.exists():
        return True
    try:
        return not auth.describe().get("set")
    except Exception:
        return True


def _login_method():
    """"borrowed" when the reMarkable desktop app still holds the same login as PaperDaemon, "stolen" when it
    does not (it was taken from the app, or the app has logged in again since)."""
    try:
        from .remarkable import desktop_token
        t = str(desktop_token.find() or "").strip()
        if t.startswith("@ByteArray(") and t.endswith(")"):
            t = t[len("@ByteArray("):-1]
        return "borrowed" if t and t == auth.device_token() else "stolen"
    except Exception:
        return None


@app.get(API + "/gpus")
def gpus_list():
    """The machine's graphics cards for Settings' Renderer row: each card (id, name, memory, Direct3D 12 and 11),
    the one pages are drawn on now, and the one chosen by default"""
    from . import gpus
    cs = gpus.cards()
    want = settings._get_path(settings.load(), "render.card") or ""
    now, first = gpus.chosen(cs, want), gpus.chosen(cs)
    return {"cards": [{k: c[k] for k in ("id", "name", "memory", "d3d12", "d3d11")} for c in cs],
            "chosen": now["id"] if now else None, "default": first["id"] if first else None}


@app.get(API + "/status")
def status():
    try:
        tablet = auth.describe()
        if tablet.get("set"):
            tablet["method"] = _login_method()
    except Exception as ex:
        tablet = {"set": False, "error": str(ex)[:160]}
    s = settings.load()
    try:
        from .remarkable import sync
        mirror = {"complete": sync.mirrored()}
    except Exception:
        mirror = {"complete": False}
    return {"version": __version__, "tablet": tablet, "pull": _pull, "mirror": mirror, "secrets": _secret_flags(),
            "loop": loop.status(), "lineup": settings.active(s)["name"], "first_run": _first_run(),
            "can_start": settings.startable(s),
            "false_mirror": {"exists": paths.false_mirror_exists(), "up": bool(_fm.get("port"))},
            "render": _render_status()}


# THE GRAPHICS CARD NOT DRAWING: the engine's pictures (pipeline/page/gpu.py) or the page editor's -- either falls back to
# drawing on the processor, slower; the daemon page says so, with the reason (the first one, this session)
_render_down = {"editor": None}


def _render_status():
    try:
        from .pipeline.page import gpu
        engine = gpu.failure()
    except Exception:
        engine = None
    return {"engine": engine, "editor": _render_down["editor"]}


# A PAGE PAST 250,000 STROKES: the page editor warns once for that page, ever -- kept here by the page's own id (it
# outlives a restart, and a page moved within its notebook), in <data>/editor/large-pages.json
def _large_file():
    return os.path.join(paths.sub("editor"), "large-pages.json")


def _large_key(doc, page):
    from .remarkable import local
    return "%s/%s" % (doc, local.page_id(doc, page))


@app.get(API + "/library/{doc}/page/{page}/large-warned")
def get_large_warned(doc: str, page: int):
    """Has the page editor warned about this page's size before? {"warned": bool}"""
    if not _doc_ok(doc):
        return _bad("not a document id")
    try:
        with open(_large_file(), encoding="utf-8") as f:
            seen = json.load(f)
        return {"warned": _large_key(doc, page) in seen}
    except (OSError, ValueError):
        return {"warned": False}
    except Exception as ex:
        return _bad(str(ex)[:200])


@app.post(API + "/library/{doc}/page/{page}/large-warned")
def post_large_warned(doc: str, page: int):
    """The page editor warned about this page's size: never again for it."""
    if not _doc_ok(doc):
        return _bad("not a document id")
    try:
        key = _large_key(doc, page)
        try:
            with open(_large_file(), encoding="utf-8") as f:
                seen = json.load(f)
        except (OSError, ValueError):
            seen = {}
        seen[key] = int(time.time())
        paths.write_json_atomic(_large_file(), seen)
    except Exception as ex:
        return _bad(str(ex)[:200])
    return {"warned": True}


_FALLBACK = ("lost", "refused", "none", "card")       # the window's words for each: render.why.<code>


@app.post(API + "/render/fallback")
def post_render_fallback(body: dict = Body(default={})):
    """The page editor draws without the graphics card: why, as one of the codes the window words for the user (the
    first this session is kept). What the card itself said goes to the engine's log, never to the screen."""
    code = body.get("code") if body.get("code") in _FALLBACK else "refused"
    detail = str(body.get("why") or "")[:500]
    if detail:
        print("The page editor draws on the processor (%s): %s" % (code, detail), file=sys.stderr, flush=True)
    if not _render_down["editor"]:
        _render_down["editor"] = code
    return {"ok": True}


# THE WINDOW'S CARD: the arguments its web view was started with (the shell's, announced; the development window's), so
# the editor can tell whether it is on the card Settings chose. A change of Renderer or card starts the window again
# with the new ones (_renderer_changed: the shell is told, and answers here once the new window is up); until then the
# editor draws on no card.
_window = {"args": None}


@app.get(API + "/render/window")
def get_render_window():
    """Whether the Renderer is the processor (cpu: the editor draws on the processor, as chosen), and whether the
    window's web view is on the card chosen (current: started with the arguments the Renderer asks for now; a window
    no shell started counts as current)."""
    from . import gpus
    s = settings.load()
    return {"cpu": bool(settings._get_path(s, "render.processor")),
            "current": _window["args"] is None or _window["args"] == gpus.window_for(s)}


@app.post(API + "/render/window")
def post_render_window(body: dict = Body(default={})):
    """The shell started the window again, with these arguments."""
    args = body.get("args")
    if isinstance(args, list) and all(isinstance(a, str) for a in args):
        _window["args"] = args
    return {"ok": True}


def _renderer_changed(s):
    """The Renderer or its card changed: the engine's card let go (its next picture is drawn where Settings says now,
    and a card that failed is tried again), and the window started again by the shell on the new card -- with no
    card at all for the processor."""
    try:
        from .pipeline.page import gpu
        gpu.renderer_changed()
    except Exception:
        pass
    _render_down["editor"] = None
    from . import gpus
    args = gpus.window_for(s)
    if _window["args"] is not None and args != _window["args"]:
        tell_shell("webview " + json.dumps(args))


# ---------------------------------------------------------------- the false mirror
# A library on this computer only, answered by the daemon as the tablet's is. Its own engine (python -m paperdaemon
# --false-mirror PORT, __main__.false_mirror_engine) serves the same API over it with the cloud switched off; the
# False Mirror tab's requests come here as /fm/... and go on to it unchanged, so every library route, picture and
# cache is the same code over the other folder.

_fm = {"proc": None, "port": None}
_fm_lock = threading.Lock()


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fm_start():
    """The false mirror's engine, when there is a false mirror and it is not running."""
    with _fm_lock:
        if not paths.false_mirror_exists() or (_fm["proc"] is not None and _fm["proc"].poll() is None):
            return
        import subprocess
        port = _free_port()
        from .remarkable import books
        env = dict(os.environ, PAPERDAEMON_PAIRING_TOKEN=pairing_token(), PAPERDAEMON_PARENT=str(os.getpid()),
                   RM_FACES=books.false_mirror_faces())
        _fm["faces"] = env["RM_FACES"]
        cmd = ([sys.executable, "--false-mirror", str(port)] if loop.FROZEN
               else [sys.executable, "-m", "paperdaemon", "--false-mirror", str(port)])
        logs = os.path.join(paths.false_mirror_state_dir(), "logs")
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "engine.out"), "ab") as out:
            kw = dict(env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
            if sys.platform == "win32":
                kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            _fm["proc"] = subprocess.Popen(cmd, **kw)
        _fm["port"] = port
    wait_up(port, timeout=30)


def fm_stop():
    with _fm_lock:
        p, _fm["proc"], _fm["port"] = _fm["proc"], None, None
    if p is not None:
        loop.end(p)


def fm_refresh():
    """The false mirror's engine started again when the faces its pages are set in have changed (the setting, or an
    account signed in or out): a page is drawn as its own library shows it."""
    from .remarkable import books
    if _fm.get("port") and _fm.get("faces") != books.false_mirror_faces():
        fm_stop()
        threading.Thread(target=fm_start, daemon=True).start()


import atexit as _atexit
_atexit.register(fm_stop)


@app.api_route(API + "/fm/{rest:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def fm_proxy(rest: str, request: Request):
    """A False Mirror request, passed on to the false mirror's engine as it came."""
    if not _fm.get("port"):
        await run_in_threadpool(fm_start)
    if not _fm.get("port"):
        return JSONResponse({"error": "there is no false mirror"}, status_code=404)
    import urllib.error
    import urllib.request
    url = "http://127.0.0.1:%d%s/%s" % (_fm["port"], API, rest) + (("?" + request.url.query) if request.url.query else "")
    body = await request.body()
    req = urllib.request.Request(url, data=body or None, method=request.method)
    for h in ("authorization", "content-type", "if-none-match"):          # a page's version goes on, and comes back
        if request.headers.get(h):
            req.add_header(h, request.headers[h])

    def go():
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.status, r.read(), r.headers.get("content-type") or "application/octet-stream", r.headers.get("etag")
        except urllib.error.HTTPError as ex:
            return ex.code, ex.read(), ex.headers.get("content-type") or "application/json", ex.headers.get("etag")
    try:
        code, data, ctype, etag = await run_in_threadpool(go)
    except OSError as ex:
        return JSONResponse({"error": "the false mirror's engine did not answer: %s" % str(ex)[:160]}, status_code=502)
    # the job abandoned is the false mirror's host's: that host is the one to stop (its engine runs no loop)
    if rest == "queue/abandon" and request.method == "POST" and code == 200:
        await run_in_threadpool(lambda: loop.restart_host(who="fm-host"))
    if code == 304:
        return Response(status_code=304, headers={"ETag": etag} if etag else None)
    return Response(content=data, status_code=code, media_type=ctype, headers={"ETag": etag, "Cache-Control": "no-store"} if etag else None)


@app.post(API + "/false-mirror")
def post_false_mirror():
    """Create the false mirror: its library and state folders, a first notebook, its engine, and its halves of the
    loop when the loop runs."""
    if paths.local_only():
        return _bad("not here", 404)
    if not paths.false_mirror_exists():
        os.makedirs(paths.false_mirror_state_dir(), exist_ok=True)
        # THE FALSE MIRROR IS WATCHED FROM THE MOMENT IT IS MADE: its ledger starts now, so every page made or changed
        # in it from here on is a job -- also one made while its daemon was not running yet (ledger.classify)
        paths.write_json_atomic(os.path.join(paths.false_mirror_state_dir(), "rm-ledger.json"),
                                {"version": 1, "entries": {}, "watching_since": int(time.time())})
        os.makedirs(paths.false_mirror_dir())
        made = True
    else:
        made = False
    fm_start()
    if made:                                         # a first notebook, with its first page, made by its own engine
        _fm_call("POST", "/library/notebook", {"name": "Notebook"})
    loop.start_false_mirror()
    return status()


@app.post(API + "/false-mirror/export")
def post_false_mirror_export(body: dict = Body(...)):
    """A false-mirror document exported as a PDF into the user's Downloads folder (a new name when one is taken)
    -> {path, name}."""
    doc = str(body.get("doc") or "")
    if paths.local_only() or not _doc_ok(doc):
        return _bad("not a document id")
    import urllib.request
    fm_start()
    if not _fm.get("port"):
        return _bad("there is no false mirror", 404)
    req = urllib.request.Request("http://127.0.0.1:%d%s/library/%s/export.pdf" % (_fm["port"], API, doc))
    req.add_header("Authorization", "Bearer " + pairing_token())
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
    except Exception as ex:
        return _bad("the document could not be exported: %s" % str(ex)[:200], 502)
    return _to_downloads(body.get("name") or "Document", ".pdf", data)


def _to_downloads(name, ext, data):
    """`data` written into the user's Downloads folder as `name` + `ext` (a new name when one is taken) -> {path, name}."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name)).strip(" .") or "Document"
    folder = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(folder, exist_ok=True)
    path, n = os.path.join(folder, name + ext), 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(folder, "%s (%d)%s" % (name, n, ext))
    with open(path, "wb") as f:
        f.write(data)
    return {"path": path, "name": os.path.basename(path)}


@app.delete(API + "/false-mirror")
def delete_false_mirror():
    """Delete the false mirror: its halves and engine stop, then its folders go, and its inbox setting is cleared."""
    if paths.local_only():
        return _bad("not here", 404)
    import shutil
    loop.stop_false_mirror()
    fm_stop()
    for d in (paths.false_mirror_dir(), paths.false_mirror_state_dir()):
        for _ in range(10):                          # a process just ended may hold a file for a moment
            shutil.rmtree(d, ignore_errors=True)
            if not os.path.exists(d):
                break
            time.sleep(0.5)
    return status()


@app.get(API + "/settings")
def get_settings():
    from . import region
    return {"settings": settings.load(), "secrets": _secret_flags(), "defaults": region.defaults()}


@app.put(API + "/settings")
def put_settings(body: dict = Body(...)):
    try:
        before = settings.load()
        saved = settings.save(body)
        loop.settings_saved()                        # a running daemon and host take the change up when idle
        fm_refresh()
        if any(settings._get_path(before, k) != settings._get_path(saved, k) for k in ("render.processor", "render.card")):
            _renderer_changed(saved)
        return {"settings": saved, "secrets": _secret_flags()}
    except ValueError as ex:
        return _bad(str(ex))


@app.put(API + "/secret/{name}")
def put_secret(name: str, body: dict = Body(...)):
    if name not in SECRETS:
        return _bad("unknown secret", 404)
    if name == "device_token":
        auth.set_device_token(body.get("value"))
        fm_refresh()
    else:
        vault.put(SECRETS[name], body.get("value"))
    return {"secrets": _secret_flags()}


@app.put(API + "/keys/{role}")
def put_key(role: str, body: dict = Body(...)):
    """An API key for one server or search service ({where: its address or the service's name, value}), shared
    by every lineup that uses it; an empty value removes it."""
    if role not in ("text", "image", "search") or not str(body.get("where") or "").strip():
        return _bad("say which role and where the key is for")
    vault.put(vault.key_name(role, body["where"]), body.get("value"))
    return {"secrets": _secret_flags()}


@app.delete(API + "/secret/{name}")
def delete_secret(name: str):
    if name not in SECRETS:
        return _bad("unknown secret", 404)
    vault.delete(SECRETS[name])
    if name == "device_token":
        auth.forget_user_token()
        fm_refresh()
    return {"secrets": _secret_flags()}


# ---------------------------------------------------------------- tablet

@app.post(API + "/tablet/check")
def tablet_check():
    """Sign in with the device token and read the library's root: proof the token works."""
    from .remarkable import sync
    try:
        auth.user_token(force=True)
        root, gen = sync.get_root()
        return {"ok": True, "generation": gen, "tablet": auth.describe()}
    except Exception as ex:
        return {"ok": False, "error": str(ex)[:240]}


def _doing(paused=False):
    """What PaperDaemon is doing, in a few words, for the tray."""
    if _pull.get("running"):
        return "Updating the Mirror"
    if paused:
        return "Resting"
    return "Watching the Mirror" if loop.status().get("running") else "Idle"


def tell_shell(what):
    """One plain-ASCII line to the desktop shell, which reads the engine's output. Best effort: without a
    shell, or with its pipe gone, nothing happens, and whatever called this goes on."""
    try:
        print("PAPERDAEMON_SHELL " + what, flush=True)
    except (OSError, ValueError, UnicodeError):
        pass


@app.post(API + "/tablet/pull")
def tablet_pull():
    """Bring PaperDaemon's mirror up to date, in the background. The first pull copies the whole
    library, which can be gigabytes; /status reports progress."""
    if _pull["running"]:
        return {"started": False, "pull": _pull}
    threading.Thread(target=run_pull, daemon=True).start()
    return {"started": True, "pull": _pull}


_PULL_ONE = threading.Lock()


def run_pull():
    """One pull, here and now, its progress in /status (the Tablet screen's bar and the tray) -> True when it
    finished. The keeper (keeper.py) and the Tablet screen's button both run it; never two at once."""
    from .remarkable import sync
    if not _PULL_ONE.acquire(blocking=False):
        return False
    try:
        return _pull_once(sync)
    finally:
        _PULL_ONE.release()


def _pull_once(sync):
    """One pull. The bar shows only once the cloud has something new: a check that finds the library as it was
    passes without a sign."""
    # the last error stays until a pull succeeds: offline, the check every minute keeps ONE error up, not one that
    # comes and goes with each try
    _pull.update(running=False, started=time.time(), files=0, bytes=0, documents=0, documents_total=0,
                 bytes_total=0, result=None)
    try:
        def plan(documents, size):
            _pull.update(running=True, documents_total=documents, bytes_total=size)
            tell_shell("status Updating the Mirror")

        def progress(name, size):
            if name is None:
                _pull["documents"] += 1
                return
            _pull["files"] += 1
            _pull["bytes"] += size
            total = _pull["bytes_total"]
            pct = min(99, int(100 * _pull["bytes"] / total)) if total else 0     # by bytes, as the bar
            if pct != _pull.get("tray_pct"):
                _pull["tray_pct"] = pct               # the shell's tray tooltip
                tell_shell("status Updating the Mirror - %d%%" % pct)
        r = sync.pull(progress=progress, plan=plan)
        if r.get("changed") or not _pull.get("thumbs_started"):
            from . import thumbs
            _pull["thumbs_started"] = thumbs.wake()      # the page pictures, for what landed
        _pull.update(error=None, error_code=None)
        _pull["result"] = {"changed": r.get("changed"), "downloaded": len(r.get("downloaded") or []),
                           "deleted": len(r.get("deleted") or []), "generation": r.get("generation")}
    except Exception as ex:
        _pull["error"] = "%s: %s" % (type(ex).__name__, str(ex)[:200])
        from .remarkable import auth as _auth
        _pull["error_code"] = "unauthorized" if isinstance(ex, _auth.NotConnected) else "failed"
    finally:
        _pull["running"] = False
        if _pull.pop("start_after", False) and not _pull.get("error"):      # Finish asked to start once it is done
            try:
                loop.start(_engine["port"], host_token())
            except Exception:
                pass
        tell_shell("status " + _doing())
    return not _pull.get("error")


@app.post(API + "/updates/check")
def post_updates_check():
    """Ask the desktop shell to look for an update: the engine tells it on the line it reads (the shell shows
    the version and the changes, and installs only when the user agrees). Without the shell there is nothing
    to update."""
    if not _engine.get("announced"):
        return {"asked": False, "why": "updates are checked by the installed app"}
    tell_shell("check-updates")
    return {"asked": True}


@app.get(API + "/settings/schema")
def get_settings_schema():
    """Every setting: its path, type, default, allowed values, label, help and message."""
    return {"fields": settings.schema()}


@app.post(API + "/tablet/desktop-token")
def tablet_desktop_token(body: dict = Body(default={})):
    """Take the reMarkable desktop app's login: {"mode": "borrow"} copies it into PaperDaemon's credential
    entry; {"mode": "steal"} copies it and then removes it from the app's saved settings, which signs the app
    out. Steal refuses while the app runs, and removes nothing until the copy is safely stored."""
    from .remarkable import desktop_token
    mode = (body or {}).get("mode") or "borrow"
    if mode not in ("borrow", "steal"):
        return _bad("mode is borrow or steal")
    if mode == "steal" and desktop_token.app_running():
        return _bad("Quit the reMarkable app first, then steal its login.", 409)
    token = desktop_token.find()
    if not token:
        return {"found": False, "set": False}
    try:
        auth.set_device_token(token)
    except Exception as ex:
        return {"found": True, "set": False, "error": str(ex)[:160]}
    out = {"found": True, "set": vault.has(auth.DEVICE_KEY)}
    fm_refresh()
    if mode == "steal" and out["set"]:
        out["removed"] = desktop_token.remove_login()
    return out


# ---------------------------------------------------------------- lineups

def _lineups_view():
    s = settings.load()
    return {"in_use": settings.in_use(), "lineups": s["lineups"]}


@app.get(API + "/lineups/{name}/features")
def get_lineup_features(name: str):
    """Every feature with its state for the named lineup, and for an off or degraded one its reasons."""
    from .models import lineup
    s = settings.load()
    if settings.lineup(s, name) is None:
        return _bad("no lineup named %r" % name, 404)
    return {"lineup": name, "features": lineup.features(s, name)}


@app.get(API + "/lineups")
def get_lineups():
    return _lineups_view()


@app.get(API + "/lineups/{name}/memories")
def get_memories(name: str):
    from . import memories
    if settings.lineup(settings.load(), name) is None:
        return _bad("no lineup named %r" % name, 404)
    return {"memories": memories.of(name), "max": memories.MAX}


@app.put(API + "/lineups/{name}/memories/{mid}")
def put_memory(name: str, mid: str, body: dict = Body(...)):
    """The user's edit of a memory's text (the user cannot add one)."""
    from . import memories
    try:
        memories.edit(name, mid, body.get("text"))
    except KeyError as ex:
        return _bad(str(ex).strip("'\""), 404)
    except ValueError as ex:
        return _bad(str(ex))
    return {"memories": memories.of(name), "max": memories.MAX}


@app.delete(API + "/lineups/{name}/memories/{mid}")
def delete_memory(name: str, mid: str):
    from . import memories
    if not memories.remove(name, mid):
        return _bad("no memory %s" % mid, 404)
    return {"memories": memories.of(name), "max": memories.MAX}


@app.put(API + "/lineups/{name}")
def put_lineup(name: str, body: dict = Body(...)):
    s = settings.load()
    new = settings.normalize_lineup(dict(body, name=body.get("name") or name))
    idx = [i for i, lu in enumerate(s["lineups"]) if lu["name"] == name]
    if idx:
        old = s["lineups"][idx[0]]
        merged = settings.normalize_lineup({"name": new["name"],
                                            "text": dict(old["text"], **(body.get("text") or {})),
                                            "image": dict(old["image"], **(body.get("image") or {})),
                                            "search": dict(old.get("search") or {}, **(body.get("search") or {})),
                                            "tags": body["tags"] if "tags" in body else old.get("tags") or []})
        s["lineups"][idx[0]] = merged
        if s["lineup"] == name:
            s["lineup"] = merged["name"]
        if merged["name"] != name:
            from . import loras, memories
            memories.rename(name, merged["name"])        # a renamed lineup keeps its memories
            try:
                loras.rename(name, merged["name"])       # and its LoRAs
            except OSError:
                pass
            if settings.in_use() == name:
                settings.use(merged["name"])
    else:
        s["lineups"].append(new)
    try:
        settings.save(s)
    except ValueError as ex:
        return _bad(str(ex))
    return _lineups_view()


@app.post(API + "/lineups/{name}/loras/open")
def post_lineup_loras_open(name: str):
    """The lineup's LoRA folder in the file manager (made when it is not there) -> {path, files}."""
    from . import loras
    if settings.lineup(settings.load(), name) is None:
        return _bad("no lineup named %r" % name, 404)
    try:
        return {"path": loras.open_folder(name), "files": loras.files(name)}
    except OSError as ex:
        return _bad(str(ex)[:200])


@app.delete(API + "/lineups/{name}")
def delete_lineup(name: str):
    s = settings.load()
    if settings.lineup(s, name) is None:
        return _bad("no lineup named %r" % name, 404)
    if len(s["lineups"]) < 2:
        return _bad("keep at least one lineup")
    if settings.in_use() == name and not card.idle():
        return _bad("a job is running on this lineup; delete it once the job is done")
    s["lineups"] = [lu for lu in s["lineups"] if lu["name"] != name]
    try:
        settings.save(s)
    except ValueError as ex:
        return _bad(str(ex))
    from . import memories
    memories.drop(name)                                  # a deleted lineup's memories go with it
    if settings.in_use() == name:
        settings.use(None)
    return _lineups_view()


# ---------------------------------------------------------------- places, the library and harnesses

@app.get(API + "/places")
def get_places(q: str = ""):
    """The cities `q` names, for the Location control -> [{label, lat, lon, holidays}]."""
    from . import places
    return places.search(q)


@app.get(API + "/library")
def get_library():
    """Everything in the Mirror the way the tablet shows it: folders and documents, each with its parent ("" for My
    files) -> [{id, name, parent, type: folder|document, kind, pages, tags, modified, opened, at_page, cover_page}],
    folders first by name, then the documents last touched first (opened or written in, whichever is later). `at_page` is the page it was last open on
    (1-based); `cover_page` the page its cover shows, by the tablet's own setting (the first page, or the last one
    open)."""
    from .remarkable import library
    out = []
    for u, m in library.items().items():
        t = m.get("type")
        if t not in ("CollectionType", "DocumentType"):
            continue
        pages, kind, tags, at, cover = 0, "", [], 1, 1
        try:
            with open(os.path.join(library.M, u + ".content"), encoding="utf-8") as f:
                c = json.load(f)
        except (OSError, ValueError):
            c = {}
        tags = [str(x.get("name") if isinstance(x, dict) else x) for x in (c.get("tags") or [])]
        if t == "DocumentType":
            kind = c.get("fileType") or "notebook"
            pages = len(_live(c))
            at = _at_page(m, pages, c)
            cover = at if c.get("coverPageNumber") == -1 else 1      # -1: the tablet shows the last page open
        out.append({"id": u, "name": m.get("visibleName") or u, "parent": m.get("parent") or "",
                    "type": "folder" if t == "CollectionType" else "document", "kind": kind, "pages": pages,
                    "tags": tags, "modified": int(str(m.get("lastModified") or 0) or 0),
                    "opened": int(str(m.get("lastOpened") or 0) or 0), "at_page": at, "cover_page": cover})
    # documents last TOUCHED first: opened or written in, whichever is later (writing in a notebook moves its
    # modified time; its opened time is not always sent up with it)
    out.sort(key=lambda d: (d["type"] != "folder",
                            d["name"].lower() if d["type"] == "folder" else -max(d["opened"] or 0, d["modified"] or 0)))
    return out


def _at_page(meta, pages, content=None):
    """The page a document was last open on, 1-based: the page the document itself records as last open (its
    `cPages.lastOpened`, a page id, which stays right when pages are added before it), else the metadata's
    `lastOpenedPage` (counted from 0, and stale in about one notebook of five)."""
    if content:
        pid = ((content.get("cPages") or {}).get("lastOpened") or {}).get("value")
        live = [p.get("id") for p in _live(content)]
        if pid in live:
            return live.index(pid) + 1
    try:
        k = int(meta.get("lastOpenedPage") or 0)
    except (TypeError, ValueError):
        k = 0
    return max(1, min(pages or 1, k + 1))


def _live(c):
    """A document's pages as the tablet shows them (deleted ones left out)."""
    from . import ledger
    try:
        return ledger.live_pages(c)
    except Exception:
        return ((c.get("cPages") or {}).get("pages")) or c.get("pages") or []


@app.get(API + "/library/{doc}")
def get_library_doc(doc: str):
    """One document's tags and each page's tags, for the viewer -> {"tags": [...], "page_tags": [[...], ...]}."""
    from .remarkable import library
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", doc):
        return JSONResponse({"error": "not a document id"}, status_code=400)
    try:
        with open(os.path.join(library.M, doc + ".content"), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        return JSONResponse({"error": "not in the Mirror"}, status_code=404)
    by_page = {}
    for t in c.get("pageTags") or []:
        by_page.setdefault(t.get("pageId"), []).append(str(t.get("name") or ""))
    return {"tags": [str(x.get("name") if isinstance(x, dict) else x) for x in (c.get("tags") or [])],
            "page_tags": [by_page.get(p.get("id"), []) for p in _live(c)]}


@app.get(API + "/library/{doc}/cover.png")
def get_library_cover(doc: str):
    """The document's cover, small, for the grid: the page the tablet shows as its cover (the first page, or the
    last one open, by the document's own setting)."""
    page = _cover_page(doc)
    return _kept_or_missing(doc, page, thumbs_size("cover"))


def thumbs_size(kind):
    from . import thumbs
    return thumbs.COVER if kind == "cover" else thumbs.THUMB


def _cover_page(doc):
    """The page the tablet shows as the document's cover: the first, or the last one open (its own setting)."""
    from .remarkable import library
    page = 1
    try:
        with open(os.path.join(library.M, doc + ".content"), encoding="utf-8") as f:
            c = json.load(f)
        if c.get("coverPageNumber") == -1:
            page = _at_page(library.items().get(doc) or {}, len(_live(c)), c)
    except (OSError, ValueError):
        pass
    return page


def _kept_or_missing(doc, page, size):
    """A grid picture or a cover from the page picture cache, or 404 {"missing": true, "page", "size"}: the window
    draws it on the graphics card and hands it back (PUT .../thumb/{page}?size=), drawn nowhere else (thumbs.py)."""
    from .remarkable import library
    from . import thumbs
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", doc):
        return JSONResponse({"error": "not a document id"}, status_code=400)
    if not library.items().get(doc):
        return JSONResponse({"error": "not in the Mirror"}, status_code=404)
    try:
        out = thumbs.cached(doc, page, size)
    except Exception as ex:
        return JSONResponse({"error": "no such page: %s" % str(ex)[:160]}, status_code=404)
    if out:
        return FileResponse(out, media_type="image/webp", headers={"Cache-Control": "no-store"})
    return JSONResponse({"error": "not drawn yet", "missing": True, "page": page, "size": size}, status_code=404)


@app.get(API + "/library/{doc}/chapters")
def get_library_chapters(doc: str):
    """The document's chapters as the tablet lists them (remarkable/chapters.py) -> [{"title", "page", "level"}];
    [] when it has none."""
    from .remarkable import library
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", doc):
        return JSONResponse({"error": "not a document id"}, status_code=400)
    from .remarkable import chapters
    try:
        return chapters.cached(library.M, doc)
    except Exception:
        return []


@app.get(API + "/library/{doc}/links/{page}")
def get_library_links(doc: str, page: int):
    """The links on one page of a PDF or EPUB, for the viewer to follow: {"aspect": the file's page height over its
    width (the page picture is that page, full width, and below it any ink written past its foot), "links":
    [{"box": [x0, y0, x1, y1] as fractions of the file's page from its top left, "go": the page it takes you to (as
    the viewer counts pages) or null, "uri": a web address or null}]}. A page the user added has none."""
    none = {"aspect": None, "links": []}
    from .remarkable import library, links
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", doc) or page < 1:
        return JSONResponse({"error": "not a document page"}, status_code=400)
    pdf = os.path.join(library.M, doc + ".pdf")
    if not os.path.isfile(pdf):
        return none
    try:
        with open(os.path.join(library.M, doc + ".content"), encoding="utf-8") as f:
            live = _live(json.load(f))
    except (OSError, ValueError):
        return none
    if page > len(live):
        return none
    idx = (live[page - 1].get("redir") or {}).get("value")
    if idx is None:
        return none
    shown = {}
    for i, pg in enumerate(live):
        r = (pg.get("redir") or {}).get("value")
        if r is not None:
            shown.setdefault(int(r), i + 1)
    try:
        got = links.on_page(pdf, int(idx))
        from .pipeline.page import render as R
        size = R.pdf_page_size(pdf, int(idx))
    except Exception:
        return none
    out = []
    for l in got:
        go = shown.get(l["page"]) if l["page"] is not None else None
        if go is None and not l["uri"]:
            continue
        out.append({"box": [round(v, 5) for v in l["box"]], "go": go, "uri": l["uri"]})
    return {"aspect": (size[1] / float(size[0])) if size else None, "links": out}


@app.post(API + "/open-link")
def post_open_link(body: dict = Body(...)):
    """A web link from a page, opened in the user's browser (http and https only)."""
    url = str(body.get("url") or "")
    if not re.match(r"(?i)^https?://", url):
        return _bad("only web links open")
    try:
        os.startfile(url)                            # Windows: the default browser
    except (AttributeError, OSError) as ex:
        return {"opened": False, "error": str(ex)[:200]}
    return {"opened": True}


@app.get(API + "/library/{doc}/thumb/{page}.png")
def get_library_thumb(doc: str, page: int):
    """One page, small, for the viewer's page grid."""
    if page < 1:
        return JSONResponse({"error": "pages count from 1"}, status_code=400)
    return _kept_or_missing(doc, page, thumbs_size("grid"))


@app.put(API + "/library/{doc}/thumb/{page}")
async def put_library_thumb(doc: str, page: int, request: Request):
    """A grid picture or a cover the window drew (?size= the width it was asked for), kept in the page picture cache."""
    from . import thumbs
    if not _doc_ok(doc) or page < 1:
        return _bad("not a page")
    try:
        size = int(request.query_params.get("size") or 0)
    except ValueError:
        size = 0
    if size not in (thumbs.THUMB, thumbs.COVER):
        return _bad("a picture %d or %d wide" % (thumbs.THUMB, thumbs.COVER))
    data = await request.body()
    if not data or len(data) > 8_000_000:
        return _bad("a picture of up to 8 MB")
    try:
        await run_in_threadpool(thumbs.put, doc, page, size, data)
    except Exception as ex:
        return _bad("not kept: %s" % str(ex)[:200])
    return {"kept": True}


@app.post(API + "/library/{doc}/opened")
def post_library_opened(doc: str, page: int = 0):
    """A document, or one of its pages (?page=), was opened: its picture (its cover, or that page's) is forgotten, and
    the next look at it draws it anew (thumbs.py)."""
    from . import thumbs
    if not _doc_ok(doc):
        return _bad("not a document id")
    try:
        n = thumbs.forget(doc, page if page > 0 else _cover_page(doc))
    except Exception:
        n = 0
    return {"forgotten": n}


@app.get(API + "/library/{doc}/page/{page}/source.png")
def get_library_page_source(doc: str, page: int):
    """The PDF's or book's page under a page, alone, the page's frame in size, for the page editor; 404 for a notebook
    page."""
    import io as _io
    from .pipeline.page import render as R
    try:
        im = R.source_image(doc, page)
    except Exception:
        im = None
    if im is None:
        return JSONResponse({"error": "no source page"}, status_code=404)
    b = _io.BytesIO()
    im.save(b, format="PNG")
    return Response(content=b.getvalue(), media_type="image/png")


@app.get(API + "/library/{doc}/page/{page}/text")
def get_library_page_text(doc: str, page: int):
    """The text layer of the PDF's or book's page under a page, for selecting it in the page editor: {text, boxes (one
    [x0, y0, x1, y1] per character, page units), lines ([start, end) character ranges)}; 404 for a page with no PDF
    text. The same for the Mirror and the False Mirror (the document's own PDF, or the book as laid out)."""
    from .pipeline.page import pdf as pagepdf
    if not _doc_ok(doc):
        return _bad("not a document id")
    try:
        got = pagepdf.page_text(doc, page)
    except Exception:
        got = None
    if not got:
        return JSONResponse({"error": "no text on this page"}, status_code=404)
    return JSONResponse(got, headers={"Cache-Control": "no-store"})


@app.post(API + "/harnesses/open")
def post_harnesses_open(body: dict = Body(default={})):
    """Open the harnesses folder of one kind (`kind`: text -> llm, image -> image; its guide is in it) in the
    file manager."""
    folder = harnesses.user_folder()
    sub = harnesses.SUBFOLDERS.get(str((body or {}).get("kind") or ""))
    if sub:
        folder = os.path.join(folder, sub)
    from . import folders
    try:
        folders.open_folder(folder)                  # in front, over PaperDaemon's window
    except (AttributeError, OSError) as ex:
        return {"opened": False, "folder": folder, "error": str(ex)[:200]}
    return {"opened": True, "folder": folder}


@app.get(API + "/harnesses")
def get_harnesses():
    out = [harnesses.describe(p) for p in harnesses.all_harnesses()]
    out += [{"id": None, "name": e["file"], "kind": None, "extends": None, "source": "user", "fields": {},
             "file": e["file"], "error": e["error"]} for e in harnesses.user_errors()]
    return out


# ---------------------------------------------------------------- models

def _slot_view(role, s, lineup=None):
    d = slots.describe(role, s, lineup)
    lu = settings.lineup(s, lineup) if lineup else settings.active(s)
    d["server"] = hotswap.status(role, s, lu[role]) if d["configured"] else None
    d["card"] = card.status(s)["states"][role]
    d["work"] = {k: v for k, v in _work[role].items() if k != "report"}   # the report is last_test
    d["last_test"] = checks.last(role)
    return d


@app.get(API + "/models")
def get_models(lineup: str = ""):
    """The slots of the named lineup (the one in use when none is named)."""
    s = settings.load()
    if lineup and settings.lineup(s, lineup) is None:
        return _bad("no lineup named %r" % lineup, 404)
    name = lineup or settings.active(s)["name"]
    return {"text": _slot_view("text", s, name), "image": _slot_view("image", s, name), "lineup": name}


def _on_lineup(name, fn):
    """Run fn with the named lineup's slots, once the tablet loop has no job (a job's calls go to its own
    lineup, so a test never runs beside one)."""
    while loop.busy() is not None:
        time.sleep(1.0)
    if not name:
        return fn()
    settings.force(name)
    try:
        return fn()
    finally:
        settings.force(None)


def _background(role, kind, fn):
    w = _work[role]
    if w["running"]:
        return False
    w.update(kind=kind, running=True, since=time.time(), waited=0, report=None, error=None)

    def run():
        try:
            w["report"] = fn()
        except Exception as ex:
            w["error"] = "%s" % (str(ex)[:400] or type(ex).__name__)
        finally:
            w["running"] = False
    threading.Thread(target=run, name="%s-%s" % (kind, role), daemon=True).start()
    return True


@app.post(API + "/models/{role}/start")
def post_start(role: str, lineup: str = ""):
    if role not in slots.ROLES:
        return _bad("unknown slot", 404)

    def run():
        def waited(sec):
            _work[role]["waited"] = round(sec)
        _on_lineup(lineup, lambda: card.ensure(role, on_wait=waited))
        return {"started": True}
    return {"started": _background(role, "start", run), "work": _work[role]}


@app.post(API + "/models/{role}/stop")
def post_stop(role: str):
    if role not in slots.ROLES:
        return _bad("unknown slot", 404)
    if card.in_flight().get(role):
        return _bad("a call to the %s model is in progress" % role, 409)
    return {"stopped": hotswap.stop(role)}


# ---------------------------------------------------------------- the tablet loop, jobs, notepads

@app.post(API + "/loop/start-when-ready")
def post_loop_start_when_ready():
    """Setup's Proceed: start now when the Mirror is complete, else as soon as the pull building it ends."""
    if _pull.get("running"):
        _pull["start_after"] = True
        return dict(loop.status(), waiting_for_mirror=True)
    return post_loop_start()


@app.post(API + "/loop/start")
def post_loop_start():
    out = loop.start(_engine["port"], host_token())
    tell_shell("status " + _doing())
    return out


@app.post(API + "/loop/stop")
def post_loop_stop():
    """Pause: the host stops, and so do the model servers PaperDaemon started (their memory and the graphics
    card's are freed; the start scripts bring them back when the next job needs them). A server PaperDaemon did
    not start is never stopped. The daemon goes on queuing what the mirror shows; Start works the queue."""
    loop.pause()
    try:
        from .models import hotswap
        hotswap.stop_all()
    except Exception:
        pass
    try:
        from .pipeline.page import gpu                 # the engine's graphics helper, and its card memory, let go too
        gpu.release()
    except Exception:
        pass
    tell_shell("status " + _doing(paused=True))
    return loop.status()


@app.get(API + "/loop")
def get_loop():
    return loop.status()


@app.get(API + "/jobs")
def get_jobs(limit: int = 50, lineup: str = ""):
    """The latest jobs, newest first; with `lineup`, only that lineup's (a job not yet worked goes by its tag)."""
    s = settings.load()
    rows = ledger.jobs(5000 if lineup else max(1, min(int(limit), 1000)))
    for r in rows:
        r["lineup"] = r.get("lineup") or settings.lineup_name_for(s, r.get("tag"))
    if lineup:
        rows = [r for r in rows if r["lineup"] == lineup][:max(1, min(int(limit), 1000))]
    return rows


@app.post(API + "/fill")
async def post_fill(request: Request, w: int, h: int, ppg: float, flat: int = 0):
    """THE PAGE EDITOR'S FILL, painted by the decomposer itself: the area (w x h grid pixels, one bit each, rows packed
    as numpy.packbits does, the request's body) through its ring planner in C (fastdecomp rmfast.fill, as rm_model runs
    it), placed on the area's own grid. -> {"strokes": [{"pts": [[x, y], ...], "field": width field, "pen": code}]},
    points in grid pixels (a pixel's center at its index), each ring a stroke; `flat` paints as the highlighter."""
    data = await request.body()
    if w <= 0 or h <= 0 or w * h > 16_000_000 or len(data) < (w * h + 7) // 8 or not 0 < ppg < 1000:
        return JSONResponse({"error": "the area does not fit its size"}, status_code=400)

    def run():
        import numpy as np
        from PIL import Image
        from .pipeline.decompose.fastdecomp import rmfast
        from .pipeline.decompose.reference import rm_paint
        bits = np.unpackbits(np.frombuffer(data, np.uint8))[: w * h].reshape(h, w)
        mask = Image.fromarray((bits * 255).astype(np.uint8), "L")
        out = rmfast.fill(mask, (0, 0, 0, 255), float(ppg), (0, 0, w, h), (0, 0), (w, h), 1 if flat else 0, rm_paint)
        return {"strokes": [{"pts": [[float(x), float(y)] for x, y in pts], "field": int(field[0]), "pen": int(pen)}
                            for pts, field, pen, *_ in out]}
    return await run_in_threadpool(run)


@app.get(API + "/progress")
def get_progress():
    """The page a job is working on and how far it is: {doc, page, done, total} (done and total null until the
    model's plan is in), or null when no job is being worked."""
    p = os.path.join(paths.state_dir(), "run", "progress.json")
    try:
        with open(p, encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        return None
    if not any(e.get("status") == "working" and e.get("doc_id") == got.get("doc") for e in ledger.entries().values()):
        return None                                   # a host that stopped mid-job left it behind
    return got


@app.get(API + "/queue")
def get_queue():
    """The jobs waiting and the one being worked, in the order the daemon hands them over."""
    return ledger.queue()


@app.post(API + "/queue/order")
def post_queue_order(body: dict = Body(...)):
    """The user's order for the waiting jobs; the job being worked stays first."""
    keys = body.get("keys") if isinstance(body, dict) else None
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        return JSONResponse({"error": "keys: the queue's keys, in the order wanted"}, status_code=400)
    return ledger.reorder(keys)


@app.post(API + "/queue/drop")
def post_queue_drop(body: dict = Body(...)):
    """A waiting job taken out of the queue; the job being worked cannot be."""
    key = body.get("key") if isinstance(body, dict) else None
    out = ledger.drop(key) if isinstance(key, str) else None
    if out is None:
        return JSONResponse({"error": "not a waiting job"}, status_code=400)
    return out


@app.post(API + "/queue/abandon")
def post_queue_abandon(body: dict = Body(...)):
    """The job being worked, stopped at once and thrown away: the host ends (and with it the job's model call and
    drawing), what the job wrote to its notebook goes back to the cloud's copy, the page is settled, and the host
    starts again for the next job (unless paused). A job writes its page at its commit, its last step; what some
    steps write before it (a game clearing its page, pages a job adds) is what is put back. A document a job pushed
    as its own (an adventure's journal) is already on the tablet and stays."""
    from .remarkable import sync
    key = body.get("key") if isinstance(body, dict) else None
    if not isinstance(key, str) or (ledger.load()["entries"].get(key) or {}).get("status") != "working":
        return JSONResponse({"error": "not the job being worked"}, status_code=400)
    loop.restart_host(then_start=False)
    try:
        out = ledger.abandon(key, revert=lambda doc, since: sync.revert_since(doc, since) + sync.drop_new_since(since))
    finally:
        q = os.path.join(paths.state_dir(), "rm-queue")
        for n in (os.listdir(q) if os.path.isdir(q) else []):
            if n.endswith(".json"):
                try:
                    with open(os.path.join(q, n), encoding="utf-8") as f:
                        if key in (json.load(f).get("keys") or []):
                            os.remove(os.path.join(q, n))
                except (OSError, ValueError):
                    pass
        loop.restart_host()
    if out is None:
        return JSONResponse({"error": "not the job being worked"}, status_code=400)
    return out


@app.get(API + "/notepads")
def get_notepads():
    return notepad.notepads()


@app.get(API + "/notepads/{doc}")
def get_notepad(doc: str):
    try:
        pad = notepad.Notepad(doc)
        try:
            from .pipeline.page import render as _R
            numbers = {p["id"]: i + 1 for i, p in enumerate(_R.live_pages(doc))}
        except Exception:
            numbers = {}
        return {"doc": doc, "notebook": ledger.notebook_name(doc) if notepad.DOC_ID.match(doc) else "",
                "text": pad.text(), "entries": pad.parsed(numbers)}
    except ValueError as ex:
        return _bad(str(ex), 404)


@app.post(API + "/notepads/{doc}/wipe")
def post_notepad_wipe(doc: str):
    why = loop.busy()
    if why and why != "a model call is in progress":
        return _bad("%s; wipe the notepad when it has finished" % why, 409)
    try:
        return {"wiped": notepad.Notepad(doc).wipe()}
    except ValueError as ex:
        return _bad(str(ex), 404)


# ---------------------------------------------------------------- decompose and send

@app.post(API + "/decompose")
def post_decompose(body: dict = Body(...)):
    from . import studio
    try:
        # keep: the Decompose screen's decomps are kept on disk (studio's note), under the picture's name
        out, strokes = studio.decompose(body.get("image"), body.get("width"), preview=not body.get("strokes"),
                                        job=str(body.get("job") or "")[:64] or None,
                                        keep=(str(body.get("name") or "Picture") if body.get("keep") else None),
                                        height=body.get("height"))
    except (ValueError, OSError) as ex:
        return _bad(str(ex)[:300])
    except Exception as ex:
        return _bad("%s: %s" % (type(ex).__name__, str(ex)[:300]), 502)
    if body.get("strokes"):                   # THE STROKES THEMSELVES, for the page editor's paste as strokes (Ctrl+Shift+V)
        out["lines"] = [{"pts": [[float(x), float(y)] for x, y in st[0]], "widths": [int(round(w)) for w in st[1]],
                         "pen": getattr(st[2], "name", str(st[2])), "penCode": int(st[2]), "color": int(st[3]),
                         # the page keeps a color as four numbers, alpha last: the decomposer's three, opaque
                         "colorRgba": ([int(v) for v in st[4]] + [255])[:4] if len(st) > 4 and st[4] else None} for st in strokes]
        # the picture lies centered in a box `box` wide and `box_h` tall (a square without a height), fitted to it, from
        # the decomposer's top
        out["center"] = [0.0, studio.TOP + out["box_h"] / 2.0]
    return out


@app.get(API + "/decomps")
def get_decomps(offset: int = 0, limit: int = 10):
    """The kept decomps, newest first -> {total, items: [{id, name, strokes, points, seconds, width, height, sent}]}."""
    from . import studio
    return studio.decomps_page(offset, limit)


@app.get(API + "/decomps/{did}/preview.png")
def get_decomp_preview(did: str):
    from . import studio
    try:
        return FileResponse(studio.decomp_preview(did), media_type="image/png", headers={"Cache-Control": "max-age=31536000, immutable"})
    except (ValueError, OSError) as ex:
        return _bad(str(ex)[:200], 404)


@app.delete(API + "/decomps/{did}")
def delete_decomp(did: str):
    from . import studio
    try:
        studio.delete_decomp(did)
    except (ValueError, OSError) as ex:
        return _bad(str(ex)[:200], 404)
    return {"deleted": did}


@app.post(API + "/decompose/save")
def post_decompose_save(body: dict = Body(...)):
    """A decomp's picture saved into the user's Downloads folder -> {path, name}: a kept decomp's (`id`) preview, or a
    PNG data URL (`image`)."""
    import base64
    import binascii
    from . import studio
    if body.get("id"):
        try:
            with open(studio.decomp_preview(str(body["id"])), "rb") as f:
                data = f.read()
            name = studio.decomp_meta(str(body["id"])).get("name") or "Picture"
        except (ValueError, OSError) as ex:
            return _bad(str(ex)[:200], 404)
        return _to_downloads(os.path.splitext(name)[0] + " decomp", ".png", data)
    image = str(body.get("image") or "")
    if not image.startswith("data:image/png;base64,"):
        return _bad("not a PNG picture")
    try:
        data = base64.b64decode(image.split(",", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        return _bad("not a PNG picture")
    if not data.startswith(b"\x89PNG") or len(data) > 80 * 1024 * 1024:
        return _bad("not a PNG picture")
    base = os.path.splitext(str(body.get("name") or ""))[0] or "Picture"
    return _to_downloads(base + " decomp", ".png", data)


@app.post(API + "/logs/send")
def post_logs_send():
    """PaperDaemon's logs, as pages added to the inbox notebook: {sent, doc, pages, first}."""
    from . import studio
    try:
        return studio.send_logs()
    except ValueError as ex:
        return _bad(str(ex)[:300])
    except Exception as ex:
        return _bad("%s: %s" % (type(ex).__name__, str(ex)[:300]), 502)


@app.get(API + "/decompose/progress")
def get_decompose_progress(job: str = ""):
    """How far the screen's decompose `job` has come: {state: waiting | running, done: 0..1}."""
    from . import studio
    return studio.progress(job)


@app.post(API + "/decompose/send")
def post_decompose_send(body: dict = Body(...)):
    """SEND TO TABLET LANDS IN EVERY INBOX: every notebook with the inbox tag (Settings: tags.inbox), in the Mirror (with a
    reMarkable account signed in: without one there is no tablet to reach) and in the false mirror when there is one;
    a mirror with none of them takes it at the end of its Quick sheets. Either mirror alone is enough. Nobody is asked
    to pick. -> {sent, mirror?, false_mirror?, errors}."""
    from . import studio
    if paths.local_only():                            # the false mirror's engine: its own inboxes only
        try:
            return studio.send(body.get("image"), body.get("width"), decomp=body.get("id"))
        except (ValueError, OSError) as ex:
            return _bad(str(ex)[:300])
        except Exception as ex:
            return _bad("%s: %s" % (type(ex).__name__, str(ex)[:300]), 502)
    real, fake = _signed_in(), paths.false_mirror_exists()
    if not real and not fake:
        return _bad("sign in to a reMarkable account to send to the tablet")
    if not body.get("id") and not body.get("image"):
        return _bad("send what: a decomp's id or an image")
    # SEND IS KICKED OFF, NOT WAITED FOR: the page written into each inbox and the sync to the tablet (a pull first, a
    # push after, retried while the tablet syncs) take their time in the background; the button is answered at once.
    # Only what can be told at once is said at once -- a Mirror with no inbox to land in; what goes wrong after is
    # logged.
    import threading
    errors = []
    if real:
        try:
            studio._targets(settings.load())
        except ValueError as ex:
            errors.append("Mirror: %s" % str(ex)[:200])
            real = False
    if not real and not fake:
        return _bad("; ".join(errors)[:300], 502)

    def run():
        if real:
            try:
                studio.send(body.get("image"), body.get("width"), settings.load(), decomp=body.get("id"))
            except Exception as ex:
                print("send to the tablet: Mirror: %s" % str(ex)[:200], flush=True)
        if fake:
            code, got = _fm_call("POST", "/decompose/send", body)
            if code != 200:
                print("send to the tablet: False Mirror: %s" % ((got or {}).get("error") if isinstance(got, dict) else got), flush=True)
    threading.Thread(target=run, name="decompose-send", daemon=True).start()
    return {"sent": True, "queued": True, "mirror": bool(real), "false_mirror": bool(fake), "errors": errors}


def _fm_call(method, path, body=None, timeout=600):
    """One request to the false mirror's engine, from this engine -> (status, the decoded JSON or the raw text)."""
    import urllib.error
    import urllib.request
    fm_start()
    if not _fm.get("port"):
        return 404, {"error": "there is no false mirror"}
    req = urllib.request.Request("http://127.0.0.1:%d%s%s" % (_fm["port"], API, path), method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Authorization", "Bearer " + pairing_token())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as ex:
        code, raw = ex.code, ex.read()
    except OSError as ex:
        return 502, {"error": str(ex)[:200]}
    try:
        return code, json.loads(raw)
    except ValueError:
        return code, raw.decode("utf-8", "replace")[:300]


# ---------------------------------------------------------------- the false mirror's own edits (remarkable/local.py)
# Answered only by the false mirror's engine (its requests reach it as /fm/...); the Mirror's engine refuses them all.

def _local(fn, *a):
    from .remarkable import local
    try:
        return fn(*a)
    except local.NotHere as ex:
        return _bad(str(ex), 404)
    except (ValueError, KeyError, OSError) as ex:
        return _bad(str(ex)[:300])


def _doc_ok(u):
    return bool(re.fullmatch(r"[0-9a-fA-F-]{36}", u or ""))


@app.post(API + "/library/notebook")
def post_library_notebook(body: dict = Body(default={})):
    """A new notebook: {name, parent, template (a template's file, with an account signed in), cover: last | first}."""
    from .remarkable import local
    template = str(body.get("template") or "Blank") if _signed_in() else "Blank"
    cover = "first" if body.get("cover") == "first" else "last"
    tags = [str(t) for t in body.get("tags") or [] if str(t).strip()][:20]
    return _local(lambda: {"id": local.new_notebook(str(body.get("name") or ""), str(body.get("parent") or ""),
                                                    template, cover, tags)})


@app.post(API + "/library/quick-sheets")
def post_library_quick_sheets():
    """Quick sheets, as the tablet's button: a new page at the end of the library's one Quick sheets -> {id, page}."""
    from .remarkable import local
    return _local(lambda: dict(zip(("id", "page"), local.quick_sheets())))


@app.post(API + "/library/folder")
def post_library_folder(body: dict = Body(default={})):
    from .remarkable import local
    return _local(lambda: {"id": local.new_folder(str(body.get("name") or ""), str(body.get("parent") or ""))})


@app.post(API + "/library/import")
async def post_library_import(request: Request, name: str = "", parent: str = ""):
    """A PDF or an EPUB, its bytes the request's body, into folder `parent`."""
    from .remarkable import local
    data = await request.body()
    return await run_in_threadpool(_local, lambda: {"id": local.import_file(name, data, parent)})


@app.post(API + "/library/{doc}/pages/{act}")
def post_library_pages_act(doc: str, act: str, body: dict = Body(default={})):
    """Several pages of a notebook at once, as the tablet's page overview does them: delete, duplicate, move ({to, at,
    where: before | after}) or tags ({add, remove}). {pages: [page numbers]} -> {pages: how many}."""
    from .remarkable import local
    if not _doc_ok(doc) or (body.get("to") and not _doc_ok(str(body.get("to")))):
        return _bad("not a document id")
    nos = [int(n) for n in body.get("pages") or [] if str(n).isdigit()]
    if act == "delete":
        return _local(lambda: {"pages": local.delete_pages(doc, nos)})
    if act == "duplicate":
        return _local(lambda: {"pages": local.duplicate_pages(doc, nos)})
    if act == "move":
        at = body.get("at")
        return _local(lambda: {"pages": local.move_pages(doc, nos, str(body.get("to") or "") or None,
                                                          int(at) if at not in (None, "") else None,
                                                          str(body.get("where") or "after"))})
    if act == "tags":
        return _local(lambda: {"pages": local.tag_pages(doc, nos, [str(t) for t in body.get("add") or []],
                                                         [str(t) for t in body.get("remove") or []])})
    return _bad("no such page action", 404)


@app.post(API + "/library/{u}/duplicate")
def post_library_duplicate(u: str):
    from .remarkable import local
    if not _doc_ok(u):
        return _bad("not a document id")
    return _local(lambda: {"id": local.duplicate(u)})


@app.post(API + "/library/{doc}/pages")
def post_library_page(doc: str, body: dict = Body(default={})):
    from .remarkable import local
    if not _doc_ok(doc):
        return _bad("not a document id")
    return _local(lambda: {"page": local.new_page(doc, body.get("after"))})


@app.get(API + "/library/{doc}/export.pdf")
def get_library_export(doc: str):
    from .remarkable import local
    if not _doc_ok(doc):
        return _bad("not a document id")
    got = _local(local.export_pdf, doc)
    return got if isinstance(got, JSONResponse) else Response(content=got, media_type="application/pdf")


@app.post(API + "/library/{u}/move")
def post_library_move(u: str, body: dict = Body(default={})):
    from .remarkable import local
    if not _doc_ok(u):
        return _bad("not an id")
    return _local(lambda: {"moved": local.move(u, str(body.get("parent") or ""))})


@app.delete(API + "/library/{u}")
def delete_library_item(u: str):
    from .remarkable import local
    if not _doc_ok(u):
        return _bad("not an id")
    return _local(lambda: {"deleted": local.delete(u)})


@app.put(API + "/library/{u}/tags")
def put_library_tags(u: str, body: dict = Body(default={})):
    from .remarkable import local
    if not _doc_ok(u):
        return _bad("not an id")
    return _local(lambda: (local.set_tags(u, body.get("tags") or []), {"tags": body.get("tags") or []})[1])


@app.put(API + "/library/{doc}/page/{page}/tags")
def put_library_page_tags(doc: str, page: int, body: dict = Body(default={})):
    from .remarkable import local
    if not _doc_ok(doc):
        return _bad("not a document id")
    return _local(lambda: (local.set_page_tags(doc, page, body.get("tags") or []), {"tags": body.get("tags") or []})[1])


@app.get(API + "/library/{doc}/page/{page}/scene")
def get_library_scene(doc: str, page: int, request: Request):
    """One page as the page editor holds it (remarkable/local.scene_of): the false mirror's pages only. Its version
    (local.page_version) comes as the ETag; asked with the same one (If-None-Match), the answer is 304 and the page is
    not read at all -- the editor looks every few seconds, and a page with a decomp on it is megabytes to read."""
    from .remarkable import local
    if not _doc_ok(doc):
        return _bad("not a document id")
    # either library's page, to read (the window draws its pictures with the editor); written in the False Mirror only
    try:
        version = local.page_version(doc, page)
    except Exception:
        version = ""
    if version and request.headers.get("if-none-match") == version:
        return Response(status_code=304, headers={"ETag": version})
    if request.query_params.get("form") == "bin":   # the editor's binary form (fastrm's note): the points as the file has them
        from .remarkable import fastrm
        got = _local(lambda: local.scene_of(doc, page, arrays=True))
        if not isinstance(got, dict):
            return got
        return Response(fastrm.scene_bytes(got), media_type="application/octet-stream",
                        headers={"ETag": version, "Cache-Control": "no-store"} if version else {"Cache-Control": "no-store"})
    got = _local(local.scene_of, doc, page)
    if isinstance(got, dict) and version:
        return JSONResponse(got, headers={"ETag": version, "Cache-Control": "no-store"})
    return got


@app.get(API + "/library/{doc}/page/{page}/picture/{name}")
def get_library_picture(doc: str, page: int, name: str):
    """A picture placed on the page (a capture, a pasted image), its file as it is: the page editor draws it."""
    from .remarkable import local
    if not _doc_ok(doc):
        return _bad("not a document id")
    try:
        p = local.picture_path(doc, page, name)
    except ValueError as ex:
        return _bad(str(ex)[:200])
    if not p:
        return _bad("no such picture", 404)
    return FileResponse(p, media_type="image/png" if p.endswith(".png") else "image/jpeg")


@app.post(API + "/library/{doc}/page/{page}/picture")
async def post_library_picture(doc: str, page: int, request: Request):
    """A new picture for the page (PNG or JPEG bytes, the request's body), kept beside it under a name of its own:
    -> {name, width, height}. The page editor places it on the page with its next save."""
    from .remarkable import local
    if not _doc_ok(doc):
        return _bad("not a document id")
    data = await request.body()
    if not data or len(data) > 40_000_000:
        return _bad("a picture of up to 40 MB")
    return await run_in_threadpool(_local, lambda: local.add_picture(doc, page, data))


@app.put(API + "/library/{doc}/page/{page}/scene")
async def put_library_scene(doc: str, page: int, request: Request):
    """The page from the editor: its scene as JSON, or in its binary form (application/octet-stream, fastrm's note)."""
    from .remarkable import local, fastrm
    if not _doc_ok(doc):
        return _bad("not a document id")
    data = await request.body()
    try:
        if (request.headers.get("content-type") or "").startswith("application/octet-stream"):
            scene = fastrm.scene_from_bytes(data)
        else:
            scene = json.loads(data)
    except ValueError as ex:
        return _bad("the page could not be read: %s" % str(ex)[:200])
    if not isinstance(scene, dict):
        return _bad("not a page")
    got = await run_in_threadpool(_local, lambda: {"strokes": local.write_scene(doc, page, scene), "version": local.page_version(doc, page)})
    if isinstance(got, JSONResponse):                 # refused: the reason in the engine's output too, for a report
        print("[editor] page %s/%d not saved: %s" % (doc[:8], page, got.body.decode("utf-8", "replace")[:300]), flush=True)
    return got


# ---------------------------------------------------------------- a Mirror page edited in place (remarkable/inplace.py)
# THE TABLET'S OWN PAGES are written from their own files, never anew: the editor reads a page with its ids and its
# stamp, and saves it with that stamp. A save is refused, with the reason the editor shows, when the page changed since
# it was read ("stale", 409), when the tablet changed it in the cloud ("tablet", 409), when the cloud cannot be asked
# ("offline", 503), or when the edit cannot be written in place exactly ("cannot", 422).
def _refused(ex):
    code = {"stale": 409, "tablet": 409, "offline": 503}.get(getattr(ex, "reason", ""), 422)
    print("[editor] mirror page not saved (%s): %s" % (getattr(ex, "reason", "?"), str(ex)[:300]), flush=True)
    return JSONResponse({"error": str(ex), "reason": getattr(ex, "reason", "cannot")}, status_code=code)


_stamps = {}


def _mirror_stamp(doc, page):
    """A Mirror page's stamp now (inplace.stamp_of), its digest made again only when the file's size or time changed."""
    from .remarkable import inplace, local
    path = os.path.join(local.M, doc, local.page_id(doc, page) + ".rm")
    try:
        st = os.stat(path)
    except OSError:
        return inplace.stamp_of(None)
    key, mark = (doc, page), (st.st_size, st.st_mtime_ns)
    kept = _stamps.get(key)
    if kept and kept[0] == mark:
        return kept[1]
    with open(path, "rb") as f:
        s = inplace.stamp_of(f.read())
    if len(_stamps) > 64:
        _stamps.clear()
    _stamps[key] = (mark, s)
    return s


@app.get(API + "/library/{doc}/page/{page}/mirror-scene")
def get_mirror_scene(doc: str, page: int, request: Request):
    """A Mirror page as the editor holds it (local.scene_of), each stroke and layer with its id, and the page's stamp
    ("stamp", also the ETag) to save it with: JSON, or the editor's binary form (?form=bin)."""
    from .remarkable import inplace, fastrm
    if not _doc_ok(doc):
        return _bad("not a document id")
    # ASKED WITH THE STAMP IT HAS (If-None-Match), the editor's look every few seconds: 304 while the page's bytes are the
    # same, and the page is not read (its digest only, kept while the file's size and time hold)
    have = (request.headers.get("if-none-match") or "").strip('"')
    if have:
        try:
            if _mirror_stamp(doc, page) == have:
                return Response(status_code=304, headers={"ETag": have})
        except Exception:
            pass
    arrays = request.query_params.get("form") == "bin"
    got = _local(lambda: inplace.read_page(doc, page, arrays=arrays))
    if not isinstance(got, dict):
        return got
    headers = {"ETag": got["stamp"], "Cache-Control": "no-store"}
    if arrays:
        return Response(fastrm.scene_bytes(got), media_type="application/octet-stream", headers=headers)
    return JSONResponse(got, headers=headers)


@app.put(API + "/library/{doc}/page/{page}/mirror-scene")
async def put_mirror_scene(doc: str, page: int, request: Request):
    """A Mirror page saved from the editor, in place: its scene as JSON or in the binary form, with the stamp it was read
    with (?stamp=, the If-Match header, or the scene's own "stamp"). ?push=1 sends the document to the tablet after.
    -> {strokes, kept, erased, added, text, layers, untouched, changed, stamp, version[, push]}."""
    from .remarkable import inplace, fastrm
    if not _doc_ok(doc):
        return _bad("not a document id")
    data = await request.body()
    try:
        if (request.headers.get("content-type") or "").startswith("application/octet-stream"):
            scene = fastrm.scene_from_bytes(data)
        else:
            scene = json.loads(data)
    except ValueError as ex:
        return _bad("the page could not be read: %s" % str(ex)[:200])
    if not isinstance(scene, dict):
        return _bad("not a page")
    stamp = request.query_params.get("stamp") or (request.headers.get("if-match") or "").strip('"') or scene.get("stamp")
    push = request.query_params.get("push") in ("1", "true")

    def go():
        try:
            got = inplace.write_in_place(doc, page, scene, stamp)
            if push:
                got["push"] = inplace.push(doc)
            return got
        except inplace.Refused as ex:
            return _refused(ex)
        except RuntimeError as ex:                   # written nowhere: the page did not read back
            print("[editor] mirror page %s/%d not saved: %s" % (doc[:8], page, str(ex)[:300]), flush=True)
            return JSONResponse({"error": str(ex)[:300], "reason": "cannot"}, status_code=500)
    return await run_in_threadpool(_local, go)


@app.post(API + "/library/{doc}/page/{page}/mirror-picture")
async def post_mirror_picture(doc: str, page: int, request: Request):
    """A new picture for a Mirror page (PNG or JPEG bytes, the request's body), kept beside it under a name of its own:
    -> {name, width, height}. The editor places it on the page with its next save (mirror-scene)."""
    from .remarkable import inplace
    if not _doc_ok(doc):
        return _bad("not a document id")
    data = await request.body()
    if not data or len(data) > 40_000_000:
        return _bad("a picture of up to 40 MB")
    return await run_in_threadpool(_local, lambda: inplace.add_picture(doc, page, data))


@app.post(API + "/library/{doc}/push")
def post_library_push(doc: str):
    """A Mirror document's edits sent to the tablet now, by PaperDaemon's own sync (the editor's Ctrl+S, or the document
    closed). -> what the push said."""
    from .remarkable import inplace
    if not _doc_ok(doc):
        return _bad("not a document id")

    def go():
        try:
            return inplace.push(doc)
        except Exception as ex:
            if isinstance(ex, (inplace.local.NotHere,)):
                raise
            return JSONResponse({"error": "the document could not be sent to the tablet: %s" % str(ex)[:200],
                                 "reason": "offline"}, status_code=503)
    return _local(go)


@app.post(API + "/library/sync")
def post_library_sync():
    """The false mirror syncs (Ctrl+S in the page editor, or a document closed): the daemon looks at its pages' ink as
    it is now. Between syncs it sees each page as at the last one, never half drawn."""
    from .remarkable import local
    return _local(lambda: (local.sync_request(), {"synced": True})[1])


@app.put(API + "/library/{doc}/page/{page}/template")
def put_library_page_template(doc: str, page: int, body: dict = Body(...)):
    from .remarkable import local
    if not _doc_ok(doc):
        return _bad("not a document id")
    return _local(lambda: (local.set_page_template(doc, page, body.get("file")), {"template": body.get("file")})[1])


# ---------------------------------------------------------------- the tablet's page templates (remarkable/templates.py)
# Borrowed from the user's own desktop app and library, never shipped. Read by the window only: no page a model sees
# is drawn with its template until every reader of a page treats it as background (add-page-editor, D10).

_tpl = {"tried": False}


def _templates():
    from .remarkable import templates
    if not os.path.exists(os.path.join(templates.folder(), "index.json")) and not _tpl["tried"]:
        _tpl["tried"] = True                         # once a run: an app found later is read at the next start
        try:
            templates.extract()
        except Exception:
            pass
    return templates


def _signed_in():
    """Templates, like the tablet's faces, come with a signed-in account (add-epub-reading, D6)."""
    try:
        return bool(auth.describe().get("set"))
    except Exception:
        return False


@app.get(API + "/templates")
def get_templates():
    """Every portrait template there is, defaults and rM Methods, Blank first -> [{name, file, source, icon, drawn}];
    403 {"signin": true} without an account signed in."""
    if not _signed_in():
        return JSONResponse({"error": "sign in to a reMarkable account for templates", "signin": True}, status_code=403)
    return _templates().catalog()


@app.get(API + "/templates/{file}.svg")
def get_template_svg(file: str, w: int = 1620, h: int = 2160, aw: int = 0, ah: int = 0):
    """One template drawn on a w x h page, as SVG (empty for Blank). `aw` x `ah`: the area to cover, centered across the
    page and from its top -- what repeats runs on across all of it (templates.svg)."""
    if not _signed_in():
        return JSONResponse({"error": "sign in to a reMarkable account for templates", "signin": True}, status_code=403)
    T = _templates()
    entry = next((t for t in T.catalog() if t["file"] == file), None)
    if entry is None:
        return JSONResponse({"error": "no such template"}, status_code=404)
    w, h = max(100, min(int(w), 10000)), max(100, min(int(h), 10000))
    aw, ah = max(w, min(int(aw), 20000)), max(h, min(int(ah), 60000))
    area = (-(aw - w) / 2.0, 0.0, w + (aw - w) / 2.0, float(ah))
    return Response(content=T.svg(T.definition(entry), w, h, area=area), media_type="image/svg+xml")


@app.get(API + "/fonts/own/{name}")
def get_own_font(name: str):
    """One of PaperDaemon's own typed-text faces (shipped: Arimo, Gelasio), for the page editor."""
    m = re.fullmatch(r"(Arimo|Gelasio)-(Regular|Bold|Italic|BoldItalic)", name)
    if not m:
        return _bad("not one of PaperDaemon's faces")
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content", "typed-fonts", m.group(1).lower(), name + ".ttf")
    return FileResponse(p, media_type="font/ttf") if os.path.isfile(p) else JSONResponse({"error": "missing"}, status_code=404)


@app.get(API + "/fonts/{name}")
def get_font(name: str):
    """One of the tablet's faces from the content folder (never shipped: the user's own desktop app's), for the page
    editor's typed text; 404 when it is not installed, or when the false mirror is set in PaperDaemon's own faces (no
    account signed in, or its setting)."""
    from .remarkable import books
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", name):
        return _bad("not a font name")
    p = paths.font_file(name)
    if not p or books.false_mirror_faces() != "tablet":
        return JSONResponse({"error": "not installed"}, status_code=404)
    return FileResponse(p, media_type="font/ttf")


# ---------------------------------------------------------------- the benchmark

@app.get(API + "/tests")
def get_tests(lineup: str = ""):
    """The lineup's test: its latest result while the lineup is unchanged, and the table's rows before any run."""
    from . import benchmark
    s = settings.load()
    if lineup and settings.lineup(s, lineup) is None:
        return _bad("no lineup named %r" % lineup, 404)
    return dict(benchmark.result(lineup or None, s), plan=benchmark.plan(lineup or None, s))


@app.post(API + "/tests/run")
def post_tests_run(body: dict = Body(default={})):
    from . import benchmark
    try:
        return benchmark.start(_engine["port"], host_token(), body.get("lineup") or None)
    except KeyError as ex:
        return _bad(str(ex).strip("'\""), 404)
    except RuntimeError as ex:
        return _bad(str(ex), 409)


@app.get(API + "/tests/status")
def get_tests_status():
    from . import benchmark
    return benchmark.status()


@app.post(API + "/tests/cancel")
def post_tests_cancel():
    from . import benchmark
    return {"canceled": benchmark.cancel()}


# ---------------------------------------------------------------- pairing and the UI

@app.get(API + "/pairing")
def get_pairing():
    return {"token": pairing_token()}


@app.post(API + "/pairing/rotate")
def post_rotate():
    return {"token": rotate_pairing()}


# ---------------------------------------------------------------- the host's surface

@app.post("/host/lineup")
def host_lineup(body: dict = Body(default={})):
    """The host names the lineup its next job runs on (the one owning the job's tag): the job's model calls and
    pictures go to that lineup's slots from now on."""
    name = str(body.get("name") or "")
    if settings.lineup(settings.load(), name) is None:
        return _bad("no lineup named %r" % name, 404)
    settings.use(name)
    return {"in_use": name}


@app.get("/host/memories")
def host_memories(lineup: str):
    """The lineup's memories, for the job's instructions."""
    from . import memories
    return {"memories": memories.of(lineup), "max": memories.MAX}


@app.post("/host/memories")
def host_memories_apply(body: dict = Body(default={})):
    """The model's `remember` list from one job's decision, applied to the job's lineup -> {done}."""
    from . import memories
    name = str(body.get("lineup") or "")
    if settings.lineup(settings.load(), name) is None:
        return _bad("no lineup named %r" % name, 404)
    return {"done": memories.apply(name, body.get("changes") or [])}


@app.post("/host/load")
def host_load(body: dict = Body(default={})):
    try:
        return card.load(body.get("key") or "text")
    except ValueError as ex:
        return _bad(str(ex))


@app.post(API + "/search/test")
def post_search_test(lineup: str = ""):
    """One search with the named lineup's web search, for the Test button -> {"ok", "results" | "error"}."""
    from . import search
    try:
        if lineup:
            settings.force(lineup)
        try:
            got = search.query("reMarkable tablet")
        finally:
            if lineup:
                settings.force(None)
        return {"ok": True, "results": len(got.get("results") or [])}
    except Exception as ex:
        return {"ok": False, "error": str(ex)[:200]}


@app.get("/host/search")
def host_search(q: str, images: int = 0):
    """A web search for the host, by the active lineup (paperdaemon/search.py), in SearXNG's shape."""
    from . import search
    try:
        return search.query(q, bool(images))
    except search.SearchError as ex:
        return JSONResponse({"error": str(ex)}, status_code=503)
    except Exception as ex:
        return JSONResponse({"error": "the search failed: %s" % str(ex)[:160]}, status_code=502)


@app.get("/host/status")
def host_status():
    return card.status()


@app.post("/host/generate")
def host_generate(body: dict = Body(...)):
    try:
        return card.generate(body)
    except Exception as ex:
        return {"error": str(ex)[:300] or type(ex).__name__}


@app.post("/host/edit")
def host_edit(body: dict = Body(...)):
    try:
        return card.edit(body)
    except Exception as ex:
        return {"error": str(ex)[:300] or type(ex).__name__}


@app.get("/host/image/{name}")
def host_image(name: str):
    data = card.take_render(name)
    if data is None:
        return _bad("no such picture", 404)
    return Response(data, media_type="image/png")


def _text_upstream(s):
    """(API base URL, headers) of the text slot, for the proxy: a request for v1/<route> goes to <API base>/<route>
    (adapters.api_base: a server's address takes /v1, a location naming its API's path is used as it is)."""
    m = slots.slot("text", s)
    base = adapters.api_base(m.get("location") or "") if (m.get("location") or "").strip() else ""
    # UNCOMPRESSED: the proxy passes the answer's bytes on as they come, without the server's Content-Encoding, so a
    # gzipped error (llama.cpp compresses its error replies) reached the host as "HTTP 400: \x1f\x8b..." -- unreadable
    headers = {"Content-Type": "application/json", "Accept-Encoding": "identity"}
    key = vault.get(slots.key_of("text", m))
    if key:
        headers["Authorization"] = "Bearer " + key
    return base, headers


@app.api_route("/host/llm/{key}/{rest:path}", methods=["GET", "POST"])
async def host_llm(key: str, rest: str, request: Request):
    """The text slot, through the engine. A POST is a model call: the engine makes the text server ready
    first (by the engine rule) and counts the call in flight until its answer has been streamed back."""
    import httpx
    s = settings.load()
    base, headers = _text_upstream(s)
    if not base:
        return JSONResponse({"error": {"message": "the text slot has no location"}}, status_code=503)
    rest = rest.lstrip("/")
    route = rest[3:] if rest.startswith("v1/") else rest          # onto the API base, which carries the version
    if request.method == "GET":
        if rest == "health":
            # healthy when a call would be served: the server answers, or its start script can start it
            ok = await run_in_threadpool(lambda: card.ready("text", s)
                                         or scripts.has_script(slots.slot("text", s)))
            return JSONResponse({"status": "ok"} if ok else {"status": "unavailable"},
                                status_code=200 if ok else 503)
        if not await run_in_threadpool(card.ready, "text", s):
            return JSONResponse({"error": {"message": "the text model is not running"}}, status_code=503)
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as c:
            r = await c.get(base + "/" + route, headers=headers, params=dict(request.query_params))
        return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))

    body = await request.body()
    try:
        d = json.loads(body)
        if isinstance(d, dict):
            d = slots.harness("text", s).tune(d, slots.caps("text", s))
            body = json.dumps(d).encode()
    except (ValueError, TypeError):
        pass
    try:
        await run_in_threadpool(card.acquire, "text")
    except Exception as ex:
        return JSONResponse({"error": {"message": str(ex)[:400]}}, status_code=503)
    if (slots.slot("text", s).get("api") or "openai") != "openai":
        # another API family: the adapter speaks it, and the answer goes back in the shape the host reads
        try:
            req = adapters.from_openai(json.loads(body))
            reply = await run_in_threadpool(lambda: adapters.for_slot("text", s).chat(
                caps=slots.caps("text", s), harness=slots.harness("text", s), **req))
        except Exception as ex:
            return JSONResponse({"error": {"message": str(ex)[:400]}}, status_code=502)
        finally:
            card.release("text")
        return Response(adapters.openai_stream(reply), media_type="text/event-stream")
    released = {"done": False}

    async def finish():
        if not released["done"]:
            released["done"] = True
            card.release("text")

    client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=30.0))
    try:
        upstream = await client.send(client.build_request("POST", base + "/" + route, content=body, headers=headers),
                                     stream=True)
    except Exception as ex:
        await client.aclose()
        await finish()
        return JSONResponse({"error": {"message": "the text server did not answer: %s" % str(ex)[:200]}},
                            status_code=502)

    async def stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        except httpx.HTTPError:                  # the server went away mid-answer: the host sees a short reply
            pass
        finally:
            await upstream.aclose()
            await client.aclose()
            await finish()

    async def cleanup():
        await upstream.aclose()
        await client.aclose()
        await finish()

    return StreamingResponse(stream(), status_code=upstream.status_code,
                             media_type=upstream.headers.get("content-type"), background=BackgroundTask(cleanup))


# ---------------------------------------------------------------- the window's page

@app.get("/")
def index():
    return FileResponse(os.path.join(UI, "index.html"), headers={"Cache-Control": "no-cache"})


@app.middleware("http")
async def _fresh_ui(request: Request, call_next):
    """The window asks again for its screens on every load (a cheap 304 when nothing changed), so a new build is
    never shown through a copy the webview kept from the old one."""
    response = await call_next(request)
    if request.url.path.startswith("/ui/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/ui", StaticFiles(directory=UI), name="ui")


def serve(port, hosts):
    """One server per listening address, each in its own thread -> the uvicorn servers."""
    _engine["port"] = int(port)
    servers = []
    for host in hosts:
        # log_config=None: no uvicorn access log (it would record every request path), and a windowed
        # build has no console for uvicorn's default handlers
        srv = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", log_config=None))
        threading.Thread(target=srv.run, name="api-%s" % host, daemon=True).start()
        servers.append(srv)
    return servers


def wait_up(port, timeout=20.0):
    """True once the localhost server answers."""
    import socket
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False
