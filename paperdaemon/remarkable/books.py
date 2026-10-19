"""BOOKS, READ AS THE TABLET READS THEM. The tablet's software lays an EPUB out with Qt's own text engine: each spine
item in a QTextDocument on the book page, the book's CSS rewritten its way, its faces loaded and kept, and the pages
painted by Qt into the PDF it uploads beside the book. PaperDaemon does the same with the same Qt (PySide6, pinned to
the tablet's version), so a book's pages here are the tablet's pages. Measured against the tablet's own PDFs of five
test books: the same pages and every glyph where the tablet put it, except the weight-700 kerning inside bold words and
a book that names a face it does not carry after other books brought faces (openspec add-epub-reading, design.md).

Qt's GUI layer wants a process of its own, so a book is laid out in a child process (`layout`, run by `main`): it
writes the pages as a PDF and an index (pages, where each chapter and anchor falls) into PaperDaemon's cache, never
into a mirror. `rendition(doc)` is what the rest of PaperDaemon calls; it lays the book out once per book, settings and
faces, and returns the cached files.

THE FACES. A page is drawn as its own library shows it. With the tablet's faces (borrowed from the desktop app while an
account is signed in): EB Garamond as the app builds it, reMarkable Sans. With PaperDaemon's own: the published EB
Garamond, and Noto Sans where reMarkable Sans is named. Noto Sans, Noto Sans Mono and Noto Sans Hebrew are the tablet's
own versions in both, shipped with PaperDaemon (OFL). RM_FACES ("tablet" or "own") says which; the false mirror's
processes are told by the engine, the real mirror's use the tablet's when they are here.
"""

import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import urllib.parse
import zipfile

from .. import paths

W, H = 1404, 1872                   # the book page, whatever the tablet
PDF_PT = (445, 594)                 # the tablet's PDF page: 1404 x 1872 at 227 dpi
BASE = 38                           # the body size at text scale 1
MARGINS = 125                       # the tablet's default margins
PICTURE_SLACK = 15                  # a picture is at most the text height less this (measured once: 1607 of 1622)
SHEET = "p { line-height: %s } h1, h2, h3 { margin-top: 2em; margin-bottom: 1em } code {font-family: 'Noto Sans Mono'}"
MONO = {"monospace", "courier", "courier new", "consolas", "menlo", "monaco", "lucida console", "noto sans mono",
        "dejavu sans mono", "liberation mono", "andale mono"}
# the tablet's font matching takes these to its serif choice: Noto Sans Hebrew on a tablet with only its own faces
SERIF = {"serif", "times", "times new roman", "georgia", "palatino", "palatino linotype", "book antiqua",
         "liberation serif", "dejavu serif", "nimbus roman", "tinos", "cambria", "garamond", "baskerville"}
VERSION = 1                         # of the layout: a change here lays every book out again


# ------------------------------------------------------------------------------------------------ faces

def _shipped(*parts):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content", "book-fonts", *parts)


def borrowed():
    """The tablet's faces taken from the desktop app, or None: {'ebg': [regular, italic], 'rms': path}."""
    d = paths.fonts_dir()
    ebg = [os.path.join(d, n) for n in ("EBGaramond-Regular.ttf", "EBGaramond-Italic.ttf")]
    rms = os.path.join(d, "reMarkableSans-Regular.ttf")
    if all(os.path.isfile(p) for p in ebg) and os.path.isfile(rms):
        return {"ebg": ebg, "rms": rms}
    return None


def mode():
    """'tablet' or 'own': the faces pages are set in here."""
    m = os.environ.get("RM_FACES")
    if m in ("tablet", "own"):
        return m if (m == "own" or borrowed()) else "own"
    return "tablet" if borrowed() else "own"


def false_mirror_faces(s=None):
    """The faces the false mirror is set in, as the engine decides it for the false mirror's processes: the tablet's only
    with an account signed in, the desktop app's faces taken, and the false mirror's setting not PaperDaemon's own."""
    from .. import settings as S
    from . import auth
    s = s or S.load()
    if (s.get("false_mirror") or {}).get("faces") == "own" or not borrowed():
        return "own"
    try:
        return "tablet" if auth.describe().get("set") else "own"
    except Exception:
        return "own"


