"""Harnesses: what each model family works with, as data.

A harness is a JSON file. PaperDaemon ships six in shipped/ (a default per kind, Qwen 3.6 27B, Qwen 3.8 27B,
FLUX.2 Klein 9B and Z-Image Turbo), and the user adds their own in <data>/harnesses/; both are read by the
same loader and checked by the same rules (schema.py). A harness extends another and names only what
differs; every field it leaves out keeps the value of the harness it extends.

    {
      "id": "qwen-small-context",          optional; the file name without .json when left out
      "name": "Qwen 3.6, small context",   optional; the id when left out
      "extends": "qwen3.6-27b",            the harness it extends; a kind's default when left out
      "kind": "text",                      needed only when "extends" is left out
      "patterns": ["qwen-?3\\\\.?6"],        optional: model names that make it the automatic guess
      "refuse": ["(^|-)base(-|\\\\.|$)"],      optional: names that rule it out even when a pattern matches
      "max_output": 4096,                  any field of its kind (schema.FIELDS), with the value it takes
      "request": {"vision": {"off": {"cache_prompt": true}}}
    }

`request` is extra fields for every chat request, keyed by a capability and its value: above, while the
slot's vision is off, every request carries cache_prompt: true. The engine applies it; the host never sees
it. How the model thinks and how much context it has are the server's own settings (its start script),
never a harness's.

An image harness owns its WORKFLOWS: named recipes the host asks for by name, so a coloring page is
"childrensColoringBook" to every model and each image harness carries it out its own way. A workflow is
the wording ({subject} is where the text model's description goes) and optionally what it is for, its steps,
LoRA adapters ({"file", "strength"}, applied per picture by the image server) and whether it starts from a
reference picture. Workflows add to the ones the harness extends; one with the same name replaces it. A
complete example is examples/klein-character-turnaround.json.

The guess reads three hints in order of how deliberate they are: the model name the slot names, the model
the server reports, and the model file named in the start script. User harnesses are tried before the
shipped ones. A file that cannot be read or breaks a rule is listed with the reason and skipped; it never
stops the other harnesses.
"""
import copy
import json
import os
import re

from . import schema
from .schema import ABILITIES, EDIT_ABILITY
from .text import TextProtocols

COLORING_BOOK = "childrensColoringBook"
HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED_FOLDER = os.path.join(HERE, "shipped")
META = ("id", "name", "extends", "kind", "patterns", "refuse", "notes", "server", "models")
# what every harness file says about itself, for the people who read it; never used, never inherited
DECLARED = ("server", "models", "notes")
HINT_LABEL = {"model": "the model name", "server": "the model the server reports", "launch": "the start script"}
# a model file in a start script: the argument of -m / --model / --diffusion-model, or any path to a model file
_FILE = re.compile(r"""(?:--?(?:m|model|diffusion-model)\s+)?["']?([^\s"'=]+\.(?:gguf|safetensors|ckpt|bin|pt))""",
                   re.IGNORECASE)


def normalize(hint):
    """A model name, file name or server id -> lowercase with every run of separators one '-', so
    'Qwen_Qwen3.6-27B', 'qwen3.6-27b-Q8_0.gguf' and 'Qwen3.6 27B' compare alike."""
    return re.sub(r"[^a-z0-9.]+", "-", str(hint or "").lower()).strip("-")


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


class Harness:
    """One model family's data. Subclasses are made by the loader, one per file; nothing here branches on
    which model it is."""
    id = ""
    name = ""
    kind = ""
    extends = None
    source = "shipped"
    file = None
    patterns = ()
    refuse = ()
    server = ""
    models = ()
    notes = ""
    CAPABILITIES = ()
    FIELDS = ()

    @classmethod
    def matches(cls, hint):
        h = normalize(hint)
        if not h or not cls.patterns:
            return False
        if any(re.search(p, h) for p in cls.refuse):
            return False
        return any(re.search(p, h) for p in cls.patterns)

    @classmethod
    def fields(cls):
        """The harness's effective value for every field, as plain JSON values."""
        out = {}
        for f in cls.FIELDS:
            v = getattr(cls, f)
            if isinstance(v, tuple):
                v = list(v)
            elif isinstance(v, dict):
                v = copy.deepcopy(v)
            out[f] = v
        return out


