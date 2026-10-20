"""PaperDaemon's settings: one JSON file, merged over these defaults. Secrets are NOT here (see vault).

Models come in LINEUPS. A lineup is a name and two slots, text and image, and a slot is the whole
configuration of one model:

    location   where the model answers (a URL); empty for an image slot means "no pictures"
    script     the start script: a file name in <data>/start-scripts/ or a full path; empty means the
               user runs the server (or it is a remote service)
    harness    "auto" or a harness id

A slot may also carry, for less common setups: `script_text` (an inline script, used when `script` is
empty), `api` (how the server is spoken to: openai or anthropic for text, sdapi or openai-images for
pictures), `model` (the model name to ask for), and `overrides`/`tested` (capability values set by the
user or accepted from a model check).

The settings keep a list of lineups, every one of them live: a page's tag picks the lineup that works it
(lineup_of_tag), and the engine uses that lineup's slots for the job's model calls (use()). Tags are unique
across PaperDaemon, and none may be the ignore or the standing instructions tag (both in Settings).
"""
import copy
import json
import os
import urllib.parse

from . import paths

# PaperDaemon's own ports: the engine's API, and the two model servers its start scripts run. They avoid
# the ports other local model software commonly uses (Ollama 11434, the usual Stable Diffusion server
# ports 7860 and 1234, LM Studio 1234).
API_PORT = 8770
TEXT_PORT = 8790
IMAGE_PORT = 8791

ROLES = ("text", "image")
APIS = {"text": ("openai", "anthropic"), "image": ("sdapi", "openai-images")}

# TWO TAG NAMES ARE UNIVERSAL, not settings: the same for every user, matched without regard to case.
# "ignore" on a folder, a notebook or a page means nothing there is ever worked on; "sprompt" on a PAGE
# makes that page its notebook's standing instructions (on a notebook or folder it means nothing). The
# ledger reads them from here. The tag each lineup watches for is the user's to choose.
# the languages of PaperDaemon's own window, each named in itself; ui/strings has a strings-<code>.xml for every one,
# translated from English
LANGUAGES = {"en": "English", "es": "Español", "pt": "Português", "fr": "Français", "de": "Deutsch", "cy": "Cymraeg",
             "ja": "日本語", "nb": "Norsk bokmål", "zh": "简体中文", "ko": "한국어", "ar": "العربية", "hi": "हिन्दी",
             "bn": "বাংলা", "ru": "Русский", "ur": "اردو", "id": "Bahasa Indonesia", "it": "Italiano", "tr": "Türkçe",
             "vi": "Tiếng Việt"}
IGNORE_TAG = "ignore"
SPROMPT_TAG = "sprompt"
FIXED_TAGS = (IGNORE_TAG, SPROMPT_TAG)
# the social sites a request for posts that names no site searches: all of them, always
SOCIAL_SITES = ("reddit", "hackernews", "bluesky", "4chan", "mastodon")
# what earlier versions kept as settings and this one drops when it loads them
_RETIRED_TABLET_KEYS = ("mute_tag", "sprompt_tag", "trigger_tag")   # trigger_tag: each lineup's watch tag now


def slot_defaults(role):
    return {"location": "", "script": "", "script_text": "", "harness": "auto", "api": APIS[role][0],
            "model": "", "overrides": {}, "tested": {}}


# A new installation starts with one blank lineup for the user to fill in: no model, server or start script is
# assumed. The text slot is the one a lineup needs; the image slot may stay empty.
SHIPPED_LINEUPS = [{"name": "Lineup 1", "text": slot_defaults("text"), "image": slot_defaults("image")}]
DEFAULT_LINEUP = "Lineup 1"

