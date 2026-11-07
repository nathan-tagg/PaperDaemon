"""An ink adventure that is over says so on its last scene page, where the next move's ideas would be: a story that
ended still showed "You could: ..." for a turn no game would take (a finished game gives its page back)."""
from PIL import ImageDraw

from paperdaemon.pipeline.games import adventure as AD


def _drawn(tmp_path, status, monkeypatch):
    said = []
    real = ImageDraw.ImageDraw.text

    def text(self, xy, s, *a, **k):
        said.append(str(s))
        return real(self, xy, s, *a, **k)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", text)
    state = {"turns": [{}] * 6, "place": "Oakhaven Apiary", "title": "The Silent Swarm",
             "hero": {"name": "Elara Vane"}, "status": status}
    scene = {"place": "Oakhaven Apiary", "what_happened": "The swarm closes in.", "around": "The hives hum on.",
             "options": ["Crawl to the cart", "Call for Barnaby"]}
    AD.turn_png(state, scene, str(tmp_path / ("%s.png" % status)))
    return said


def test_an_adventure_that_is_over_says_so_instead_of_offering_a_next_move(tmp_path, monkeypatch):
    assert "The end: Elara Vane has fallen." in _drawn(tmp_path, "down", monkeypatch)
    assert "The end: a victory." in _drawn(tmp_path, "victory", monkeypatch)
    died = _drawn(tmp_path, "death", monkeypatch)
    assert "The end: Elara Vane has died." in died and not any(s.startswith("You could") for s in died)


def test_one_still_played_offers_its_loose_ideas(tmp_path, monkeypatch):
    said = _drawn(tmp_path, "playing", monkeypatch)
    assert any(s.startswith("You could: Crawl to the cart") for s in said)
    assert not any(s.startswith("The end") for s in said)


def test_a_turn_where_nothing_in_view_changed_keeps_its_picture_and_never_takes_the_card(tmp_path):
    # an "edit" for a few words took 40 s to change nothing the page shows, and the text model came back cold
    from PIL import Image
    shot = tmp_path / "003.png"
    Image.new("RGB", (8, 8)).save(shot)
    calls = []

    class Paint(object):
        def session(self, fn):
            calls.append("card")
            return fn()

    def painted():
        calls.append("painted")
        return str(shot)
    assert AD._scene_picture(Paint(), {"mode": "keep"}, str(shot), [], painted) == str(shot) and calls == []
    AD._scene_picture(Paint(), {"mode": "keep"}, str(shot), [{"name": "Jory"}], painted)
    assert calls == ["card", "painted"]                  # someone new came: they are painted, the scene with them
    del calls[:]
    AD._scene_picture(Paint(), {"mode": "edit"}, str(shot), [], painted)
    assert calls == ["card", "painted"]
    del calls[:]
    AD._scene_picture(Paint(), {"mode": "keep"}, str(tmp_path / "none.png"), [], painted)
    assert calls == ["card", "painted"]                  # no picture to keep: one is painted