class TextHarness(Harness, TextProtocols):
    kind = "text"
    CAPABILITIES = ("vision", "forced_tool", "max_output")
    FIELDS = CAPABILITIES + ("brief_additions", "request", "features", "assists", "inspect_tokens")
    request = {}
    features = {}                       # {"off": [feature names]}: a harness may narrow what is offered

    def tune(self, request, caps):
        """A chat request with this harness's `request` fields merged in, for the capability values `caps`."""
        for cap, by_value in (self.request or {}).items():
            v = caps.get(cap)
            key = ("true" if v else "false") if isinstance(v, bool) else str(v)
            if key in by_value:
                request = _merge(request, by_value[key])
        return request


class ImageHarness(Harness):
    kind = "image"
    CAPABILITIES = ("steps", "steps_range", "cfg", "sampler", "scheduler", "shift", "size")
    FIELDS = CAPABILITIES + ("workflows", "abilities")
    size_multiple = 16                  # width and height are rounded to this
    workflows = {}
    abilities = ()

    @classmethod
    def workflow(cls, name):
        return cls.workflows.get(str(name or "").strip()) if name else None

    @classmethod
    def apply(cls, subject, name=None):
        """-> (prompt, the workflow's settings, the name when this harness has no such workflow). With no
        workflow, or one this harness lacks, the subject is the prompt exactly as written."""
        if not name:
            return subject, {}, None
        wf = cls.workflow(name)
        if wf is None:
            return subject, {}, str(name)
        return wf["prompt"].replace("{subject}", str(subject)), {k: v for k, v in wf.items() if k not in ("about", "prompt")}, None

    @classmethod
    def can(cls, ability):
        return ability in cls.abilities

    @classmethod
    def offer(cls):
        """What the text model is told about this image model."""
        return {"id": cls.id, "name": cls.name, "abilities": list(cls.abilities),
                "workflows": {n: {"about": str(wf.get("about") or ""), "reference": bool(wf.get("reference"))}
                              for n, wf in sorted(cls.workflows.items())},
                "steps": cls.steps, "steps_range": list(cls.steps_range)}


ROOTS = {"text": TextHarness, "image": ImageHarness}


def _read(folder):
    out = []
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".json"))
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError("the file holds no JSON object")
            out.append((n, d, None))
        except (OSError, ValueError) as ex:
            out.append((n, None, str(ex)[:200]))
    return out


