"""A document's chapters, as the tablet lists them: [{"title", "page", "level"}], `page` being the document's own
page (1-based), after any pages the user inserted or moved.

A PDF's chapters are its outline, or, when it has none, the links on its contents pages (links.contents). An EPUB's are the book's own table of contents (EPUB 3's nav page, else the
EPUB 2 NCX); the tablet shows an EPUB through a PDF rendition whose outline is empty, so each chapter is placed on
the first rendition page, at or after the previous chapter's, whose text carries the first words of the chapter
itself (found by following the entry's link into the book).
"""

import html
import posixpath
import os
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser


def _norm(s):
    """Words only, case-folded, ligatures and other compatibility forms spelled out."""
    s = unicodedata.normalize("NFKC", html.unescape(str(s or ""))).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", s).split())


def _page_text(s):
    """A rendition page's text with words that a line break hyphenated joined again."""
    return _norm(re.sub(r"(\w)[-­‐]\s*[\r\n]+\s*(\w)", r"\1\2", str(s or "")))


def _pdf_outline(pd):
    """[(title, pdf page index, level)] from the PDF's outline."""
    out = []
    for bm in pd.get_toc(max_depth=4):
        dest = bm.get_dest()
        idx = dest.get_index() if dest is not None else None
        if idx is not None:
            out.append(((bm.get_title() or "").strip() or "Untitled", int(idx), int(getattr(bm, "level", 0) or 0)))
    return out


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _join(from_file, href):
    """A link inside the book, resolved against the file it is written in -> "dir/file.xhtml#anchor" or None."""
    if not href:
        return None
    href = html.unescape(href)
    f, _, anchor = href.partition("#")
    f = posixpath.normpath(posixpath.join(posixpath.dirname(from_file), f)) if f else from_file
    return f + ("#" + anchor if anchor else "")


class _Text(HTMLParser):
    """A page's text, and where in it the element with id `anchor` begins."""

    def __init__(self, anchor):
        super().__init__(convert_charrefs=True)
        self.anchor, self.parts, self.at, self.skip = anchor, [], None, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        if self.anchor and self.at is None and dict(attrs).get("id") == self.anchor:
            self.at = len(self.parts)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _read(z, f, anchor=None):
    try:
        raw = z.read(f).decode("utf-8", "replace")
    except KeyError:
        return None
    t = _Text(anchor)
    t.feed(raw)
    return t


def _spine(z, opf_path):
    """The book's files in reading order, each with the number of words in it -> [(file, words)]."""
    opf = ET.fromstring(z.read(opf_path))
    base = posixpath.dirname(opf_path)
    items = {e.get("id"): posixpath.normpath(posixpath.join(base, e.get("href") or "")) for e in opf.iter() if _local(e.tag) == "item"}
    out = []
    for e in opf.iter():
        if _local(e.tag) == "itemref" and e.get("idref") in items:
            t = _read(z, items[e.get("idref")])
            out.append((items[e.get("idref")], len(_norm(" ".join(t.parts)).split()) if t else 0))
    return out


def _target(z, href, spine, n):
    """Where `href` leads: (the first `n` words of the text from there, normalized; how far into the book that is,
    0..1, by words)."""
    f, _, anchor = href.partition("#")
    t = _read(z, f, anchor or None)
    if t is None:
        return [], None
    start = t.at if (anchor and t.at is not None) else 0
    words = _norm(" ".join(t.parts[start:])).split()
    before = len(_norm(" ".join(t.parts[:start])).split())
    total = sum(w for _f, w in spine) or 1
    done = 0
    for name, w in spine:
        if name == f:
            return words[:n], (done + before) / float(total)
        done += w
    return words[:n], None


