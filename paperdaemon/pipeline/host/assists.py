"""Keyword assists, applied after the model's decision and never in place of it (harnesses/schema.py has their
format). A hint that fires goes back to the model once, as a turn; the model keeps its choice or changes it. An
override sets the value, and the job's record says which assist did it. No shipped harness carries any."""
import re

from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB

# what each decision acts on: the steps of some kinds (None: every step), or the rulings; and the field it decides
_ON = {"step.kind": (None, "do"), "step.replaces": (None, "replaces"), "markup.target": (ST.MARK_UP, "target"),
       "posts.source": (("posts",), "source"), "image.steps": (("image", "coloring"), "steps"),
       "item.ruling": ("rulings", "then")}


def _text(a, obj):
    if a["reads"] == "item.text":
        return str(((JOB.listing or {}).get(obj.get("id")) or {}).get("text") or "")
    return str(obj.get(a["reads"].split(".", 1)[1]) or "")


def _fires(a, text):
    if a.get("ends_with"):
        return text.rstrip().endswith(a["ends_with"])
    low = text.lower()
    return any(re.search(r"(?<!\w)%s(?!\w)" % re.escape(k.lower()), low) for k in a.get("keywords") or ())


def apply(args, assists):
    """Run the harness's assists over a decision's arguments (plan or answer) -> (args, hint or None). Overrides
    are applied to the arguments and recorded; a hint is returned once per assist per job."""
    hints = []
    for n, a in enumerate(assists or ()):
        kinds, field = _ON.get(a.get("decision"), (None, None))
        if field is None:
            continue
        objs = (args.get("rulings") or []) if kinds == "rulings" else \
            [q for q in args.get("steps") or [] if isinstance(q, dict) and (kinds is None or q.get("do") in kinds)]
        for obj in objs:
            if not isinstance(obj, dict) or not _fires(a, _text(a, obj)):
                continue
            if a.get("when") and str(obj.get(field)) != a["when"]:
                continue
            if a.get("set"):
                obj.update(a["set"])
                JOB.assisted.append("assist %d (%s) set %s on %s" % (n + 1, a["decision"], a["set"], obj.get("id") or obj.get("do")))
            elif n not in JOB.assists_hinted:
                JOB.assists_hinted.add(n)
                hints.append(a["hint"])
    return args, (" ".join(hints) if hints else None)
