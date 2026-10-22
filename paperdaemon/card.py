"""The model servers and every call PaperDaemon makes to them.

THE ENGINE RULE. Each model is a location, a start script and a harness. Before a model call, if
PaperDaemon's own server for that model is not running (the processes its start script started have all
ended, or it never ran), PaperDaemon runs that model's start script and waits until the location
answers (hotswap.start, by the contract in scripts.py). A slot with no start script is used as it is:
the user runs that server, or it is a remote service.

A start script never runs while a model call is in progress: call() counts the calls in flight, and a
script waits until there are none. One script runs at a time. The scripts do the hot swap themselves
(the text script takes the image server off the graphics card and the image script the text server),
so PaperDaemon never stops a model server itself; it ends its own servers only when it quits.

The host reaches the models through the engine: its text calls through the proxy under /host/llm (see
server.py), and its pictures through /host/generate and /host/edit, which run here. A picture is kept
only until the host fetches it. /host/load is how the host says which model it wants next; the start
itself waits for that model's first call, so a model is started only when a call needs it.

A picture may name a WORKFLOW (`workflow` on /host/generate or /host/edit): the active image harness's
wording for it goes round the subject, with the settings it needs (Klein's coloring book: 12 steps) and
any LoRA adapters it names, sent with that request only. Without one the prompt goes to the model exactly
as the host sent it. A workflow the harness does not have, or a LoRA file the server does not list,
changes nothing else and is reported in the answer (`workflow_missing`, `loras_missing`) for the job's
log; neither is a failure. An edit needs the harness's ability for its mode (a reference edit:
edit_reference).
"""
import base64
import contextlib
import io
import os
import threading
import time

from . import paths, scripts
from . import settings as S
from .harnesses import ABILITIES, EDIT_ABILITY
from .models import adapters, hotswap, slots

EDIT_MODES = ("ref", "img2img", "inpaint")

_cond = threading.Condition(threading.RLock())
_inflight = {role: 0 for role in slots.ROLES}
_run = {"loading": None, "wanted": "text"}
_state = {role: {"phase": "idle", "msg": "", "since": None} for role in slots.ROLES}


class NotReady(Exception):
    """A model server could not be made ready for a call."""


def image_harness_id(s=None):
    """The image slot's harness, by id ("" when it cannot be told)."""
    try:
        return slots.pick("image", s)[0].id
    except Exception:
        return ""


def ready(role, s=None):
    """True when a call to `role` would go straight through: PaperDaemon's own server is running and was
    found answering, or the slot has no start script and its location answers."""
    s = s or S.load()
    if not slots.configured(role, s):
        return False
    if scripts.has_script(slots.slot(role, s)):
        srv = hotswap.ours(role)
        return bool(srv is not None and srv.ready and srv.key == hotswap.needed(role, s))
    return hotswap.answering(role, s)


def in_flight():
    with _cond:
        return dict(_inflight)


def loading():
    return _run["loading"] is not None


def idle():
    """No model call in flight and no start script running."""
    with _cond:
        return not any(_inflight.values()) and _run["loading"] is None


def _acquire(role, s, on_wait=None):
    """Make `role` ready for one call and count the call as in flight. -> the hotswap.Server or None."""
    if role not in slots.ROLES:
        raise ValueError("no such slot: %r" % (role,))
    with _cond:
        while True:
            s = s or S.load()
            if not slots.configured(role, s):
                raise NotReady("the %s slot has no location" % role)
            m = slots.slot(role, s)
            if not scripts.has_script(m):
                _inflight[role] += 1
                return None
            srv = hotswap.ours(role)
            # the server running is ready AND is the one this lineup's start script starts: the last script
            # loaded is the one needed, so nothing runs again
            if srv is not None and srv.ready and srv.key == scripts.identity(m):
                _inflight[role] += 1
                return srv
            if _run["loading"] is None and not any(_inflight.values()):
                _run["loading"] = role
                _state[role].update(phase="loading", msg="starting the %s server" % role, since=time.time())
                break
            _cond.wait(0.5)
            s = None                              # read the settings again: the lineup may have changed
    srv, err = None, None
    try:
        srv = hotswap.start(role, s, on_wait=on_wait)
    except Exception as ex:
        err = ex
    with _cond:
        _run["loading"] = None
        if err is None:
            _state[role].update(phase="ready", msg="")
            _inflight[role] += 1
        else:
            _state[role].update(phase="error", msg=str(err)[:400] or type(err).__name__)
        _cond.notify_all()
    if err is not None:
        raise NotReady(str(err)) from err
    return srv


def _release(role):
    with _cond:
        _inflight[role] = max(0, _inflight[role] - 1)
        _cond.notify_all()


