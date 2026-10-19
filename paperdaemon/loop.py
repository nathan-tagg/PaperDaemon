"""The tablet loop: the daemon (paperdaemon.pipeline.daemon, which watches the mirror and queues jobs) and the
host (paperdaemon.pipeline.host, which works them), run as two children of the engine.

They are told where everything is through the environment: the mirror, the state folder, the tags, the
text harness's values (with what the image harness offers), SearXNG, and the engine's own surfaces -- /host/llm for every text call (the
engine starts the text server by the engine rule, see card.py) and /host for pictures. A supervisor
keeps them up: it restarts only a half that has exited, with a doubling pause, and gives up after a few
failures rather than bury the one line that says what went wrong.

Every lineup is live at once: a page's tag picks the lineup that works it (settings.lineup_of_tag), and the
host names that lineup to the engine at the start of each job (/host/lineup). The run file holds every
lineup's values, so nothing restarts when a job goes to another lineup. When saved settings change what the
halves were started with, they restart once no job is running. Processes are stopped by the ids PaperDaemon
spawned, never by name.

PAUSE STOPS THE HOST, NOT THE DAEMON: while paused the daemon keeps reading every mirror update and queuing the
jobs it finds (the queue is the ledger, and survives a restart); no job is worked until the host is started again.
"""
import atexit
import json
import os
import subprocess
import sys
import threading
import time

from . import card, paths
from . import settings as S

HALVES = (("daemon", "paperdaemon.pipeline.daemon"), ("host", "paperdaemon.pipeline.host"))
FAILS_MAX, BACKOFF0 = 5, 15.0        # respawns before giving up; the first pause, doubling
TAIL_LINES = 12
WINDOWS = sys.platform == "win32"
FROZEN = bool(getattr(sys, "frozen", False))

_procs = {}                          # who -> {"proc", "started", "fails", "next", "gave_up"}
_lock = threading.RLock()
_run = {"on": False, "port": None, "token": None, "thread": None, "msg": "not started", "pending": None,
        "env_key": None, "paused": False}


def pipeline_command(module, *args):
    """The command line that runs a pipeline module: `python -m <module>`, or -- in a packaged build, where
    sys.executable is PaperDaemon itself -- PaperDaemon's hidden --run-pipeline entry."""
    if FROZEN:
        return [sys.executable, "--run-pipeline", module] + list(args)
    return [sys.executable, "-m", module] + list(args)


def check(s=None):
    """None when the loop can start, else (code, the reason in English, its values): the window shows the code's own
    words (issue.loop_<code>) in the user's language."""
    s = s or S.load()
    from .remarkable import auth
    try:
        if not auth.describe().get("set"):
            return "no_token", "no reMarkable device token is set (Settings > Tablet)", {}
    except Exception as ex:
        return "token_unreadable", "the device token could not be read: %s" % str(ex)[:120], {"why": str(ex)[:120]}
    return None


def preflight(s=None):
    """None when the loop can start, else the reason it cannot (in English)."""
    got = check(s)
    return got[1] if got else None


def harness_values(s=None, name=None):
    """The text harness's values the host is told, for one lineup (the one in use by default), and what the
    image harness offers (its name, abilities, workflows and steps; None with no image slot), which the brief
    tells the model."""
    from .models import slots
    s = s or S.load()
    lu = S.lineup(s, name) if name else S.active(s)
    p = slots.pick("text", s, lu["text"])[0]
    caps = slots.caps("text", s, lu["text"])
    image = None
    if str(lu["image"].get("location") or "").strip():
        h = slots.pick("image", s, lu["image"])[0]
        image = h.offer()
        ic = slots.caps("image", s, lu["image"])    # the slot's own steps, overrides included
        image.update(steps=ic["steps"], steps_range=list(ic["steps_range"]))
    return {"id": p.id, "name": p.name, "lineup": lu["name"], "capabilities": caps,
            "text_location": lu["text"].get("location") or "",
            "model": str(lu["text"].get("model") or "PaperDaemon"),
            "brief_additions": getattr(p, "brief_additions", "") or "", "image": image}


def run_content(s=None):
    """What the host's run file holds: every lineup's values (all are live), and the settings the host reads."""
    from .models import lineup
    s = s or S.load()
    return lineup.run_file({lu["name"]: harness_values(s, lu["name"]) for lu in s.get("lineups") or []}, s)


