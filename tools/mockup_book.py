"""The tablet book: every mockup screen, in each state its controls reach, as one PDF in which every
control is a link to the page that shows what it does.

    uv run python tools/mockup_book.py [--out build/mockup]

It inlines the screens of docs/design/mockups into book.html, lets book.js lay out every state and page,
prints the result with headless Microsoft Edge, points each link straight at its page (tablets follow page
destinations more reliably than named ones), adds an outline, and checks that every link lands on a page
of the book. Nothing is sent anywhere, and the Edge profile it uses is deleted afterward."""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCKUPS = os.path.join(ROOT, "docs", "design", "mockups")
SCREENS = [("first-run", "First run"), ("overview", "Overview"), ("notepads", "Notepads"),
           ("decompose", "Decompose and send"), ("benchmark", "Benchmark"), ("tablet", "Tablet"),
           ("models", "Models"), ("search", "Search"), ("capabilities", "Capabilities"), ("network", "Network")]
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
TITLE = "PaperDaemon app mockup"


def screen(name):
    """A mockup's own styles and its body, without its scripts."""
    with open(os.path.join(MOCKUPS, name + ".html"), encoding="utf-8") as f:
        src = f.read()
    head, _, rest = src.partition("</head>")
    styles = "\n".join(re.findall(r"<style>(.*?)</style>", head, re.S))
    body = re.search(r"<body>(.*)</body>", rest, re.S).group(1)
    return styles, re.sub(r"<script\b.*?</script>", "", body, flags=re.S)


def write_book(out):
    rel = os.path.relpath(MOCKUPS, out).replace(os.sep, "/")
    styles, templates = [], []
    for name, title in SCREENS:
        css, body = screen(name)
        styles.append(css)
        templates.append('<template data-screen="%s" data-title="%s" data-file="%s.html">%s</template>'
                         % (name, html.escape(title), name, body))
    page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>%s</title>
<link rel="stylesheet" href="%s/paper.css">
<link rel="stylesheet" href="%s/book.css">
<style>
%s
</style>
<script>window.MOCKUP_BOOK = true;</script>
<script src="%s/mockup.js"></script>
<script src="%s/book.js" defer></script>
</head>
<body>
<div id="book"></div>
%s
</body>
</html>
""" % (TITLE, rel, rel, "\n".join(styles), rel, rel, "\n".join(templates))
    path = os.path.join(out, "book.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


def edge(args, url, timeout=900):
    exe = next((p for p in EDGE if os.path.exists(p)), None)
    if not exe:
        sys.exit("Microsoft Edge was not found")
    profile = tempfile.mkdtemp(prefix="paperdaemon-book-edge-")
    try:
        return subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                               "--allow-file-access-from-files", "--user-data-dir=" + profile,
                               "--disable-pdf-tagging", "--window-size=1160,1547", "--virtual-time-budget=240000", *args, url],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def book_map(url):
    """The map book.js leaves in the page: counts, the outline, and any control with nowhere to go."""
    dom = edge(["--dump-dom"], url).stdout
    m = re.search(r'<script type="application/json" id="bk-map">(.*?)</script>', dom, re.S)
    if not m:
        sys.exit("book.js did not finish; open build/mockup/book.html in Edge to see why")
    return json.loads(html.unescape(m.group(1)) if "&quot;" in m.group(1) else m.group(1))


def finish(raw, out_pdf, outline):
    """Named destinations become page destinations, the outline goes in, and every link is checked."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, NameObject

    reader = PdfReader(raw)
    index = {name: reader.get_destination_page_number(d) for name, d in reader.named_destinations.items()}
    writer = PdfWriter(clone_from=reader)
    links, bad = 0, []
    for n, page in enumerate(writer.pages):
        for ref in page.get("/Annots") or []:
            a = ref.get_object()
            if a.get("/Subtype") != "/Link":
                continue
            dest = a.get("/Dest")
            if dest is None and "/A" in a:
                act = a["/A"].get_object()
                dest = act.get("/D") if act.get("/S") == "/GoTo" else None
                if dest is None:
                    bad.append((n + 1, "an outside link: %s" % act.get("/URI")))
                    continue
            name = str(dest) if not isinstance(dest, ArrayObject) else None
            if name is not None and name not in index:
                bad.append((n + 1, "no page for %r" % name))
                continue
            target = index[name] if name is not None else None
            if target is not None:
                a[NameObject("/Dest")] = ArrayObject([writer.pages[target].indirect_reference, NameObject("/Fit")])
                if "/A" in a:
                    del a["/A"]
            links += 1
    root = writer._root_object
    for k in ("/Dests", "/Names", "/StructTreeRoot", "/MarkInfo"):      # the tablet needs no tag tree
        if k in root:
            del root[k]
    for page in writer.pages:
        if "/StructParents" in page:
            del page["/StructParents"]
        for ref in page.get("/Annots") or []:
            a = ref.get_object()
            if "/StructParent" in a:
                del a["/StructParent"]
    writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
    for item in outline:                                  # the PDF's names carry a leading slash
        at = index.get("/" + item["id"], index.get(item["id"]))
        if at is not None:
            writer.add_outline_item(item["title"], at)
    writer.add_metadata({"/Title": TITLE, "/Creator": "PaperDaemon mockups"})
    writer.page_mode = "/UseOutlines"
    with open(out_pdf, "wb") as f:
        writer.write(f)
    return len(writer.pages), links, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "mockup"))
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)                      # a relative --out made a broken file:/// address
    os.makedirs(a.out, exist_ok=True)
    url = "file:///" + write_book(a.out).replace(os.sep, "/")
    info = book_map(url)
    raw = os.path.join(a.out, "book-raw.pdf")
    edge(["--no-pdf-header-footer", "--print-to-pdf=" + raw], url)
    if not os.path.exists(raw):
        sys.exit("Edge printed nothing")
    out_pdf = os.path.join(a.out, TITLE + ".pdf")
    pages, links, bad = finish(raw, out_pdf, info["outline"])
    os.remove(raw)
    for s in info["screens"]:
        print("%-20s %3d states  %3d dialog and menu pages" % (s["title"], s["states"], s["overlays"]))
    print("%d pages, %d links, %d MB -> %s" % (pages, links, round(os.path.getsize(out_pdf) / 2 ** 20), out_pdf))
    for d in info["dead"][:40]:
        print("no target: %s | %s | %s" % (d["screen"], d["control"], d["state"][:80]))
    if len(info["dead"]) > 40:
        print("... and %d more with no target" % (len(info["dead"]) - 40))
    for p, why in bad[:20]:
        print("bad link on page %d: %s" % (p, why))
    if pages != info["pages"]:
        print("warning: book.js made %d pages, the PDF has %d" % (info["pages"], pages))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