def load(folder, known, source="user", kind=None, entries=None):
    """The harness files of a folder, each built on the one it extends (`known`: id -> class, the ones
    already loaded). `kind`: the kind a file there has when it names neither a kind nor a parent. `entries`:
    the files already read, (name, data, error[, extra class attributes]); the folder's JSON files by default.
    -> (classes, [{"file", "error"}])."""
    known = dict(known)
    defaults = {k: known.get("default-" + k) for k in ROOTS}
    errors, pending, made = [], {}, []
    for entry in (entries if entries is not None else _read(folder)):
        name, d, err = entry[:3]
        extra = entry[3] if len(entry) > 3 else None
        if err:
            errors.append({"file": name, "error": err})
            continue
        pid = str(d.get("id") or os.path.basename(name)[:-5]).strip()
        if kind and not d.get("kind") and not d.get("extends"):
            d = dict(d, kind=kind)
        if not pid or pid in known or pid in pending:
            errors.append({"file": name, "error": "the id %r is already taken" % pid})
            continue
        pending[pid] = (name, d, extra)
    progress = True
    while pending and progress:
        progress = False
        for pid in list(pending):
            name, d, extra = pending[pid]
            kind, parent_id = d.get("kind"), d.get("extends")
            if parent_id in ("default",):
                parent_id = "default-" + (kind or "text")
            if not parent_id and kind in ROOTS and defaults.get(kind) is not None:
                parent_id = defaults[kind].id
            if not parent_id:
                if kind not in ROOTS:
                    errors.append({"file": name, "error": "say which harness it extends, or its kind (text or image)"})
                    pending.pop(pid)
                    progress = True
                    continue
                parent = ROOTS[kind]
            else:
                parent = known.get(parent_id)
                if parent is None:
                    if parent_id in pending:
                        continue                     # its parent is built in a later pass
                    errors.append({"file": name, "error": "it extends %r, which is not a harness" % parent_id})
                    pending.pop(pid)
                    progress = True
                    continue
            if kind and kind != parent.kind:
                errors.append({"file": name, "error": "a %s harness cannot extend the %s harness %r"
                               % (kind, parent.kind, parent.id)})
                pending.pop(pid)
                progress = True
                continue
            pending.pop(pid)
            progress = True
            attrs, problems = _attrs(d, parent, source)
            if problems:
                errors.append({"file": name, "error": "; ".join(problems)})
                continue
            attrs.update(id=pid, name=str(d.get("name") or pid), extends=parent.id or None, source=source, file=name)
            attrs.update(extra or {})
            cls = type("Harness_" + re.sub(r"\W", "_", pid), (parent,), attrs)
            known[pid] = cls
            made.append(cls)
            if pid == "default-" + cls.kind:
                defaults[cls.kind] = cls
    for pid, (name, _d, _x) in pending.items():
        errors.append({"file": name, "error": "its extends form a loop"})
    return made, errors


def _attrs(d, parent, source):
    """The class attributes a harness file sets, and the rules it breaks."""
    attrs, problems = {}, []
    # SAID IN EVERY FILE: the server it is made for, the models, and notes -- read by people choosing a harness
    if not (isinstance(d.get("server"), str) and d["server"].strip()):
        problems.append("say which server it is made for: \"server\": \"llama.cpp\"")
    models = d.get("models")
    if not (isinstance(models, list) and models and all(isinstance(m, str) and m.strip() for m in models)):
        problems.append("say which models it is made for: \"models\": [\"Qwen 3.8 27B\"]")
    if not isinstance(d.get("notes", ""), str):
        problems.append("notes must be text")
    attrs.update(server=str(d.get("server") or ""), models=tuple(models or ()) if isinstance(models, list) else (),
                 notes=str(d.get("notes") or ""))
    for k, v in d.items():
        if k in META:
            continue
        if k not in parent.FIELDS:
            problems.append("%s is not a field of a %s harness" % (k, parent.kind))
            continue
        why = schema.check(k, v)
        if why:
            problems.append(why)
            continue
        if k == "workflows":
            attrs[k] = dict(parent.workflows, **{n: dict(w) for n, w in v.items()})
        elif k == "request":
            attrs[k] = _merge(parent.request or {}, v)
        else:
            attrs[k] = tuple(v) if isinstance(v, list) else v
    attrs["patterns"] = ()                       # a harness is picked by name unless it says what names it
    for key in ("patterns", "refuse"):           # a refuse list it leaves out is the one it extends
        if key not in d:
            continue
        pats = d[key]
        if not isinstance(pats, list) or not all(isinstance(p, str) for p in pats):
            problems.append("%s must be a list of regular expressions" % key)
            continue
        try:
            for p in pats:
                re.compile(p)
            attrs[key] = tuple(pats)
        except re.error as ex:
            problems.append("a pattern does not compile: %s" % ex)
    return attrs, problems


# ---------------------------------------------------------------- the registry