def environment(s=None, port=8770, token="", state=None, mirror=None):
    """What the daemon and the host are told. One definition, because the supervisor restarts a half with
    the same environment the other half is already running under. `state` and `mirror` default to
    PaperDaemon's own (the benchmark passes its isolated ones)."""
    s = s or S.load()
    from .models import lineup
    t = s["tablet"]
    data = state or paths.data_dir()
    mirror = mirror or paths.mirror_dir()
    engine = "http://127.0.0.1:%d" % int(port)
    run_dir = os.path.join(data, "run")
    os.makedirs(run_dir, exist_ok=True)
    # the pipeline builds its lettering font into <data>/fonts and expects the folder to be there
    paths.sub("fonts")
    env = dict(os.environ)
    env.update(
        RM_MIRROR=mirror, RM_CACHE=mirror, RM_STATE=data,
        RM_TRIGGERS=json.dumps([tag for tag, _name in S.all_tags(s)]),
        RM_TRIGGER_LINEUPS=json.dumps(dict((tag.strip().lower(), name) for tag, name in S.all_tags(s))),
        RM_IGNORE_TAG=S.fixed_tags(s)[0], RM_SPROMPT_TAG=S.fixed_tags(s)[1],
        RM_INBOX=str(t.get("inbox") or ""),
        # every text call goes through the engine, which starts the text server when it is not running
        RM_LLM="%s/host/llm/%s" % (engine, token or "-"),
        # the host's run file: every lineup's harness values and features, and the settings the host reads
        RM_RUN=lineup.write_run_file(run_content(s), run_dir),
        RM_INTERVAL="1", RM_MAX_ATTEMPTS="2",
        RM_PY=sys.executable,
        RM_STUDIO=engine + "/host", RM_STUDIO_TOKEN=str(token or ""),
        PYTHONIOENCODING="utf-8",
    )
    # the decomposer's compiled code is cached in the data folder, not beside the pipeline's files (which
    # may be read-only in an installed app)
    env.setdefault("NUMBA_CACHE_DIR", paths.sub("cache", "numba"))
    return env


def fm_environment(s=None, port=8770, token=""):
    """What the false mirror's daemon and host are told: the same as the Mirror's, over the false mirror's library
    and its own state, with the cloud switched off and its own decompose inbox."""
    s = s or S.load()
    state = paths.false_mirror_state_dir()          # made by the Create button, never here
    env = environment(s, port, token, state=state, mirror=paths.false_mirror_dir())
    from .remarkable import books
    env.update(RM_LOCAL_ONLY="1", RM_INBOX=str((s.get("false_mirror") or {}).get("inbox") or ""),
               RM_FACES=books.false_mirror_faces(s))
    return env


def fm_logs():
    return os.path.join(paths.false_mirror_state_dir(), "logs")


# who -> (the module, whether it works the false mirror): the Mirror's halves, and the false mirror's when it exists
ROLES = {"daemon": ("paperdaemon.pipeline.daemon", False), "host": ("paperdaemon.pipeline.host", False),
         "fm-daemon": ("paperdaemon.pipeline.daemon", True), "fm-host": ("paperdaemon.pipeline.host", True)}


def _spawn_role(who, s=None):
    module, fm = ROLES[who]
    s = s or S.load()
    if fm:
        return spawn(who[3:], module, fm_environment(s, _run["port"], _run["token"]), fm_logs())
    return spawn(who, module, environment(s, _run["port"], _run["token"]))


def _start_false_mirror(s):
    """The false mirror's daemon and host, when it exists (called with the lock held)."""
    if not paths.false_mirror_exists() or "fm-host" in _procs:
        return
    env = fm_environment(s, _run["port"], _run["token"])
    for who, proc in spawn_halves(env, state=paths.false_mirror_state_dir(), logs=fm_logs()).items():
        _procs["fm-" + who] = dict(proc=proc, started=time.time(), fails=0, next=0.0, gave_up=None)


def start_false_mirror():
    """A false mirror was just created: its halves join a running loop."""
    with _lock:
        if _run["on"]:
            _start_false_mirror(S.load())


def stop_false_mirror():
    """The false mirror is being deleted: its halves stop first."""
    with _lock:
        for who in ("fm-daemon", "fm-host"):
            st = _procs.pop(who, None)
            if st:
                end(st.get("proc"))


def _fm_faces(s):
    try:
        from .remarkable import books
        return books.false_mirror_faces(s)
    except Exception:
        return "own"


def _env_key(s):
    """What the halves are started with: when a settings change alters it, they restart."""
    return json.dumps({"run": run_content(s), "tags": S.all_tags(s), "fixed": S.fixed_tags(s), "inbox": s["tablet"].get("inbox"),
                       "fm_inbox": (s.get("false_mirror") or {}).get("inbox"), "fm_faces": _fm_faces(s)},
                      sort_keys=True)


