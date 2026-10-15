"""Add or replace interface strings in ui/strings/strings-<code>.xml, keeping the file's order and escaping.

    uv run python tools/add_strings.py <code> <file.json>     # {"name": "text", ...}; "name": null removes one
"""
import json
import os
import sys
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRINGS = os.path.join(ROOT, "paperdaemon", "ui", "strings")
HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n<!-- PaperDaemon\'s interface text, %s. Names are '
        '"screen.thing"; {placeholders} are filled in by the window. -->\n<resources>\n')


def read(path):
    import xml.etree.ElementTree as ET
    if not os.path.exists(path):
        return {}
    return {s.get("name"): (s.text or "") for s in ET.parse(path).getroot().iter("string")}


def write(code, strings, language):
    path = os.path.join(STRINGS, "strings-%s.xml" % code)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEAD % language)
        for name, text in strings.items():
            f.write('  <string name="%s">%s</string>\n' % (name, escape(text)))
        f.write("</resources>\n")


def main(code, src):
    sys.path.insert(0, ROOT)
    from paperdaemon.settings import LANGUAGES
    os.makedirs(STRINGS, exist_ok=True)
    path = os.path.join(STRINGS, "strings-%s.xml" % code)
    have = read(path)
    for name, text in json.load(open(src, encoding="utf-8")).items():
        if text is None:
            have.pop(name, None)            # null: the string is gone
        else:
            have[name] = text
    write(code, have, LANGUAGES.get(code, code))
    print("%s: %d strings" % (os.path.basename(path), len(have)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
