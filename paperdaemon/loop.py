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
        "env_key": None}


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


def _env_key(s):
    """What the halves are started with: when a settings change alters it, they restart."""
    return json.dumps({"run": run_content(s), "tags": S.all_tags(s), "fixed": S.fixed_tags(s), "inbox": s["tablet"].get("inbox")},
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


def start(port, token, s=None):
    """Start the daemon and the host. The text server is started by the first text call (the engine
    rule), not here."""
    s = s or S.load()
    with _lock:
        if _run["on"]:
            return status()
        got = check(s)
        if got:
            _run.update(msg=got[1], code=got[0], args=got[2])
            return status()
        _run.update(on=True, port=int(port), token=token, msg="running", code="running", args={}, env_key=_env_key(s))
        env = environment(s, port, token)
        for who, proc in spawn_halves(env).items():
            _procs[who] = dict(proc=proc, started=time.time(), fails=0, next=0.0, gave_up=None)
        if _run["thread"] is None:
            th = threading.Thread(target=_supervise, name="loop-supervisor", daemon=True)
            th.start()
            _run["thread"] = th
    return status()


def stop():
    """Stop both halves (the model servers in their job objects end with the engine)."""
    with _lock:
        _run["on"] = False
        _run.update(msg="stopped", code="stopped", args={})
        for who in list(_procs):
            end(_procs[who].get("proc"))
        _procs.clear()


def status():
    s = S.load()
    out = {"running": running(), "msg": _run["msg"], "code": _run.get("code") or "not_started",
           "args": dict(_run.get("args") or {}), "lineup": S.in_use(), "restart_pending": bool(_run["pending"]),
           "busy": busy(), "card": card.status(s), "halves": {}}
    with _lock:
        for who, _script in HALVES:
            st = _procs.get(who)
            p = st["proc"] if st else None
            out["halves"][who] = {"pid": p.pid if p else None, "alive": bool(p is not None and p.poll() is None),
                                  "started": st["started"] if st else None, "fails": st["fails"] if st else 0,
                                  "gave_up": st.get("gave_up") if st else None, "tail": tail(who)}
    return out


# ---------------------------------------------------------------- settings changes

def _apply():
    _run["pending"] = None
    if _run["on"]:
        s = S.load()
        key = _env_key(s)
        if key != _run["env_key"]:
            _run["env_key"] = key
            env = environment(s, _run["port"], _run["token"])
            for who in ("host", "daemon"):
                st = _procs.get(who)
                if st is not None:
                    end(st["proc"])
                    st.update(proc=spawn(who, dict(HALVES)[who], env), started=time.time(), fails=0, next=0.0,
                              gave_up=None)


def settings_saved():
    """The settings changed: if the loop runs, its halves take them up once no job is running (the next
    supervisor tick that finds the loop idle restarts them, when what they were started with changed)."""
    with _lock:
        if _run["on"]:
            _run["pending"] = True


def _supervise():
    while True:
        time.sleep(2)
        if not _run["on"]:
            continue
        try:
            now = time.time()
            env = None
            with _lock:
                if _run["pending"] and busy() is None:
                    _apply()
                for who, module in HALVES:
                    st = _procs.get(who)
                    if st is None or not _run["on"]:
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
                    env = env or environment(S.load(), _run["port"], _run["token"])
                    st["proc"], st["started"] = spawn(who, module, env), now
                    st["next"] = now + BACKOFF0 * (2 ** (st["fails"] - 1))
        except Exception as ex:
            _run.update(msg="supervisor: %s" % str(ex)[:200], code="supervisor", args={"why": str(ex)[:200]})


atexit.register(stop)