def store():
    """The folder where the faces books bring are kept: the false mirror's own (the tablet keeps them too), or None."""
    return os.path.join(paths.false_mirror_state_dir(), "fonts") if paths.local_only() else None


# ------------------------------------------------------------------------------------------------ the book

def _decode(data):
    m = re.match(rb"\s*<\?xml[^>]*encoding=[\"']([A-Za-z0-9_.-]+)", data)
    for enc in ((m.group(1).decode(),) if m else ()) + ("utf-8", "cp1252"):
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", "replace")


def _join(base_dir, href):
    href = urllib.parse.unquote(href.split("#")[0])
    return posixpath.normpath(posixpath.join(base_dir, href)).lstrip("/")


def spine(z):
    """The book's reading order: its spine's files, as paths in the zip."""
    c = _decode(z.read("META-INF/container.xml"))
    opf = re.search(r"<rootfile\b[^>]*full-path=[\"']([^\"']+)", c).group(1)
    o = _decode(z.read(opf))
    items = {}
    for tag in re.findall(r"<(?:\w+:)?item\b[^>]*>", o):
        i = re.search(r"\bid=[\"']([^\"']+)", tag)
        h = re.search(r"\bhref=[\"']([^\"']+)", tag)
        if i and h:
            items[i.group(1)] = h.group(1)
    base = posixpath.dirname(opf)
    names = set(z.namelist())
    out = []
    for i in re.findall(r"<(?:\w+:)?itemref\b[^>]*\bidref=[\"']([^\"']+)", o):
        if i in items:
            p = _join(base, items[i])
            if p in names:
                out.append(p)
    return out


def _qt(fontdir, app_family):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QPA_FONTDIR"] = fontdir          # Qt sees these faces and no others: never the computer's
    from PySide6.QtGui import QGuiApplication, QFont
    app = QGuiApplication.instance() or QGuiApplication(["paperdaemon-books"])
    f = QFont(app_family)
    f.setPixelSize(16)                              # the tablet's application font: Qt sizes the default sheet's em by it
    app.setFont(f)
    return app