def _epub_toc(path):
    """([(title, level, href)], the package file's path) from an EPUB's table of contents, in reading order; href
    is the entry's target (a file inside the book, with its #anchor) resolved against the book's root."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        container = ET.fromstring(z.read("META-INF/container.xml"))
        opf_path = next(e.get("full-path") for e in container.iter() if _local(e.tag) == "rootfile")
        opf = ET.fromstring(z.read(opf_path))
        base = posixpath.dirname(opf_path)
        items = [e for e in opf.iter() if _local(e.tag) == "item"]
        nav = next((e for e in items if "nav" in (e.get("properties") or "").split()), None)
        ncx = next((e for e in items if e.get("media-type") == "application/x-dtbncx+xml"), None)
        out = []
        if nav is not None:
            p = posixpath.normpath(posixpath.join(base, nav.get("href")))
            if p in names:
                root = ET.fromstring(z.read(p))
                for el in root.iter():
                    if _local(el.tag) == "nav" and "toc" in (el.get("{http://www.idpf.org/2007/ops}type") or el.get("epub:type") or "toc"):
                        def walk(ol, level):
                            for li in ol:
                                if _local(li.tag) != "li":
                                    continue
                                a = next((x for x in li if _local(x.tag) in ("a", "span")), None)
                                if a is not None:
                                    out.append(("".join(a.itertext()).strip(), level, _join(p, a.get("href"))))
                                for sub in li:
                                    if _local(sub.tag) == "ol":
                                        walk(sub, level + 1)
                        for ol in el:
                            if _local(ol.tag) == "ol":
                                walk(ol, 0)
                        break
        if not out and ncx is not None:
            p = posixpath.normpath(posixpath.join(base, ncx.get("href")))
            if p in names:
                root = ET.fromstring(z.read(p))
                navmap = next((e for e in root.iter() if _local(e.tag) == "navMap"), None)

                def walk(node, level):
                    for np_ in node:
                        if _local(np_.tag) != "navPoint":
                            continue
                        label = next((e for e in np_.iter() if _local(e.tag) == "text"), None)
                        content = next((e for e in np_ if _local(e.tag) == "content"), None)
                        if label is not None and (label.text or "").strip():
                            out.append((label.text.strip(), level, _join(p, content.get("src") if content is not None else None)))
                        walk(np_, level + 1)
                if navmap is not None:
                    walk(navmap, 0)
        return [(t, lv, h) for t, lv, h in out if t], opf_path


def _place(toc, opf_path, pd, z):
    """Each chapter on a rendition page that carries the first words of the chapter's own text (where its link
    leads: its heading and what follows it, which a printed contents page does not have), or its title when the
    link leads nowhere readable. Of the pages that do, the one nearest where the chapter sits by its share of the
    book's words. A chapter found nowhere is left out. -> [(title, pdf page index, level)] in reading order."""
    texts = []
    for i in range(len(pd)):
        page = pd[i]
        tp = page.get_textpage()
        try:
            texts.append(_page_text(tp.get_text_range()))
        finally:
            tp.close()
            page.close()
    spine = _spine(z, opf_path)
    n = len(texts)
    out = []
    reach = max(15, n // 6)                  # how far from its share of the book a chapter may sit
    for title, level, href in toc:
        words, share = _target(z, href, spine, 24) if href else ([], None)
        guess = share * n if share is not None else (out[-1][1] if out else 0)
        if href and share is not None and not words:
            # a page with no text (a cover, a picture): by its share of the book's words, but never before its
            # place among the book's files -- each file begins a page of its own, and front matter has no words
            f = href.partition("#")[0]
            at = next((i for i, (name, _w) in enumerate(spine) if name == f), 0)
            out.append((title, min(n - 1, max(int(guess), at)), level))
            continue
        # runs of the chapter's opening words; the later ones start past a drop cap, which the book's text splits
        # from its word ("m ost")
        tries = [" ".join(words[s:s + k]) for s in (0, 1, 2, 3, 5, 8) for k in (12, 8) if len(words) >= s + k]
        tries = tries or [_norm(title)]
        hit = None
        for want in tries:
            if not want:
                continue
            hits = [i for i in range(n) if want in texts[i] and abs(i - guess) <= reach]
            if hits:
                hit = min(hits, key=lambda i: (abs(i - guess), i))
                break
        if hit is not None:
            out.append((title, hit, level))
    return out


def of(mirror, doc, live):
    """The chapters of document `doc` in `mirror`, whose shown pages are `live` (sync.live_pages)."""
    import os
    import pypdfium2
    where = {}
    for i, pg in enumerate(live):
        idx = (pg.get("redir") or {}).get("value")
        if idx is not None:
            where.setdefault(int(idx), i + 1)
    pdf = os.path.join(mirror, doc + ".pdf")
    epub = os.path.join(mirror, doc + ".epub")
    if not os.path.isfile(pdf):
        # a book PaperDaemon lays out itself: its layout knows the page every link of the contents lands on
        if not os.path.isfile(epub):
            return []
        try:
            from paperdaemon.remarkable import books
            import json as _json
            try:
                with open(os.path.join(mirror, doc + ".content"), encoding="utf-8") as f:
                    content = _json.load(f)
            except (OSError, ValueError):
                content = {}
            _laid, index = books.lay_out(epub, books.settings_of(content))
            toc, _opf = _epub_toc(epub)
        except Exception:
            return []
        anchors = index.get("anchors") or {}
        out = []
        for title, level, href in toc:
            at = anchors.get(href) if href else None
            if at is None and href:
                at = anchors.get(href.partition("#")[0])
            if at is not None and int(at) in where:
                out.append({"title": title, "page": where[int(at)], "level": level})
        return out
    from paperdaemon.pdflock import LOCK
    with LOCK:                                       # PDFium is not safe on two threads at once
        pd = pypdfium2.PdfDocument(pdf)
        try:
            found = _pdf_outline(pd)
            if not found and os.path.isfile(epub):
                try:
                    with zipfile.ZipFile(epub) as z:
                        toc, opf_path = _epub_toc(epub)
                        found = _place(toc, opf_path, pd, z)
                except (KeyError, StopIteration, ET.ParseError, zipfile.BadZipFile):
                    found = []
            if not found:                            # no outline: the links on its contents pages (links.py)
                from paperdaemon.remarkable import links
                found = links.contents(pd)
        finally:
            pd.close()
    return [{"title": t, "page": where[i], "level": lv} for t, i, lv in found if i in where]


_MEMO = {}


def _stamp(mirror, doc):
    """What a document's chapters depend on: its content (the pages and their order) and its PDF and EPUB files."""
    parts = []
    for ext in (".content", ".pdf", ".epub"):
        try:
            st = os.stat(os.path.join(mirror, doc + ext))
            parts.append("%d.%d" % (st.st_size, st.st_mtime_ns))
        except OSError:
            parts.append("-")
    return "|".join(parts)


def cached(mirror, doc):
    """The document's chapters, worked out ONCE and kept on disk (<data>/cache/chapters): a big book's take seconds
    (a book of over ten thousand pages, about 40 s), so they are never worked out again until the book changes."""
    import json
    from paperdaemon import paths
    from paperdaemon.remarkable.sync import live_pages
    stamp = _stamp(mirror, doc)
    hit = _MEMO.get(doc)
    if hit and hit[0] == stamp:
        return hit[1]
    path = os.path.join(paths.cache_dir("chapters"), doc + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("stamp") == stamp:
            _MEMO[doc] = (stamp, saved["chapters"])
            return saved["chapters"]
    except (OSError, ValueError, KeyError):
        pass
    with open(os.path.join(mirror, doc + ".content"), encoding="utf-8") as f:
        got = of(mirror, doc, live_pages(json.load(f)))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"stamp": stamp, "chapters": got}, f)
    os.replace(tmp, path)
    _MEMO[doc] = (stamp, got)
    return got
