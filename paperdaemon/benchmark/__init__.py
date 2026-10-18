"""The benchmark: a fixed set of pages run through the REAL pipeline -- the daemon, the host and the
models of a lineup -- in a state folder and a mirror of their own, so lineups can be compared on the same
cases every time.

Isolation. Each run gets <data>/benchmark/<run id>/ with its own state folder and mirror, filled with the
fixture notebooks (tests/benchmark/cases, built by fixtures.py). The daemon and the host run with:
  - RM_STATE and RM_MIRROR pointed there, so nothing of the user's library or ledger is read or written;
  - RM_HOST_DRY_DOCS=1, so documents a job makes are staged, never published;
  - no credentials (PYTHON_KEYRING_BACKEND set to keyring's null backend), so the daemon cannot pull the
    real library into the fixture mirror or push a fixture page to the tablet;
  - the fixtures' trigger tag, whatever the user's own is.

One table. A run checks the lineup's models first (does each one answer), then runs the page cases, then the tests
that need no pipeline (handwriting, the network). Each is one row of the same table, filled in as it finishes.

One result per lineup. The latest finished run of each lineup is kept with a fingerprint of the lineup as it was;
any change to the lineup voids it (it is shown as out of date until the next run). There is no history.

One runner. The models are reached through the engine like every job (card.call), so the engine rule
holds: a run waits until the tablet loop is idle, pauses it, runs, and puts it back as it was. A lineup
other than the active one is used for the run only and never saved.

A case passes when its job ends "done" and the page gained the kind of content the case asks for:
text (typed text or written strokes), a drawing (strokes or a picture), a chart (a picture: charts reach
the page as pictures) or a picture (a coloring page goes on as one). Seconds
run from the moment the case's job began (it was claimed, and the job before it had ended) to the moment
it ended; the daemon works one job at a time.
"""
import hashlib
import io
import json
import os
import shutil
import threading
import time

from .. import loop, paths
from .. import settings as S
from . import probes

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.dirname(HERE)
DONE = ("done", "skipped")

_run = {"id": None, "running": False, "lineup": None, "started": None, "finished": None, "state": None,
        "cases": [], "models": [], "probes": None, "image": True, "fingerprint": "", "msg": "",
        "cancel": None, "thread": None}
_lock = threading.Lock()


def cases_dir():
    """Where the fixture cases are: PAPERDAEMON_CASES, the source tree's tests/benchmark/cases, or the
    copy packaged with the app."""
    env = os.environ.get("PAPERDAEMON_CASES")
    if env:
        return env
    for p in (os.path.join(os.path.dirname(PACKAGE), "tests", "benchmark", "cases"),
              os.path.join(PACKAGE, "benchmark_cases")):
        if os.path.isdir(p):
            return p
    return os.path.join(os.path.dirname(PACKAGE), "tests", "benchmark", "cases")