def acquire(role, s=None, on_wait=None):
    """The first half of call(), for a caller that cannot use a with-block (the streaming proxy). Every
    acquire() is followed by exactly one release()."""
    return _acquire(role, s, on_wait)


def release(role):
    _release(role)


@contextlib.contextmanager
def call(role, s=None, on_wait=None):
    """Hold this around one model call: the server is made ready first (by the engine rule) and no start
    script runs until the call has ended."""
    srv = _acquire(role, s, on_wait)
    try:
        yield srv
    finally:
        _release(role)


def ensure(role, s=None, on_wait=None):
    """Make `role` ready now, without holding it (the model check, the API's start button)."""
    with call(role, s, on_wait) as srv:
        return srv


# ---------------------------------------------------------------- what the host reads

def load(key):
    """The host's /load: the model it wants next. The start waits for that model's first call (the
    engine rule), so this only records the wish and clears an old failure."""
    if key not in slots.ROLES:
        raise ValueError("no such model: %r" % (key,))
    with _cond:
        _run["wanted"] = key
        if _state[key]["phase"] == "error":
            _state[key].update(phase="idle", msg="")
    return status()


def status(s=None):
    """What the host reads before and after pictures: the model it may call next (`key`) and whether a
    start is under way (`phase`)."""
    s = s or S.load()
    with _cond:
        key, busy = _run["wanted"], _run["loading"]
        states = {r: dict(_state[r]) for r in slots.ROLES}
    if busy:
        phase, msg = "loading", states[busy]["msg"]
    elif states[key]["phase"] == "error":
        phase, msg = "error", states[key]["msg"]
    elif slots.configured(key, s):
        phase, msg = "ready", ""
    else:
        phase, msg = "error", "the %s slot has no location" % key
    return {"key": key, "phase": phase, "msg": msg, "tablet": {"image": "image"}, "llm_ctx": None,
            "llm_kv": None, "loaded": {"harness": image_harness_id(s)}, "states": states,
            "in_flight": in_flight()}


# ---------------------------------------------------------------- pictures

def renders_dir():
    return paths.sub("renders")


def _seed(v):
    try:
        seed = int(v if v is not None else -1)
    except (TypeError, ValueError):
        seed = -1
    if seed < 0:
        seed = int(time.time() * 1000) % 2147483647
    return seed


def _b64(v):
    """A picture as the server wants it: bare base64 (a data URL's prefix dropped)."""
    v = str(v or "")
    return v.split(",", 1)[1] if v.startswith("data:") else v


def _save(raw, seed, tag):
    name = "%s-%s-%d.png" % (time.strftime("%Y%m%d-%H%M%S"), tag, seed)
    with open(os.path.join(renders_dir(), name), "wb") as f:
        f.write(raw)
    return name


def take_render(name):
    """The PNG bytes of a render, which is then deleted: PaperDaemon keeps no picture beyond the job that
    asked for it. None when there is no such file."""
    if not name or name != os.path.basename(name) or not name.lower().endswith(".png"):
        return None
    path = os.path.join(renders_dir(), name)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    try:
        os.remove(path)
    except OSError:
        pass
    return data


def _sd_post(base, route, body):
    """One request to the Stable Diffusion server -> the PNG bytes of its first image."""
    d = adapters._request("POST", base + "/sdapi/v1/" + route, body, timeout=adapters.MODEL_CALL)
    imgs = (d or {}).get("images") or []
    if not imgs:
        raise adapters.AdapterError("the image server returned no image")
    return base64.b64decode(imgs[0].split(",", 1)[-1])


def _picture_params(p, caps):
    steps = int(p.get("steps") or caps["steps"])
    cfg = float(p.get("cfg") or caps["cfg"])
    sampler = p.get("sampler") or caps["sampler"]
    return steps, cfg, sampler


def workflow_request(p, s=None):
    """What a picture request becomes on the active image harness.

    `p` is what the host sent: prompt (the subject, or the whole prompt when no workflow is named),
    workflow?, steps? (the model's or the user's), user_numbers? (the numbers the user wrote: a step count
    among them is used as written). -> {"prompt", "steps", "workflow" (the name, when applied), "missing"
    (the name, when this harness has no such workflow), "loras" (the workflow's), "reference"}. The
    workflow's wording and settings are the harness's; one it does not have leaves the prompt exactly as
    sent."""
    caps = slots.caps("image", s)
    h = slots.pick("image", s)[0]
    want = str(p.get("workflow") or "").strip() or None
    prompt, settings, missing = h.apply(p["prompt"], want)
    requested = p.get("steps")
    steps = slots.picture_steps(caps, int(requested) if requested not in (None, "") else None,
                                settings.get("steps"), p.get("user_numbers") or ())
    return {"prompt": prompt, "steps": steps, "workflow": want if want and not missing else None,
            "missing": missing, "loras": list(settings.get("loras") or []),
            "reference": bool(settings.get("reference"))}


