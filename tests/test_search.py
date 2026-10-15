"""Web search is part of a lineup: none, a search service with an API key, or a search server hosted locally."""
import pytest

from paperdaemon import search, settings, vault


def _lineup_search(sr):
    s = settings.load()
    s["lineups"][0]["search"] = dict(settings.search_defaults(), **sr)
    s["lineup"] = s["lineups"][0]["name"]
    return s


def test_an_earlier_searxng_setting_reads_as_local():
    lu = settings.normalize_lineup({"name": "x", "search": {"kind": "searxng", "url": "http://127.0.0.1:8888"}})
    assert lu["search"] == {"kind": "local", "provider": "", "url": "http://127.0.0.1:8888", "script_text": ""}
    assert settings.normalize_lineup({"name": "y"})["search"]["kind"] == "none"


def test_a_lineups_search_is_checked():
    assert settings.check_search({"kind": "api", "provider": "bing"}, "L")
    assert settings.check_search({"kind": "local", "url": "127.0.0.1"}, "L")
    assert not settings.check_search({"kind": "api", "provider": "exa"}, "L")
    assert not settings.check_search({"kind": "local", "url": "http://127.0.0.1:8888"}, "L")


@pytest.mark.parametrize("provider, answer, how", [
    ("brave", {"web": {"results": [{"title": "T", "url": "U", "description": "D"}]}}, "_get"),
    ("tavily", {"results": [{"title": "T", "url": "U", "content": "D"}]}, "_post"),
    ("exa", {"results": [{"title": "T", "url": "U", "text": "D"}]}, "_post"),
    ("serper", {"organic": [{"title": "T", "link": "U", "snippet": "D"}]}, "_post"),
])
def test_each_service_answers_in_one_shape(monkeypatch, provider, answer, how):
    vault.put(vault.key_name("search", provider), "k")
    monkeypatch.setattr(search, how, lambda *a, **k: answer)
    got = search.query("q", s=_lineup_search({"kind": "api", "provider": provider}))
    assert got == {"results": [{"title": "T", "url": "U", "content": "D"}]}


def test_no_key_or_no_search_says_so():
    with pytest.raises(search.SearchError, match="no API key"):
        search.query("q", s=_lineup_search({"kind": "api", "provider": "brave"}))
    with pytest.raises(search.SearchError, match="no web search"):
        search.query("q", s=_lineup_search({"kind": "none"}))


def test_only_searxngs_shape_counts_as_a_search_server(monkeypatch):
    from paperdaemon import search
    assert search.searxng_shape({"results": [{"url": "https://a", "title": "A"}], "query": "x"})
    assert search.searxng_shape({"results": []})
    for bad in ({}, {"results": "x"}, {"results": [{"title": "no url"}]}, [], "<html>"):
        assert not search.searxng_shape(bad)
    sr = {"kind": "local", "url": "http://127.0.0.1:8888"}
    monkeypatch.setattr(search, "_get", lambda url, headers=None: {"status": "ok"})   # something else on the port
    assert not search._answering(sr)
    monkeypatch.setattr(search, "_get", lambda url, headers=None: {"results": []})
    assert search._answering(sr)