# ---------------------------------------------------------------- the schema
# Every setting, once: where it lives, its type, its default, what it may be, how the screens label and
# explain it, and the message a bad value gets. load() fills the defaults from it, validate() checks
# against it, the API serves it (GET /api/v1/settings/schema) and the screens take their rules from it.
# The lineups are a list of their own (check_lineup), and the capability rules of a slot live with the
# harnesses (harnesses/schema). Secrets are named here but kept in the credential store, never the file.
SCHEMA = [
    {"path": "tablet.inbox", "type": "text", "default": "", "label": "Decompose inbox",
     "help": "The notebook, by its path on the tablet, that Send to Tablet adds pages to; empty until chosen."},
    {"path": "false_mirror.inbox", "type": "text", "default": "", "label": "False Mirror decompose inbox",
     "help": "The notebook, by its path in the False Mirror, that Send to Tablet also adds pages to; empty until chosen."},
    {"path": "false_mirror.faces", "type": "choice", "default": "tablet", "choices": ["tablet", "own"],
     "label": "False Mirror faces",
     "help": "The faces typed text and books are set in, in the False Mirror: the tablet's (from the reMarkable desktop app, with an account signed in) or PaperDaemon's own."},
    {"path": "false_mirror.convert", "type": "bool", "default": False, "label": "Convert books with the tablet",
     "help": "Books imported into the False Mirror are converted by the tablet: each is sent, for a moment, to the root of the tablet's library."},
    {"path": "location.name", "type": "text", "default": "", "label": "Location",
     "help": "The city picked on the Overview, for the weather, holidays and sunrise on calendars; its coordinates and holiday region below come with it."},
    {"path": "location.lat", "type": "number", "default": None, "min": -90, "max": 90, "label": "Latitude",
     "message": "location.lat must be a number from -90 to 90, or empty"},
    {"path": "location.lon", "type": "number", "default": None, "min": -180, "max": 180, "label": "Longitude",
     "message": "location.lon must be a number from -180 to 180, or empty"},
    {"path": "location.holidays", "type": "text", "default": "", "label": "Holidays",
     "help": "The region whose public holidays calendars show (a country code such as US)."},
    # the two tags read the same way whatever the lineup: one keeps pages out, one marks a notebook's standing
    # instructions. Every tag in PaperDaemon is unique: no lineup's tag may be either of these.
    {"path": "tags.ignore", "type": "text", "default": IGNORE_TAG, "required": True, "label": "Ignore tag",
     "message": "the ignore tag cannot be empty"},
    {"path": "tags.sprompt", "type": "text", "default": SPROMPT_TAG, "required": True, "label": "Standing instructions tag",
     "message": "the standing instructions tag cannot be empty"},
    # the user's preferences: empty until they choose (the Settings screen asks once the Mirror is built), and
    # read from the computer's region settings meanwhile (region.py)
    {"path": "prefs.temperature", "type": "choice", "default": "", "choices": ["", "fahrenheit", "celsius"],
     "label": "Temperature", "message": "prefs.temperature is fahrenheit or celsius"},
    {"path": "prefs.clock", "type": "choice", "default": "", "choices": ["", "12", "24"],
     "label": "Clock", "message": "prefs.clock is 12 or 24"},
    {"path": "prefs.week_start", "type": "choice", "default": "", "choices": ["", "sunday", "monday", "saturday"],
     "label": "Week starts on", "message": "prefs.week_start is sunday, monday or saturday"},
    {"path": "prefs.language", "type": "choice", "default": "en", "choices": list(LANGUAGES),
     "label": "Language", "message": "prefs.language is one of " + ", ".join(LANGUAGES)},
    {"path": "network.allowed", "type": "bool", "default": True, "label": "Allow network access",
     "help": "Off, PaperDaemon reaches nothing on the internet itself: no weather, social posts, Wikipedia, maps or web "
             "search. The models in the lineup and the reMarkable cloud are not affected."},
    {"path": "features.off", "type": "list", "default": [], "label": "Features switched off",
     "help": "Features PaperDaemon never offers the model, whatever the lineup can do."},
    {"path": "server.port", "type": "integer", "default": API_PORT, "min": 1024, "max": 65535, "label": "Port",
     "message": "server.port must be a number from 1024 to 65535"},
    {"path": "server.listen", "type": "list", "default": ["127.0.0.1"], "must_include": "127.0.0.1",
     "label": "Addresses", "message": "server.listen must include 127.0.0.1 (the desktop window uses it)"},
    {"path": "secrets.device_token", "type": "secret", "store": "remarkable-device-token",
     "label": "reMarkable login"},
]


def _set_path(d, path, value):
    keys = path.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = copy.deepcopy(value)


def _get_path(d, path):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


DEFAULTS = {}
for _f in SCHEMA:
    if _f["type"] != "secret":
        _set_path(DEFAULTS, _f["path"], _f["default"])
DEFAULTS["lineups"] = SHIPPED_LINEUPS
DEFAULTS["lineup"] = DEFAULT_LINEUP


def schema():
    """The schema as the API serves it."""
    return copy.deepcopy(SCHEMA)


