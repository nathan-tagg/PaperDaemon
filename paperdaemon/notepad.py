"""A notebook's notepad: what every job in that notebook asked and did, so a follow-up on another page has
something to refer to.

It is <state>/rm-notepad/<notebook id>.md: one "## <time>, page id <page id>" entry per job, each a few
"- " lines. Entries are filed under the page's id, never its number, because inserting or removing a page
renumbers the pages after it. A game keeps its state inside its notebook's notepad, as JSON in an HTML
comment the model never sees. Wiping a notepad deletes the file.
"""
import os
import re
import time

from . import paths

DOC_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
HEAD = re.compile(r"(?m)^## ([^\n,]+), page id ([0-9a-f-]{8,36})$")
SHOW = 2600                          # characters of the newest entries the model is shown
ASKED, ON_PAGE = "asked:", "on the page:"   # the labels of an entry's lines that the window shows apart


def folder(state=None):
    return os.path.join(state or paths.state_dir(), "rm-notepad")


def _is_skip(entry):
    """A skipped job's entry. A skip changed nothing and its note is only the model's reasoning, which later
    jobs would read as fact, so it is never shown back."""
    return bool(HEAD.match(entry) and re.search(r"(?m)^- skipped:", entry))


class Notepad(object):
    """One notebook's notepad."""

    def __init__(self, doc, state=None):
        if not DOC_ID.match(str(doc or "")):
            raise ValueError("not a notebook id")
        self.doc = doc
        self.path = os.path.join(folder(state), doc + ".md")

    def text(self):
        """The whole file ("" when there is none)."""
        try:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def entries(self):
        return len(re.findall(r"^## ", self.text(), re.MULTILINE))

    def read(self, limit=SHOW, page_id=None, numbers=None):
        """The notepad as the model is shown it: the newest entries, `limit` characters of them, plus every
        entry for this page however old; each header says "THIS page", the page's number now (`numbers`:
        {page id: number}), or that the page is gone. Skipped jobs and game state are left out."""
        t = re.sub(r"<!-- game-state .*?-->\n?", "", self.text(), flags=re.S)
        t = "".join(e for e in re.split(r"(?m)^(?=## )", t.strip()) if not _is_skip(e)).strip()
        if len(t) > limit:
            cut = t[-limit:]
            tail = cut[cut.find("\n## ") + 1:] if "\n## " in cut else cut
            older = ""
            if page_id:
                mine = [e.strip() for e in re.split(r"(?m)^(?=## )", t[:len(t) - len(tail)])
                        if e.startswith("## ") and e.split("\n", 1)[0].endswith("page id %s" % page_id)]
                if mine:
                    older = "(earlier entries for THIS page)\n%s\n\n" % "\n\n".join(mine)
            t = older + "...\n" + tail          # "..." on its own line, so the next header still starts a line
        numbers = numbers or {}

        def head(m):
            if page_id and m.group(2) == page_id:
                return "## %s, THIS page" % m.group(1)
            n = numbers.get(m.group(2))
            return "## %s, page %d" % (m.group(1), n) if n else "## %s, a page no longer in this notebook" % m.group(1)
        return HEAD.sub(head, t)

    def parsed(self, numbers=None):
        """The entries as parts, for the window: [{"when": "YYYY-MM-DD HH:MM", "page_id", "page": its number now
        (`numbers`: {page id: number}) or None, "asked": [what was asked], "did": [the other lines]}], oldest first.
        The labels the host writes ("asked:", "on the page:") are read here, beside the format, never in the window."""
        out = []
        t = re.sub(r"<!-- game-state .*?-->\n?", "", self.text(), flags=re.S)
        for e in re.split(r"(?m)^(?=## )", t.strip()):
            m = HEAD.match(e)
            if not m:
                continue
            asked, did = [], []
            for ln in e.split("\n")[1:]:
                ln = re.sub(r"^[-*]\s+", "", ln.strip())
                if not ln:
                    continue
                if ln.lower().startswith(ASKED):
                    asked.append(ln[len(ASKED):].strip())
                else:
                    did.append(ln[len(ON_PAGE):].strip() if ln.lower().startswith(ON_PAGE) else ln)
            out.append({"when": m.group(1).strip(), "page_id": m.group(2), "page": (numbers or {}).get(m.group(2)),
                        "asked": asked, "did": did})
        return out

    def append(self, page_id, lines):
        """One entry, newest last, filed under the page's id. `lines` are short strings."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("## %s, page id %s\n" % (time.strftime("%Y-%m-%d %H:%M"), page_id or "unknown"))
            for ln in lines:
                ln = " ".join(str(ln).split())
                if ln:
                    f.write("- %s\n" % ln[:400])
            f.write("\n")

    def wipe(self):
        """Empty the notepad (and any game state in it). -> the number of entries removed."""
        n = self.entries()
        try:
            os.remove(self.path)
        except FileNotFoundError:
            return 0
        return n


def notepads(state=None, mirror=None):
    """[{doc, notebook, entries, chars}] for every notebook with a notepad, for the Notepads screen."""
    from . import ledger
    out = []
    try:
        names = sorted(os.listdir(folder(state)))
    except OSError:
        return out
    for n in names:
        doc = n[:-3]
        if not n.endswith(".md") or not DOC_ID.match(doc):
            continue
        text = Notepad(doc, state).text()
        out.append({"doc": doc, "notebook": ledger.notebook_name(doc, state, mirror),
                    "entries": len(re.findall(r"^## ", text, re.MULTILINE)), "chars": len(text)})
    return out
