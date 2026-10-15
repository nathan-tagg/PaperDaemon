"""The two model slots of a lineup (the one in use unless one is named): their settings, their harness, and
their effective capabilities.

A slot's capability resolves in layers: the user's override, else a model-check result the user
accepted, else the harness's value (a user harness's, a model harness's, or the default's). The models
screen shows each value with the layer it came from.
"""
import re

from .. import harnesses
from .. import settings as S
from ..harnesses import schema as rules

ROLES = S.ROLES
def key_of(role, m):
    """The credential store's name for a slot's API key: one per server, shared by every lineup that uses it."""
    from .. import vault
    return vault.key_name(role, (m or {}).get("location") or "")
CAP_RULES = rules.RULES

# the models each slot's server last reported (filled by the model check): a hint for the guess
_reported = {"text": [], "image": []}


def report_models(role, names):
    _reported[role] = [str(n) for n in names if n]


def slot(role, s=None, lineup=None):
    """The slot's settings: the lineup in use's, or the named lineup's."""
    s = s or S.load()
    lu = S.lineup(s, lineup) if lineup else S.active(s)
    if lu is None:
        raise KeyError("no lineup named %r" % lineup)
    return lu[role]


def location(role, s=None):
    return str(slot(role, s).get("location") or "").strip()


def configured(role, s=None):
    return bool(location(role, s))


def off_machine(role, s=None):
    """The host a slot sends pages to when it is not this computer, else None."""
    url = location(role, s)
    return S.host_of(url) if url and not S.loopback(url) else None


def script_text(m):
    """The text of a slot's start script (for the harness guess), or ""."""
    from .. import scripts
    try:
        return scripts.text_of(m) or ""
    except OSError:
        return ""


def pick(role, s=None, m=None):
    """-> (harness class, "user" | "guess", the hint's source or None, the hint or None)."""
    m = m if m is not None else slot(role, s)
    chosen = m.get("harness") or "auto"
    if chosen != "auto":
        p = harnesses.get(chosen)
        if p is not None and p.kind == role:
            return p, "user", None, None
    p, source, hint = harnesses.guess(role, m.get("model"), _reported.get(role), script_text(m))
    return p, "guess", source, hint


def capabilities(role, s=None, m=None):
    """-> {capability: {"value": v, "source": "override" | "test" | "harness" | "default"}}."""
    m = m if m is not None else slot(role, s)
    p = pick(role, s, m)[0]
    base = harnesses.DEFAULT[role]
    over, tested = m.get("overrides") or {}, m.get("tested") or {}
    out = {}
    for c in p.CAPABILITIES:
        if c in over:
            out[c] = {"value": over[c], "source": "override"}
        elif c in tested:
            out[c] = {"value": tested[c], "source": "test"}
        else:
            v = getattr(p, c)
            out[c] = {"value": list(v) if isinstance(v, tuple) else v,
                      "source": "default" if getattr(base, c) == v else "harness"}
    return out


def caps(role, s=None, m=None):
    return {k: v["value"] for k, v in capabilities(role, s, m).items()}


def harness(role, s=None, m=None):
    """An instance of the slot's harness, for its hooks (tune, prompt)."""
    return pick(role, s, m)[0]()


def describe(role, s=None, lineup=None):
    """Everything the models screen shows about a slot (the named lineup's, else the one in use), secrets
    excepted."""
    s = s or S.load()
    lu = S.lineup(s, lineup) if lineup else S.active(s)
    m = lu[role]
    loc = str(m.get("location") or "").strip()
    p, how, source, hint = pick(role, s, m)
    if how == "user":
        why = "picked by you"
    elif source:
        why = "guessed from %s (%s)" % (harnesses.HINT_LABEL[source], hint)
    else:
        why = "no harness matched, so the default harness is used"
    return {
        "lineup": lu["name"],
        "configured": bool(loc),
        "location": loc,
        "script": m.get("script") or "",
        "harness": {"id": p.id, "name": p.name, "how": how, "why": why},
        "capabilities": capabilities(role, s, m),
        "off_machine": S.host_of(loc) if loc and not S.loopback(loc) else None,
        "harnesses": [{"id": q.id, "name": q.name} for q in harnesses.for_kind(role)],
        "reported": list(_reported.get(role) or []),
    }


def check_harness_and_overrides(role, m, where=None):
    """Errors in a slot's harness choice and capability values (used by settings.validate)."""
    where = where or "the %s slot" % role
    errs = []
    chosen = m.get("harness") or "auto"
    if chosen != "auto":
        p = harnesses.get(chosen)
        if p is None or p.kind != role:
            errs.append("%s: %r is not a %s harness" % (where, chosen, role))
    allowed = harnesses.DEFAULT[role].CAPABILITIES
    for layer in ("overrides", "tested"):
        vals = m.get(layer) or {}
        if not isinstance(vals, dict):
            errs.append("%s: %s must be a list of capabilities" % (where, layer))
            continue
        for c, v in vals.items():
            if c not in allowed:
                errs.append("%s: %s is not a capability of a %s model" % (where, c, role))
            elif not CAP_RULES[c][0](v):
                errs.append("%s: %s must be %s" % (where, c, CAP_RULES[c][1]))
    return errs


# ---- picture parameters

def numbers_in(*texts):
    """Whole numbers written in the texts: what counts as the user's own step count."""
    out = set()
    for t in texts:
        out.update(int(n) for n in re.findall(r"(?<![\w.])(\d{1,4})(?![\w.])", str(t or "")))
    return out


def picture_steps(caps, requested=None, workflow_steps=None, user_numbers=()):
    """The step count for a picture. A count the user wrote (it is among `user_numbers`, the numbers in
    the notebook prompt and on the page) is used as written; one the model chose is kept inside the
    harness's range; with none, the picture's workflow says (a coloring page's 12 on Klein), else the
    harness's default."""
    if requested is not None:
        n = int(requested)
        if n in set(int(u) for u in user_numbers):
            return max(1, min(150, n))
        lo, hi = caps["steps_range"]
        return max(lo, min(hi, n))
    if workflow_steps:
        return int(workflow_steps)
    return caps["steps"]


def picture_size(caps, width=None, height=None, multiple=16):
    """Width and height rounded down to the harness's multiple, defaulting to the harness's size."""
    w, h = width or caps["size"][0], height or caps["size"][1]
    return max(multiple, int(w) // multiple * multiple), max(multiple, int(h) // multiple * multiple)
