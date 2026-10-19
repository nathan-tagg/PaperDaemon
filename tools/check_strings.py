"""The interface's words are all in ui/strings: every PD.t name the screens use is in strings-en.xml and in every
translation (with the same {placeholders}), no translation has a name English lacks, and no English text is left
written into the screens' code.

    uv run python tools/check_strings.py           -> exit 1 and a list when anything is wrong
"""
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "paperdaemon", "ui")
STRINGS = os.path.join(UI, "strings")
sys.path.insert(0, ROOT)
from paperdaemon.settings import LANGUAGES  # noqa: E402  (the languages the window speaks)
LANGS = tuple(LANGUAGES)

# a quoted literal that reads as words for a person: two letters in a row, a space or a capital, and none of the
# marks of code (markup is checked by its text between tags below)
WORDS = re.compile(r"[A-Za-z]{2,}")
CODE_LIKE = re.compile(r"^[\w.\-/#:%?=&*+,;!()\[\]{}$@^|<>\\'\" ]*$")


def load(code):
    path = os.path.join(STRINGS, "strings-%s.xml" % code)
    if not os.path.exists(path):
        return None
    return {s.get("name"): (s.text or "") for s in ET.parse(path).getroot().iter("string")}


def used_names():
    out = {}
    for f in glob.glob(os.path.join(UI, "*.js")):
        for m in re.finditer(r"PD\.t(?:Html)?\(\s*\"([\w.\-]+)\"", open(f, encoding="utf-8").read()):
            out.setdefault(m.group(1), os.path.basename(f))
        for m in re.finditer(r"PD\.count\(\s*\"([\w.\-]+)\"", open(f, encoding="utf-8").read()):
            for form in (".one", ".other"):
                out.setdefault(m.group(1) + form, os.path.basename(f))
    return out