def spawn(who, module, env, logs=None, cwd=None):
    """One pipeline module as a child: its output appended to <logs>/<who>.out (a file, never a pipe
    nobody reads), no console window of its own."""
    logs = logs or paths.sub("logs")
    os.makedirs(logs, exist_ok=True)
    paths.cap_file(os.path.join(logs, who + ".out"))
    out = open(os.path.join(logs, who + ".out"), "ab")
    try:
        out.write(("\n---- %s started %s\n" % (who, time.strftime("%Y-%m-%d %H:%M:%S"))).encode())
        out.flush()
        kw = dict(cwd=cwd or env.get("RM_STATE") or paths.data_dir(), env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
        if WINDOWS:
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kw["start_new_session"] = True
        return subprocess.Popen(pipeline_command(module), **kw)
    finally:
        out.close()                     # the child holds its own handle


def spawn_halves(env, state=None, logs=None):
    """Both halves: the host first, then the daemon once the host has stamped its start
    (rm-queue/host-started). The daemon reads a job queued before the host's stamp as one a previous host
    dropped and hands it over again, so the other order makes the first job of a start run twice.
    -> {who: process}."""
    stamp = os.path.join(state or paths.data_dir(), "rm-queue", "host-started")
    t0 = time.time()
    procs = {"host": spawn("host", dict(HALVES)["host"], env, logs)}
    while procs["host"].poll() is None:
        try:
            if os.path.getmtime(stamp) >= t0 - 1.0:
                break
        except OSError:
            pass
        time.sleep(0.2)
    procs["daemon"] = spawn("daemon", dict(HALVES)["daemon"], env, logs)
    return procs


def end(proc):
    """Stop one child and everything it started, by its process id."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if WINDOWS:
            # the venv's python.exe is a launcher with the interpreter as its child: the tree, by id
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            import signal
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=20)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def tail(who, logs=None):
    path = os.path.join(logs or paths.sub("logs"), who + ".out")
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - 16384))
            lines = f.read().decode("utf-8", "replace").splitlines()
        # blank lines say nothing in the terminal view (and an older log's console wipes, a carriage return and
        # spaces, read as blank lines)
        return [ln for ln in lines if ln.strip()][-TAIL_LINES:]
    except OSError:
        return []


def busy(state=None):
    """Why the loop is not idle now -- a job is queued or working, or a model call is in flight -- or None."""
    data = state or paths.data_dir()
    q = os.path.join(data, "rm-queue")
    try:
        if any(f.endswith(".json") for f in os.listdir(q)):
            return "a job is queued"
    except OSError:
        pass
    try:
        with open(os.path.join(data, "rm-ledger.json"), encoding="utf-8") as f:
            entries = (json.load(f) or {}).get("entries") or {}
        if any(isinstance(e, dict) and e.get("status") == "working" for e in entries.values()):
            return "a job is working"
    except (OSError, ValueError):
        pass
    if not card.idle():
        return "a model call is in progress"
    return None


def running():
    return bool(_run["on"])


def paused():
    return bool(_run["on"] and _run["paused"])


def start(port, token, s=None):
    """Start the daemon and the host. The text server is started by the first text call (the engine
    rule), not here."""
    s = s or S.load()
    with _lock:
        if _run["on"] and _run["paused"]:
            # PAUSED: the daemons kept queuing; the hosts come back and work the queues
            _run.update(paused=False, msg="running", code="running", args={})
            for who in ("host", "fm-host"):
                st = _procs.get(who)
                if st is not None and st["proc"].poll() is not None:
                    st.update(proc=_spawn_role(who, s), started=time.time(), fails=0, next=0.0, gave_up=None)
            return status()
        if _run["on"]:
            return status()
        got = check(s)
        # THE FALSE MIRROR NEEDS NO TABLET: without a login only its halves run
        if got and not paths.false_mirror_exists():
            _run.update(msg=got[1], code=got[0], args=got[2])
            return status()
        _run.update(on=True, port=int(port), token=token, msg="running", code="running", args={}, env_key=_env_key(s))
        if not got:
            env = environment(s, port, token)
            for who, proc in spawn_halves(env).items():
                _procs[who] = dict(proc=proc, started=time.time(), fails=0, next=0.0, gave_up=None)
        _start_false_mirror(s)
        if _run["thread"] is None:
            th = threading.Thread(target=_supervise, name="loop-supervisor", daemon=True)
            th.start()
            _run["thread"] = th
    return status()


def pause():
    """Pause: the host stops -- no job is worked -- and the daemon goes on queuing what the mirror shows."""
    with _lock:
        if not _run["on"]:
            return status()
        _run.update(paused=True, msg="paused", code="paused", args={})
        for who in ("host", "fm-host"):
            st = _procs.get(who)
            if st is not None:
                end(st.get("proc"))
    return status()


def restart_host(then_start=True, who="host"):
    """A host ends at once -- the job it is working is abandoned (see server's /queue/abandon) -- and, unless the
    loop is paused or `then_start` is False, starts again for the next job. `who`: "host" (the Mirror's) or "fm-host"."""
    with _lock:
        st = _procs.get(who)
        if st is not None:
            end(st.get("proc"))
        if then_start and st is not None and _run["on"] and not _run["paused"]:
            st.update(proc=_spawn_role(who), started=time.time(), fails=0, next=0.0, gave_up=None)


def stop():
    """Stop both halves (the model servers in their job objects end with the engine)."""
    with _lock:
        _run["on"] = False
        _run["paused"] = False
        _run.update(msg="stopped", code="stopped", args={})
        for who in list(_procs):
            end(_procs[who].get("proc"))
        _procs.clear()


def status():
    s = S.load()
    out = {"running": running() and not _run["paused"], "paused": bool(_run["on"] and _run["paused"]), "msg": _run["msg"], "code": _run.get("code") or "not_started",
           "args": dict(_run.get("args") or {}), "lineup": S.in_use(), "restart_pending": bool(_run["pending"]),
           "busy": busy(), "card": card.status(s), "halves": {}}
    with _lock:
        for who, _script in HALVES:
            st = _procs.get(who)
            p = st["proc"] if st else None
            out["halves"][who] = {"pid": p.pid if p else None, "alive": bool(p is not None and p.poll() is None),
                                  "started": st["started"] if st else None, "fails": st["fails"] if st else 0,
                                  "gave_up": st.get("gave_up") if st else None, "tail": tail(who)}
        # the false mirror's halves, when it has them
        for who in ("fm-daemon", "fm-host"):
            st = _procs.get(who)
            if st is None:
                continue
            p = st["proc"]
            out["halves"][who] = {"pid": p.pid, "alive": p.poll() is None, "started": st["started"], "fails": st["fails"],
                                  "gave_up": st.get("gave_up"), "tail": tail(who[3:], fm_logs())}
    return out


# ---------------------------------------------------------------- settings changes

def _apply():
    _run["pending"] = None
    if _run["on"]:
        s = S.load()
        key = _env_key(s)
        if key != _run["env_key"]:
            _run["env_key"] = key
            for who in ("host", "daemon", "fm-host", "fm-daemon"):
                st = _procs.get(who)
                if st is not None and not (who.endswith("host") and _run["paused"]):
                    end(st["proc"])
                    st.update(proc=_spawn_role(who, s), started=time.time(), fails=0, next=0.0, gave_up=None)


def settings_saved():
    """The settings changed: if the loop runs, its halves take them up once no job is running (the next
    supervisor tick that finds the loop idle restarts them, when what they were started with changed)."""
    with _lock:
        if _run["on"]:
            _run["pending"] = True


_convert = {"thread": None, "last": 0.0}
CONVERT_EVERY = 30                                   # seconds between looks for the false mirror's books to convert


def _convert_tick():
    try:
        from .remarkable import convert
        convert.tick()
    except Exception as ex:
        _run.update(msg="convert: %s" % str(ex)[:200])


def _supervise():
    while True:
        time.sleep(2)
        if not _run["on"]:
            continue
        try:
            now = time.time()
            # the false mirror's books, converted by the tablet (remarkable/convert.py): its cloud work is the engine's
            th = _convert["thread"]
            if now - _convert["last"] >= CONVERT_EVERY and (th is None or not th.is_alive()):
                _convert["last"] = now
                _convert["thread"] = threading.Thread(target=_convert_tick, daemon=True)
                _convert["thread"].start()
            with _lock:
                if _run["pending"] and busy() is None:
                    _apply()
                for who in list(_procs):
                    st = _procs.get(who)
                    if st is None or not _run["on"] or (who.endswith("host") and _run["paused"]):
                        continue
                    if st["proc"].poll() is None:
                        if now - st["started"] > 60:
                            st["fails"], st["next"] = 0, 0.0      # it stayed up; forget the history
                        continue
                    if st["gave_up"] or now < st["next"]:
                        continue
                    st["fails"] += 1
                    if st["fails"] > FAILS_MAX:
                        st["gave_up"] = ("%s stopped %d times and is left alone -- the reason is in the first "
                                         "lines it printed in logs/%s.out" % (who, FAILS_MAX, who))
                        _run.update(msg=st["gave_up"], code="gave_up", args={"who": who, "n": FAILS_MAX})
                        continue
                    st["proc"], st["started"] = _spawn_role(who), now
                    st["next"] = now + BACKOFF0 * (2 ** (st["fails"] - 1))
        except Exception as ex:
            _run.update(msg="supervisor: %s" % str(ex)[:200], code="supervisor", args={"why": str(ex)[:200]})


atexit.register(stop)