_shipped, _shipped_errors = load(SHIPPED_FOLDER, {}, source="shipped")
if _shipped_errors:
    raise RuntimeError("a shipped harness did not load: %s" % _shipped_errors)
SHIPPED_BY_ID = {p.id: p for p in _shipped}
DEFAULT = {"text": SHIPPED_BY_ID["default-text"], "image": SHIPPED_BY_ID["default-image"]}
SHIPPED = tuple(p for p in _shipped if p.id not in ("default-text", "default-image"))
BUILT_IN = (DEFAULT["text"], DEFAULT["image"]) + SHIPPED

_user = {"key": None, "made": (), "errors": []}
FOLDER = "harnesses"
SUBFOLDERS = {"text": "llm", "image": "image"}      # the user's folder: one for LLMs, one for image models
GUIDE = "How to create a new harness.md"           # in each subfolder, written for its kind
GUIDES = {"text": "GUIDE-llm.md", "image": "GUIDE-image.md"}
SKILLS_FILE = "harness.json"                        # a skills-only harness: a folder with this and skills\*.md


def _seed(folder):
    """The two subfolders, each with its kind's guide (always the current one: the guide is the app's). Nothing
    else: PaperDaemon's own harnesses are part of the app, and the folder holds only the user's."""
    for kind, sub in SUBFOLDERS.items():
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
        with open(os.path.join(HERE, GUIDES[kind]), "rb") as f:
            text = f.read()
        guide = os.path.join(folder, sub, GUIDE)
        try:
            with open(guide, "rb") as f:
                same = f.read() == text
        except OSError:
            same = False
        if not same:
            with open(guide, "wb") as f:
                f.write(text)


def user_folder():
    from .. import paths
    folder = paths.sub(FOLDER)
    try:
        _seed(folder)
    except OSError:
        pass
    return folder


