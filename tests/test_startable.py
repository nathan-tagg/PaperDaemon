import copy

from paperdaemon import settings


def _with(tags, location, script):
    s = settings.load()
    lu = copy.deepcopy(s["lineups"][0])
    lu["tags"] = [{"name": t} for t in tags]
    lu["text"] = dict(lu["text"], location=location, script=script, script_text="")
    s["lineups"] = [lu]
    return s


def test_the_daemon_starts_only_with_a_lineup_that_could_take_a_page():
    assert not settings.startable(_with([], "http://127.0.0.1:8080", "C:/start.bat"))         # no tag
    assert not settings.startable(_with(["claude"], "", ""))                                  # no model
    assert not settings.startable(_with(["claude"], "http://127.0.0.1:8080", ""))             # here, without its script
    assert settings.startable(_with(["claude"], "http://127.0.0.1:8080", "C:/start.bat"))
    assert settings.startable(_with(["claude"], "https://api.example.com", ""))              # elsewhere: no script needed