class Book:
    def __init__(self, path, keep=None):
        self.z = zipfile.ZipFile(path)
        self.keep = keep                            # a folder the faces this book brings are kept in, or None
        self.alias = {}
        self.base = BASE
        self._faces()

    def _faces(self):
        """Every @font-face of the book's CSS is loaded (and kept: the tablet keeps them for every later book)."""
        from PySide6.QtCore import QByteArray
        from PySide6.QtGui import QFontDatabase
        for name in self.z.namelist():
            if not name.lower().endswith(".css"):
                continue
            css = _decode(self.z.read(name))
            for block in re.findall(r"@font-face\s*{([^}]+)}", css):
                fam = re.search(r"font-family\s*:\s*([^;]+)", block)
                src = re.search(r"url\s*\(([^)]+)\)", block)
                if not fam or not src:
                    continue
                try:
                    data = self.z.read(_join(posixpath.dirname(name), src.group(1).strip("'\" ")))
                except KeyError:
                    continue
                fid = QFontDatabase.addApplicationFontFromData(QByteArray(data))
                fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                if not fams:
                    continue
                self.alias[fam.group(1).strip().strip("'\"").lower()] = fams[0]
                if self.keep:
                    os.makedirs(self.keep, exist_ok=True)
                    kept = os.path.join(self.keep, hashlib.sha256(data).hexdigest()[:20] + ".font")
                    if not os.path.exists(kept):
                        with open(kept + ".part", "wb") as f:
                            f.write(data)
                        os.replace(kept + ".part", kept)

    def family(self, value):
        """A CSS font-family list as the tablet resolves it: a face the book carries, else one the tablet has, else its
        fallbacks (monospace names to Noto Sans Mono, serif names to Noto Sans Hebrew, the rest to Noto Sans)."""
        from PySide6.QtGui import QFontDatabase
        known = {f.lower(): f for f in QFontDatabase.families()}
        mono = serif = False
        for raw in value.split(","):
            low = raw.strip().strip("'\"").strip().lower()
            if low in self.alias:
                return self.alias[low]
            if low in known:
                return known[low]
            mono = mono or low in MONO
            serif = serif or low in SERIF
        return "Noto Sans Mono" if mono else "Noto Sans Hebrew" if serif else "Noto Sans"

    def css(self, text):
        """reMarkable's rewrite of the book's own CSS."""
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"@font-face\s*{[^}]*}", "", text)
        text = re.sub(r"(font-family\s*:\s*)([^;}\n]+)", lambda m: "%s'%s'" % (m.group(1), self.family(m.group(2))), text)

        def lines(m):                               # the reader's line spacing governs body text, not headings
            sel, body = m.group(1), m.group(2)
            if sel.strip() and all(re.fullmatch(r"\s*h[1-6][^,]*", part) for part in sel.split(",")):
                return m.group(0)
            return sel + "{" + re.sub(r"line-height\s*:[^;}]*;?", "", body) + "}"
        if "{" in text:
            text = re.sub(r"([^{}]*)\{([^{}]*)\}", lines, text)
        else:                                       # an inline style="" is body text
            text = re.sub(r"line-height\s*:[^;}]*;?", "", text)
        text = re.sub(r"text-align\s*:\s*(left|justify|start)\s*;?", "", text)
        base = self.base                            # 1em = 1rem = 12pt = 100% = the body size
        unit = lambda m: "%gpx" % round(float(m.group(1)) * base * {"em": 1, "rem": 1, "pt": 1 / 12.0}[m.group(2)], 3)
        text = re.sub(r"(?<=[:\s\-])(\d*\.?\d+)(em|rem|pt)(?=;|\s|\}|$)", unit, text)
        return re.sub(r"(font-size\s*:\s*)(\d*\.?\d+)%",
                      lambda m: "%s%gpx" % (m.group(1), int(float(m.group(2)) * base / 100)), text)

    def chapter(self, path, scale=1.0, line_height=100, margins=MARGINS, align="justify"):
        from PySide6.QtCore import QByteArray, QSizeF, Qt
        from PySide6.QtGui import QFont, QImage, QTextCharFormat, QTextCursor, QTextDocument
        book, folder = self, posixpath.dirname(path)

        class Fragment(QTextDocument):
            def loadResource(self, kind, url):
                try:
                    data = book.z.read(_join(folder, url.toString()))
                except KeyError:
                    return super().loadResource(kind, url)
                if kind == QTextDocument.ResourceType.StyleSheetResource:
                    return book.css(_decode(data))
                if kind == QTextDocument.ResourceType.ImageResource:
                    img = QImage()
                    img.loadFromData(data)
                    return img
                return QByteArray(data)

        self.base = round(BASE * scale)
        d = Fragment()
        f = QFont("EB Garamond")
        f.setPixelSize(self.base)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        d.setUseDesignMetrics(True)
        o = d.defaultTextOption()
        o.setAlignment(Qt.AlignmentFlag.AlignJustify if align == "justify" else Qt.AlignmentFlag.AlignLeft)
        d.setDefaultTextOption(o)
        d.setDefaultFont(f)
        d.setDocumentMargin(margins)
        d.setDefaultStyleSheet(SHEET % ("%d%%" % line_height))
        d.setPageSize(QSizeF(W, H))
        html = _decode(self.z.read(path))
        html = re.sub(r"(<style[^>]*>)(.*?)(</style>)", lambda m: m.group(1) + self.css(m.group(2)) + m.group(3), html,
                      flags=re.S | re.I)
        html = re.sub(r"(\bstyle=)([\"'])(.*?)\2", lambda m: m.group(1) + m.group(2) + self.css(m.group(3)) + m.group(2),
                      html, flags=re.S)
        d.setHtml(html)

        def fragments():
            blk = d.begin()
            while blk.isValid():
                it = blk.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid():
                        yield frag
                    it += 1
                blk = blk.next()

        def merge(frag, fmt):
            c = QTextCursor(d)
            c.setPosition(frag.position())
            c.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
            c.mergeCharFormat(fmt)

        tw, th = W - 2 * margins, H - 2 * margins - PICTURE_SLACK
        for frag in list(fragments()):
            cf = frag.charFormat()
            if (cf.fontFamilies() or [None])[0] == "monospace":
                # Qt's own <pre>, <tt>, <kbd>, <samp>: on the tablet the family "monospace" lands on Noto Sans
                fx = QTextCharFormat()
                fx.setFontFamilies(["Noto Sans"])
                merge(frag, fx)
            if cf.isImageFormat():
                # a picture is set to the text width, never taller than the page holds
                imf = cf.toImageFormat()
                img = d.resource(QTextDocument.ResourceType.ImageResource, imf.name())
                if isinstance(img, QImage) and not img.isNull() and img.width() and img.height():
                    w, h = tw, round(img.height() * tw / img.width())
                    if h > th:
                        h, w = th, round(img.width() * th / img.height())
                    imf.setWidth(w)
                    imf.setHeight(h)
                    c = QTextCursor(d)
                    c.setPosition(frag.position())
                    c.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                    c.setCharFormat(imf)
        for frag in list(fragments()):
            if frag.charFormat().font().family() == "reMarkable Sans":
                fx = QTextCharFormat()                  # the tablet hints its UI face to whole pixels; others unhinted
                fx.setFontHintingPreference(QFont.HintingPreference.PreferFullHinting)
                merge(frag, fx)
        d.setPageSize(QSizeF(W, H))
        return d

    def anchors(self, d):
        """{anchor name: 0-based page within the chapter}."""
        lo = d.documentLayout()
        out = {}
        blk = d.begin()
        while blk.isValid():
            y = lo.blockBoundingRect(blk).y()
            it = blk.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    for name in frag.charFormat().anchorNames():
                        out.setdefault(name, int(max(0.0, y) // H))
                it += 1
            blk = blk.next()
        return out


def layout(epub, out_pdf, out_index, scale=1.0, margins=MARGINS, line_height=100, align="justify", faces="tablet",
           keep=None):
    """Lay a book out (in this process, which becomes a Qt process): the pages into `out_pdf`, the index into
    `out_index`. -> the index."""
    import shutil
    import tempfile
    fontdir = tempfile.mkdtemp(prefix="pd-faces-")
    try:
        for n in ("NotoSans-Regular.ttf", "NotoSansMono-Regular.ttf", "NotoSansHebrew-Regular.ttf"):
            shutil.copy(_shipped("noto", n), fontdir)
        lent = borrowed() if faces == "tablet" else None
        ebg = lent["ebg"] if lent else [_shipped("eb-garamond", n) for n in ("EBGaramond-Regular.ttf", "EBGaramond-Italic.ttf")]
        for p in ebg:
            shutil.copy(p, fontdir)
        if lent:
            shutil.copy(lent["rms"], fontdir)
        app = _qt(fontdir, "reMarkable Sans" if lent else "Noto Sans")
        from PySide6.QtCore import QByteArray, QMarginsF, QRectF, QSizeF
        from PySide6.QtGui import QFontDatabase, QPageSize, QPainter, QPdfWriter
        if keep and os.path.isdir(keep):                # faces earlier books brought, as the tablet keeps them
            for n in sorted(os.listdir(keep)):
                if n.endswith(".font"):
                    with open(os.path.join(keep, n), "rb") as f:
                        QFontDatabase.addApplicationFontFromData(QByteArray(f.read()))
        book = Book(epub, keep=keep)
        w = QPdfWriter(out_pdf + ".part")
        w.setResolution(227)
        w.setPageSize(QPageSize(QSizeF(*PDF_PT), QPageSize.Unit.Point))
        w.setPageMargins(QMarginsF(0, 0, 0, 0))
        w.setCreator("PaperDaemon")
        p = QPainter(w)
        index = {"version": VERSION, "faces": "tablet" if lent else "own", "chapters": [], "anchors": {}}
        page = 0
        for path in spine(book.z):
            d = book.chapter(path, scale=scale, line_height=line_height, margins=margins, align=align)
            n = d.pageCount()
            index["chapters"].append({"path": path, "first": page, "pages": n})
            index["anchors"][path] = page
            for name, at in book.anchors(d).items():
                index["anchors"]["%s#%s" % (path, name)] = page + at
            for i in range(n):
                if page:
                    w.newPage()
                p.save()
                p.translate(0, -i * H)
                d.drawContents(p, QRectF(0, i * H, W, H))
                p.restore()
                page += 1
        if page:
            w.newPage()                                 # the tablet ends every book with a blank page
        page += 1
        p.end()
        del app
        index["pages"] = page
        os.replace(out_pdf + ".part", out_pdf)
        paths.write_json_atomic(out_index, index)
        return index
    finally:
        shutil.rmtree(fontdir, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ for PaperDaemon

def _command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--books"]
    return [sys.executable, "-m", "paperdaemon.remarkable.books"]


def settings_of(content):
    """The reading settings a book is laid out with, from its .content (the tablet's defaults where it has none)."""
    c = content or {}
    lh = c.get("lineHeight")
    return {"scale": float(c.get("textScale") or 1), "margins": int(c.get("margins") or MARGINS),
            "line_height": 100 if lh in (None, -1) else int(lh),
            "align": "left" if c.get("textAlignment") == "left" else "justify"}


def lay_out(epub, settings=None, faces=None):
    """The book laid out (once: cached by the book, its settings and the faces). -> (pdf path, index) or raises."""
    s = dict(settings_of(None), **(settings or {}))
    faces = faces or mode()
    keep = store()
    st = os.stat(epub)
    kept = sorted(os.listdir(keep)) if keep and os.path.isdir(keep) else []
    key = hashlib.sha256(json.dumps([VERSION, os.path.abspath(epub), st.st_size, st.st_mtime_ns, s, faces, kept],
                                    sort_keys=True).encode()).hexdigest()[:24]
    folder = os.path.join(paths.data_dir(), "cache", "books", key)
    pdf, idx = os.path.join(folder, "book.pdf"), os.path.join(folder, "index.json")
    if not (os.path.isfile(pdf) and os.path.isfile(idx)):
        os.makedirs(folder, exist_ok=True)
        cmd = _command() + [epub, pdf, idx, "--scale", str(s["scale"]), "--margins", str(s["margins"]),
                            "--line-height", str(s["line_height"]), "--align", s["align"], "--faces", faces]
        if keep:
            cmd += ["--keep", keep]
        kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
        if r.returncode or not os.path.isfile(pdf):
            raise RuntimeError("the book could not be laid out: %s" % r.stdout.decode("utf-8", "replace")[-400:])
    with open(idx, encoding="utf-8") as f:
        return pdf, json.load(f)


def rendition(doc, mirror=None):
    """The pages a book of the mirror is drawn from: the tablet's PDF when it has sent one (never in the false mirror,
    which converts nothing of its own: a PDF there came from the tablet), else PaperDaemon's layout. -> path or None."""
    mirror = mirror or os.environ.get("RM_MIRROR") or paths.mirror_dir()
    pdf = os.path.join(mirror, doc + ".pdf")
    if os.path.isfile(pdf):
        return pdf
    epub = os.path.join(mirror, doc + ".epub")
    if not os.path.isfile(epub):
        return None
    try:
        with open(os.path.join(mirror, doc + ".content"), encoding="utf-8") as f:
            content = json.load(f)
    except (OSError, ValueError):
        content = {}
    return lay_out(epub, settings_of(content))[0]


def main(argv=None):
    import argparse
    a = argparse.ArgumentParser(prog="paperdaemon-books")
    a.add_argument("epub")
    a.add_argument("pdf")
    a.add_argument("index")
    a.add_argument("--scale", type=float, default=1.0)
    a.add_argument("--margins", type=int, default=MARGINS)
    a.add_argument("--line-height", type=int, default=100)
    a.add_argument("--align", default="justify")
    a.add_argument("--faces", default="tablet")
    a.add_argument("--keep")
    o = a.parse_args(argv)
    layout(o.epub, o.pdf, o.index, scale=o.scale, margins=o.margins, line_height=o.line_height, align=o.align,
           faces=o.faces, keep=o.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