def server_loras(base):
    """The LoRA files the Stable Diffusion server can load, as it names them (paths inside its
    --lora-model-dir), or None when it does not say. Asking also makes it look at the folder again."""
    try:
        d = adapters._request("GET", base + "/sdapi/v1/loras", timeout=30)
    except adapters.AdapterError:
        return None
    out = []
    for e in d if isinstance(d, list) else []:
        if isinstance(e, dict) and (e.get("path") or e.get("name")):
            out.append(str(e.get("path") or e.get("name")))
    return out


def lora_list(wanted, listed):
    """A workflow's LoRAs -> (the request's "lora" list [{"path", "multiplier"}], [files left out]).

    A file is matched to what the server lists by its path, else by its file name, else by its name
    without the extension (the server lists paths with either slash). One the server does not list is
    left out, and the picture is made without it. `listed` None (the server does not say) sends every
    file as written and lets the server judge."""
    norm = lambda x: str(x).replace("\\", "/").strip("/").lower()
    stem = lambda x: os.path.splitext(norm(x).split("/")[-1])[0]
    got, missing = [], []
    for lo in wanted or []:
        f, w = str(lo.get("file") or "").strip(), float(lo.get("strength", 1.0))
        if not f:
            continue
        if listed is None:
            got.append({"path": f, "multiplier": w})
            continue
        hit = (next((x for x in listed if norm(x) == norm(f)), None)
               or next((x for x in listed if norm(x).split("/")[-1] == norm(f).split("/")[-1]), None)
               or next((x for x in listed if stem(x) == stem(f)), None))
        if hit is None:
            missing.append(f)
        else:
            got.append({"path": hit, "multiplier": w})
    return got, missing


def lineup_loras(s=None):
    """THE LINEUP'S OWN LoRAs (loras.py): the files in its folder, and how its image harness applies them ->
    (its `loras` instructions or None, [files])."""
    from . import loras as LF
    lu = S.active(s)
    mine = LF.files(lu["name"]) if lu else []
    return slots.pick("image", s)[0].loras, mine


def _with_loras(body, wf, ad, s=None):
    """Put the workflow's LoRAs and the lineup's on a server request: the lineup's as its image harness says,
    "request" in the request's list (stable-diffusion.cpp's server ignores tags in the prompt), "prompt" as
    <lora:name:strength> tags. -> the files left out."""
    how, mine = lineup_loras(s)
    wanted = list((wf or {}).get("loras") or [])
    missing = []
    if mine and how is None:
        missing += mine                                        # the harness does not say how to apply them
    elif mine and how["via"] == "request":
        wanted += [{"file": f, "strength": float(how.get("strength", 1.0))} for f in mine]
    elif mine and ad.family == "sdapi":
        body["prompt"] = (str(body.get("prompt") or "") + " " + " ".join(
            "<lora:%s:%g>" % (os.path.splitext(f)[0], float(how.get("strength", 1.0))) for f in mine)).strip()
    elif mine:
        missing += mine
    if not wanted:
        return missing
    if ad.family != "sdapi":
        return missing + [str(lo.get("file")) for lo in wanted]   # only a Stable Diffusion server takes them
    got, left = lora_list(wanted, server_loras(ad.base))
    if got:
        body["lora"] = got
    return missing + left


def generate(p, s=None):
    """A picture from the image server (as the host sends it: prompt, workflow?, width, height, seed,
    steps?, user_numbers?) -> the item {kind, name, secs, seed, steps, cfg, sampler, size, workflow,
    workflow_missing, loras, loras_missing}. A workflow that starts from a picture goes through edit()."""
    s = s or S.load()
    wf = workflow_request(p, s)
    if wf["reference"]:
        raise ValueError("the %s workflow starts from a picture: send it to /edit with the picture"
                         % wf["workflow"])
    with call("image", s):
        caps = slots.caps("image", s)
        ad = adapters.for_slot("image", s)
        seed = _seed(p.get("seed"))
        steps = wf["steps"]
        cfg = float(p.get("cfg") or caps["cfg"])
        sampler = p.get("sampler") or caps["sampler"]
        width, height = int(p.get("width") or caps["size"][0]), int(p.get("height") or caps["size"][1])
        t0 = time.time()
        if ad.family == "sdapi":
            body = adapters.SDAPI.request(wf["prompt"], width, height, steps, cfg, sampler, caps.get("scheduler"),
                                          seed, caps.get("shift"))
            if str(p.get("negative") or "").strip():
                body["negative_prompt"] = p["negative"]
            lora_missing = _with_loras(body, wf, ad, s)
            raw = _sd_post(ad.base, "txt2img", body)
            scheduler = body.get("scheduler") or "default"
            loras = [x["path"] for x in body.get("lora") or []]
        else:
            lora_missing = _with_loras({}, wf, ad, s)
            raw = ad.generate(wf["prompt"], width, height, steps, cfg, sampler, caps.get("scheduler"), seed,
                              caps.get("shift"))
            scheduler, loras = "default", []
    name = _save(raw, seed, "gen")
    return {"kind": "gen", "name": name, "secs": round(time.time() - t0, 1), "seed": seed, "steps": steps,
            "cfg": cfg, "sampler": sampler, "scheduler": scheduler, "size": "%dx%d" % (width, height),
            "workflow": wf["workflow"], "workflow_missing": wf["missing"], "loras": loras,
            "loras_missing": lora_missing}


