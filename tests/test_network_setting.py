"""Allow network access: off, PaperDaemon's own internet calls stop in one place, and what needs them is off."""
import json

import pytest

from paperdaemon import net, settings
from paperdaemon.models import lineup


def _run_file(tmp_path, monkeypatch, name="lineup.json", **cfg):
    p = tmp_path / name                              # a new run file is a new path (the host reads one per start)
    p.write_text(json.dumps({"settings": cfg}), encoding="utf-8")
    monkeypatch.setenv("RM_RUN", str(p))


def test_off_stops_every_call_before_it_leaves(tmp_path, monkeypatch):
    _run_file(tmp_path, monkeypatch, network={"allowed": False})
    assert not net.allowed()
    with pytest.raises(net.Off):
        net.urlopen("https://api.open-meteo.com/v1/forecast")
    from paperdaemon.pipeline.charts import weather
    assert weather.daily(40.76, -111.89) == {}          # a calendar without its forecast, not a failure


def test_on_by_default(tmp_path, monkeypatch):
    _run_file(tmp_path, monkeypatch)
    assert net.allowed()


def test_off_turns_off_search_and_posts_and_says_so(fresh):
    s = settings.load()
    s["network"]["allowed"] = False
    settings.save(s)
    got = lineup.features(settings.load())
    assert got["search"]["state"] == "off" and got["posts"]["state"] == "off" and got["web_picture"]["state"] == "off"
    assert "network access is off" in " ".join(got["posts"]["because"])
    assert got["calendar"]["state"] != "off"                 # still a calendar, without the forecast
    run = lineup.run_file({}, settings.load())
    assert run["settings"]["network"] == {"allowed": False}


def test_the_brief_tells_the_model(tmp_path, monkeypatch):
    import paperdaemon.pipeline.host as H
    _run_file(tmp_path, monkeypatch, network={"allowed": False})
    assert "The internet is off" in H._prefs_sentence()
    _run_file(tmp_path, monkeypatch, "lineup2.json", social={"sites": ["reddit", "bluesky"]})
    assert "come from Reddit and Bluesky" in H._prefs_sentence()