def cases():
    """[{id, title, kind, request, expect, doc, page, tag}] in a fixed order."""
    out = []
    d = cases_dir()
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        p = os.path.join(d, n, "case.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def key_of(case):
    return "%s/%s" % (case["doc"][:8], case["page"][:8])


# ---------------------------------------------------------------- what a page holds

def page_content(mirror, doc, page):
    """{strokes, text, pictures} on a page: live pen strokes, typed characters and inserted pictures."""
    out = {"strokes": 0, "text": 0, "pictures": 0}
    path = os.path.join(mirror, doc, page + ".rm")
    import logging
    logging.getLogger("rmscene").setLevel(logging.ERROR)    # it warns about every block newer than it knows
    try:
        from rmscene import read_blocks
        from rmscene import scene_stream as ss
        with open(path, "rb") as f:
            blocks = list(read_blocks(io.BytesIO(f.read())))
        for b in blocks:
            if isinstance(b, ss.SceneLineItemBlock) and getattr(b.item, "value", None) is not None:
                out["strokes"] += 1
            elif isinstance(b, ss.RootTextBlock):
                try:
                    out["text"] += sum(len(x) for x in b.value.items.values() if isinstance(x, str))
                except Exception:
                    pass
    except (OSError, ImportError, ValueError):
        pass
    asset_dir = os.path.join(mirror, doc, page)
    try:
        out["pictures"] = sum(1 for n in os.listdir(asset_dir) if n.lower().endswith((".png", ".jpg", ".jpeg")))
    except OSError:
        pass
    return out


def judge(case, before, after, entry):
    """-> (passed, notes) for one case, from the page before and after and its ledger entry."""
    status = (entry or {}).get("status")
    notes = []
    if status != "done":
        note = str((entry or {}).get("note") or "")
        return False, ["the job ended %s%s" % (status or "without a record", ": " + note[:160] if note else "")]
    gained = {k: after[k] - before[k] for k in before}
    want = (case.get("expect") or {}).get("content", "text")
    if want == "text":
        ok = gained["text"] > 0 or gained["strokes"] > 0
        what = "an answer in words"
    elif want == "drawing":
        ok = gained["strokes"] >= 20 or gained["pictures"] > 0
        what = "a drawing"
    elif want == "chart":
        # a chart reaches the page as a picture; lettering the numbers instead is not a chart
        ok = gained["pictures"] > 0
        what = "a chart (a picture on the page)"
    elif want == "picture":
        # a coloring page goes on as a picture, so it can be colored and erased over
        ok = gained["pictures"] > 0
        what = "a picture"
    else:
        ok, what = False, want
    notes.append("added %d strokes, %d typed characters, %d pictures" % (gained["strokes"], gained["text"],
                                                                       gained["pictures"]))
    if not ok:
        notes.append("expected %s" % what)
    return ok, notes


# ---------------------------------------------------------------- a run

def status():
    with _lock:
        out = {k: v for k, v in _run.items() if k not in ("cancel", "thread")}
        out["cases"] = [dict(c) for c in _run["cases"]]
    out["passed"] = sum(1 for c in out["cases"] if c.get("result") == "pass")
    out["failed"] = sum(1 for c in out["cases"] if c.get("result") == "fail")
    with _lock:
        out["rows"] = rows()
    return out


# ---------------------------------------------------------------- one result per lineup

def fingerprint(lu):
    """What a lineup is, as a short hash: any change to it (models, search, tags, its name) changes this."""
    return hashlib.sha1(json.dumps(lu or {}, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _results_path():
    return os.path.join(paths.sub("benchmark"), "results.json")


def _results():
    try:
        with open(_results_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def result(name=None, s=None):
    """The lineup's latest test: {"result": {finished, rows, passed, total, msg} or None, "changed": the lineup
    changed since it}. A changed lineup's result is not returned: it no longer says anything about the lineup."""
    s = s or S.load()
    lu = S.lineup(s, name) if name else S.active(s)
    r = _results().get((lu or {}).get("name") or name or "")
    if not r:
        return {"result": None, "changed": False}
    if r.get("fingerprint") != fingerprint(lu):
        return {"result": None, "changed": True}
    return {"result": {k: r.get(k) for k in ("finished", "rows", "passed", "total", "msg")}, "changed": False}


def plan(name=None, s=None):
    """The table before any run of the lineup (the one in use when none is named): one row per thing tested."""
    s = s or S.load()
    lu = (S.lineup(s, name) if name else S.active(s)) or {}
    image = bool(str((lu.get("image") or {}).get("location") or "").strip())
    out = [probes.row("model-text", "off", "not_run"),
           probes.row("model-image", "off", "not_run" if image else "no_image")]
    by = {c["id"] for c in cases()}
    for cid, eid, name in CASE_ENTRIES:
        if cid in by:
            out.append(probes.row(eid, "off", "no_image" if cid == "coloring-page" and not image else "not_run"))
    out.insert(min(4, len(out)), probes.row("handwriting", "off", "not_run"))
    out += [probes.row(i, "off", "not_run") for i, n in PROBE_NAMES]
    return out


def start(port, token, lineup=None):
    """Start a run in the background. -> status()."""
    s = S.load()
    if lineup and S.lineup(s, lineup) is None:
        raise KeyError("no lineup named %r" % lineup)
    all_cases = cases()
    if not all_cases:
        raise RuntimeError("no benchmark cases were found in %s" % cases_dir())
    with _lock:
        if _run["running"]:
            raise RuntimeError("a benchmark run is already under way")
        run_id = time.strftime("%Y%m%d-%H%M%S")
        lu = S.lineup(s, lineup) if lineup else S.active(s)
        _run.update(id=run_id, running=True, lineup=lu["name"], started=time.time(),
                    finished=None, state=None, msg="waiting for the tablet loop to be idle",
                    cancel=threading.Event(), models=[], probes=None, fingerprint=fingerprint(lu),
                    report=[], cases=[{"id": c["id"], "title": c["title"], "result": "queued", "seconds": None,
                                       "notes": [], "note": ""} for c in all_cases])
        th = threading.Thread(target=_work, args=(port, token, lineup, all_cases), name="benchmark", daemon=True)
        _run["thread"] = th
    th.start()
    return status()


def cancel():
    with _lock:
        if _run["running"] and _run["cancel"] is not None:
            _run["cancel"].set()
            return True
    return False


def _set(case_id, **kw):
    with _lock:
        for c in _run["cases"]:
            if c["id"] == case_id:
                c.update(kw)


def prepare(state, all_cases):
    """A fresh state folder and mirror holding the fixture notebooks. -> the mirror's path."""
    mirror = os.path.join(state, "mirror")
    os.makedirs(mirror, exist_ok=True)
    for c in all_cases:
        src = os.path.join(cases_dir(), c["id"], "mirror")
        for n in os.listdir(src):
            p = os.path.join(src, n)
            if os.path.isdir(p):
                shutil.copytree(p, os.path.join(mirror, n), dirs_exist_ok=True)
            else:
                shutil.copyfile(p, os.path.join(mirror, n))
    return mirror


def environment(s, port, token, state, mirror, tag):
    """The halves' environment for a run: the cases' tag is the only one watched, and it goes to the lineup under
    test (the one forced for the run), whatever the user's own tags are."""
    import json
    from ..models import lineup as LU
    env = loop.environment(s, port, token, state=state, mirror=mirror)
    with open(env["RM_RUN"], encoding="utf-8") as f:
        run = json.load(f)
    run["tag_lineup"] = {tag.lower(): S.active(s)["name"]}
    env["RM_RUN"] = LU.write_run_file(run, os.path.dirname(env["RM_RUN"]))
    env.update(RM_TRIGGERS=json.dumps([tag]), RM_HOST_DRY_DOCS="1",
               PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    return env


def _work(port, token, lineup, all_cases):
    was_running, was_paused = loop.running(), loop.paused()
    procs = {}
    state = None
    try:
        # one runner: the tablet loop finishes what it is doing, then pauses for the run (a paused loop works
        # nothing, though its queue may hold jobs)
        while not was_paused and loop.busy() is not None:
            if _run["cancel"].wait(2.0):
                raise RuntimeError("canceled before the run began")
        if was_running:
            loop.stop()
        if lineup:
            S.force(lineup)
        s = S.load()
        # the models first: does each answer? A text model that does not leaves nothing for the pages to test
        text_ok = _check_models(s)
        if not text_ok:
            for c in all_cases:
                _set(c["id"], result="fail", notes=["the text model did not pass its check"])
            all_cases = []
        state = paths.sub("benchmark", _run["id"])
        mirror = prepare(state, all_cases)
        before = {c["id"]: page_content(mirror, c["doc"], c["page"]) for c in all_cases}
        tag = all_cases[0].get("tag") or "PaperDaemon"
        env = environment(s, port, token, state, mirror, tag)
        logs = os.path.join(state, "logs")
        with _lock:
            _run.update(state=state, msg="running")
        if all_cases:
            procs.update(loop.spawn_halves(env, state=state, logs=logs))
        pending = {c["id"]: c for c in all_cases}
        since = {}                    # case -> when its job was seen claimed
        last_end = time.time()        # the daemon runs one job at a time: a job starts after the last one ended
        while pending:
            if _run["cancel"].wait(2.0):
                for cid in pending:
                    _set(cid, result="canceled")
                break
            entries = _ledger(state)
            for cid, c in list(pending.items()):
                e = entries.get(key_of(c))
                if not e:
                    continue
                if e.get("status") == "working" and cid not in since:
                    since[cid] = float(e.get("claim_at") or time.time())
                    _set(cid, result="working")
                if e.get("status") in DONE and not e.get("requeue"):
                    after = page_content(mirror, c["doc"], c["page"])
                    ok, notes = judge(c, before[cid], after, e)
                    t1 = float(e.get("completed_at") or time.time())
                    t0 = max(since.get(cid, last_end), last_end)
                    last_end = max(last_end, t1)
                    _set(cid, result="pass" if ok else "fail", notes=notes, seconds=round(max(0.0, t1 - t0), 1),
                         note=str(e.get("note") or ""))
                    pending.pop(cid)
            dead = [w for w, p in procs.items() if p.poll() is not None]
            if dead and pending:
                for cid in pending:
                    _set(cid, result="fail", notes=["the %s stopped: %s" % (" and ".join(dead),
                                                     " | ".join(loop.tail(dead[0], logs)[-3:]))])
                break
        for p in procs.values():          # the halves are done; the Test tab's own tests need no pipeline
            loop.end(p)
        procs.clear()
        if not _run["cancel"].is_set():
            with _lock:
                _run["msg"] = "testing the network"
            with _lock:
                _run["probes"] = []
                _run["msg"] = "reading handwriting"
            hw = probes.handwriting(s, _run["cancel"]) if text_ok else probes.row(
                "handwriting", "fail", "not_run", d="text_failed")
            with _lock:
                _run["probes"].append(hw)
                _run["msg"] = "testing the network"
            for fn in (probes.web_search, probes.social, probes.weather):
                if _run["cancel"].is_set():
                    break
                r = fn(s)
                if r:
                    with _lock:
                        _run["probes"].append(r)
        with _lock:
            _run["msg"] = "finished"
    except Exception as ex:
        with _lock:
            _run["msg"] = "the run failed: %s" % (str(ex)[:300] or type(ex).__name__)
    finally:
        for p in procs.values():
            loop.end(p)
        S.force(None)
        if was_running:
            try:
                loop.start(port, token)
                if was_paused:
                    loop.pause()
            except Exception:
                pass
        with _lock:
            _run.update(running=False, finished=time.time())
            canceled = _run["cancel"].is_set()
        if not canceled:
            _record()


# the Test tab: one entry per thing a lineup can do, in this order; the page cases' entries come first
CASE_ENTRIES = (("typed-question", "answer", "Answer questions"), ("ink-question", "ink", "Answer a handwritten question"),
                ("chart", "chart", "Make charts"), ("draw", "draw", "Draw"), ("coloring-page", "picture", "Make pictures"))


def _wrote(note):
    """What a job wrote, from its note ("... Wrote: <the reply>")."""
    i = note.find("Wrote: ")
    return note[i + 7:].strip() if i >= 0 else ""


# the network tests, by id and name, in the order they run (their rows wait under these names until they do)
PROBE_NAMES = (("search", "Search the web"), ("social", "Social media"), ("weather", "Weather"))


def _model_row(role, name, report):
    """A model's check as one row: passed when every check did, with what each check found."""
    found = report.get("checks") or []
    bad = [c for c in found if not c.get("ok")]
    state = "pass" if found and not bad else "fail"
    detail = " · ".join("%s%s" % (c.get("name"), "" if c.get("ok") else " (%s)" % (c.get("detail") or "failed"))
                        for c in found)
    if state == "pass":
        return probes.row("model-" + role, state, "answers", raw=detail)
    return probes.row("model-" + role, state, "check_failed", {"check": bad[0].get("name") if bad else "?"}, raw=detail)


def _check_models(s):
    """Check the text model, then the image model if the lineup has one, each into its row. -> the text model passed."""
    from ..models import checks, slots
    with _lock:
        _run["msg"] = "checking the models"
        _run["models"] = []
        _run["image"] = slots.configured("image", s)
    done = []
    for role, name, fn in (("text", "Text model", checks.test_text), ("image", "Image model", checks.test_image)):
        if role == "image" and not slots.configured("image", s):
            row = probes.row("model-image", "off", "no_image", d="no_image")
        else:
            try:
                row = _model_row(role, name, fn(s))
            except Exception as ex:
                row = probes.row("model-" + role, "fail", "no_answer", raw="%s: %s" % (type(ex).__name__, str(ex)[:200]))
        done.append(row)
        with _lock:
            _run["models"] = list(done)
    return done[0]["state"] == "pass"


def rows():
    """The run as one table, as far as it has got (call with _lock held): the models, then each page case (waiting,
    working or done) with reading handwriting beside the handwritten question, then the network tests."""
    r = _run
    out = list(r["models"])
    have_m = {x["id"] for x in out}
    out += [probes.row(i, "wait", "waiting") for i in ("model-text", "model-image") if i not in have_m]
    by = {c["id"]: c for c in r["cases"]}
    for cid, eid, name in CASE_ENTRIES:
        c = by.get(cid)
        if c is None:
            continue
        if cid == "coloring-page" and not r.get("image", True):
            out.append(probes.row(eid, "off", "no_image", d="no_image"))
            continue
        res, took = c.get("result"), c.get("seconds")
        if res in ("queued", None):
            out.append(probes.row(eid, "wait", "waiting"))
            continue
        if res == "working":
            out.append(probes.row(eid, "busy", "working"))
            continue
        state = "pass" if res == "pass" else "fail"
        verb = "answered_in" if eid in ("answer", "ink") else "done_in"
        m = (verb if state == "pass" else "failed_after") if took is not None \
            else ("canceled" if res == "canceled" else "failed")
        wrote = _wrote(c.get("note") or "")
        detail = wrote if (eid in ("answer", "ink") and wrote) else "; ".join(c.get("notes") or []) or ""
        out.append(probes.row(eid, state, m, {"s": took} if took is not None else None, raw=detail))
    done = list(r["probes"] or [])
    hw = [x for x in done if x["id"] == "handwriting"] or [probes.row("handwriting", "wait", "waiting")]
    out.insert(min(4, len(out)), hw[0])          # beside answering a handwritten question
    have = {x["id"] for x in done}
    out += [x for x in done if x["id"] != "handwriting"]
    out += [probes.row(i, "wait", "waiting") for i, n in PROBE_NAMES if i not in have]
    if r["cancel"] is not None and r["cancel"].is_set():
        out = [dict(x, state="off", metric=probes.say("ts.m.canceled"), m=["ts.m.canceled", {}])
               if x["state"] in ("wait", "busy") else x for x in out]
    elif not r["running"] and r["finished"]:
        out = [x for x in out if x["state"] != "wait"]       # a test that does not apply is gone
    return out


def _ledger(state):
    try:
        with open(os.path.join(state, "rm-ledger.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get("entries") or {}
    except (OSError, ValueError):
        return {}


def _record():
    """Keep this run as its lineup's result, replacing the one before (there is no history)."""
    st = status()
    done = [r for r in st["rows"] if r["state"] in ("pass", "fail", "partly")]
    row = {"fingerprint": st["fingerprint"], "finished": st["finished"], "msg": st["msg"], "rows": st["rows"],
           "passed": sum(1 for r in done if r["state"] == "pass"), "total": len(done)}
    every = _results()
    every[st["lineup"]] = row
    try:
        path = _results_path()
        with open(path + ".part", "w", encoding="utf-8") as f:
            json.dump(every, f)
        os.replace(path + ".part", path)
    except OSError:
        pass


__all__ = ["cases", "cases_dir", "start", "status", "cancel", "result", "plan", "fingerprint", "judge", "page_content",
           "prepare"]
