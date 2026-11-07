"""A search's best pages are read for what bears on the question, so a write step has the facts and not just a line of
snippet each (web.readable: the page's prose, the paragraphs sharing the most of the question's words, in order)."""
from paperdaemon.pipeline.host.features import web as W

PAGE = """<html><head><title>Eclipse 2044</title><script>var x = "total solar eclipse everywhere";</script>
<style>p { color: red }</style></head><body>
<nav><a href="/">Home</a> <a href="/eclipses">All total solar eclipses</a></nav>
<header><h1>Upcoming eclipses</h1></header>
<article>
<p>The next total solar eclipse visible from the contiguous United States will take place on August 23, 2044.</p>
<p>Its path of totality crosses Montana, North Dakota and a corner of South Dakota after sunrise, then Canada.</p>
<p>Our shop sells eclipse glasses, posters and mugs in every size, shipped within two days.</p>
<p>The one after that, on August 12, 2045, crosses the country from California to Florida.</p>
</article>
<footer><p>Copyright 2026, all rights reserved, total solar eclipse news network.</p></footer>
</body></html>"""


def test_a_page_is_cut_to_what_bears_on_the_question():
    got = W.readable(PAGE, "next total solar eclipse lower 48 states path of totality")
    assert "August 23, 2044" in got and "Montana, North Dakota" in got
    assert "var x" not in got and "Home" not in got and "Copyright" not in got and "color: red" not in got
    assert got.index("2044") < got.index("Montana")                  # in the page's own order
    assert "mugs" not in got or got.index("mugs") > got.index("Montana")


def test_a_cap_and_pages_not_read():
    assert len(W.readable(PAGE, "total solar eclipse", cap=120)) <= 120
    assert W.readable("<p>short</p>", "eclipse") == ""
    assert not W._readable_url("https://en.wikipedia.org/wiki/Solar_eclipse_of_August_23,_2044")
    assert not W._readable_url("https://example.org/paper.pdf") and W._readable_url("https://example.org/eclipse")


def test_the_paragraph_with_the_facts_beats_the_ones_that_repeat_the_topic():
    # every paragraph of a page about eclipses says "total solar eclipse"; the one that answers says "lower 48" and
    # names the states -- the words that tell the paragraphs apart weigh the most
    generic = "".join("<p>A total solar eclipse is a sight: the total solar eclipse path of totality darkens the sky "
                      "for those in the path, and a total solar eclipse is rare (%d).</p>" % i for i in range(6))
    page = "<html><body><article>%s<p>The next total eclipse visible from the lower 48 states comes on Aug. 23, 2044, " \
           "over Montana, North Dakota and South Dakota.</p></article></body></html>" % generic
    got = W.readable(page, "next total solar eclipse visible from lower 48 states path of totality", cap=200)
    assert "Montana" in got and "2044" in got
