"""What the window keeps for itself between starts lives on the engine (ui_memory.py, GET/PUT /ui/memory): the web
view's own storage does not survive a restart in every install (its store dropped the tail of its log at each restart
on the maintainer's machine, 2026-11-09, so the window came back on the Overview after every update)."""
import json
import os

from fastapi.testclient import TestClient

from paperdaemon import server, ui_memory


def _home(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPERDAEMON_HOME", str(tmp_path))
    return str(tmp_path)


def test_remembered_things_are_kept_in_one_small_file(monkeypatch, tmp_path):
    home = _home(monkeypatch, tmp_path)
    assert ui_memory.load() == {}
    got = ui_memory.remember({"last-screen": "fmirror", "last-at:fmirror": "the-dogfood-folder",
                              "decomps-per": 50, "prefs-note-seen": True})
    assert got["last-screen"] == "fmirror" and got["decomps-per"] == 50 and got["prefs-note-seen"] is True
    assert json.load(open(os.path.join(home, "ui-memory.json"), encoding="utf-8")) == got
    assert "last-at:fmirror" not in ui_memory.remember({"last-at:fmirror": None})       # null forgets one
    assert ui_memory.load()["last-screen"] == "fmirror"                      # read back from the file


def test_bad_names_and_values_are_refused_and_nothing_is_written(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    ui_memory.remember({"last-screen": "tablet"})
    for bad in ({"Last Screen": "x"}, {"a": "x" * 201}, {"a": {"nested": 1}}, {"a": ["list"]}, ["not", "a", "dict"]):
        try:
            ui_memory.remember(bad)
            raise AssertionError("accepted %r" % (bad,))
        except ValueError:
            pass
    assert ui_memory.load() == {"last-screen": "tablet"}


def test_the_window_reads_and_writes_it_through_the_api(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    assert c.get("/api/v1/ui/memory").json() == {}
    r = c.put("/api/v1/ui/memory", json={"last-screen": "fmirror", "last-at:fmirror": "abc"})
    assert r.status_code == 200 and r.json() == {"last-screen": "fmirror", "last-at:fmirror": "abc"}
    assert c.put("/api/v1/ui/memory", json={"last-at:fmirror": None}).json() == {"last-screen": "fmirror"}
    assert c.get("/api/v1/ui/memory").json() == {"last-screen": "fmirror"}
    assert c.put("/api/v1/ui/memory", json={"bad name": 1}).status_code == 400
    assert TestClient(server.app).get("/api/v1/ui/memory").status_code == 401     # the token, like every API call