def edit_body(p, caps, src, size, wf=None):
    """The Stable Diffusion server request for an edit -> (route, body). Mode "ref" hands the picture in
    as a reference in `extra_images` (the field the server reads for reference pictures); "img2img"
    starts from it; "inpaint" changes only the white of the mask. `wf` is workflow_request()'s answer:
    its prompt and steps replace the request's."""
    mode = p.get("mode") or "ref"
    if mode not in EDIT_MODES:
        raise ValueError("no edit mode %r; have %s" % (mode, ", ".join(EDIT_MODES)))
    sw, sh = size
    steps, cfg, sampler = _picture_params(p, caps)
    prompt = p["prompt"]
    if wf is not None:
        prompt, steps = wf["prompt"], wf["steps"]
    w = int(p.get("width") or sw) // 16 * 16
    h = int(p.get("height") or sh) // 16 * 16
    body = {"prompt": prompt, "steps": steps, "cfg_scale": cfg, "width": w, "height": h,
            "sampler_name": sampler, "batch_size": 1, "seed": _seed(p.get("seed"))}
    if str(p.get("negative") or "").strip():
        body["negative_prompt"] = p["negative"]
    if mode == "ref":
        body["extra_images"] = [src]
        return "txt2img", body
    body["init_images"] = [src]
    body["denoising_strength"] = float(p["strength"] if p.get("strength") is not None else 0.6)
    if mode == "inpaint":
        if not p.get("mask"):
            raise ValueError("inpaint needs a mask (white = change)")
        body["mask"] = _b64(p["mask"])
    return "img2img", body


def edit(p, s=None):
    """An existing picture changed by the image server: mode "ref" hands the picture in as a reference
    and the prompt says what to change; "img2img" starts from it, `strength` 0..1 saying how far the
    result may wander; "inpaint" changes only the white of `mask`. A `workflow` (one that starts from a
    picture) supplies the wording, steps and LoRAs as for generate(). -> the item."""
    s = s or S.load()
    src = _b64(p.get("image"))
    if not src:
        raise ValueError("no picture to edit")
    mode = p.get("mode") or "ref"
    h = slots.pick("image", s)[0]
    need = EDIT_ABILITY.get(mode)
    if need and not h.can(need):
        raise NotReady("the image model's harness (%s) does not say it %s, so the %s edit is not sent"
                       % (h.name, ABILITIES[need], mode))
    from PIL import Image
    with Image.open(io.BytesIO(base64.b64decode(src))) as im:
        size = im.size
    wf = workflow_request(p, s) if p.get("workflow") else None
    with call("image", s):
        caps = slots.caps("image", s)
        ad = adapters.for_slot("image", s)
        if ad.family != "sdapi":
            raise NotReady("editing a picture needs a Stable Diffusion web UI server in the image slot")
        route, body = edit_body(p, caps, src, size, wf)
        lora_missing = _with_loras(body, wf, ad, s)
        t0 = time.time()
        raw = _sd_post(ad.base, route, body)
    name = _save(raw, body["seed"], "edit")
    return {"kind": "edit", "name": name, "secs": round(time.time() - t0, 1), "seed": body["seed"],
            "mode": p.get("mode") or "ref", "steps": body["steps"], "cfg": body["cfg_scale"],
            "sampler": body["sampler_name"], "strength": body.get("denoising_strength"),
            "size": "%dx%d" % (body["width"], body["height"]),
            "workflow": wf["workflow"] if wf else None, "workflow_missing": wf["missing"] if wf else None,
            "loras": [x["path"] for x in body.get("lora") or []], "loras_missing": lora_missing}
