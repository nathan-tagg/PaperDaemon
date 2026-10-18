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

Notepads
  GET    /notepads               [{doc, notebook, entries, chars}]
  GET    /notepads/{doc}         {doc, notebook, text}
  POST   /notepads/{doc}/wipe    {wiped: entries removed}   (refused while a job is working)

Places (the Location control)
  GET    /places?q=              [{label, lat, lon, holidays}], best first

Decompose and send
  POST   /decompose {image (data URL or link), width, job?}  {preview (PNG data URL), strokes, points, seconds, box, width, height}
  GET    /decompose/progress?job=                   {state: waiting | running, done: 0..1}
  POST   /decompose/send {image, width}             {sent, doc, page, created, strokes}
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
            "loop": loop.status(), "lineup": settings.active(s)["name"], "first_run": _first_run()}


@app.get(API + "/settings")
def get_settings():
    from . import region
    return {"settings": settings.load(), "secrets": _secret_flags(), "defaults": region.defaults()}


@app.put(API + "/settings")
def put_settings(body: dict = Body(...)):
    try:
        saved = settings.save(body)
        loop.settings_saved()                        # a running daemon and host take the change up when idle
        return {"settings": saved, "secrets": _secret_flags()}
    except ValueError as ex:
        return _bad(str(ex))


@app.put(API + "/secret/{name}")
def put_secret(name: str, body: dict = Body(...)):
    if name not in SECRETS:
        return _bad("unknown secret", 404)
    if name == "device_token":
        auth.set_device_token(body.get("value"))
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
            from . import memories
            memories.rename(name, merged["name"])        # a renamed lineup keeps its memories
            if settings.in_use() == name:
                settings.use(merged["name"])
    else:
        s["lineups"].append(new)
    try:
        settings.save(s)
    except ValueError as ex:
        return _bad(str(ex))
    return _lineups_view()


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


def _page_png(doc, page, size, top=False):
    """Page `page` (1-based) of a document drawn from the Mirror, `size` pixels at most on its long side, from the page
    picture cache (thumbs.py) -> (path, None) or (None, error response)."""
    from .remarkable import library
    from . import thumbs
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", doc):
        return None, JSONResponse({"error": "not a document id"}, status_code=400)
    if not library.items().get(doc):
        return None, JSONResponse({"error": "not in the Mirror"}, status_code=404)
    try:
        return thumbs.draw(doc, page, size, top), None
    except Exception as ex:
        return None, JSONResponse({"error": "could not draw it: %s" % str(ex)[:160]}, status_code=404)


@app.get(API + "/library/{doc}/cover.png")
def get_library_cover(doc: str):
    """The document's cover, small, for the grid: the page the tablet shows as its cover (the first page, or the
    last one open, by the document's own setting)."""
    from .remarkable import library
    page = 1
    try:
        with open(os.path.join(library.M, doc + ".content"), encoding="utf-8") as f:
            c = json.load(f)
        if c.get("coverPageNumber") == -1:
            page = _at_page(library.items().get(doc) or {}, len(_live(c)), c)
    except (OSError, ValueError):
        pass
    out, err = _page_png(doc, page, 480, top=True)
    return err or FileResponse(out, media_type="image/webp")


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
    from . import thumbs
    out, err = _page_png(doc, page, thumbs.THUMB, top=True)
    return err or FileResponse(out, media_type="image/webp")


@app.get(API + "/library/{doc}/page/{page}.png")
def get_library_page(doc: str, page: int):
    """One page, large, for the notebook view."""
    if page < 1:
        return JSONResponse({"error": "pages count from 1"}, status_code=400)
    out, err = _page_png(doc, page, 2160)
    return err or FileResponse(out, media_type="image/webp")


@app.post(API + "/harnesses/open")
def post_harnesses_open(body: dict = Body(default={})):
    """Open the harnesses folder of one kind (`kind`: text -> llm, image -> image; its guide is in it) in the
    file manager."""
    folder = harnesses.user_folder()
    sub = harnesses.SUBFOLDERS.get(str((body or {}).get("kind") or ""))
    if sub:
        folder = os.path.join(folder, sub)
    try:
        os.startfile(folder)                         # Windows: File Explorer
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
        out, _strokes = studio.decompose(body.get("image"), body.get("width"), job=str(body.get("job") or "")[:64] or None)
    except (ValueError, OSError) as ex:
        return _bad(str(ex)[:300])
    except Exception as ex:
        return _bad("%s: %s" % (type(ex).__name__, str(ex)[:300]), 502)
    return out


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
    from . import studio
    try:
        return studio.send(body.get("image"), body.get("width"))
    except (ValueError, OSError) as ex:
        return _bad(str(ex)[:300])
    except Exception as ex:
        return _bad("%s: %s" % (type(ex).__name__, str(ex)[:300]), 502)


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
    headers = {"Content-Type": "application/json"}
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