def check_field(f, v):
    """The error for one value of a schema field, or None."""
    t = f["type"]
    if t == "text":
        if not isinstance(v, str) or (f.get("required") and not v.strip()):
            return f.get("message") or "%s must be text" % f["path"]
    elif t == "number":
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not f["min"] <= v <= f["max"]):
            return f["message"]
    elif t == "integer":
        if not isinstance(v, int) or isinstance(v, bool) or not f["min"] <= v <= f["max"]:
            return f["message"]
    elif t == "choice":
        if v not in f["choices"]:
            return f["message"]
    elif t == "url":
        if not isinstance(v, str) or (v and urllib.parse.urlsplit(v).scheme not in ("http", "https")):
            return "%s must start with http:// or https://" % f["path"]
    elif t == "list":
        if not isinstance(v, list) or (f.get("must_include") and f["must_include"] not in v):
            return f.get("message") or "%s must be a list" % f["path"]
        if f.get("choices") and any(x not in f["choices"] for x in v):
            return f.get("message") or "%s holds only %s" % (f["path"], ", ".join(f["choices"]))
    elif t == "bool":
        if not isinstance(v, bool):
            return "%s is true or false" % f["path"]
    return None


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def upgrade_slot(m):
    """A slot as saved by an earlier version, in today's shape: the harness was once called its
    "profile", and an image slot's coloring_steps capability is now the steps of the harness's coloring
    book style."""
    m = dict(m)
    if "profile" in m:
        old = m.pop("profile")
        m.setdefault("harness", old)
    for layer in ("overrides", "tested"):
        if isinstance(m.get(layer), dict) and "coloring_steps" in m[layer]:
            m[layer] = {k: v for k, v in m[layer].items() if k != "coloring_steps"}
    return m


SEARCH_KINDS = ("none", "api", "local")
SEARCH_PROVIDERS = ("brave", "tavily", "exa", "serper")


def search_defaults():
    """A lineup's web search: none; a search service by `provider` (its key is the credential store's key:search:<provider>);
    or a search server hosted locally at `url` (SearXNG's JSON API), with an optional start script."""
    return {"kind": "none", "provider": "", "url": "", "script_text": ""}


def check_search(sr, where):
    errs = []
    if sr.get("kind") not in SEARCH_KINDS:
        errs.append("%s: web search is none, api or local" % where)
    elif sr["kind"] == "api" and sr.get("provider") not in SEARCH_PROVIDERS:
        errs.append("%s: the search service is one of %s" % (where, ", ".join(SEARCH_PROVIDERS)))
    elif sr["kind"] == "local" and not str(sr.get("url") or "").startswith(("http://", "https://")):
        errs.append("%s: the local search server needs its address (http://... or https://...)" % where)
    return errs


def tags_defaults():
    """A lineup's tags: an ordered list of tags it watches for, each with the prompt a page under it receives.
    Empty until the user names one."""
    return []


def check_tags(tags, where):
    errs, seen = [], set()
    if not isinstance(tags, list):
        return ["%s: the tags are a list" % where]
    for t in tags:
        n = str((t or {}).get("name") or "").strip().lower()
        if not n:
            errs.append("%s: every tag needs a name" % where)
        elif n in seen:
            errs.append("%s: the tag %s is used twice" % (where, n))
        seen.add(n)
        if len(str((t or {}).get("prompt") or "")) > 10000:
            errs.append("%s: a tag's prompt is at most 10,000 characters" % where)
    return errs


def tags_of(lu):
    """A lineup's tag names, in their order."""
    return [str(t.get("name") or "").strip() for t in (lu.get("tags") or []) if str(t.get("name") or "").strip()]


def startable(s):
    """True when some lineup could take a page: it has a tag, and its text model somewhere to run (a model on this
    computer with its start script). Whether the model answers or passes the lineup's test does not count here."""
    from . import scripts
    for lu in s.get("lineups") or []:
        m = lu.get("text") or {}
        url = str(m.get("location") or "").strip()
        if tags_of(lu) and url and (not loopback(url) or scripts.has_script(m)):
            return True
    return False


def all_tags(s):
    """Every lineup's tags -> [(tag, lineup name)], in the lineups' order and each lineup's own order."""
    return [(t, lu.get("name")) for lu in s.get("lineups") or [] for t in tags_of(lu)]


def lineup_of_tag(s, tag):
    """The lineup that watches for `tag` (case does not matter), or None."""
    want = str(tag or "").strip().lower()
    for t, name in all_tags(s):
        if t.lower() == want:
            return lineup(s, name)
    return None


