"""An EPUB's chapters are read from the book's own contents and placed on its rendition's pages."""
import io
import zipfile

from paperdaemon.remarkable import chapters as C


class _Page:
    def __init__(self, text):
        self.text = text

    def get_textpage(self):
        return self

    def get_text_range(self):
        return self.text

    def close(self):
        pass


class _Pdf(list):
    """Stands in for the rendition: a list of pages with a text layer."""


def _book(nav=True):
    files = {
        "META-INF/container.xml": '<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
        "OPS/book.opf": ('<package><manifest>'
                         '<item id="cover" href="cover.xhtml"/>'
                         '<item id="c1" href="text/one.xhtml"/><item id="c2" href="text/two.xhtml"/>'
                         + ('<item id="nav" href="nav.xhtml" properties="nav"/>' if nav else
                            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
                         + '</manifest><spine><itemref idref="cover"/><itemref idref="c1"/><itemref idref="c2"/></spine></package>'),
        "OPS/cover.xhtml": '<html><body><img src="c.jpg"/></body></html>',
        "OPS/text/one.xhtml": '<html><body><h1>One</h1><p>T he storm came over the hills before dawn and nobody in the town was awake to see it '
                              + 'roll in across the dry fields</p>' + "<p>filler words here</p>" * 40 + '</body></html>',
        "OPS/text/two.xhtml": '<html><body><h1 id="t">Two</h1><p>Morning found the river high and brown and full of branches that had '
                              + 'come down from the north in the night</p>' + "<p>more filler words</p>" * 40 + '</body></html>',
    }
    if nav:
        files["OPS/nav.xhtml"] = ('<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>'
                                  '<li><a href="cover.xhtml">Cover</a></li>'
                                  '<li><a href="text/one.xhtml">Chapter One</a></li>'
                                  '<li><a href="text/two.xhtml#t">Chapter Two</a></li></ol></nav></body></html>')
    else:
        files["OPS/toc.ncx"] = ('<ncx><navMap>'
                                '<navPoint><navLabel><text>Chapter One</text></navLabel><content src="text/one.xhtml"/>'
                                '<navPoint><navLabel><text>A part</text></navLabel><content src="text/one.xhtml"/></navPoint></navPoint>'
                                '<navPoint><navLabel><text>Chapter Two</text></navLabel><content src="text/two.xhtml#t"/></navPoint>'
                                '</navMap></ncx>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


def test_nav_and_ncx_are_read_in_order():
    for nav in (True, False):
        toc, opf = C._epub_toc(io.BytesIO(_book(nav)))
        titles = [t for t, _lv, _h in toc]
        assert titles[-1] == "Chapter Two" and "Chapter One" in titles
        assert opf == "OPS/book.opf"
        assert dict((t, h) for t, _lv, h in toc)["Chapter Two"] == "OPS/text/two.xhtml#t"


def test_placed_by_their_own_words_not_a_contents_page():
    raw = _book(True)
    toc, opf = C._epub_toc(io.BytesIO(raw))
    z = zipfile.ZipFile(io.BytesIO(raw))
    pdf = _Pdf([_Page(""),                                                  # the cover: a picture
                _Page("Contents\nChapter One ........ 3\nChapter Two ........ 5"),  # names both, words of neither
                _Page("One\nThe storm came over the hills be-\nfore dawn and nobody in the town was awake"),
                _Page("filler words here " * 30),
                _Page("Two\nMorning found the river high and brown and full of branches"),
                _Page("more filler words " * 30)])
    got = C._place(toc, opf, pdf, z)
    assert [(t, i) for t, i, _lv in got] == [("Cover", 0), ("Chapter One", 2), ("Chapter Two", 4)]