def stray_text():
    """English left in the screens' code: text between tags in HTML strings, and plain quoted sentences."""
    hits = []
    for f in sorted(glob.glob(os.path.join(UI, "*.js"))):
        in_comment = False
        for n, line in enumerate(open(f, encoding="utf-8"), 1):
            if in_comment:                               # inside a /* ... */ comment
                if "*/" not in line:
                    continue
                in_comment, line = False, line.split("*/", 1)[1]
            if "/*" in line:
                head, _, rest = line.partition("/*")
                if "*/" in rest:
                    line = head + rest.split("*/", 1)[1]
                else:
                    in_comment, line = True, head
            code = re.sub(r"(^|\s)//.*$", "", line)    # a // comment (never the // of an address)
            for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', code) + re.findall(r"'((?:[^'\\]|\\.)*)'", code):
                if re.search(r"' \+ |\" \+ | \+ '| \+ \"", lit):
                    continue                             # the pieces between two strings joined with code
                if lit.strip() in ALLOWED:
                    continue
                # text between tags, with any markup and escapes taken out
                text = re.sub(r"<[^>]*>", " ", lit)
                text = re.sub(r"&\w+;|\\[nrt]", " ", text)
                plain = lit.strip()
                if "<" not in lit and re.fullmatch(r"[a-z0-9 _.\-\[\]=:#\"*>~+,]+", plain):
                    continue                             # class names, selectors, "use strict": not words for a person
                between = [w.strip() for w in re.findall(r">([^<]+)<", lit + "<")]
                if any(re.match(r"[A-Z][a-z]", w) and w not in ALLOWED for w in between):
                    hits.append("%s:%d: %s" % (os.path.basename(f), n, lit.strip()[:90]))   # a word between tags
                    continue
                if " " in plain or re.search(r">[^<]*[A-Za-z]{2,}", lit):
                    words = [w for w in re.findall(r"[A-Za-z][A-Za-z']+", text)]
                    if len(words) >= 2 and not re.search(r"[{}=;()]|\bvar\(|\bpx\b|^\s*[\w-]+\s*:", text):
                        hits.append("%s:%d: %s" % (os.path.basename(f), n, lit.strip()[:90]))
                elif re.fullmatch(r"[A-Z][a-z]+(?: [a-z]+)*[.!?]?", lit.strip()) and lit.strip() not in ALLOWED:
                    hits.append("%s:%d: %s" % (os.path.basename(f), n, lit.strip()[:90]))
    return hits


# single words that are not words for a person: names, codes, DOM and API vocabulary
ALLOWED = {"Enter", "Escape", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Bearer", "GET", "PUT", "POST",
           "DELETE", "PaperDaemon", "Content-Type", "Authorization", "Home", "End", "Backspace",
           "Files",                                  # the drag-and-drop type of dropped files (DataTransfer.types)
           "@echo off\\r\\n",                         # a new blank start script's first line: batch code
           # proper names, the same in every language: sites, and each language named in itself
           "Reddit", "Hacker News", "Bluesky", "Mastodon", "English", "Deutsch", "Cymraeg", "Español", "Português",
           "Français", "Anthropic", "OpenAI", "Brave Search", "Tavily", "Exa", "Serper"} | set(LANGUAGES.values())


ENGINE_PREFIXES = ("ts.row.", "ts.m.", "ts.d.", "issue.loop_")       # the engine sends these by name; the screen looks them up


def main():
    problems = []
    en = load("en") or {}
    names = {n: f for n, f in used_names().items() if not n.endswith((".", "_"))}     # "ts.row." + an id is a prefix
    for n, f in sorted(names.items()):
        if n not in en:
            problems.append("missing in English: %s (used in %s)" % (n, f))
    ph = lambda s: sorted(set(re.findall(r"\{(\w+)\}", s)))
    for code in LANGS[1:]:
        tr = load(code)
        if tr is None:
            problems.append("no strings-%s.xml" % code)
            continue
        for n in en:
            if n not in tr:
                problems.append("strings-%s.xml lacks %s" % (code, n))
            elif ph(tr[n]) != ph(en[n]) and not (n.endswith(".one") and ph(tr[n]) == [p for p in ph(en[n]) if p != "n"]):
                # (a language may say "one file" without the number)
                problems.append("strings-%s.xml: %s has placeholders %s, English %s" % (code, n, ph(tr[n]), ph(en[n])))
        for n in tr:
            if n not in en and not (re.search(r"\.(zero|two|few|many)$", n) and re.sub(r"\.\w+$", ".other", n) in en):
                problems.append("strings-%s.xml has %s, which English lacks" % (code, n))
    # a name passed around before it is looked up (a table of states, a dialog's parts) counts as used too, and so
    # does a count's .one/.other when the count's name appears
    # (the page editor is a page of its own, in a frame, and looks its words up through the window's PD.t)
    js = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(UI, "*.js")) + glob.glob(os.path.join(UI, "*.html")))
    quoted = set(re.findall(r"\"([\w.\-]+)\"", js))
    # names the ENGINE sends (the Test tab's rows, the loop's state): used when the engine's code quotes the part
    # after the prefix, or the whole name
    py = "".join(open(f, encoding="utf-8").read()
                 for f in glob.glob(os.path.join(ROOT, "paperdaemon", "**", "*.py"), recursive=True))
    engine = set(re.findall(r"[\"']([\w\-]+)[\"']", py))
    quoted |= set(re.findall(r"[\"'](ts\.[\w.\-]+)[\"']", py))
    quoted |= set(re.findall(r"i18n\.say\(\s*[\"']([\w.\-]+)[\"']", py))          # what the engine says itself
    quoted |= {n for n in en for pre in ENGINE_PREFIXES if n.startswith(pre) and n[len(pre):].split(".")[0] in engine}
    unused = sorted(n for n in set(en) - set(names) if n not in quoted and re.sub(r"\.(one|other)$", "", n) not in quoted)
    for n in unused:
        problems.append("in English but used nowhere: %s" % n)
    problems += ["text in the code, not in the strings: " + h for h in stray_text()]
    for p in problems:
        print(p)
    print("%d strings, %d problems" % (len(en), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