def lineup_name_for(s, tag_name):
    """The lineup a tag as written on the tablet goes to ("qwen: draw a cat" -> the lineup watching "qwen"), the
    longest watched tag winning; None when no lineup watches it."""
    low = str(tag_name or "").strip().lower()
    for t, name in sorted(all_tags(s), key=lambda x: len(x[0]), reverse=True):
        k = t.lower()
        if low == k or (low.startswith(k) and low[len(k):][:1] in (":", ",", "-", "–", " ")):
            return name
    return None


def fixed_tags(s):
    """The ignore and standing instructions tags as the settings name them -> (ignore, sprompt)."""
    tg = s.get("tags") or {}
    return (str(tg.get("ignore") or IGNORE_TAG).strip(), str(tg.get("sprompt") or SPROMPT_TAG).strip())


def _upgrade_tags(tg):
    """An earlier version's {watch, ignore, sprompt, custom} -> the list: the watch tag first (its prompt empty),
    then the custom tags with theirs."""
    if isinstance(tg, list):
        return [{"name": str((t or {}).get("name") or "").strip(), "prompt": str((t or {}).get("prompt") or "")}
                for t in tg if isinstance(t, dict)]
    if not isinstance(tg, dict):
        return []
    out = [{"name": str(tg["watch"]).strip(), "prompt": ""}] if str(tg.get("watch") or "").strip() else []
    out += [{"name": str(c.get("name") or "").strip(), "prompt": str(c.get("prompt") or "")}
            for c in (tg.get("custom") or []) if isinstance(c, dict)]
    return out


def normalize_lineup(lu):
    """A lineup with every slot field present (missing ones take their defaults), upgraded from an
    earlier version's shape."""
    lu = dict(lu or {})
    out = {"name": str(lu.get("name") or "").strip()}
    for role in ROLES:
        got = upgrade_slot(lu.get(role)) if isinstance(lu.get(role), dict) else {}
        out[role] = _merge(slot_defaults(role), got)
    sr = dict(lu.get("search")) if isinstance(lu.get("search"), dict) else {}
    if sr.get("kind") == "searxng":                 # an earlier version's name for a local SearXNG
        sr["kind"] = "local"
    out["search"] = {k: sr.get(k, v) for k, v in search_defaults().items()}
    out["tags"] = _upgrade_tags(lu.get("tags"))
    return out


def _shape(s):
    s.pop("models", None)                   # an older single-slot shape; lineups replace it
    # web search is each lineup's now; new documents go where the job is; a request for posts searches every social site
    for k in ("search", "output_folder", "social"):
        s.pop(k, None)
    old_tag = str((s.get("tablet") or {}).get("trigger_tag") or "").strip()
    for k in _RETIRED_TABLET_KEYS:
        (s.get("tablet") or {}).pop(k, None)
    if not isinstance(s.get("lineups"), list):
        s["lineups"] = copy.deepcopy(SHIPPED_LINEUPS)
    shaped = []
    for lu in s["lineups"]:
        if not isinstance(lu, dict):
            continue
        old = lu.get("tags") if isinstance(lu.get("tags"), dict) else None
        if old is not None:                 # an earlier version kept ignore and sprompt per lineup: they are global now
            for k in ("ignore", "sprompt"):
                v = str(old.get(k) or "").strip()
                if v and v.lower() != {"ignore": IGNORE_TAG, "sprompt": SPROMPT_TAG}[k] and                         str((s.get("tags") or {}).get(k) or "") in ("", {"ignore": IGNORE_TAG, "sprompt": SPROMPT_TAG}[k]):
                    s.setdefault("tags", {})[k] = v
        shaped.append(normalize_lineup(lu))
    # the one trigger tag of an earlier version goes to the lineup that was active then, if no lineup has it yet
    if old_tag and old_tag.lower() not in FIXED_TAGS and             not any(t.get("name", "").lower() == old_tag.lower() for lu in shaped for t in lu["tags"]):
        home = next((lu for lu in shaped if lu["name"] == s.get("lineup")), shaped[0] if shaped else None)
        if home is not None and not home["tags"]:
            home["tags"] = [{"name": old_tag, "prompt": ""}]
    s["lineups"] = shaped
    # the lineup last in use, a fallback only (every lineup is live; a job's tag picks its lineup)
    if shaped and s.get("lineup") not in [lu["name"] for lu in shaped]:
        s["lineup"] = shaped[0]["name"]
    return s


