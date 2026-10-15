"""Every harness field, what it accepts, and how the rule reads in an error. One definition, used by the
harness loader (shipped and user files alike), the per-slot overrides and the API."""
import re

# what an image harness may say it can do, and how the brief describes each
ABILITIES = {
    "generate": "makes a picture from a sentence",
    "edit_reference": "edits a picture handed to it as a reference (the prompt says what to change)",
    "img2img": "redraws a picture starting from another one",
    "inpaint": "changes only a masked part of a picture",
}
# the engine's edit modes and the ability each needs
EDIT_ABILITY = {"ref": "edit_reference", "img2img": "img2img", "inpaint": "inpaint"}


def _posint(v):
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _steps(v):
    return isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 150


def _pair(v, ok):
    return isinstance(v, (list, tuple)) and len(v) == 2 and all(ok(x) for x in v)


def _workflow_name(n):
    return isinstance(n, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", n) is not None


def _lora(x):
    """{"file": a path inside the server's LoRA folder, "strength": its weight}"""
    return (isinstance(x, dict) and set(x) <= {"file", "strength"} and isinstance(x.get("file"), str)
            and x["file"].strip() != "" and ".." not in x["file"].replace("\\", "/").split("/")
            and _number(x.get("strength", 1.0)) and -4.0 <= x.get("strength", 1.0) <= 4.0)


def _workflow(wf):
    """A workflow: its wording with {subject} in it, and optionally what it is for, its steps, its LoRAs and
    whether it starts from a reference picture."""
    if not isinstance(wf, dict) or set(wf) - {"prompt", "about", "steps", "loras", "reference"}:
        return False
    p = wf.get("prompt")
    return (isinstance(p, str) and "{subject}" in p and len(p) <= 4000
            and isinstance(wf.get("about", ""), str) and len(wf.get("about", "")) <= 300
            and (wf.get("steps") is None or _steps(wf["steps"]))
            and isinstance(wf.get("loras", []), list) and len(wf.get("loras", [])) <= 8
            and all(_lora(x) for x in wf.get("loras", []))
            and isinstance(wf.get("reference", False), bool))


def _workflows(v):
    return isinstance(v, dict) and len(v) <= 50 and all(_workflow_name(k) and _workflow(w) for k, w in v.items())


def _abilities(v):
    return isinstance(v, (list, tuple)) and all(isinstance(a, str) and a in ABILITIES for a in v)


# KEYWORD ASSISTS: data a harness may carry to help a weaker model with one decision, after the model has made
# it (never in place of it). Each names a decision from the closed list the features declare, the text it reads,
# what fires it (whole keywords, case ignored, or the text's last characters), an optional condition on the
# model's value, and a hint (the model is told once and decides again) or a set (an override, recorded).
def decisions():
    from paperdaemon.pipeline import features as F
    return tuple(sorted({d for f in F.Catalog().by_name.values() for d in f.decisions}))


ASSIST_READS = ("step.what", "step.words", "step.source", "step.search", "item.text")


def _assist(a):
    if not isinstance(a, dict) or a.get("decision") not in decisions() or a.get("reads") not in ASSIST_READS:
        return False
    fires = isinstance(a.get("keywords"), list) and a["keywords"] and all(isinstance(k, str) and k for k in a["keywords"])
    fires = fires or (isinstance(a.get("ends_with"), str) and a["ends_with"] != "")
    acts = (isinstance(a.get("hint"), str) and a["hint"].strip() != "") != isinstance(a.get("set"), dict)
    known = set(a) <= {"decision", "reads", "keywords", "ends_with", "when", "hint", "set"}
    return bool(fires and acts and known and isinstance(a.get("when", ""), str))


RULES = {
    "assists": (lambda v: isinstance(v, list) and all(_assist(a) for a in v),
                "a list of assists, each {\"decision\": one the features declare, \"reads\": one of step.what, step.words, "
                "step.source, step.search, item.text, \"keywords\": [words] or \"ends_with\": text, optionally \"when\": "
                "the model's value, and \"hint\": what to tell the model or \"set\": {fields to override}}"),
    "inspect_tokens": (lambda v: _posint(v) and int(v) <= 200000, "a whole number of tokens above 0"),
    "vision": (lambda v: isinstance(v, bool), "true or false"),
    "forced_tool": (lambda v: isinstance(v, bool), "true or false"),
    "max_output": (lambda v: v is None or _posint(v), "a whole number above 0, or empty"),
    "brief_additions": (lambda v: isinstance(v, str) and len(v) <= 20000, "text of at most 20,000 characters"),
    "steps": (_steps, "a whole number from 1 to 150"),
    "steps_range": (lambda v: _pair(v, _steps) and v[0] <= v[1], "two step counts, low then high"),
    "cfg": (lambda v: _number(v) and v >= 0, "a number, 0 or more"),
    "sampler": (lambda v: isinstance(v, str) and v.strip() != "", "a sampler name"),
    "scheduler": (lambda v: v is None or (isinstance(v, str) and v.strip() != ""), "a scheduler name, or empty"),
    "shift": (lambda v: v is None or _number(v), "a number, or empty"),
    "size": (lambda v: _pair(v, lambda x: isinstance(x, int) and not isinstance(x, bool) and 64 <= x <= 4096),
             "width and height from 64 to 4096"),
    "workflows": (_workflows, "named workflows, each {\"prompt\": wording with {subject} in it, and optionally "
                              "\"about\": what it is for, \"steps\": a step count, \"loras\": [{\"file\", "
                              "\"strength\"}], \"reference\": true or false}"),
    "abilities": (_abilities, "a list of: generate, edit_reference, img2img, inpaint"),
    "features": (lambda v: isinstance(v, dict) and set(v) <= {"off"} and isinstance(v.get("off", []), list)
                 and all(isinstance(n, str) for n in v.get("off", [])), "{\"off\": [feature names]}"),
    "request": (lambda v: isinstance(v, dict) and all(isinstance(c, str) and isinstance(by, dict)
                                                      and all(isinstance(x, dict) for x in by.values())
                                                      for c, by in v.items()),
                "{capability: {value: {fields merged into every chat request}}}"),
}


def check(field, value):
    """None when `value` is acceptable for `field`, else the rule it breaks."""
    rule = RULES.get(field)
    if rule is None:
        return "%s is not a harness field" % field
    return None if rule[0](value) else "%s must be %s" % (field, rule[1])