def _skills_entries(place):
    """The skills-only harnesses of a folder: each subfolder with a harness.json -> (name, data, error, extra)."""
    out = []
    try:
        subs = sorted(n for n in os.listdir(place) if os.path.isfile(os.path.join(place, n, SKILLS_FILE)))
    except OSError:
        return out
    for n in subs:
        name = os.path.join(n, SKILLS_FILE)
        try:
            with open(os.path.join(place, name), encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError("the file holds no JSON object")
            out.append((name, dict(d, id=d.get("id") or n), None,
                        {"skills_dir": os.path.join(place, n, "skills")}))
        except (OSError, ValueError) as ex:
            out.append((name, None, str(ex)[:200], None))
    return out


def _python_harnesses(place, known):
    """The Python harnesses of the llm folder: each `.py` defines one subclass of a text harness (the built-in
    default or any other) and overrides what it changes. -> (classes, errors)."""
    import importlib.util
    made, errors = [], []
    try:
        names = sorted(n for n in os.listdir(place) if n.lower().endswith(".py"))
    except OSError:
        return made, errors
    for n in names:
        modname = "paperdaemon_harness_" + re.sub(r"\W", "_", n[:-3])
        try:
            spec = importlib.util.spec_from_file_location(modname, os.path.join(place, n))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as ex:
            errors.append({"file": n, "error": "it did not load: %s: %s" % (type(ex).__name__, str(ex)[:160])})
            continue
        found = [c for c in vars(mod).values() if isinstance(c, type) and issubclass(c, TextHarness)
                 and c.__module__ == modname]
        if len(found) != 1:
            errors.append({"file": n, "error": "it must define exactly one text harness class (a subclass of "
                                               "paperdaemon.harnesses.DEFAULT['text']); it defines %d" % len(found)})
            continue
        cls = found[0]
        pid = str(vars(cls).get("id") or n[:-3]).strip()
        problems = []
        if pid in known:
            problems.append("the id %r is already taken" % pid)
        if not (isinstance(vars(cls).get("server"), str) and vars(cls)["server"].strip()):
            problems.append("say which server it is made for: server = \"llama.cpp\"")
        models = vars(cls).get("models")
        if not (isinstance(models, (list, tuple)) and models and all(isinstance(m, str) and m.strip() for m in models)):
            problems.append("say which models it is made for: models = [\"Qwen 3.8 27B\"]")
        if problems:
            errors.append({"file": n, "error": "; ".join(problems)})
            continue
        base = next((b for b in cls.__mro__[1:] if issubclass(b, TextHarness) and getattr(b, "id", "")), None)
        cls.id, cls.name = pid, str(vars(cls).get("name") or pid)
        cls.models, cls.source, cls.file = tuple(models), "user", n
        cls.extends = base.id if base is not None else None
        known[pid] = cls
        made.append(cls)
    return made, errors


def _user_state():
    """The user's harnesses, reloaded whenever a file in the folder changes: in `llm`, JSON harnesses, Python
    harnesses and skills-only folders; in `image`, JSON harnesses."""
    folder = user_folder()
    places = [(os.path.join(folder, sub), kind) for kind, sub in SUBFOLDERS.items()]
    key = []
    for place, _k in places:
        for root, _dirs, files in os.walk(place):
            for n in files:
                if n.lower().endswith((".json", ".py", ".md")):
                    p = os.path.join(root, n)
                    try:
                        key.append((p, os.path.getmtime(p), os.path.getsize(p)))
                    except OSError:
                        pass
    key = (folder, tuple(sorted(key)))
    if key != _user["key"]:
        known, made, errors = {p.id: p for p in BUILT_IN}, [], []
        for place, kind in places:
            sub = os.path.relpath(place, folder)
            entries = _read(place) + (_skills_entries(place) if kind == "text" else [])
            m, e = load(place, known, source="user", kind=kind, entries=entries)
            known.update((p.id, p) for p in m)
            made += m
            if kind == "text":
                pm, pe = _python_harnesses(place, known)
                made += pm
                e += pe
            errors += [dict(x, file=os.path.join(sub, x["file"])) for x in e]
        _user.update(key=key, made=tuple(made), errors=errors)
    return _user


def user_harnesses():
    return _user_state()["made"]


def user_errors():
    """[{"file", "error"}] for user harness files that did not load."""
    return list(_user_state()["errors"])


def all_harnesses():
    return BUILT_IN + user_harnesses()


def get(harness_id):
    if harness_id == "default":
        return DEFAULT["text"]
    for p in all_harnesses():
        if p.id == harness_id:
            return p
    return None


def for_kind(kind):
    """The harnesses a slot of this kind may use, the default first."""
    return [DEFAULT[kind]] + [p for p in SHIPPED + user_harnesses() if p.kind == kind]


def launch_models(script):
    """The model files a start script names."""
    return [m.group(1) for m in _FILE.finditer(script or "")]


def guess(kind, model="", server=(), launch=""):
    """-> (harness class, which hint matched or None, the hint's text or None)."""
    hints = [("model", model)] + [("server", s) for s in (server or ())] + \
            [("launch", f) for f in launch_models(launch)]
    candidates = [p for p in user_harnesses() + SHIPPED if p.kind == kind]
    for source, hint in hints:
        for p in candidates:
            if p.matches(hint):
                return p, source, hint
    return DEFAULT[kind], None, None


def describe(p):
    """A harness as the API lists it."""
    return {"id": p.id, "name": p.name, "kind": p.kind, "extends": p.extends, "source": p.source,
            "server": p.server, "models": list(p.models), "notes": p.notes, "fields": p.fields()}


__all__ = ["ABILITIES", "BUILT_IN", "COLORING_BOOK", "DEFAULT", "EDIT_ABILITY", "SHIPPED", "HINT_LABEL",
           "Harness", "TextHarness", "ImageHarness", "get", "for_kind", "guess", "launch_models", "normalize",
           "all_harnesses", "user_harnesses", "user_errors", "describe", "load"]