def load():
    try:
        with open(paths.settings_file(), encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    return _shape(_merge(DEFAULTS, saved))


def exists():
    """False until settings have been saved once: the first run."""
    return os.path.isfile(paths.settings_file())


def save(s):
    """Validate, then write atomically. Returns the settings as saved."""
    s = _shape(_merge(DEFAULTS, s))
    errs = validate(s)
    if errs:
        raise ValueError("; ".join(errs))
    path = paths.settings_file()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, path)
    return s


def host_of(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def loopback(url):
    """True when the endpoint is on this computer."""
    import ipaddress
    h = host_of(url)
    if h == "localhost":
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


# ---------------------------------------------------------------- lineups

def lineup(s=None, name=None):
    """The named lineup, or the active one. None when there is no such lineup."""
    s = s or load()
    want = name if name is not None else s.get("lineup")
    for lu in s.get("lineups") or []:
        if lu.get("name") == want:
            return lu
    return None


_forced = {"name": None}
_in_use = {"name": None}


def force(name):
    """Use the named lineup instead of the one in use until force(None), without saving anything (the
    benchmark runs a lineup this way)."""
    _forced["name"] = name


def use(name):
    """The lineup the current job runs on (the host names it at the start of every job, by the job's tag).
    Every lineup is live; this only says whose slots the next model call goes to."""
    _in_use["name"] = name or None


def in_use():
    return _in_use["name"]


def active(s=None):
    """The lineup in use: the one forced for a benchmark run, else the current job's, else the last one
    saved as in use, else the first."""
    s = s or load()
    lu = lineup(s, _forced["name"]) if _forced["name"] else None
    lu = lu or (lineup(s, _in_use["name"]) if _in_use["name"] else None)
    lu = lu or lineup(s)
    if lu is None:
        lus = s.get("lineups") or []
        lu = lus[0] if lus else normalize_lineup({"name": ""})
    return lu


def check_slot(role, m, where="slot"):
    """Errors in one slot's values."""
    from .models import slots                     # the capability rules live with the slots
    errs = []
    if m.get("api") not in APIS[role]:
        errs.append("%s: api is one of %s" % (where, ", ".join(APIS[role])))
    url = str(m.get("location") or "").strip()
    if url and urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        errs.append("%s: the location must start with http:// or https://" % where)
    for k in ("script", "script_text", "model"):
        if not isinstance(m.get(k), str):
            errs.append("%s: %s must be text" % (where, k))
    errs.extend(slots.check_harness_and_overrides(role, m, where))
    return errs


def check_lineup(lu):
    errs = []
    name = str(lu.get("name") or "").strip()
    if not name:
        errs.append("a lineup needs a name")
    elif len(name) > 80 or any(c in name for c in "/\\\r\n\t"):
        errs.append("a lineup's name is at most 80 characters, without slashes or line breaks")
    for role in ROLES:
        errs.extend(check_slot(role, lu[role], "%s's %s slot" % (name or "the lineup", role)))
    errs.extend(check_search(lu.get("search") or search_defaults(), name or "the lineup"))
    errs.extend(check_tags(lu.get("tags") or tags_defaults(), name or "the lineup"))
    return errs


def validate(s):
    """Every error in the settings, each in the schema's words."""
    errs = []
    for f in SCHEMA:
        if f["type"] != "secret":
            err = check_field(f, _get_path(s, f["path"]))
            if err:
                errs.append(err)
    lus = s.get("lineups") or []
    if not lus:
        errs.append("keep at least one lineup")
    # EVERY TAG IS UNIQUE across PaperDaemon: a tag picks the lineup a page goes to, so two lineups cannot both
    # watch for it, and none may be the ignore or the standing instructions tag
    ignore, sprompt = fixed_tags(s)
    if ignore.lower() == sprompt.lower():
        errs.append("the ignore tag and the standing instructions tag cannot be the same")
    owner = {ignore.lower(): "the ignore tag", sprompt.lower(): "the standing instructions tag"}
    for t, name in all_tags(s):
        k = t.lower()
        if k in owner and owner[k] != name:
            if owner[k].startswith("the "):          # a lineup's tag and a Settings tag: say both sides
                errs.append("the tag %s is a tag of %s, so it cannot also be %s" % (t, name, owner[k]))
            else:
                errs.append("the tag %s is already a tag of %s" % (t, owner[k]))
        owner.setdefault(k, name)
    names = [lu.get("name") for lu in lus]
    if len(set(names)) < len(names):
        errs.append("two lineups cannot share a name")
    for lu in lus:
        errs.extend(check_lineup(lu))
    return errs
