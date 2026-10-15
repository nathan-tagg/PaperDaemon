"""What a notebook brings to its jobs: its instructions (tags' prompts, the standing instructions page, the lineup's memories) and its notepad."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from paperdaemon import ledger as S
from paperdaemon.notepad import Notepad
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline import host as H

SPROMPT_MAX = 10000              # characters of a notebook's instructions the model is given


def notebook_prompt(doc_id):
    """The text of every page of this notebook tagged `sprompt`: typed text first, OCR of ink
    when there is none. '' when the notebook has no such page."""
    try:
        c = S.content(doc_id)
    except Exception:
        return ""
    pids = [t.get("pageId") for t in (c.get("pageTags") or [])
            if str(t.get("name", "")).strip().lower() == H.SPROMPT_TAG]
    if not pids:
        return ""
    live = S.live_pages(c)
    index = dict((p["id"], i + 1) for i, p in enumerate(live))
    parts = []
    for pid in pids:
        n = index.get(pid)
        if not n:
            continue
        txt = ""
        try:
            from paperdaemon.pipeline.page import typed as TY
            _tb, paras = TY.paragraphs(doc_id, n)
            txt = "\n".join(str(p.get("text", "")).strip() for p in paras if str(p.get("text", "")).strip())
        except Exception:
            txt = ""
        if not txt.strip():
            try:
                import re as _re
                out = os.path.join(H.QUEUE, "_host_sprompt.png")
                R.render(doc_id, n, out, typed=True)
                rows = H.describe_png(out).splitlines()[1:]
                txt = "\n".join(_re.sub(r"^\s*y=\s*-?\d+\s+x=\s*-?\d+\s+size~\s*\d+\s+", "", r) for r in rows)
            except Exception:
                txt = ""
        if txt.strip():
            parts.append(txt.strip())
    # 10,000 characters of them: a notebook's system prompt can feasibly get large, so a cap near
    # 1,500 characters is too tight
    got = "\n\n".join(parts)
    if len(got) > SPROMPT_MAX:
        H.log("  sprompt cut to %d of its %d characters" % (SPROMPT_MAX, len(got)))
    return got[:SPROMPT_MAX]


def tag_prompts(doc_id):
    """The prompts of the job's lineup's tags (Lineup > Tagging) that reach this job: on its page, its notebook,
    or any folder above it -> [(tag, prompt)], in the order the lineup's Tagging tab lists them. A tag with an
    empty prompt adds nothing."""
    mine = [c for c in (H.RUN.get("tags") or []) if str(c.get("name") or "").strip()]
    if not mine:
        return []
    names = set()

    def add(tags):
        for t in tags or []:
            trig = S.trigger_of(str(t.get("name") if isinstance(t, dict) else t))
            if trig:
                names.add(trig)
    try:
        c = S.content(doc_id)
        add(c.get("tags"))
        n = JOB.page
        live = S.live_pages(c)
        if n and 0 < n <= len(live):
            pid = live[n - 1].get("id")
            add([t for t in (c.get("pageTags") or []) if t.get("pageId") == pid])
        parent, depth = (S.meta(doc_id) or {}).get("parent"), 0
        while parent and parent != "trash" and depth < 8:
            add((S.content(parent) or {}).get("tags"))
            parent, depth = (S.meta(parent) or {}).get("parent"), depth + 1
    except Exception:
        pass
    return [(c["name"], str(c.get("prompt") or "").strip()) for c in mine
            if c["name"].strip().lower() in names and str(c.get("prompt") or "").strip()]


def memories_system():
    """The lineup's memories, after the brief and before the user's prompts -> '' when it has none. They change
    only when a job changes them, so the cached prefix (the brief and the tools) still holds."""
    name = H.RUN.get("lineup") or ""
    if not name or not os.environ.get("RM_STUDIO"):
        return ""
    try:
        got = H._studio("/memories?lineup=%s" % urllib.parse.quote(name), timeout=30)
    except Exception as ex:
        H.log("  memories not read: %s" % str(ex)[:120])
        return ""
    items, most = got.get("memories") or [], int(got.get("max") or 30)
    out = ("\n\nYOUR MEMORIES: lessons you have learned about working for this user, in their own jobs "
           "(%d of %d kept%s). Follow them. Change them with remember on your decision: a lesson only -- "
           "never the work on a page, the user's personal details, or anything about this notebook (that is "
           "the notepad's)." % (len(items), most, "; FULL: replace one to add" if len(items) >= most else ""))
    for m in items:
        out += "\n  %s: %s" % (m.get("id"), m.get("text"))
    return out


def notebook_system(doc_id):
    """This notebook's system prompt, for the END of the system message -> '' when it has none.

    IN THE SYSTEM MESSAGE, not among the page data. In the first user message ("follow them,
    within the rules above") it ranks under the brief, whose rule that a request on the page is new
    work wins: told "never revisit a page", the model drew a castle on a finished coloring page.
    After the static brief, so the brief's cached prefix still holds."""
    out = ""
    # the tags' prompts first, in the Tagging tab's order; the notebook's own system prompt always LAST
    for name, prompt in H.tag_prompts(doc_id):
        out += ("\n\nTHE USER'S PROMPT FOR THE TAG '%s', which this page, its notebook or a folder above it "
                "carries. Follow it like the notebook's system prompt.\n" % name) + prompt
    sp = H.notebook_prompt(doc_id)
    JOB.sprompt = sp                        # the decision's last word points back at it (job_context)
    if sp:
        out += ("\n\nTHIS NOTEBOOK'S SYSTEM PROMPT. The user wrote it on a page of this notebook tagged "
                "'%s'. It governs every job in this notebook; where it and the rules above differ, "
                "it wins.\n" % H.SPROMPT_TAG + sp)
    return out


def t_notepad(text):
    """Remember something for FUTURE jobs in this notebook -- not this one."""
    text = " ".join(str(text or "").split())
    if not text:
        return {"error": "notepad needs the text to remember"}
    JOB.notepad.append(text)
    return {"ok": True, "note": "Written to this notebook's notepad when the job ends; every later "
                                "job in this notebook will see it."}


def _sprompt_pages(doc_id):
    """Page ids in this notebook tagged `sprompt` -- instruction pages, never work."""
    try:
        c = json.load(open(os.path.join(R.RM, doc_id + ".content"), encoding="utf-8"))
        return set(t.get("pageId") for t in (c.get("pageTags") or [])
                   if str(t.get("name", "")).strip().lower() == H.SPROMPT_TAG)
    except Exception:
        return set()


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("notepad", "Remember something for FUTURE jobs in THIS notebook -- a preference the user stated, what "
  "a running list is about. Shown to every later job here under THIS NOTEBOOK'S NOTEPAD.",
  {"text": "string"}, t_notepad),
]
