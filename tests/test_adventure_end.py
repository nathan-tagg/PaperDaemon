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
